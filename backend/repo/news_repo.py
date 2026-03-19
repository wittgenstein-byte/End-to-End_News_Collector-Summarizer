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
    """เก็บข้อมูลใน JSON files บน local disk"""

    def __init__(self, output_file: Path, seen_file: Path) -> None:
        self._output = output_file
        self._seen   = seen_file

    # ── News ─────────────────────────────────────────────────────

    def load_news(self) -> list[dict]:
        return self._read_json(self._output, default=[])  # type: ignore[return-value]

    def save_news(self, data: list[dict]) -> None:
        self._write_json(self._output, data)

    # ── Seen URLs ────────────────────────────────────────────────

    def load_seen(self) -> set[str]:
        raw: list = self._read_json(self._seen, default=[])
        return set(raw)

    def save_seen(self, seen: set[str]) -> None:
        self._write_json(self._seen, list(seen))

    # ── Private helpers ──────────────────────────────────────────

    def _read_json(self, path: Path, *, default):
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

    def _write_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ── Factory / DI helper ───────────────────────────────────────────

def get_news_repository() -> FileNewsRepository:
    """FastAPI Depends() factory — inject settings ที่นี่เดียว"""
    from config import settings
    return FileNewsRepository(
        output_file=settings.output_file,
        seen_file=settings.seen_file,
    )