import httpx
import trafilatura
import asyncio
import re
import os
import time
import json
from pathlib import Path
from urllib.parse import urlparse

# ใช้ Playwright ที่มีอยู่แล้ว หรือสร้างขึ้นมาเพื่อ fallback (Tier 2)
from playwright.async_api import async_playwright

# 1. Shared browser instance for Playwright
_pw = None
_browser = None

async def get_browser():
    global _pw, _browser
    if _pw is None:
        _pw = await async_playwright().start()
    if _browser is None or not _browser.is_connected():
        _browser = await _pw.chromium.launch(headless=True)
    return _browser

async def get_page_source_async(url: str) -> str:
    """Fallback: use Playwright to render JS for Tier 2"""
    browser = await get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        html = await page.content()
        return html
    except Exception as e:
        print(f"Playwright error for {url}: {e}")
        return ""
    finally:
        await page.close()

_sem = asyncio.Semaphore(5)  # concurrent fetch

# 2. Persistent Site Registry
REGISTRY_FILE = "site_registry.json"

def load_registry() -> dict:
    if Path(REGISTRY_FILE).exists():
        try:
            return json.loads(Path(REGISTRY_FILE).read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_registry(registry: dict):
    Path(REGISTRY_FILE).write_text(json.dumps(registry, indent=2), encoding="utf-8")

SITE_REGISTRY = load_registry()

# 4. In-memory content cache
_content_cache: dict[str, tuple[str, float]] = {}  # url -> (text, timestamp)
CACHE_TTL = 3600  # 1 hour

async def fetch_tier1(url: str) -> str:
    async with _sem:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            try:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
            except Exception as e:
                print(f"Tier 1 request error for {url}: {e}")
                return ""
    
    text = trafilatura.extract(
        r.text,
        include_comments=False,
        include_tables=False,
        favor_precision=True,  # ตัด boilerplate ให้ aggressive กว่า
    )
    return text or ""

async def fetch_tier2(url: str) -> str:
    # ใช้ Playwright ที่มีอยู่แล้ว แต่แค่ยิงเมื่อ tier1 ล้มเหลว
    html = await get_page_source_async(url)
    text = trafilatura.extract(html, favor_precision=True)
    return text or ""

async def fetch_tier3(url: str) -> str:
    # เรียกเมื่อ tier1+2 ล้มเหลว หรือ site มี paywall
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"https://r.jina.ai/{url}")
            r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"Tier 3 request error for {url}: {e}")
        return ""

async def extract_content(url: str) -> str:
    # ตรวจ cache ก่อน
    if url in _content_cache:
        text, ts = _content_cache[url]
        if time.time() - ts < CACHE_TTL:
            print(f"[{url}] Serving from cache...")
            return text

    domain = urlparse(url).netloc.replace("www.", "")
    tier   = SITE_REGISTRY.get(domain, 1)  # default ลอง tier1 ก่อน

    text = ""
    print(f"[{domain}] Fetching {url} with Tier {tier}...")
    
    if tier <= 1:
        text = await fetch_tier1(url)

    if not text or len(text) < 200:
        if tier <= 1:
            print(f"[{domain}] Tier 1 failed or content too short. Falling back to Tier 2 (Playwright)...")
        text = await fetch_tier2(url)
        if text and len(text) >= 200:
            SITE_REGISTRY[domain] = 2  # จดจำว่าต้องใช้ tier2
            save_registry(SITE_REGISTRY)
        
    if not text or len(text) < 200:
        if tier <= 2:
            print(f"[{domain}] Tier 2 failed or content too short. Falling back to Tier 3 (Jina)...")
        text = await fetch_tier3(url)
        SITE_REGISTRY[domain] = 3
        save_registry(SITE_REGISTRY)

    # Cache result
    if text:
        _content_cache[url] = (text, time.time())
    return text

# 3. Separate Thai and English phrase cutting logic
CUT_PHRASES_TH = ["ข่าวที่เกี่ยวข้อง", "อ่านเพิ่มเติม", "ติดตามเรา", "แท็ก"]
CUT_PHRASES_EN = ["related:", "tags:", "read more:", "advertisement"]

def prepare_for_llm(text: str, max_chars: int = 2500) -> str:
    # 1. ยุบ whitespace ซ้ำ
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    
    # 2. ตัด section ท้าย 
    # Thai — ตรงตัว
    for phrase in CUT_PHRASES_TH:
        idx = text.find(phrase)
        if idx > 500:          # ถ้าอยู่ท้ายบทความจริงๆ ไม่ใช่ต้น
            text = text[:idx]
    
    # English — case-insensitive
    lower = text.lower()
    for phrase in CUT_PHRASES_EN:
        idx = lower.find(phrase)
        if idx > 500:
            text = text[:idx]
            lower = text.lower() # update lower for next iterations if cut
    
    # 3. cap ความยาว — 2500 chars ≈ 600 tokens ภาษาไทย
    return text.strip()[:max_chars]

async def collect_markdown_async(url: str, output_dir: str = "collected_md") -> str:
    """
    Fetch markdown content from a URL using a 3-tier fallback approach and save it as a .md file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    raw_text = await extract_content(url)
    if not raw_text:
        raise Exception("Failed to extract content from all 3 tiers.")
        
    final_text = prepare_for_llm(raw_text)

    # ดึง filename จาก url 
    parsed_url = urlparse(url)
    filename = parsed_url.path.strip("/").split("/")[-1]
    if not filename:
        filename = "index"
        
    if not filename.endswith(".md"):
        filename += ".md"

    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(final_text)

    return filepath

# Clean up playwright resources gracefully
async def close_playwright():
    global _browser, _pw
    if _browser:
        await _browser.close()
    if _pw:
        await _pw.stop()

async def collect_markdown_with_jina(url: str, output_dir: str = "collected_md") -> str:
    """Async wrapper keeping old name for backward compatibility"""
    # Simply await the async version. Do not close playwright early!
    return await collect_markdown_async(url, output_dir)

if __name__ == "__main__":
    async def main():
        url = input("Enter URL to collect .md file from: ").strip()

        if not url:
            print("Error: URL cannot be empty")
        else:
            try:
                filepath = await collect_markdown_with_jina(url)
                print(f"Successfully saved to: {filepath}")
            except Exception as e:
                print(f"Error: {e}")
            finally:
                await close_playwright() # only close here if running as CLI
                
    asyncio.run(main())
