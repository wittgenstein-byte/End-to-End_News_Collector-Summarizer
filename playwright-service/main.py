import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from playwright.async_api import Browser, Route, async_playwright

# --- Browser pool: เปิดครั้งเดียว ใช้ซ้ำ + จำกัด concurrency ป้องกัน RAM พุ่ง ---
browser_instance: Browser = None
playwright_instance = None
_SCRAPE_SEMAPHORE = asyncio.Semaphore(3)
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})

@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser_instance, playwright_instance
    playwright_instance = await async_playwright().start()
    browser_instance = await playwright_instance.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",  # สำคัญใน Docker (shared memory เล็ก)
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--mute-audio",
            "--no-first-run",
            "--js-flags=--max-old-space-size=512",
        ]
    )
    print("Browser started")
    yield
    await browser_instance.close()
    await playwright_instance.stop()
    print("Browser closed")

app = FastAPI(title="Playwright Service", lifespan=lifespan)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

async def _block_heavy_resources(route: Route) -> None:
    if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
    else:
        await route.continue_()

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/scrape")
async def scrape(
    url: str = Query(..., description="URL to scrape"),
    wait_tag: str | None = Query("body", description="CSS selector to wait for"),
    wait_ms: int = Query(2000, description="Milliseconds to wait after tag appears")
):
    async with _SCRAPE_SEMAPHORE:
        context = None
        page = None
        try:
            context = await browser_instance.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            await page.route("**/*", _block_heavy_resources)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            except Exception as e:
                print(f"Goto timeout or error: {e}")

            if wait_tag:
                try:
                    await page.wait_for_selector(wait_tag, timeout=5_000)
                except Exception as e:
                    print(f"Wait_tag '{wait_tag}' error: {e}")

            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)

            html = await page.content()
            return {"html": html}

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            # ปิด context เสมอ ไม่ว่าจะ error หรือไม่
            if page:
                await page.close()
            if context:
                await context.close()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001)