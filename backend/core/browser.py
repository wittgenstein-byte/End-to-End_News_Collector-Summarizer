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

import httpx

from backend.config import settings

# ── Async wrapper ─────────────────────────────────────────────────

async def fetch_html_playwright(
    url: str,
    *,
    wait_tag: str = "h2",
    wait_ms: int  = 2_000,
) -> str:
    """
    Async entry point — เรียกได้จาก coroutine โดยตรง
    ส่ง URL ไปให้ Playwright service ถ้าล้มเหลวจะ fallback ไปใช้ local Playwright
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                settings.playwright_service_url,
                params={"url": url, "wait_tag": wait_tag, "wait_ms": wait_ms}
            )
            resp.raise_for_status()
            data = resp.json()
            html = data.get("html", "")
            if html:
                return html
    except Exception:
        pass

    # Fallback to local Playwright
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if wait_tag:
                try:
                    await page.wait_for_selector(wait_tag, timeout=wait_ms)
                except Exception:
                    pass
            elif wait_ms > 0:
                await page.wait_for_timeout(wait_ms)
            html = await page.content()
            await browser.close()
            return html
    except Exception as e:
        print(f"Error in Playwright fetch for {url}: {e}")
        return ""