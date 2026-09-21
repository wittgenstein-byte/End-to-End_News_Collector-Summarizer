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
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

# ── Port (abstract interface) ─────────────────────────────────────
# SOLID D — high-level modules (services) พึ่ง abstraction นี้
#           ไม่พึ่ง FileNewsRepository โดยตรง

class NewsRepositoryPort(Protocol):
    def load_news(self)  -> list[dict]: ...
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


# ── Concrete implementation ───────────────────────────────────────

class FileNewsRepository:
    """เก็บข้อมูลใน unified JSON file บน local disk"""

    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file

    # ── News ─────────────────────────────────────────────────────

    def load_news(self) -> list[dict]:
        data = self._read_data()
        return data.get("articles", [])

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

    _REPO_INSTANCE = FileNewsRepository(data_file=settings.data_file)
    return _REPO_INSTANCE