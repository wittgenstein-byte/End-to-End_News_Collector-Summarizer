"""
repo/event_repo.py
────────────────────────────────────────────────────────────────
SOLID  S — จัดการ persistence ของ anonymous user + events ใน SQLite
SOLID  D — repo instance ถูก inject ผ่าน factory
GRASP  Information Expert — รู้จัก schema และ query ของ event analytics
────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventRepository:
    """Store anonymous visitor IDs and user interaction events in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS anonymous_users (
                    user_id TEXT PRIMARY KEY,
                    consented INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    article_url TEXT,
                    article_title TEXT,
                    source TEXT,
                    category TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES anonymous_users(user_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_events_user_id_on_created_at "
                "ON user_events(user_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_events_event_name "
                "ON user_events(event_name)"
            )

    def upsert_user(self, user_id: str, consented: bool = True) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO anonymous_users(user_id, consented, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    consented = excluded.consented,
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, int(consented), now, now),
            )

    def record_event(
        self,
        user_id: str,
        event_name: str,
        *,
        article_url: str | None = None,
        article_title: str | None = None,
        source: str | None = None,
        category: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_events(
                    user_id,
                    event_name,
                    article_url,
                    article_title,
                    source,
                    category,
                    metadata,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    event_name,
                    article_url,
                    article_title,
                    source,
                    category,
                    payload,
                    now,
                ),
            )
            conn.execute(
                "UPDATE anonymous_users SET last_seen_at = ? WHERE user_id = ?",
                (now, user_id),
            )

    def count_events(self, user_id: str | None = None) -> int:
        with self._connect() as conn:
            if user_id:
                row = conn.execute(
                    "SELECT COUNT(*) AS count FROM user_events WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS count FROM user_events"
                ).fetchone()
            return int(row["count"]) if row else 0


def get_event_repository() -> EventRepository:
    """FastAPI Depends() factory for the anonymous event database."""
    from backend.config import settings

    return EventRepository(db_path=settings.event_db_path)
