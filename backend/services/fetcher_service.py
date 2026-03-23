"""
services/fetcher_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — ดึง HTML/Markdown เท่านั้น  ไม่รู้จัก LLM / storage
SOLID  O — เพิ่ม Tier ใหม่ได้โดย subclass FetchStrategy
           ไม่แก้ FetcherService เดิม (open for extension)
SOLID  L — ทุก strategy แทนกันได้สมบูรณ์
GRASP  Low Coupling — แต่ละ Tier ไม่รู้จักกัน
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import httpx
import trafilatura

# ใช้ constants จาก core — ไม่ define ซ้ำ (DRY)
from backend.core.constants import BROWSER_HEADERS as _BROWSER_HEADERS, CLOUDFLARE_TELLS as _CLOUDFLARE_TELLS


# ── Strategy base class (SOLID O + L) ────────────────────────────

class FetchStrategy(ABC):
    """Abstract strategy — ทุก Tier ต้อง implement"""

    name: str = "unknown"

    @abstractmethod
    async def fetch(self, url: str) -> str | None:
        """คืน Markdown string หรือ None ถ้าล้มเหลว"""


# ── Tier 1: httpx ปกติ ────────────────────────────────────────────

class HttpxBasicStrategy(FetchStrategy):
    name = "Tier 1 (HTTPX)"

    async def fetch(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, timeout=10)
                if resp.status_code != 200:
                    return None
                md = trafilatura.extract(resp.text)
                return md if md and len(md) > 100 else None
        except Exception:
            return None


# ── Tier 2: httpx + Browser headers ──────────────────────────────


class HttpxHeadersStrategy(FetchStrategy):
    name = "Tier 2 (HTTPX + Headers)"

    async def fetch(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(
                headers=_BROWSER_HEADERS, follow_redirects=True
            ) as client:
                resp = await client.get(url, timeout=15)
                if resp.status_code != 200:
                    return None
                md = trafilatura.extract(resp.text)
                if not md or len(md) <= 100:
                    return None
                if any(t in md for t in _CLOUDFLARE_TELLS):
                    return None
                return md
        except Exception:
            return None


# ── Tier 3: Playwright — ใช้ core/browser (ไม่ duplicate logic) ──

class PlaywrightStrategy(FetchStrategy):
    """
    ใช้ core.browser.fetch_html_playwright แทน sync playwright ตรง ๆ
    เพราะ core/browser เป็น single source of truth สำหรับ browser fetch
    """
    name = "Tier 3 (Playwright)"

    async def fetch(self, url: str) -> str | None:
        try:
            from backend.core.browser import fetch_html_playwright
            # wait_until="domcontentloaded" ใช้ wait_tag="body" แทน
            html = await fetch_html_playwright(url, wait_tag="body", wait_ms=2_000)
            md   = trafilatura.extract(html)
            return md if md else None
        except Exception:
            return None


# ── FetcherService — orchestrates strategies ─────────────────────
# GRASP Controller: ตัดสินใจว่าจะเรียก strategy ไหน

class FetcherService:
    """
    ลองแต่ละ strategy ตามลำดับ — หยุดทันทีเมื่อสำเร็จ
    SOLID O: เพิ่ม strategy ใหม่โดยส่ง list ที่ยาวขึ้น
    """

    def __init__(self, strategies: list[FetchStrategy] | None = None) -> None:
        self._strategies: list[FetchStrategy] = strategies or [
            HttpxBasicStrategy(),
            HttpxHeadersStrategy(),
            PlaywrightStrategy(),
        ]

    async def fetch_markdown(self, url: str) -> tuple[str, str] | tuple[None, None]:
        """
        Returns (markdown_content, method_name) หรือ (None, None) ถ้าทุก tier ล้มเหลว
        """
        for strategy in self._strategies:
            print(f"  [{strategy.name}] กำลังดึง: {url}")
            result = await strategy.fetch(url)
            if result:
                print(f"  ✅ สำเร็จด้วย {strategy.name}")
                return result, strategy.name
            print(f"  ❌ {strategy.name} ล้มเหลว")
        return None, None


# ── DI factory ────────────────────────────────────────────────────

def get_fetcher_service() -> FetcherService:
    return FetcherService()