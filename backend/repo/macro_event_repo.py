"""
repo/macro_event_repo.py
─────────────────────────────────────────────────────────────────
SOLID  S — Handles persistence, indexing, and retrieval of MacroEventRecord.
SOLID  O — Implements MacroEventRepositoryPort; extensible to other persistence backends.
SOLID  L — FileMacroEventRepository and MongoMacroEventRepository are interchangeable.
SOLID  D — Accepts data file Path via constructor; DI factory for FastAPI Depends().
GRASP  Information Expert — Manages macro-event serialization, child-to-macro index, and cache.
GRASP  Creator — Manages persistent MacroEventRecord collection and atomic disk sync.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from backend.core.file_lock import InterProcessFileLock
from backend.schemas.macro_event_schema import MacroEventRecord

logger = logging.getLogger(__name__)


# ── Port (Abstract Protocol) ──────────────────────────────────────

@runtime_checkable
class MacroEventRepositoryPort(Protocol):
    """Port interface defining Macro-Event persistence operations."""

    def get_macro_event(self, macro_id: str) -> MacroEventRecord | None: ...

    def save_macro_event(self, macro: MacroEventRecord) -> None: ...

    def save_macro_events_batch(self, macros: list[MacroEventRecord]) -> None: ...

    def list_macro_events(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MacroEventRecord]: ...

    def find_candidate_macro_events(
        self,
        since_time: datetime,
        anchor: str | None = None,
        max_anchor_episode_days: int = 45,
    ) -> list[MacroEventRecord]: ...

    def get_macro_event_by_child_id(self, child_id: str) -> MacroEventRecord | None: ...

    def count_macro_events(self, status: str | None = None) -> int: ...

    def delete_macro_event(self, macro_id: str) -> bool: ...

    def clear_all(self) -> None: ...


# ── Concrete Implementation: InMemoryMacroEventRepository ──────────

class InMemoryMacroEventRepository:
    """
    In-memory mock/test implementation of MacroEventRepositoryPort.
    Ensures unit tests run isolated without writing to production JSON files.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._macro_events: dict[str, MacroEventRecord] = {}
        self._child_to_macro_id: dict[str, str] = {}

    def get_macro_event(self, macro_id: str) -> MacroEventRecord | None:
        clean_id = macro_id.strip() if macro_id else ""
        if not clean_id:
            return None
        with self._lock:
            record = self._macro_events.get(clean_id)
            return record.model_copy(deep=True) if record else None

    def save_macro_event(self, macro: MacroEventRecord) -> None:
        with self._lock:
            rec = macro.model_copy(deep=True)
            self._macro_events[rec.macro_event_id] = rec
            for cid in rec.child_event_ids:
                self._child_to_macro_id[cid] = rec.macro_event_id

    def save_macro_events_batch(self, macros: list[MacroEventRecord]) -> None:
        with self._lock:
            for m in macros:
                self.save_macro_event(m)

    def list_macro_events(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MacroEventRecord]:
        with self._lock:
            records = list(self._macro_events.values())
            if status and status.lower() != "all":
                records = [r for r in records if r.status == status.lower()]
            records.sort(key=lambda r: r.updated_at, reverse=True)
            return [r.model_copy(deep=True) for r in records[offset : offset + limit]]

    def find_candidate_macro_events(
        self,
        since_time: datetime,
        anchor: str | None = None,
        max_anchor_episode_days: int = 45,
    ) -> list[MacroEventRecord]:
        since_utc = (
            since_time.replace(tzinfo=timezone.utc)
            if since_time.tzinfo is None
            else since_time.astimezone(timezone.utc)
        )
        clean_anchor = anchor.strip().lower() if anchor else None
        with self._lock:
            candidates: list[MacroEventRecord] = []
            for m in self._macro_events.values():
                m_act = m.last_activity_at or m.updated_at
                m_act_utc = (
                    m_act.replace(tzinfo=timezone.utc)
                    if m_act.tzinfo is None
                    else m_act.astimezone(timezone.utc)
                )
                time_match = m_act_utc >= since_utc
                anchor_match = False
                m_anchors = [
                    a.lower() for a in (m.storyline_anchor, m.named_crisis_anchor) if a
                ]
                if (
                    clean_anchor
                    and m_anchors
                    and any(clean_anchor in ma or ma in clean_anchor for ma in m_anchors)
                    and (since_utc - timedelta(days=max_anchor_episode_days) <= m_act_utc <= since_utc + timedelta(days=max_anchor_episode_days + 14))
                ):
                    anchor_match = True
                if time_match or anchor_match:
                    candidates.append(m.model_copy(deep=True))
            candidates.sort(key=lambda r: r.updated_at, reverse=True)
            return candidates

    def get_macro_event_by_child_id(self, child_id: str) -> MacroEventRecord | None:
        clean_cid = child_id.strip() if child_id else ""
        if not clean_cid:
            return None
        with self._lock:
            mid = self._child_to_macro_id.get(clean_cid)
            if mid and mid in self._macro_events:
                return self._macro_events[mid].model_copy(deep=True)
            return None

    def count_macro_events(self, status: str | None = None) -> int:
        with self._lock:
            if not status or status.lower() == "all":
                return len(self._macro_events)
            return sum(1 for m in self._macro_events.values() if m.status == status.lower())

    def delete_macro_event(self, macro_id: str) -> bool:
        clean_id = macro_id.strip() if macro_id else ""
        if not clean_id:
            return False
        with self._lock:
            if clean_id in self._macro_events:
                m = self._macro_events.pop(clean_id)
                for cid in m.child_event_ids:
                    if self._child_to_macro_id.get(cid) == clean_id:
                        del self._child_to_macro_id[cid]
                return True
            return False

    def clear_all(self) -> None:
        with self._lock:
            self._macro_events.clear()
            self._child_to_macro_id.clear()


