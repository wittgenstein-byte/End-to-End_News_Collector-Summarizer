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

_BROWSER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;"
                       "q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
}

_CLOUDFLARE_TELLS = {"Just a moment", "Enable JavaScript"}


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


# ── Tier 3: Playwright (sync ใน thread pool) ─────────────────────

def _playwright_sync_fetch(url: str) -> str:
    """รันใน asyncio.to_thread เพราะ playwright sync API block"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_BROWSER_HEADERS["User-Agent"])
        page = context.new_page()
        # Reduce timeout and wait_for_timeout to speed up the process
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=8_000)
            page.wait_for_timeout(500)
        except Exception:
            # If it times out, we still try to get the content
            pass
        html = page.content()
        browser.close()
    return html


class PlaywrightStrategy(FetchStrategy):
    name = "Tier 3 (Playwright)"

    async def fetch(self, url: str) -> str | None:
        try:
            html = await asyncio.to_thread(_playwright_sync_fetch, url)
            md = trafilatura.extract(html)
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