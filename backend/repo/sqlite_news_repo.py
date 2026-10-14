"""
repo/sqlite_news_repo.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ persistence และ query ข้อมูลข่าวใน SQLite NoSQL/Relational
SOLID  O — ขยายจาก NewsRepositoryPort โดยไม่ต้องแก้ core domain logic
SOLID  L — สามารถสลับใช้แทน FileNewsRepository และ MongoNewsRepository ได้ 100%
SOLID  D — รองรับการ inject db_path และ PRAGMA config ผ่าน constructor
GRASP  Information Expert — จัดการ connection, schema, indexes, และ SQL query
GRASP  Creator — จัดการ article, article_content, และ seen_url records
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SqliteNewsRepository:
    """
    High-performance SQLite repository implementation with:
      - WAL mode (Write-Ahead Logging) for non-blocking concurrent reads & writes
      - Decoupled schema: compact listing metadata vs heavy article content
      - In-memory SQLite page cache (64 MB) & memory-mapped I/O (256 MB)
      - Covering B-Tree indexes on fetched_at, category, source, and story_id
    """

    def __init__(
        self,
        db_path: Path | str,
        wal_mode: bool = True,
        cache_size_kb: int = 64000,
        mmap_size_bytes: int = 268435456,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._wal_mode = wal_mode
        self._cache_size_kb = cache_size_kb
        self._mmap_size_bytes = mmap_size_bytes
        self._write_lock = threading.Lock()

        # Thread-local storage for sqlite3 connections
        self._local = threading.local()

        # Initialize schema and indexes
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or initialize thread-local connection with WAL mode and PRAGMAs."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self._db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row

            # Apply performance PRAGMAs
            if self._wal_mode:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")

            conn.execute(f"PRAGMA cache_size = -{self._cache_size_kb};")
            conn.execute(f"PRAGMA mmap_size = {self._mmap_size_bytes};")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA foreign_keys = ON;")

            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        """Initialize decoupled database tables and B-Tree indexes."""
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                # 1. Compact listing metadata table (for fast feed pagination & sorting)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS articles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT UNIQUE NOT NULL,
                        title TEXT NOT NULL,
                        source TEXT NOT NULL,
                        fetched_at TEXT NOT NULL,
                        summary TEXT DEFAULT '',
                        category TEXT,
                        story_id TEXT,
                        image_url TEXT DEFAULT '',
                        classification_method TEXT DEFAULT '',
                        sentiment TEXT
                    );
                    """
                )

                # 2. Decoupled heavy content table (loaded on demand for reading/summarizing)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS article_contents (
                        url TEXT PRIMARY KEY REFERENCES articles(url) ON DELETE CASCADE,
                        content TEXT DEFAULT '',
                        raw_html TEXT DEFAULT '',
                        bullets_json TEXT DEFAULT '[]',
                        keywords_json TEXT DEFAULT '[]',
                        updated_at TEXT
                    );
                    """
                )

                # 3. Seen URLs table for crawler deduplication
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS seen_urls (
                        url TEXT PRIMARY KEY,
                        first_seen_at TEXT NOT NULL
                    );
                    """
                )

                # 4. Covering B-Tree Indexes
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_articles_fetched_at ON articles(fetched_at DESC);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_articles_cat_fetched ON articles(category, fetched_at DESC);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_articles_src_fetched ON articles(source, fetched_at DESC);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_articles_story_id ON articles(story_id);"
                )
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url ON articles(url);"
                )

    # ── News Operations ──────────────────────────────────────────

    def load_news(self) -> list[dict[str, Any]]:
        """Load all articles ordered by fetched_at descending (metadata only)."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT url, title, source, fetched_at, summary, category, story_id,
                   image_url, classification_method, sentiment
            FROM articles
            ORDER BY fetched_at DESC;
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    def load_recent_news(self, hours: float = 48.0) -> list[dict[str, Any]]:
        """High-speed query for recent articles within candidate window (for Trending Engine)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT url, title, source, fetched_at, summary, category, story_id,
                   image_url, classification_method, sentiment
            FROM articles
            WHERE fetched_at >= ?
            ORDER BY fetched_at DESC;
            """,
            (cutoff,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def save_news(self, articles: list[dict[str, Any]]) -> None:
        """Atomic batch upsert of articles (separating metadata and heavy content)."""
        if not articles:
            return

        article_rows = []
        content_rows = []
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        for art in articles:
            url = str(art.get("url") or "").strip()
            if not url:
                continue

            article_rows.append(
                (
                    url,
                    str(art.get("title") or ""),
                    str(art.get("source") or ""),
                    str(art.get("fetched_at") or now_str),
                    str(art.get("summary") or ""),
                    art.get("category"),
                    art.get("story_id"),
                    str(art.get("image_url") or ""),
                    str(art.get("classification_method") or ""),
                    art.get("sentiment"),
                )
            )

            # Check if heavy content is present
            content = art.get("content") or art.get("body")
            raw_html = art.get("raw_html")
            bullets = art.get("bullets")
            keywords = art.get("keywords")

            if content or raw_html or bullets or keywords:
                content_rows.append(
                    (
                        url,
                        str(content or ""),
                        str(raw_html or ""),
                        json.dumps(bullets or [], ensure_ascii=False),
                        json.dumps(keywords or [], ensure_ascii=False),
                        now_str,
                    )
                )

        with self._write_lock:
            conn = self._get_connection()
            with conn:
                # 1. Upsert metadata
                conn.executemany(
                    """
                    INSERT INTO articles (
                        url, title, source, fetched_at, summary, category,
                        story_id, image_url, classification_method, sentiment
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title = excluded.title,
                        source = excluded.source,
                        fetched_at = excluded.fetched_at,
                        summary = excluded.summary,
                        category = excluded.category,
                        story_id = excluded.story_id,
                        image_url = excluded.image_url,
                        classification_method = excluded.classification_method,
                        sentiment = excluded.sentiment;
                    """,
                    article_rows,
                )

                # 2. Upsert decoupled content if provided
                if content_rows:
                    conn.executemany(
                        """
                        INSERT INTO article_contents (
                            url, content, raw_html, bullets_json, keywords_json, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(url) DO UPDATE SET
                            content = excluded.content,
                            raw_html = excluded.raw_html,
                            bullets_json = excluded.bullets_json,
                            keywords_json = excluded.keywords_json,
                            updated_at = excluded.updated_at;
                        """,
                        content_rows,
                    )

    def query_news(
        self,
        page: int = 1,
        page_size: int = 20,
        source: str = "",
        category: str | None = None,
        query: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Sub-millisecond indexed point query & pagination on compact articles table.
        Does not scan heavy body content.
        """
        page = max(1, page)
        page_size = max(1, page_size)
        offset = (page - 1) * page_size

        where_clauses: list[str] = []
        params: list[Any] = []

        if source and source.strip():
            where_clauses.append("LOWER(source) = ?")
            params.append(source.strip().lower())

        if category and category.strip() and category.strip() != "all":
            where_clauses.append("category = ?")
            params.append(category.strip())

        if query and query.strip():
            pattern = f"%{query.strip()}%"
            where_clauses.append("(title LIKE ? OR summary LIKE ?)")
            params.extend([pattern, pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        conn = self._get_connection()

        # Count total matching records
        count_cursor = conn.execute(f"SELECT COUNT(*) FROM articles {where_sql};", params)
        total = count_cursor.fetchone()[0]

        # Fetch page slice with covering index
        query_params = list(params) + [page_size, offset]
        data_cursor = conn.execute(
            f"""
            SELECT url, title, source, fetched_at, summary, category, story_id,
                   image_url, classification_method, sentiment
            FROM articles
            {where_sql}
            ORDER BY fetched_at DESC
            LIMIT ? OFFSET ?;
            """,
            query_params,
        )
        items = [dict(row) for row in data_cursor.fetchall()]
        return items, total

    def get_category_counts(self) -> dict[str, int]:
        """Aggregate article counts grouped by category in micro-seconds."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT category, COUNT(*) as count
            FROM articles
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category;
            """
        )
        counts = {row["category"]: row["count"] for row in cursor.fetchall()}

        total_cursor = conn.execute("SELECT COUNT(*) FROM articles;")
        counts["all"] = total_cursor.fetchone()[0]
        return counts

    def get_source_counts(self) -> dict[str, int]:
        """Aggregate article counts grouped by source in micro-seconds."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT source, COUNT(*) as count
            FROM articles
            WHERE source IS NOT NULL AND source != ''
            GROUP BY source;
            """
        )
        return {row["source"]: row["count"] for row in cursor.fetchall()}

    # ── Heavy Content Decoupled Accessors ─────────────────────────

    def get_article_content(self, url: str) -> dict[str, Any] | None:
        """Fetch heavy body/markdown content on-demand by URL."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT content, raw_html, bullets_json, keywords_json, updated_at
            FROM article_contents
            WHERE url = ?;
            """,
            (url,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        try:
            res["bullets"] = json.loads(res.pop("bullets_json", "[]"))
        except Exception:
            res["bullets"] = []
        try:
            res["keywords"] = json.loads(res.pop("keywords_json", "[]"))
        except Exception:
            res["keywords"] = []
        return res

    def save_article_content(
        self,
        url: str,
        content: str = "",
        raw_html: str = "",
        bullets: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        """Save decoupled heavy article content."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO article_contents (
                        url, content, raw_html, bullets_json, keywords_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        content = excluded.content,
                        raw_html = excluded.raw_html,
                        bullets_json = excluded.bullets_json,
                        keywords_json = excluded.keywords_json,
                        updated_at = excluded.updated_at;
                    """,
                    (
                        url,
                        content,
                        raw_html,
                        json.dumps(bullets or [], ensure_ascii=False),
                        json.dumps(keywords or [], ensure_ascii=False),
                        now_str,
                    ),
                )

    # ── Seen URLs ────────────────────────────────────────────────

    def load_seen(self) -> set[str]:
        """Load set of seen URLs from seen_urls and articles tables."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT url FROM seen_urls UNION SELECT url FROM articles;")
        return {row[0] for row in cursor.fetchall()}

    def save_seen(self, seen: set[str]) -> None:
        """Save seen URLs into seen_urls table."""
        if not seen:
            return
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows = [(url, now_str) for url in seen if url]

        with self._write_lock:
            conn = self._get_connection()
            with conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO seen_urls (url, first_seen_at) VALUES (?, ?);",
                    rows,
                )

    def close(self) -> None:
        """Close thread-local connection if open."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None
