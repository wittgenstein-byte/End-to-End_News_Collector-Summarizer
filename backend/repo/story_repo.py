"""
repo/story_repo.py
─────────────────────────────────────────────────────────────────
SOLID  S — Handles persistence, indexing, and retrieval of persistent stories
SOLID  O — Implements StoryRepositoryPort; extensible to other persistence engines
SOLID  L — FileStoryRepository and MongoStoryRepository are interchangeable
SOLID  D — Accepts data file Path via constructor; DI factory for FastAPI Depends()
GRASP  Information Expert — Knows story serialization, inverted URL index, and cache
GRASP  Creator — Manages persistent StoryRecord collection and disk sync
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from backend.schemas.story_schema import StoryRecord

logger = logging.getLogger(__name__)


# ── Port (Abstract Protocol) ──────────────────────────────────────
# High-level services (StoryService, TrendingService) depend on this
# abstraction, not directly on FileStoryRepository or MongoStoryRepository.

@runtime_checkable
class StoryRepositoryPort(Protocol):
    """Port interface defining story persistence operations."""

    def get_story(self, story_id: str) -> StoryRecord | None: ...

    def save_story(self, story: StoryRecord) -> None: ...

    def save_stories_batch(self, stories: list[StoryRecord]) -> None: ...

    def list_stories(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoryRecord]: ...

    def find_candidate_stories(
        self,
        since_time: datetime,
        category: str | None = None,
    ) -> list[StoryRecord]: ...

    def get_stories_by_ids(self, story_ids: list[str]) -> list[StoryRecord]: ...

    def get_story_by_article_url(self, url: str) -> StoryRecord | None: ...

    def get_stories_by_macro_id(self, macro_id: str) -> list[StoryRecord]: ...

    def delete_story(self, story_id: str) -> bool: ...

    def count_stories(self, status: str | None = None) -> int: ...


# ── Concrete Implementation: FileStoryRepository ──────────────────

class FileStoryRepository:
    """
    High-performance JSON file repository with in-memory caching,
    O(1) inverted URL lookups, and atomic disk persistence.

    Key Features:
    - In-memory cache for sub-millisecond reads
    - Inverted index (_url_to_story_id) for O(1) article-to-story tracing
    - Thread-safe operations via re-entrant lock (RLock)
    - Atomic disk persistence using NamedTemporaryFile + os.replace
    - Mtime-based cache sync across multiple instances / server restarts
    - Graceful fault tolerance for missing, empty, or corrupted JSON files
    """

    def __init__(self, data_file: Path) -> None:
        self._data_file = Path(data_file)
        self._lock = threading.RLock()
        self._stories: dict[str, StoryRecord] = {}
        self._url_to_story_id: dict[str, str] = {}
        self._last_mtime: float | None = None
        self._sync_cache()

    # ── CRUD Operations ──────────────────────────────────────────

    def get_story(self, story_id: str) -> StoryRecord | None:
        """Retrieve a single story by its unique ID in O(1) time."""
        clean_id = story_id.strip() if story_id else ""
        if not clean_id:
            return None
        with self._lock:
            self._sync_cache()
            return self._stories.get(clean_id)

    def save_story(self, story: StoryRecord) -> None:
        """Save or update a single story with atomic disk write."""
        with self._lock:
            self._sync_cache()
            self._upsert_in_memory(story)
            self._persist_to_disk()

    def save_stories_batch(self, stories: list[StoryRecord]) -> None:
        """Batch save multiple stories with a single atomic disk write."""
        if not stories:
            return
        with self._lock:
            self._sync_cache()
            for story in stories:
                self._upsert_in_memory(story)
            self._persist_to_disk()

    def list_stories(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoryRecord]:
        """
        List stories sorted by updated_at descending, with optional status filter
        and pagination.
        """
        with self._lock:
            self._sync_cache()
            items = list(self._stories.values())

            # Sort by updated_at descending
            items.sort(key=self._sort_key_updated_at, reverse=True)

            if status is not None and status.strip() and status.strip().lower() != "all":
                target_status = status.strip().lower()
                items = [s for s in items if s.status.lower() == target_status]

            start = max(0, offset)
            end = start + max(1, limit)
            return items[start:end]

    def find_candidate_stories(
        self,
        since_time: datetime,
        category: str | None = None,
    ) -> list[StoryRecord]:
        """
        Find candidate stories updated at or after `since_time`.
        Optionally filters by category (soft signal narrowing).
        Results are sorted by updated_at descending.
        """
        norm_since = self._normalize_datetime(since_time)
        cat_filter = category.strip().lower() if category and category.strip().lower() != "all" else None

        with self._lock:
            self._sync_cache()
            candidates: list[StoryRecord] = []
            for s in self._stories.values():
                story_dt = self._normalize_datetime(s.updated_at)
                if story_dt >= norm_since and (
                    cat_filter is None or s.category.strip().lower() == cat_filter
                ):
                    candidates.append(s)

            candidates.sort(key=self._sort_key_updated_at, reverse=True)
            return candidates

    def get_stories_by_ids(self, story_ids: list[str]) -> list[StoryRecord]:
        """Fetch multiple stories by ID, preserving the order of the input list."""
        if not story_ids:
            return []
        with self._lock:
            self._sync_cache()
            results: list[StoryRecord] = []
            for sid in story_ids:
                clean_id = sid.strip() if sid else ""
                story = self._stories.get(clean_id)
                if story is not None:
                    results.append(story)
            return results

    def get_story_by_article_url(self, url: str) -> StoryRecord | None:
        """O(1) lookup of the story that contains a given article URL."""
        clean_url = url.strip() if url else ""
        if not clean_url:
            return None
        with self._lock:
            self._sync_cache()
            story_id = self._url_to_story_id.get(clean_url)
            if story_id:
                return self._stories.get(story_id)
            return None

    def get_stories_by_macro_id(self, macro_id: str) -> list[StoryRecord]:
        """Retrieve all stories belonging to a given macro_event_id (SST lookup)."""
        clean_id = macro_id.strip() if macro_id else ""
        if not clean_id:
            return []
        with self._lock:
            self._sync_cache()
            return [
                s for s in self._stories.values()
                if getattr(s, "macro_event_id", None) == clean_id
            ]

    # ── Utility / Testing Helpers ────────────────────────────────

    def count_stories(self, status: str | None = None) -> int:
        """Count total tracked stories, optionally filtered by status."""
        with self._lock:
            self._sync_cache()
            if status is None or not status.strip() or status.strip().lower() == "all":
                return len(self._stories)
            target = status.strip().lower()
            return sum(1 for s in self._stories.values() if s.status.lower() == target)

    def delete_story(self, story_id: str) -> bool:
        """Delete story by ID, removing URL mappings and persisting to disk."""
        clean_id = story_id.strip() if story_id else ""
        if not clean_id:
            return False
        with self._lock:
            self._sync_cache()
            old = self._stories.pop(clean_id, None)
            if old is not None:
                for u in old.article_urls:
                    if self._url_to_story_id.get(u) == clean_id:
                        self._url_to_story_id.pop(u, None)
                self._persist_to_disk()
                return True
            return False

    def clear_all(self) -> None:
        """Reset repository store (used in testing or maintenance)."""
        with self._lock:
            self._stories.clear()
            self._url_to_story_id.clear()
            self._persist_to_disk()

    # ── Private In-Memory & Disk Helpers ─────────────────────────

    def _upsert_in_memory(self, story: StoryRecord) -> None:
        """Update internal story map and maintain inverted URL index."""
        old_story = self._stories.get(story.story_id)
        if old_story:
            # Clean up URLs removed in the update
            new_urls = set(story.article_urls)
            for old_u in old_story.article_urls:
                if old_u not in new_urls and self._url_to_story_id.get(old_u) == story.story_id:
                    self._url_to_story_id.pop(old_u, None)

        self._stories[story.story_id] = story
        for u in story.article_urls:
            if u and u.strip():
                self._url_to_story_id[u.strip()] = story.story_id

    def _sync_cache(self) -> None:
        """Sync in-memory cache with disk if file modified externally or at init."""
        if not self._data_file.exists():
            if self._stories:
                self._stories.clear()
                self._url_to_story_id.clear()
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
        """Read and validate stories from disk JSON, resilient to corruption."""
        if not self._data_file.exists():
            self._stories.clear()
            self._url_to_story_id.clear()
            self._last_mtime = None
            return

        try:
            with self._data_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse %s (%s); initializing empty store", self._data_file, exc)
            self._stories.clear()
            self._url_to_story_id.clear()
            self._last_mtime = None
            return

        raw_stories = data.get("stories", [])
        if isinstance(raw_stories, dict):
            raw_stories = list(raw_stories.values())

        loaded_stories: dict[str, StoryRecord] = {}
        loaded_url_map: dict[str, str] = {}

        for item in raw_stories:
            if not isinstance(item, dict):
                continue
            try:
                story = StoryRecord.model_validate(item)
                loaded_stories[story.story_id] = story
                for u in story.article_urls:
                    if u and u.strip():
                        loaded_url_map[u.strip()] = story.story_id
            except Exception as exc:
                logger.debug("Skipping invalid story item during load: %s", exc)
                continue

        self._stories = loaded_stories
        self._url_to_story_id = loaded_url_map
        try:
            self._last_mtime = self._data_file.stat().st_mtime
        except OSError:
            self._last_mtime = None

    def _persist_to_disk(self) -> None:
        """Atomically persist in-memory stories to disk using temporary file."""
        self._data_file.parent.mkdir(parents=True, exist_ok=True)

        sorted_stories = sorted(
            self._stories.values(),
            key=self._sort_key_updated_at,
            reverse=True,
        )
        stories_data = [s.model_dump(mode="json") for s in sorted_stories]

        active_count = sum(1 for s in sorted_stories if s.status == "active")
        dormant_count = len(sorted_stories) - active_count

        payload: dict[str, Any] = {
            "metadata": {
                "version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_stories": len(sorted_stories),
                "active_stories": active_count,
                "dormant_stories": dormant_count,
            },
            "stories": stories_data,
        }

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

            # File is closed upon exiting the with-block; safe for Windows os.replace
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
    def _sort_key_updated_at(cls, s: StoryRecord) -> datetime:
        """Sort key returning UTC-normalized datetime for StoryRecord."""
        return cls._normalize_datetime(s.updated_at)


# ── Singleton & Factory / DI Helper ───────────────────────────────

_STORY_REPO_INSTANCE: StoryRepositoryPort | None = None
_INSTANCE_LOCK = threading.Lock()


def get_story_repository() -> StoryRepositoryPort:
    """FastAPI Depends() factory — thread-safe singleton, injects Settings."""
    global _STORY_REPO_INSTANCE
    if _STORY_REPO_INSTANCE is not None:
        return _STORY_REPO_INSTANCE

    with _INSTANCE_LOCK:
        if _STORY_REPO_INSTANCE is not None:
            return _STORY_REPO_INSTANCE

        from backend.config import settings

        db_type = getattr(settings, "db_type", "json").lower().strip()
        if db_type == "mongodb":
            try:
                from backend.repo.mongo_story_repo import MongoStoryRepository

                _STORY_REPO_INSTANCE = MongoStoryRepository(
                    mongo_uri=getattr(settings, "mongo_uri", "mongodb://localhost:27017"),
                    db_name=getattr(settings, "mongo_db_name", "news_collector"),
                    collection_name=getattr(settings, "mongo_story_collection", "stories"),
                )
                return _STORY_REPO_INSTANCE
            except Exception as exc:
                logger.warning(
                    "Failed to initialize MongoStoryRepository (%s), falling back to FileStoryRepository",
                    exc,
                )

        stories_file = getattr(
            settings,
            "stories_file",
            getattr(settings, "DATA_DIR", Path("data")) / "stories_data.json",
        )
        _STORY_REPO_INSTANCE = FileStoryRepository(data_file=stories_file)
        return _STORY_REPO_INSTANCE


def reset_story_repository() -> None:
    """Reset repository singleton instance (used in tests for clean state)."""
    global _STORY_REPO_INSTANCE
    with _INSTANCE_LOCK:
        _STORY_REPO_INSTANCE = None
