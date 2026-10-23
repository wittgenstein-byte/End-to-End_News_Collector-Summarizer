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
        cache_size_kb: int = 16000,
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

            # Apply performance and disk-safety PRAGMAs
            if self._wal_mode:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.execute("PRAGMA wal_autocheckpoint = 1000;")
                conn.execute("PRAGMA journal_size_limit = 67108864;")

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
                        sentiment TEXT,
                        canonical_url TEXT
                    );
                    """
                )

                # Ensure canonical_url column exists in existing database schemas
                cursor = conn.execute("PRAGMA table_info(articles);")
                columns = [row[1] for row in cursor.fetchall()]
                if "canonical_url" not in columns:
                    conn.execute("ALTER TABLE articles ADD COLUMN canonical_url TEXT;")

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

                # 4. Canonical Article Index (Contract B Idempotency)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS canonical_article_index (
                        canonical_url TEXT PRIMARY KEY,
                        primary_raw_url TEXT NOT NULL,
                        story_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )

                # 5. Covering B-Tree Indexes
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
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_articles_canonical_url ON articles(canonical_url);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_canonical_story_id ON canonical_article_index(story_id);"
                )

                # Non-destructive migration: populate canonical_url if null or blank
                unmigrated = conn.execute(
                    "SELECT url, story_id, fetched_at FROM articles WHERE canonical_url IS NULL OR canonical_url = '';"
                ).fetchall()
                if unmigrated:
                    from backend.core.url_utils import canonicalize_url

                    for row in unmigrated:
                        raw_u = row["url"]
                        sid = row["story_id"]
                        f_at = (
                            row["fetched_at"]
                            if row["fetched_at"]
                            else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        )
                        c_u = canonicalize_url(raw_u)
                        conn.execute("UPDATE articles SET canonical_url = ? WHERE url = ?;", (c_u, raw_u))
                        conn.execute(
                            """
                            INSERT INTO canonical_article_index (
                                canonical_url, primary_raw_url, story_id, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(canonical_url) DO UPDATE SET
                                story_id = COALESCE(NULLIF(canonical_article_index.story_id, ''), excluded.story_id),
                                updated_at = excluded.updated_at;
                            """,
                            (c_u, raw_u, sid, f_at, f_at),
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

        from backend.core.url_utils import canonicalize_url

        article_rows = []
        canonical_rows = []
        content_rows = []
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        for art in articles:
            url = str(art.get("url") or "").strip()
            if not url:
                continue

            canon_url = str(art.get("canonical_url") or "").strip() or canonicalize_url(url)
            story_id = art.get("story_id")
            fetched_at = str(art.get("fetched_at") or now_str)

            article_rows.append(
                (
                    url,
                    str(art.get("title") or ""),
                    str(art.get("source") or ""),
                    fetched_at,
                    str(art.get("summary") or ""),
                    art.get("category"),
                    story_id,
                    str(art.get("image_url") or ""),
                    str(art.get("classification_method") or ""),
                    art.get("sentiment"),
                    canon_url,
                )
            )

            canonical_rows.append(
                (
                    canon_url,
                    url,
                    story_id,
                    fetched_at,
                    now_str,
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
                # 1. Upsert metadata (Preserve existing non-empty story_id)
                conn.executemany(
                    """
                    INSERT INTO articles (
                        url, title, source, fetched_at, summary, category,
                        story_id, image_url, classification_method, sentiment, canonical_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title = excluded.title,
                        source = excluded.source,
                        fetched_at = excluded.fetched_at,
                        summary = excluded.summary,
                        category = excluded.category,
                        story_id = COALESCE(NULLIF(articles.story_id, ''), NULLIF(excluded.story_id, '')),
                        image_url = excluded.image_url,
                        classification_method = excluded.classification_method,
                        sentiment = excluded.sentiment,
                        canonical_url = excluded.canonical_url;
                    """,
                    article_rows,
                )

                # 2. Upsert canonical article index
                conn.executemany(
                    """
                    INSERT INTO canonical_article_index (
                        canonical_url, primary_raw_url, story_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(canonical_url) DO UPDATE SET
                        story_id = COALESCE(NULLIF(canonical_article_index.story_id, ''), excluded.story_id),
                        updated_at = excluded.updated_at;
                    """,
                    canonical_rows,
                )

                # 3. Upsert decoupled content if provided
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

    def get_by_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        """Fetch article records matching raw URLs or canonical URLs."""
        if not urls:
            return []
        from backend.core.url_utils import canonicalize_url

        raw_set = {u.strip() for u in urls if u and u.strip()}
        canon_set = {canonicalize_url(u) for u in raw_set if canonicalize_url(u)}
        all_targets = list(raw_set | canon_set)
        if not all_targets:
            return []

        conn = self._get_connection()
        placeholders = ",".join("?" for _ in all_targets)
        cursor = conn.execute(
            f"""
            SELECT url, title, source, fetched_at, summary, category, story_id,
                   image_url, classification_method, sentiment, canonical_url
            FROM articles
            WHERE url IN ({placeholders}) OR canonical_url IN ({placeholders});
            """,
            all_targets + all_targets,
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_assigned_story_id(self, url: str) -> str | None:
        """Lookup persistent story_id by raw or canonical URL."""
        if not url:
            return None
        from backend.core.url_utils import canonicalize_url

        raw_u = url.strip()
        canon_u = canonicalize_url(raw_u)

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT story_id FROM canonical_article_index
            WHERE canonical_url = ? OR primary_raw_url = ?
            LIMIT 1;
            """,
            (canon_u, raw_u),
        )
        row = cursor.fetchone()
        if row and row["story_id"]:
            return row["story_id"]

        cursor2 = conn.execute(
            """
            SELECT story_id FROM articles
            WHERE canonical_url = ? OR url = ?
            LIMIT 1;
            """,
            (canon_u, raw_u),
        )
        row2 = cursor2.fetchone()
        return row2["story_id"] if row2 and row2["story_id"] else None

    def update_story_ids_batch(
        self,
        url_to_story_id: dict[str, str],
        allow_overwrite: bool = False,
    ) -> dict[str, str]:
        """
        Contract B: Atomically assign story_id mappings inside BEGIN IMMEDIATE transaction.
        Updates canonical_article_index and articles table.
        Returns the resolved authoritative mapping {url: authoritative_story_id}.
        """
        if not url_to_story_id:
            return {}

        from backend.core.url_utils import canonicalize_url

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        resolved: dict[str, str] = {}

        with self._write_lock:
            conn = self._get_connection()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                for raw_url, target_story_id in url_to_story_id.items():
                    raw_u = raw_url.strip()
                    if not raw_u or not target_story_id:
                        continue
                    canon_u = canonicalize_url(raw_u)

                    # 1. Claim or get in canonical_article_index
                    conn.execute(
                        """
                        INSERT INTO canonical_article_index (
                            canonical_url, primary_raw_url, story_id, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(canonical_url) DO UPDATE SET
                            story_id = CASE
                                WHEN ? = 1 THEN excluded.story_id
                                ELSE COALESCE(NULLIF(canonical_article_index.story_id, ''), excluded.story_id)
                            END,
                            updated_at = excluded.updated_at;
                        """,
                        (canon_u, raw_u, target_story_id, now_str, now_str, 1 if allow_overwrite else 0),
                    )

                    # Read back authoritative story_id
                    cursor = conn.execute(
                        "SELECT story_id FROM canonical_article_index WHERE canonical_url = ?;",
                        (canon_u,),
                    )
                    row = cursor.fetchone()
                    auth_story_id = row["story_id"] if row and row["story_id"] else target_story_id
                    resolved[raw_u] = auth_story_id

                    # 2. Update matching rows in articles table
                    conn.execute(
                        """
                        UPDATE articles
                        SET story_id = CASE
                            WHEN ? = 1 THEN ?
                            ELSE COALESCE(NULLIF(articles.story_id, ''), ?)
                        END
                        WHERE canonical_url = ? OR url = ?;
                        """,
                        (1 if allow_overwrite else 0, auth_story_id, auth_story_id, canon_u, raw_u),
                    )

                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return resolved

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
