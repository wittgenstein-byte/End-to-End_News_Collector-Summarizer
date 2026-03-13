import asyncio
import json
import time
import os
import httpx
from datetime import datetime
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Callable, Coroutine, Any
from playwright.sync_api import sync_playwright

from concurrent.futures import ThreadPoolExecutor
_executor = ThreadPoolExecutor(max_workers=2)

# เพิ่ม wrapper async ตรงนี้ (ใต้ get_page_source เดิม)
async def get_page_source_async(url: str, wait_tag: str = "h2", wait_ms: int = 2000) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        lambda: get_page_source(url, wait_tag, wait_ms)
    )

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

NAV_KEYWORDS = {
    "NEWS", "LIFE", "SUSTAINABILITY", "LEARNING", "GURU", "VIDEO",
    "PHOTOS", "PODCAST", "VISUAL STORIES", "EVENTS", "SPECIAL FEATURES",
    "DIGITAL PRODUCTS & SERVICES", "OTHER", "E-BOOK"
}

INTERVAL_MINUTES        = 15
MAX_ARTICLES_PER_SOURCE = 10
SUMMARY_SENTENCES       = 3
OUTPUT_FILE             = "news_output.json"
SEEN_FILE               = "seen_urls.json"


# ─────────────────────────────────────────────
# Seen URL tracker
# ─────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)


# ─────────────────────────────────────────────
# Output file
# ─────────────────────────────────────────────

def load_all_news() -> list[dict]:
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_all_news(news_list: list[dict]) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def get_page_source(url: str, wait_tag: str = "h2", wait_ms: int = 2000) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, timeout=30000)
        try:
            page.wait_for_selector(wait_tag, timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(wait_ms)
        html = page.content()
        browser.close()
    return html


def find_image(soup, base: str) -> str:
    """หา og:image หรือ img แรกที่ไม่ใช่ icon"""
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if any(k in src.lower() for k in ["logo", "icon", "avatar", "ads", "banner", "pixel"]):
            continue
        if len(src) < 10:
            continue
        if src.startswith("http"):
            return src
        if src.startswith("/"):
            return base + src
    return ""


async def fetch_summary_and_image(url: str, content_selectors: list[str], base: str) -> tuple[str, str]:
    """ดึง summary + image_url จากหน้าข่าวจริง"""
    if not url or not url.startswith("http"):
        return "", ""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        image_url = find_image(soup, base)
        summary   = ""
        for selector in content_selectors:
            container = soup.select_one(selector)
            if container:
                paragraphs = [p.text.strip() for p in container.select("p") if p.text.strip()]
                summary = ". ".join(paragraphs[:SUMMARY_SENTENCES])[:400]
                break
        return summary, image_url
    except Exception:
        return "", ""


def find_url(tag, base: str) -> str:
    a = tag.find("a") or tag.find_parent("a") or tag.find_next_sibling("a")
    if not a:
        parent = tag.find_parent(["div", "article", "li"])
        if parent:
            a = parent.find("a")
    if not a or not a.get("href"):
        return ""
    href = a["href"]
    if href.startswith("http"):
        return href
    return base + href if href.startswith("/") else ""


def make_article(title: str, summary: str, source: str, url: str, image_url: str = "") -> dict:
    return {
        "title":      title.strip(),
        "summary":    summary.strip() if summary else "(ไม่มีเนื้อหา)",
        "source":     source,
        "url":        url,
        "image_url":  image_url,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─────────────────────────────────────────────
# Scrapers
# ─────────────────────────────────────────────

async def scrape_thaipbs() -> list[dict]:
    base      = "https://www.thaipbs.or.th"
    selectors = ["div.content-detail", "div.article-content", "div.detail", "article"]
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}/news", headers=HEADERS, timeout=10)
    
    soup      = BeautifulSoup(resp.text, "html.parser")
    news_list = []
    
    for h in soup.select("h3")[:MAX_ARTICLES_PER_SOURCE]:
        title = h.text.strip()
        if not title:
            continue
        url                = find_url(h, base)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "ThaiPBS", url, image_url))
    return news_list


