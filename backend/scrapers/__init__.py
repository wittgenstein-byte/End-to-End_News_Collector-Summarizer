"""
scrapers/__init__.py
─────────────────────────────────────────────────────────────────
Public API ของ scrapers package

การ import ไฟล์นี้จะ:
  1. import scrapers.sources  → trigger @register_source decorators
  2. SOURCES จะมีข้อมูลครบ 4 แหล่ง พร้อมใช้งาน

ทุก module ที่ต้องการ SOURCES ควร import จากที่นี่:
    from scrapers import SOURCES       ✓
    from scrapers.registry import SOURCES   (ใช้ได้แต่ sources ยังว่างอยู่ถ้าไม่ import sources.py)
─────────────────────────────────────────────────────────────────
"""

# side-effect import — registers all sources into SOURCES list
import scrapers.sources  # noqa: F401

from scrapers.registry import SOURCES, NewsSource, register_source

__all__ = ["SOURCES", "NewsSource", "register_source"]