import sys
import httpx
import trafilatura
import asyncio
import re
import os
import time
import json
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# ใช้ Playwright ที่มีอยู่แล้ว หรือสร้างขึ้นมาเพื่อ fallback (Tier 2)
from playwright.sync_api import sync_playwright

_pw_executor = ThreadPoolExecutor(max_workers=2)

def _sync_fetch_playwright(url: str) -> str:
    """รัน Playwright แบบ sync ใน thread แยก — ไม่ขึ้นกับ event loop"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                html = page.content()
                return html
            finally:
                page.close()
                browser.close()
    except Exception as e:
        print(f"Playwright error for {url}: {e}")
        return ""

async def get_page_source_async(url: str) -> str:
    """ส่งงานไปรันใน thread pool — async-safe บน Windows + uvicorn"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _pw_executor,
        _sync_fetch_playwright,
        url
    )

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

# ── helper: upgrade registry พร้อม log เหตุผล
def _upgrade_registry(domain: str, tier: int):
    old = SITE_REGISTRY.get(domain, 1)
    if old != tier:
        SITE_REGISTRY[domain] = tier
        SITE_REGISTRY[f"{domain}.__reason__"] = f"auto-upgraded from {old} at {time.strftime('%Y-%m-%d')}"
        save_registry(SITE_REGISTRY)

# ── helper: นับ success เพื่อ upgrade เฉพาะถ้า tier2 ชนะสม่ำเสมอ
_success_counter: dict[str, dict] = {}

def _record_success(domain: str, tier: int):
    c = _success_counter.setdefault(domain, {"tier": tier, "count": 0})
    c["count"] += 1
    # upgrade ถ้า tier2 ชนะ 3 ครั้งติดต่อกัน
    if c["count"] >= 3 and c["tier"] == tier:
        _upgrade_registry(domain, tier)
        _success_counter.pop(domain)

# 4. In-memory content cache
_content_cache: dict[str, tuple[str, float]] = {}  # url -> (text, timestamp)
CACHE_TTL = 3600  # 1 hour

HEADERS_FULL = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
}

async def fetch_tier1(url: str) -> tuple[str, str]:
    """คืน (text, failure_reason)"""
    async with _sem:
        async with httpx.AsyncClient(
            timeout=8, follow_redirects=True, http2=True
        ) as client:
            try:
                r = await client.get(url, headers=HEADERS_FULL)
                r.raise_for_status()
            except HTTPStatusError as e:
                code = e.response.status_code
                reason = (
                    "blocked"     if code in (401, 403) else
                    "rate_limit"  if code == 429        else
                    "server_error"
                )
                print(f"Tier 1 HTTP {code} for {url} → {reason}")
                return "", reason
            except Exception as e:
                print(f"Tier 1 network error for {url}: {e}")
                return "", "network_error"
    
    text = trafilatura.extract(
        r.text,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    return (text or ""), "ok"

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
        text, reason = await fetch_tier1(url)

        if not text or len(text) < 200:
            if reason == "blocked":
                print(f"[{domain}] Blocked → upgrading to Tier 2 permanently")
                _upgrade_registry(domain, 2)
                text = await fetch_tier2(url)

            elif reason == "rate_limit":
                print(f"[{domain}] Rate limited → waiting 5s and retry")
                await asyncio.sleep(5)
                text, _ = await fetch_tier1(url)

            elif reason in ("network_error", "server_error", "ok"):
                print(f"[{domain}] Short/error ({reason}) → trying Tier 2")
                text = await fetch_tier2(url)
                if text and len(text) >= 200:
                    _record_success(domain, tier=2)

    elif tier == 2:
        text = await fetch_tier2(url)
        
    if not text or len(text) < 200:
        print(f"[{domain}] All tiers short → Tier 3 (Jina)")
        text = await fetch_tier3(url)
        if text and len(text) >= 200:
            _upgrade_registry(domain, 3)

    # Cache result
    if text:
        _content_cache[url] = (text, time.time())
    return text

# 3. Separate Thai and English phrase cutting logic
CUT_PHRASES_TH = [
    "ข่าวที่เกี่ยวข้อง",
    "อ่านเพิ่มเติม", 
    "ติดตามเรา",
    "แท็ก",
    "อ้างอิง",
    "RELATED POSTS",
    "MOST READ",
    "Print Friendly"
]

CUT_PHRASES_EN = [
    "related:", "tags:", "read more:", "advertisement",
    "related posts",
    "most read",
]

def prepare_for_llm(text: str, max_chars: int = 10000) -> str:
    # 1. ยุบ whitespace ซ้ำ
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    
    # 2. ตัด section ท้าย — หา cut point ที่ใกล้ที่สุดหลัง char 500
    cut_at = len(text)

    for phrase in CUT_PHRASES_TH:
        idx = text.find(phrase)
        if 500 < idx < cut_at:
            cut_at = idx

    lower = text.lower()
    for phrase in CUT_PHRASES_EN:
        idx = lower.find(phrase)
        if 500 < idx < cut_at:
            cut_at = idx

    text = text[:cut_at]
    
    # 3. cap ความยาว
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

async def collect_markdown_with_jina(url: str, output_dir: str = "collected_md") -> str:
    """Async wrapper keeping old name for backward compatibility"""
    # Simply await the async version.
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
                
    asyncio.run(main())
