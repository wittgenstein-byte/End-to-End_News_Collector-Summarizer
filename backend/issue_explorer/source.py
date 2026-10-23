"""
backend/issue_explorer/source.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการการอ่านข้อมูลข่าวจาก SQLite ในโหมด Read-Only (mode=ro)
SOLID  O — ออกแบบผ่าน ArticleSourcePort Protocol ให้สลับเป็น FTS5 ได้ในอนาคต
SOLID  D — Service พึ่งพา Protocol แทน concrete class
GRASP  Information Expert — จัดการ connection, WAL read, และ data versioning
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

from backend.config import settings

logger = logging.getLogger(__name__)


class ArticleSourcePort(Protocol):
    def search(
        self,
        where_sql: str,
        params: list[Any],
        limit: int = 500,
        date_from: str | None = None,
        date_to: str | None = None,
        source: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_background_sample(self, limit: int = 3000) -> list[str]: ...

    def data_version(self) -> str: ...

    def health(self) -> dict[str, Any]: ...


class SqliteReadOnlyArticleSource:
    """
    Read-only SQLite source connecting via `file:...mode=ro`.
    Guarantees no schema modification, write locking, or database corruption.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else settings.sqlite_file
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if not self._db_path.exists():
                raise FileNotFoundError(f"Database file not found: {self._db_path}")

            # Connect via read-only URI
            uri = f"file:{self._db_path.resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=10.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON;")
            self._local.conn = conn
        return conn

    def search(
        self,
        where_sql: str,
        params: list[Any],
        limit: int = 500,
        date_from: str | None = None,
        date_to: str | None = None,
        source: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        clauses = [where_sql]
        query_params = list(params)

        if date_from and date_from.strip():
            clauses.append("fetched_at >= ?")
            query_params.append(f"{date_from.strip()} 00:00:00")

        if date_to and date_to.strip():
            clauses.append("fetched_at <= ?")
            query_params.append(f"{date_to.strip()} 23:59:59")

        if source and source.strip():
            clauses.append("LOWER(source) = ?")
            query_params.append(source.strip().lower())

        if category and category.strip() and category.strip().lower() != "all":
            clauses.append("category = ?")
            query_params.append(category.strip())

        full_where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_params.append(max(1, min(limit, 2000)))

        sql = f"""
            SELECT id, url, title, source, fetched_at, summary, category, story_id
            FROM articles
            {full_where}
            ORDER BY fetched_at DESC
            LIMIT ?;
        """
        cursor = conn.execute(sql, query_params)
        return [dict(row) for row in cursor.fetchall()]

    def get_background_sample(self, limit: int = 3000) -> list[str]:
        """Fetch recent titles to build baseline background word frequencies."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT title FROM articles ORDER BY id DESC LIMIT ?;",
            (limit,),
        )
        return [row[0] for row in cursor.fetchall() if row[0]]

    def data_version(self) -> str:
        """Instantaneous lightweight version key: f'{count}:{max_id}'."""
        try:
            conn = self._get_connection()
            row = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM articles;").fetchone()
            if row:
                return f"{row[0]}:{row[1]}"
        except Exception as exc:
            logger.warning("Could not read data_version: %s", exc)
        return "0:0"

    def health(self) -> dict[str, Any]:
        """Verify read-only connectivity and article count."""
        try:
            conn = self._get_connection()
            row = conn.execute("SELECT COUNT(*) FROM articles;").fetchone()
            count = row[0] if row else 0
            return {
                "status": "ok",
                "storage": "sqlite",
                "readonly": True,
                "total_articles": count,
            }
        except Exception as exc:
            return {
                "status": "error",
                "storage": "sqlite",
                "readonly": True,
                "error": str(exc),
            }

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None