async def scrape_bangkokpost() -> list[dict]:
    base      = "https://www.bangkokpost.com"
    selectors = ["div.article-content", "div.story-body", "article"]
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}/thailand/general", headers=HEADERS, timeout=10)
        
    soup      = BeautifulSoup(resp.text, "html.parser")
    news_list = []
    for h in soup.select("h3"):
        title = h.text.strip()
        if not title or h.get("class", []) != [] or title.upper() in NAV_KEYWORDS:
            continue
        url                = find_url(h, base)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "Bangkok Post", url, image_url))
        if len(news_list) >= MAX_ARTICLES_PER_SOURCE:
            break
    return news_list


async def scrape_matichon() -> list[dict]:
    base      = "https://www.matichon.co.th"
    selectors = ["div.entry-content", "div.article-content", "div.content", "article"]
    html      = await get_page_source_async(f"{base}/news")
    soup      = BeautifulSoup(html, "html.parser")
    news_list = []
    for h in soup.select("h2, h3")[:MAX_ARTICLES_PER_SOURCE]:
        title = h.text.strip()
        if not title or len(title) <= 10:
            continue
        url                = find_url(h, base)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "Matichon", url, image_url))
    return news_list


async def scrape_101world() -> list[dict]:
    base      = "https://www.the101.world"
    selectors = ["div.entry-content", "div.article-body", "div.post-content", "article"]
    html      = await get_page_source_async(base)
    soup      = BeautifulSoup(html, "html.parser")
    news_list = []
    for h in soup.select("h2.entry-title")[:MAX_ARTICLES_PER_SOURCE]:
        title = h.text.strip()
        if not title:
            continue
        url                = find_url(h, base)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "101 World", url, image_url))
    return news_list


# ─────────────────────────────────────────────
# Source registry
# ─────────────────────────────────────────────

@dataclass
class NewsSource:
    name: str
    url: str
    scrape_fn: Callable[[], Coroutine[Any, Any, list[dict]]]


SOURCES = [
    NewsSource("ThaiPBS",      "https://www.thaipbs.or.th/news",              scrape_thaipbs),
    NewsSource("Bangkok Post", "https://www.bangkokpost.com/thailand/general", scrape_bangkokpost),
    NewsSource("Matichon",     "https://www.matichon.co.th/news",              scrape_matichon),
    NewsSource("101 World",    "https://www.the101.world",                     scrape_101world),
]


# ─────────────────────────────────────────────
# One scrape cycle
# ─────────────────────────────────────────────

async def run_once(seen: set) -> tuple[list[dict], set]:
    new_articles = []
    for source in SOURCES:
        try:
            print(f"  ⏳ {source.name} ...")
            articles = await source.scrape_fn()
            fresh    = [a for a in articles if a["url"] and a["url"] not in seen]
            new_articles.extend(fresh)
            for a in fresh:
                seen.add(a["url"])
            status = "✅" if fresh else "—"
            print(f"  {status} {source.name}: {len(fresh)} ข่าวใหม่ (ทั้งหมด {len(articles)})")
        except Exception as e:
            print(f"  ❌ {source.name}: {e}")
    return new_articles, seen


# ─────────────────────────────────────────────
# Main loop (standalone)
# ─────────────────────────────────────────────

async def main():
    print("🚀 News scraper เริ่มทำงาน")
    print(f"   ดึงข่าวใหม่ทุก {INTERVAL_MINUTES} นาที | กด Ctrl+C เพื่อหยุด\n")

    seen      = load_seen()
    all_news  = load_all_news()
    round_num = 0

    while True:
        round_num += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'═' * 50}")
        print(f"🔄 รอบที่ {round_num} | {now}")
        print(f"{'═' * 50}")

        new_articles, seen = await run_once(seen)

        if new_articles:
            all_news.extend(new_articles)
            save_all_news(all_news)
            save_seen(seen)
            print(f"\n✨ ข่าวใหม่ {len(new_articles)} บทความ (รวมทั้งหมด {len(all_news)})")
        else:
            print("\n  ✓ ไม่มีข่าวใหม่รอบนี้")

        next_run = datetime.fromtimestamp(time.time() + INTERVAL_MINUTES * 60).strftime("%H:%M:%S")
        print(f"\n⏰ รอบถัดไป: {next_run} (อีก {INTERVAL_MINUTES} นาที)")

        try:
            await asyncio.sleep(INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            print("\n\n👋 หยุดการทำงาน")
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 หยุดการทำงาน (KeyboardInterrupt)")