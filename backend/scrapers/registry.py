"""
scrapers/registry.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ source registry เท่านั้น
SOLID  O — เพิ่ม source ใหม่ได้โดย @register_source ไม่แก้ไฟล์นี้
GRASP  Creator — สร้างและเก็บ NewsSource objects
GRASP  Information Expert — รู้จัก SOURCES collection ทั้งหมด

ทำไมแยก NewsSource ออกจาก news_scraper.py เดิม?
  เดิม dataclass, registry, helpers, scrapers อยู่ไฟล์เดียวกัน
  → import แค่ SOURCES ก็ต้องโหลด Playwright + BeautifulSoup ทั้งหมด
  → แยกแล้ว scraper_service.py import แค่ registry ได้เบา ๆ
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Coroutine, Any


@dataclass
class NewsSource:
    name:      str
    url:       str
    color:     str                                          # hex color สำหรับ frontend badge
    scrape_fn: Callable[[], Coroutine[Any, Any, list[dict]]]


# Global registry — populated by @register_source at import time
SOURCES: list[NewsSource] = []


def register_source(name: str, url: str, color: str):
    """
    Decorator สำหรับ scraper functions
    ใช้งาน:
        @register_source("ThaiPBS", "https://...", "#e74c3c")
        async def scrape_thaipbs() -> list[dict]: ...
    """
    def decorator(func: Callable[[], Coroutine[Any, Any, list[dict]]]):
        SOURCES.append(NewsSource(name=name, url=url, color=color, scrape_fn=func))
        return func
    return decorator