"""
repositories/news_repository.py
─────────────────────────────────────────────────────────────────
SOLID  S — รับผิดชอบแค่ read/write ไฟล์ JSON
SOLID  D — รับ Settings ผ่าน constructor (inject ได้, test ได้)
GRASP  Information Expert — รู้จัก format ข้อมูลและ path ไฟล์
GRASP  Creator — สร้างและจัดการ news / seen-url collections
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

# ── Port (abstract interface) ─────────────────────────────────────
# SOLID D — high-level modules (services) พึ่ง abstraction นี้
#           ไม่พึ่ง FileNewsRepository โดยตรง

class NewsRepositoryPort(Protocol):
    def load_news(self)  -> list[dict]: ...
    def load_recent_news(self, hours: float = 48.0) -> list[dict]: ...
    def save_news(self, data: list[dict]) -> None: ...
    def load_seen(self)  -> set[str]: ...
    def save_seen(self, seen: set[str]) -> None: ...
    def query_news(
        self,
        page: int = 1,
        page_size: int = 20,
        source: str = "",
        category: str | None = None,
        query: str = "",
    ) -> tuple[list[dict], int]: ...
    def get_category_counts(self) -> dict[str, int]: ...
    def get_source_counts(self) -> dict[str, int]: ...
    def get_by_urls(self, urls: list[str]) -> list[dict]: ...
    def get_article_content(self, url: str) -> dict | None: ...
    def save_article_content(
        self,
        url: str,
        content: str = "",
        raw_html: str = "",
        bullets: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> None: ...
    def update_story_ids_batch(
        self,
        url_to_story_id: dict[str, str],
        allow_overwrite: bool = False,
    ) -> dict[str, str]: ...
    def get_assigned_story_id(self, url: str) -> str | None: ...


# ── Concrete implementation ───────────────────────────────────────

class FileNewsRepository:
    """เก็บข้อมูลใน unified JSON file บน local disk"""

    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file

    # ── News ─────────────────────────────────────────────────────

    def load_news(self) -> list[dict]:
        data = self._read_data()
        return data.get("articles", [])

    def load_recent_news(self, hours: float = 48.0) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        news = self.load_news()
        return [n for n in news if str(n.get("fetched_at") or "") >= cutoff]

    def get_by_urls(self, urls: list[str]) -> list[dict]:
        """Fetch article dicts matching raw or canonical URLs."""
        if not urls:
            return []
        from backend.core.url_utils import canonicalize_url

        raw_set = {u.strip() for u in urls if u and u.strip()}
        canon_set = {canonicalize_url(u) for u in raw_set if canonicalize_url(u)}
        return [
            a
            for a in self.load_news()
            if a.get("url") in raw_set or canonicalize_url(str(a.get("url") or "")) in canon_set
        ]

    def get_assigned_story_id(self, url: str) -> str | None:
        """Lookup persistent story_id by raw or canonical URL."""
        if not url:
            return None
        from backend.core.url_utils import canonicalize_url

        raw_u = url.strip()
        canon_u = canonicalize_url(raw_u)
        for a in self.load_news():
            u = str(a.get("url") or "")
            if u == raw_u or canonicalize_url(u) == canon_u:
                return a.get("story_id")
        return None

    def update_story_ids_batch(
        self,
        url_to_story_id: dict[str, str],
        allow_overwrite: bool = False,
    ) -> dict[str, str]:
        """Batch update article story_id assignments."""
        if not url_to_story_id:
            return {}
        from backend.core.url_utils import canonicalize_url

        data = self._read_data()
        articles = data.get("articles", [])
        resolved: dict[str, str] = {}
        target_canon = {canonicalize_url(u): sid for u, sid in url_to_story_id.items() if u}

        for a in articles:
            u = str(a.get("url") or "")
            cu = canonicalize_url(u)
            if cu in target_canon or u in url_to_story_id:
                new_sid = target_canon.get(cu) or url_to_story_id.get(u)
                old_sid = a.get("story_id")
                if allow_overwrite or not old_sid:
                    a["story_id"] = new_sid
                    resolved[u] = new_sid
                else:
                    resolved[u] = old_sid

        data["articles"] = articles
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._write_data(data)
        return resolved

    def save_news(self, articles: list[dict]) -> None:
        data = self._read_data()
        data["articles"] = articles
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["metadata"]["total_articles"] = len(articles)
        self._write_data(data)

    def query_news(
        self,
        page: int = 1,
        page_size: int = 20,
        source: str = "",
        category: str | None = None,
        query: str = "",
    ) -> tuple[list[dict], int]:
        news = self.load_news()
        news.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)

        if source:
            source_lower = source.strip().lower()
            news = [n for n in news if n.get("source", "").lower() == source_lower]
        if query:
            query_lower = query.strip().lower()
            news = [
                n
                for n in news
                if query_lower in n.get("title", "").lower()
                or query_lower in n.get("summary", "").lower()
            ]
        if category and category != "all":
            news = [n for n in news if n.get("category") == category]

        total = len(news)
        page = max(1, page)
        start = (page - 1) * page_size
        return news[start : start + page_size], total

    def get_category_counts(self) -> dict[str, int]:
        news = self.load_news()
        counts: dict[str, int] = {"all": len(news)}
        for n in news:
            cat = n.get("category")
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
        return counts

    def get_source_counts(self) -> dict[str, int]:
        news = self.load_news()
        counts: dict[str, int] = {}
        for n in news:
            src = n.get("source")
            if src:
                counts[src] = counts.get(src, 0) + 1
        return counts

    def get_article_content(self, url: str) -> dict | None:
        """Fallback for FileNewsRepository - check if in-memory or return None."""
        for art in self.load_news():
            if art.get("url") == url and (art.get("content") or art.get("body")):
                return {
                    "content": art.get("content") or art.get("body", ""),
                    "raw_html": art.get("raw_html", ""),
                    "bullets": art.get("bullets", []),
                    "keywords": art.get("keywords", []),
                }
        return None

    def save_article_content(
        self,
        url: str,
        content: str = "",
        raw_html: str = "",
        bullets: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        pass

    # ── Seen URLs ────────────────────────────────────────────────

    def load_seen(self) -> set[str]:
        data = self._read_data()
        return set(data.get("seen_urls", []))

    def save_seen(self, seen: set[str]) -> None:
        data = self._read_data()
        data["seen_urls"] = list(seen)
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._write_data(data)

    # ── Private helpers ──────────────────────────────────────────

    def _read_data(self) -> dict:
        """Read the unified data structure"""
        if not self._data_file.exists():
            return self._default_data()
        try:
            with self._data_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._default_data()

    def _write_data(self, data: dict) -> None:
        """Write the unified data structure"""
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        with self._data_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _default_data(self) -> dict:
        """Default empty data structure"""
        return {
            "metadata": {
                "version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_articles": 0,
                "total_sources": 0,
            },
            "sources": {},
            "articles": [],
            "seen_urls": [],
        }


# ── Factory / DI helper ───────────────────────────────────────────

_REPO_INSTANCE: NewsRepositoryPort | None = None


def get_news_repository() -> NewsRepositoryPort:
    """FastAPI Depends() factory — inject settings ที่นี่เดียว"""
    global _REPO_INSTANCE
    if _REPO_INSTANCE is not None:
        return _REPO_INSTANCE

    from backend.config import settings

    # 1. SQLite WAL Mode Storage Engine (Default for Max Speed)
    if settings.db_type == "sqlite":
        try:
            from backend.repo.sqlite_news_repo import SqliteNewsRepository

            sqlite_repo = SqliteNewsRepository(
                db_path=settings.sqlite_file,
                wal_mode=settings.sqlite_wal_mode,
                cache_size_kb=settings.sqlite_cache_size_kb,
                mmap_size_bytes=settings.sqlite_mmap_size_bytes,
            )

            # Auto-bootstrap / migrate from JSON if SQLite database is empty
            if settings.data_file.exists():
                cat_counts = sqlite_repo.get_category_counts()
                if cat_counts.get("all", 0) == 0:
                    try:
                        from backend.migrate_to_sqlite import migrate_json_to_sqlite

                        migrate_json_to_sqlite(
                            json_path=settings.data_file,
                            sqlite_repo=sqlite_repo,
                        )
                    except Exception as m_exc:
                        import logging

                        logging.getLogger(__name__).warning("SQLite auto-migration skipped: %s", m_exc)

            _REPO_INSTANCE = sqlite_repo
            return _REPO_INSTANCE
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to initialize SqliteNewsRepository (%s), falling back to FileNewsRepository",
                exc,
            )

    # 2. MongoDB Option
    if settings.db_type == "mongodb":
        try:
            from backend.repo.mongo_news_repo import MongoNewsRepository

            _REPO_INSTANCE = MongoNewsRepository(
                mongo_uri=settings.mongo_uri,
                db_name=settings.mongo_db_name,
            )
            return _REPO_INSTANCE
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to initialize MongoNewsRepository (%s), falling back to FileNewsRepository",
                exc,
            )

    # 3. JSON File Fallback
    _REPO_INSTANCE = FileNewsRepository(data_file=settings.data_file)
    return _REPO_INSTANCE
