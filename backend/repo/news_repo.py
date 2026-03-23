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
from pathlib import Path
from typing import Protocol
from datetime import datetime


# ── Port (abstract interface) ─────────────────────────────────────
# SOLID D — high-level modules (services) พึ่ง abstraction นี้
#           ไม่พึ่ง FileNewsRepository โดยตรง

class NewsRepositoryPort(Protocol):
    def load_news(self)  -> list[dict]: ...
    def save_news(self, data: list[dict]) -> None: ...
    def load_seen(self)  -> set[str]: ...
    def save_seen(self, seen: set[str]) -> None: ...


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
        data["metadata"]["last_updated"] = datetime.now().isoformat()
        data["metadata"]["total_articles"] = len(articles)
        self._write_data(data)

    # ── Seen URLs ────────────────────────────────────────────────

    def load_seen(self) -> set[str]:
        data = self._read_data()
        return set(data.get("seen_urls", []))

    def save_seen(self, seen: set[str]) -> None:
        data = self._read_data()
        data["seen_urls"] = list(seen)
        data["metadata"]["last_updated"] = datetime.now().isoformat()
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
                "last_updated": datetime.now().isoformat(),
                "total_articles": 0,
                "total_sources": 0
            },
            "sources": {},
            "articles": [],
            "seen_urls": []
        }


# ── Factory / DI helper ───────────────────────────────────────────

def get_news_repository() -> FileNewsRepository:
    """FastAPI Depends() factory — inject settings ที่นี่เดียว"""
    from backend.config import settings
    return FileNewsRepository(
        data_file=settings.data_file,
    )