# ── Concrete Implementation: FileMacroEventRepository ─────────────

class FileMacroEventRepository:
    """
    High-performance JSON file repository for MacroEventRecord with in-memory caching,
    O(1) child event lookups, atomic disk persistence, and automated backup.
    """

    def __init__(self, data_file: Path) -> None:
        self._data_file = Path(data_file)
        self._lock = threading.RLock()
        self._file_lock = InterProcessFileLock(self._data_file.with_suffix(self._data_file.suffix + ".lock"))
        self._macro_events: dict[str, MacroEventRecord] = {}
        self._child_to_macro_id: dict[str, str] = {}
        self._last_mtime: float | None = None
        self._sync_cache()

    # ── CRUD Operations ──────────────────────────────────────────

    def get_macro_event(self, macro_id: str) -> MacroEventRecord | None:
        """Retrieve a single macro-event by ID in O(1) time."""
        clean_id = macro_id.strip() if macro_id else ""
        if not clean_id:
            return None
        with self._lock:
            self._sync_cache()
            rec = self._macro_events.get(clean_id)
            return rec.model_copy(deep=True) if rec is not None else None

    def save_macro_event(self, macro: MacroEventRecord) -> None:
        """Save or update a single macro-event with atomic disk write and cross-process lock."""
        with self._lock, self._file_lock:
            self._sync_cache()
            self._upsert_in_memory(macro.model_copy(deep=True))
            self._persist_to_disk()

    def save_macro_events_batch(self, macros: list[MacroEventRecord]) -> None:
        """Batch save multiple macro-events with a single atomic disk write."""
        if not macros:
            return
        with self._lock, self._file_lock:
            self._sync_cache()
            for m in macros:
                self._upsert_in_memory(m.model_copy(deep=True))
            self._persist_to_disk()

    def list_macro_events(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MacroEventRecord]:
        """List macro-events with pagination, sorted by updated_at descending."""
        with self._lock:
            self._sync_cache()
            items = list(self._macro_events.values())

            if status is not None and status.strip() and status.strip().lower() != "all":
                target_status = status.strip().lower()
                items = [m for m in items if m.status.lower() == target_status]

            items.sort(key=self._sort_key_updated_at, reverse=True)
            return [m.model_copy(deep=True) for m in items[offset : offset + limit]]

    def find_candidate_macro_events(
        self,
        since_time: datetime,
        anchor: str | None = None,
        max_anchor_episode_days: int = 45,
    ) -> list[MacroEventRecord]:
        """
        Query candidate macro-events:
        1. Macro-events active/updated since since_time (e.g. within 14 days)
        2. PLUS any macro-event whose named_crisis_anchor/storyline_anchor matches the provided anchor
           within the max_anchor_episode_days episode window.
        """
        since_utc = self._normalize_datetime(since_time)
        clean_anchor = anchor.strip().lower() if anchor else ""

        with self._lock:
            self._sync_cache()
            candidates: list[MacroEventRecord] = []
            for m in self._macro_events.values():
                m_updated = self._normalize_datetime(m.updated_at)
                m_activity = (
                    self._normalize_datetime(m.last_activity_at)
                    if m.last_activity_at
                    else m_updated
                )

                time_matched = m_activity >= since_utc or m_updated >= since_utc

                anchor_matched = False
                m_anchors = [
                    a.lower() for a in (m.storyline_anchor, m.named_crisis_anchor) if a
                ]
                if (
                    clean_anchor
                    and m_anchors
                    and any(clean_anchor in ma or ma in clean_anchor for ma in m_anchors)
                    and (since_utc - timedelta(days=max_anchor_episode_days) <= m_activity <= since_utc + timedelta(days=max_anchor_episode_days + 14))
                ):
                    anchor_matched = True

                if time_matched or anchor_matched:
                    candidates.append(m.model_copy(deep=True))

            candidates.sort(key=self._sort_key_updated_at, reverse=True)
            return candidates

    def get_macro_event_by_child_id(self, child_id: str) -> MacroEventRecord | None:
        """Find the macro-event containing the given child event ID."""
        clean_cid = child_id.strip() if child_id else ""
        if not clean_cid:
            return None
        with self._lock:
            self._sync_cache()
            macro_id = self._child_to_macro_id.get(clean_cid)
            if macro_id:
                rec = self._macro_events.get(macro_id)
                return rec.model_copy(deep=True) if rec is not None else None
            return None

    def count_macro_events(self, status: str | None = None) -> int:
        """Count total tracked macro-events, optionally filtered by status."""
        with self._lock:
            self._sync_cache()
            if status is None or not status.strip() or status.strip().lower() == "all":
                return len(self._macro_events)
            target = status.strip().lower()
            return sum(1 for m in self._macro_events.values() if m.status.lower() == target)

    def clear_all(self) -> None:
        """Reset repository store (used in tests or maintenance)."""
        with self._lock, self._file_lock:
            self._macro_events.clear()
            self._child_to_macro_id.clear()
            self._persist_to_disk()

    def delete_macro_event(self, macro_id: str) -> bool:
        """Delete macro-event by ID, removing index entries and persisting to disk."""
        clean_id = macro_id.strip() if macro_id else ""
        if not clean_id:
            return False
        with self._lock:
            with self._file_lock:
                self._sync_cache()
            old = self._macro_events.pop(clean_id, None)
            if old is not None:
                for cid in old.child_event_ids:
                    if self._child_to_macro_id.get(cid) == clean_id:
                        self._child_to_macro_id.pop(cid, None)
                self._persist_to_disk()
                return True
            return False

    # ── Private In-Memory & Disk Helpers ─────────────────────────

    def _upsert_in_memory(self, macro: MacroEventRecord) -> None:
        """Update internal map and maintain child-to-macro index."""
        old_macro = self._macro_events.get(macro.macro_event_id)
        if old_macro:
            new_children = set(macro.child_event_ids)
            for old_cid in old_macro.child_event_ids:
                if old_cid not in new_children and self._child_to_macro_id.get(old_cid) == macro.macro_event_id:
                    self._child_to_macro_id.pop(old_cid, None)

        self._macro_events[macro.macro_event_id] = macro
        for cid in macro.child_event_ids:
            if cid and cid.strip():
                self._child_to_macro_id[cid.strip()] = macro.macro_event_id

    def _sync_cache(self) -> None:
        """Sync in-memory cache with disk if file modified externally or at init."""
        if not self._data_file.exists():
            if self._macro_events:
                self._macro_events.clear()
                self._child_to_macro_id.clear()
                self._last_mtime = None
            return

        try:
            current_mtime = self._data_file.stat().st_mtime
        except OSError:
            return

        if self._last_mtime is not None and current_mtime == self._last_mtime:
            return

        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Read and validate macro-events from disk JSON."""
        if not self._data_file.exists():
            self._macro_events.clear()
            self._child_to_macro_id.clear()
            self._last_mtime = None
            return

        try:
            content = self._data_file.read_text(encoding="utf-8")
            if not content.strip():
                self._macro_events.clear()
                self._child_to_macro_id.clear()
                self._last_mtime = self._data_file.stat().st_mtime
                return
            data = json.loads(content)
        except Exception as exc:
            logger.warning("Corrupted macro_events_data.json (%s), preserving empty cache", exc)
            self._macro_events.clear()
            self._child_to_macro_id.clear()
            return

        raw_macros = data.get("macro_events", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        loaded_macros: dict[str, MacroEventRecord] = {}
        loaded_child_map: dict[str, str] = {}

        for item in raw_macros:
            if not isinstance(item, dict):
                continue
            try:
                macro = MacroEventRecord.model_validate(item)
                loaded_macros[macro.macro_event_id] = macro
                for cid in macro.child_event_ids:
                    if cid and cid.strip():
                        loaded_child_map[cid.strip()] = macro.macro_event_id
            except Exception as exc:
                logger.debug("Skipping invalid macro item during load: %s", exc)
                continue

        self._macro_events = loaded_macros
        self._child_to_macro_id = loaded_child_map
        try:
            self._last_mtime = self._data_file.stat().st_mtime
        except OSError:
            self._last_mtime = None

    def _persist_to_disk(self) -> None:
        """Atomically persist in-memory macro-events to disk with backup."""
        self._data_file.parent.mkdir(parents=True, exist_ok=True)

        sorted_macros = sorted(
            self._macro_events.values(),
            key=self._sort_key_updated_at,
            reverse=True,
        )
        macros_data = [m.model_dump(mode="json") for m in sorted_macros]

        active_count = sum(1 for m in sorted_macros if m.status == "active")
        dormant_count = len(sorted_macros) - active_count

        payload: dict[str, Any] = {
            "metadata": {
                "version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_macro_events": len(sorted_macros),
                "active_macro_events": active_count,
                "dormant_macro_events": dormant_count,
            },
            "macro_events": macros_data,
        }

        # Create backup if original file exists
        if self._data_file.exists():
            bak_path = self._data_file.with_suffix(".json.bak")
            try:
                shutil.copy2(self._data_file, bak_path)
            except OSError as exc:
                logger.debug("Could not create backup of macro_events: %s", exc)

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self._data_file.parent,
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as tmp_file:
                json.dump(payload, tmp_file, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp_file.name)

            os.replace(tmp_path, self._data_file)
            try:
                self._last_mtime = self._data_file.stat().st_mtime
            except OSError:
                self._last_mtime = None
        except Exception:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    @staticmethod
    def _normalize_datetime(dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware UTC for safe comparisons."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _sort_key_updated_at(cls, m: MacroEventRecord) -> datetime:
        """Sort key returning UTC-normalized datetime for MacroEventRecord."""
        return cls._normalize_datetime(m.updated_at)


# ── Concrete Implementation: MongoMacroEventRepository ────────────

class MongoMacroEventRepository:
    """
    MongoDB repository implementation for MacroEventRecord persistence.
    """

    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017",
        db_name: str = "news_collector",
        collection_name: str = "macro_events",
        server_selection_timeout_ms: int = 3000,
    ) -> None:
        import pymongo

        self._client: pymongo.MongoClient = pymongo.MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
        )
        self._client.admin.command("ping")
        self._db = self._client[db_name]
        self._macros = self._db[collection_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        import pymongo

        try:
            self._macros.create_index([("macro_event_id", pymongo.ASCENDING)], unique=True, background=True)
            self._macros.create_index([("child_event_ids", pymongo.ASCENDING)], background=True)
            self._macros.create_index([("updated_at", pymongo.DESCENDING)], background=True)
            self._macros.create_index([("named_crisis_anchor", pymongo.ASCENDING)], background=True)
        except Exception as exc:
            logger.warning("MongoDB macro index creation failed: %s", exc)

    def get_macro_event(self, macro_id: str) -> MacroEventRecord | None:
        clean_id = macro_id.strip() if macro_id else ""
        if not clean_id:
            return None
        doc = self._macros.find_one({"macro_event_id": clean_id}, {"_id": 0})
        return MacroEventRecord.model_validate(doc) if doc else None

    def save_macro_event(self, macro: MacroEventRecord) -> None:
        doc = macro.model_dump(mode="json")
        self._macros.update_one(
            {"macro_event_id": macro.macro_event_id},
            {"$set": doc},
            upsert=True,
        )

    def save_macro_events_batch(self, macros: list[MacroEventRecord]) -> None:
        from pymongo import UpdateOne

        if not macros:
            return
        ops = [
            UpdateOne(
                {"macro_event_id": m.macro_event_id},
                {"$set": m.model_dump(mode="json")},
                upsert=True,
            )
            for m in macros
        ]
        self._macros.bulk_write(ops, ordered=False)

    def list_macro_events(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MacroEventRecord]:
        import pymongo

        filter_doc: dict[str, Any] = {}
        if status and status.strip().lower() != "all":
            filter_doc["status"] = status.strip().lower()

        cursor = (
            self._macros.find(filter_doc, {"_id": 0})
            .sort("updated_at", pymongo.DESCENDING)
            .skip(max(0, offset))
            .limit(max(1, limit))
        )
        return [MacroEventRecord.model_validate(d) for d in cursor]

    def find_candidate_macro_events(
        self,
        since_time: datetime,
        anchor: str | None = None,
        max_anchor_episode_days: int = 45,
    ) -> list[MacroEventRecord]:
        import pymongo

        since_iso = since_time.isoformat() if isinstance(since_time, datetime) else str(since_time)
        or_clauses: list[dict[str, Any]] = [
            {"updated_at": {"$gte": since_time}},
            {"updated_at": {"$gte": since_iso}},
            {"last_activity_at": {"$gte": since_time}},
            {"last_activity_at": {"$gte": since_iso}},
        ]
        if anchor and anchor.strip():
            esc_anchor = re.escape(anchor.strip())
            episode_cutoff = since_time - timedelta(days=max_anchor_episode_days)
            episode_iso = episode_cutoff.isoformat() if isinstance(episode_cutoff, datetime) else str(episode_cutoff)
            anchor_match: dict[str, Any] = {
                "$and": [
                    {
                        "$or": [
                            {"named_crisis_anchor": {"$regex": esc_anchor, "$options": "i"}},
                            {"storyline_anchor": {"$regex": esc_anchor, "$options": "i"}},
                        ]
                    },
                    {
                        "$or": [
                            {"last_activity_at": {"$gte": episode_cutoff}},
                            {"last_activity_at": {"$gte": episode_iso}},
                            {"updated_at": {"$gte": episode_cutoff}},
                            {"updated_at": {"$gte": episode_iso}},
                        ]
                    },
                ]
            }
            or_clauses.append(anchor_match)

        cursor = self._macros.find({"$or": or_clauses}, {"_id": 0}).sort("updated_at", pymongo.DESCENDING)
        return [MacroEventRecord.model_validate(d) for d in cursor]

    def get_macro_event_by_child_id(self, child_id: str) -> MacroEventRecord | None:
        clean_cid = child_id.strip() if child_id else ""
        if not clean_cid:
            return None
        doc = self._macros.find_one({"child_event_ids": clean_cid}, {"_id": 0})
        return MacroEventRecord.model_validate(doc) if doc else None

    def count_macro_events(self, status: str | None = None) -> int:
        filter_doc: dict[str, Any] = {}
        if status and status.strip().lower() != "all":
            filter_doc["status"] = status.strip().lower()
        return self._macros.count_documents(filter_doc)

    def clear_all(self) -> None:
        self._macros.delete_many({})

    def delete_macro_event(self, macro_id: str) -> bool:
        clean_id = macro_id.strip() if macro_id else ""
        if not clean_id:
            return False
        res = self._macros.delete_one({"macro_event_id": clean_id})
        return res.deleted_count > 0


# ── Singleton & Factory / DI Helper ───────────────────────────────

_MACRO_REPO_INSTANCE: MacroEventRepositoryPort | None = None
_MACRO_INSTANCE_LOCK = threading.Lock()


def get_macro_event_repository() -> MacroEventRepositoryPort:
    """FastAPI Depends() factory — thread-safe singleton."""
    global _MACRO_REPO_INSTANCE
    if _MACRO_REPO_INSTANCE is not None:
        return _MACRO_REPO_INSTANCE

    with _MACRO_INSTANCE_LOCK:
        if _MACRO_REPO_INSTANCE is not None:
            return _MACRO_REPO_INSTANCE

        from backend.config import settings

        db_type = getattr(settings, "db_type", "json").lower().strip()
        if db_type == "mongodb":
            try:
                _MACRO_REPO_INSTANCE = MongoMacroEventRepository(
                    mongo_uri=getattr(settings, "mongo_uri", "mongodb://localhost:27017"),
                    db_name=getattr(settings, "mongo_db_name", "news_collector"),
                    collection_name=getattr(settings, "mongo_macro_collection", "macro_events"),
                )
                return _MACRO_REPO_INSTANCE
            except Exception as exc:
                logger.warning(
                    "Failed to initialize MongoMacroEventRepository (%s), falling back to FileMacroEventRepository",
                    exc,
                )

        macros_file = getattr(
            settings,
            "macro_events_file",
            getattr(settings, "DATA_DIR", Path("data")) / "macro_events_data.json",
        )
        _MACRO_REPO_INSTANCE = FileMacroEventRepository(data_file=macros_file)
        return _MACRO_REPO_INSTANCE


def reset_macro_event_repository() -> None:
    """Reset repository singleton instance (used in tests for clean state)."""
    global _MACRO_REPO_INSTANCE
    with _MACRO_INSTANCE_LOCK:
        _MACRO_REPO_INSTANCE = None
