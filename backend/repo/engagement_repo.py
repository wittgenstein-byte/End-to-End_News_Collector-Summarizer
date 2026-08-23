"""
repositories/engagement_repo.py
─────────────────────────────────────────────────────────────────
SOLID  S — Handles persistence of aggregate reader engagement telemetry
SOLID  D — Accepts Settings / Path via constructor (injectable, testable)
GRASP  Information Expert — Knows file path, JSON schema, and aggregate counters
GRASP  Creator — Manages non-PII telemetry counters for news articles
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

# ── Port (abstract interface) ─────────────────────────────────────

class EngagementRepositoryPort(Protocol):
    def record_event(self, url: str, event_type: str) -> dict[str, int]: ...
    def get_engagement(self, url: str) -> dict[str, int]: ...
    def get_all_engagements(self) -> dict[str, dict[str, int]]: ...
    def clear_all(self) -> None: ...


# ── Concrete implementation ───────────────────────────────────────

class FileEngagementRepository:
    """
    Stores non-PII aggregate engagement metrics (clicks, summaries, bookmarks)
    in a unified JSON file on local disk with thread-safety.
    """

    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._lock = threading.Lock()

    def record_event(self, url: str, event_type: str) -> dict[str, int]:
        """
        Increment the aggregate counter for the given URL and event type.
        Zero PII is collected or stored.
        """
        normalized_url = url.strip()
        if not normalized_url:
            return {"clicks": 0, "summaries": 0, "bookmarks": 0}

        normalized_event = event_type.strip().lower()
        field_map = {
            "click": "clicks",
            "summary": "summaries",
            "bookmark": "bookmarks",
        }
        counter_field = field_map.get(normalized_event)
        if not counter_field:
            return self.get_engagement(normalized_url)

        with self._lock:
            data = self._read_data()
            engagements = data.setdefault("engagements", {})
            entry = engagements.setdefault(
                normalized_url,
                {"clicks": 0, "summaries": 0, "bookmarks": 0, "updated_at": ""},
            )
            entry[counter_field] = entry.get(counter_field, 0) + 1
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()

            data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
            data["metadata"]["total_tracked_urls"] = len(engagements)
            self._write_data(data)

            return {
                "clicks": entry.get("clicks", 0),
                "summaries": entry.get("summaries", 0),
                "bookmarks": entry.get("bookmarks", 0),
            }

    def get_engagement(self, url: str) -> dict[str, int]:
        """Get aggregate counts for a single URL."""
        normalized_url = url.strip()
        with self._lock:
            data = self._read_data()
            entry = data.get("engagements", {}).get(normalized_url, {})
            return {
                "clicks": entry.get("clicks", 0),
                "summaries": entry.get("summaries", 0),
                "bookmarks": entry.get("bookmarks", 0),
            }

    def get_all_engagements(self) -> dict[str, dict[str, int]]:
        """Get mapping of all tracked URLs to their aggregate counts."""
        with self._lock:
            data = self._read_data()
            raw_engagements = data.get("engagements", {})
            result: dict[str, dict[str, int]] = {}
            for url, stats in raw_engagements.items():
                result[url] = {
                    "clicks": stats.get("clicks", 0),
                    "summaries": stats.get("summaries", 0),
                    "bookmarks": stats.get("bookmarks", 0),
                }
            return result

    def clear_all(self) -> None:
        """Reset all engagement data (e.g. for PDPA data purge or test cleanup)."""
        with self._lock:
            data = self._default_data()
            self._write_data(data)

    # ── Private helpers ──────────────────────────────────────────

    def _read_data(self) -> dict[str, Any]:
        """Read data from JSON file or return default structure."""
        if not self._data_file.exists():
            return self._default_data()
        try:
            with self._data_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._default_data()

    def _write_data(self, data: dict[str, Any]) -> None:
        """Atomically persist data structure to disk using a temporary file."""
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self._data_file.parent,
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as tmp_file:
                json.dump(data, tmp_file, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp_file.name)
            os.replace(tmp_path, self._data_file)
        except Exception:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def _default_data(self) -> dict[str, Any]:
        """Default schema for engagement store."""
        return {
            "metadata": {
                "version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_tracked_urls": 0,
            },
            "engagements": {},
        }


# ── Singleton instance & factory / DI helper ───────────────────────

_engagement_repo_instance: FileEngagementRepository | None = None
_instance_lock = threading.Lock()


def get_engagement_repository() -> FileEngagementRepository:
    """FastAPI Depends() factory — returns thread-safe singleton instance."""
    global _engagement_repo_instance
    if _engagement_repo_instance is None:
        with _instance_lock:
            if _engagement_repo_instance is None:
                from backend.config import settings

                _engagement_repo_instance = FileEngagementRepository(
                    data_file=settings.engagement_file,
                )
    return _engagement_repo_instance
