"""
backend/issue_explorer/aliases.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการและขยายคำพ้อง/คำย่อ (Synonyms/Aliases) เท่านั้น
SOLID  O — เพิ่มคำพ้องใหม่ได้ผ่าน aliases.json โดยไม่ต้องแก้โค้ด
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_ALIASES_FILE = Path(__file__).resolve().parent / "aliases.json"
_ALIASES_MAP: dict[str, list[str]] = {}


def _load_aliases() -> dict[str, list[str]]:
    global _ALIASES_MAP
    if _ALIASES_MAP:
        return _ALIASES_MAP
    if _ALIASES_FILE.exists():
        try:
            with open(_ALIASES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    # normalize keys to lowercase trimmed
                    _ALIASES_MAP = {str(k).strip().lower(): [str(v).strip() for v in vals] for k, vals in raw.items()}
        except Exception as exc:
            logger.warning("Failed to load aliases.json: %s", exc)
            _ALIASES_MAP = {}
    return _ALIASES_MAP


def expand_term(term: str) -> list[str]:
    """
    Expand a term to its synonyms/abbreviations if registered.
    Always includes the original term as the first item.
    """
    cleaned = term.strip()
    if not cleaned:
        return []

    aliases_map = _load_aliases()
    key = cleaned.lower()

    results: list[str] = [cleaned]
    if key in aliases_map:
        for alias in aliases_map[key]:
            if alias and alias not in results:
                results.append(alias)

    return results
