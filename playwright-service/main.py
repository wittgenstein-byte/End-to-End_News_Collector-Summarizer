from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from playwright.async_api import async_playwright
# No external dependencies on backend package
import uvicorn

app = FastAPI(title="Playwright Service")

# Using the same user agent as the main app
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/scrape")
async def scrape(
    url: str = Query(..., description="URL to scrape"),
    wait_tag: Optional[str] = Query("body", description="CSS selector to wait for"),
    wait_ms: int = Query(2000, description="Milliseconds to wait after tag appears")
):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            
            try:
                # wait_until="domcontentloaded" is faster, and we rely on wait_tag
                await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            except Exception as e:
                print(f"Goto timeout or error: {e}")
                # We still try to get the content even if goto times out completely
                pass
            
            if wait_tag:
                try:
                    await page.wait_for_selector(wait_tag, timeout=5_000)
                except Exception as e:
                    print(f"Wait_tag '{wait_tag}' error: {e}")
                    pass
            
            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)
                
            html = await page.content()
            await browser.close()
            return {"html": html}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001)
