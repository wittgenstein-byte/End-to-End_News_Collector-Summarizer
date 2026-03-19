"""
core/browser.py
─────────────────────────────────────────────────────────────────
SOLID  S — ดึง raw HTML ด้วย browser เท่านั้น
           ไม่แปลง ไม่ parse — แค่ส่ง HTML กลับ
SOLID  O — ตั้ง wait_tag / wait_ms ได้ → ขยาย behavior โดยไม่แก้ core
GRASP  Pure Fabrication — แยกออกมาเพื่อ reuse ระหว่าง:
         • services/fetcher_service.py (PlaywrightStrategy)
         • scrapers/helpers.py (get_page_source_async)

ทำไมต้องแยก get_page_source ออกจาก fetcher_service?
  fetcher_service  → ดึง HTML แล้วแปลงเป็น Markdown ทันที (Trafilatura)
  core/browser     → ดึง raw HTML เพื่อให้ BeautifulSoup parse ต่อ
  คนละ output → ไม่ merge กัน แต่ share Playwright setup เหมือนกัน

เหตุผลที่ใช้ asyncio.to_thread แทน ThreadPoolExecutor:
  - asyncio.to_thread เป็น stdlib ตั้งแต่ Python 3.9+
  - ไม่ต้อง manage executor lifetime เอง
  - ไม่ต้อง loop.run_in_executor (deprecated pattern)
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio

from core.constants import BROWSER_HEADERS


# ── Sync implementation (รันใน thread pool) ──────────────────────

def _fetch_html_sync(url: str, wait_tag: str, wait_ms: int) -> str:
    """
    Playwright sync API — ต้องรันใน thread แยก (ไม่ใช่ event loop)
    wait_tag : CSS selector ที่รอให้โหลด  (เช่น "h2", "article")
    wait_ms  : milliseconds หลัง wait_tag ปรากฏ
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page(user_agent=BROWSER_HEADERS["User-Agent"])
        page.goto(url, timeout=30_000)
        try:
            page.wait_for_selector(wait_tag, timeout=10_000)
        except Exception:
            pass                            # บางหน้าไม่มี selector นั้น — ไม่ error
        page.wait_for_timeout(wait_ms)
        html = page.content()
        browser.close()
    return html


# ── Async wrapper ─────────────────────────────────────────────────

async def fetch_html_playwright(
    url: str,
    *,
    wait_tag: str = "h2",
    wait_ms: int  = 2_000,
) -> str:
    """
    Async entry point — เรียกได้จาก coroutine โดยตรง
    บล็อก thread แยก ไม่บล็อก event loop
    """
    return await asyncio.to_thread(_fetch_html_sync, url, wait_tag, wait_ms)