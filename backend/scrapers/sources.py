"""
scrapers/sources.py
─────────────────────────────────────────────────────────────────
SOLID  O — เพิ่ม source ใหม่ได้โดยเพิ่ม function + @register_source
           ไม่ต้องแก้ helpers / registry / scraper_service
SOLID  S — แต่ละ function รับผิดชอบ source เดียว
GRASP  Low Coupling — ใช้แค่ registry + helpers ไม่รู้จัก service ใด ๆ

หมายเหตุ: import ไฟล์นี้จาก scrapers/__init__.py เพื่อ trigger
           @register_source decorator ก่อนที่ scraper_service จะใช้ SOURCES
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from backend.config import settings
from backend.core.browser import fetch_html_playwright
from backend.core.http_cache import http_cache
from backend.scrapers.helpers import (
    fetch_summary_and_image,
    find_url,
    make_article,
    parse_rss_items,
)
from backend.scrapers.registry import register_source

# ── Bangkok Post nav items ที่ไม่ใช่ข่าว ──────────────────────────
_NAV_KEYWORDS: frozenset[str] = frozenset({
    "NEWS", "LIFE", "SUSTAINABILITY", "LEARNING", "GURU", "VIDEO",
    "PHOTOS", "PODCAST", "VISUAL STORIES", "EVENTS", "SPECIAL FEATURES",
    "DIGITAL PRODUCTS & SERVICES", "OTHER", "E-BOOK",
})

_LIMIT = settings.max_articles_per_source   # อ่านจาก config ที่เดียว


# ── ThaiPBS ───────────────────────────────────────────────────────

@register_source("ThaiPBS", "https://www.thaipbs.or.th/news", "#e74c3c")
async def scrape_thaipbs() -> list[dict]:
    base      = "https://www.thaipbs.or.th"
    selectors = ["div.content-detail", "div.article-content", "div.detail", "article"]

    text, not_modified = await http_cache.fetch(f"{base}/news", timeout=10)
    if not_modified or not text:
        return []

    soup      = BeautifulSoup(text, "html.parser")
    news_list = []

    for h in soup.select("h3")[:_LIMIT]:
        title = h.text.strip()
        if not title:
            continue
        url                = find_url(h, base)
        summary, image_url, md = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "ThaiPBS", url, image_url, md))

    return news_list

# ── Bangkok Post ──────────────────────────────────────────────────

@register_source("Bangkok Post", "https://www.bangkokpost.com/thailand/general", "#3498db")
async def scrape_bangkokpost() -> list[dict]:
    base      = "https://www.bangkokpost.com"
    selectors = ["div.article-content", "div.story-body", "article"]

    text, not_modified = await http_cache.fetch(f"{base}/thailand/general", timeout=10)
    if not_modified or not text:
        return []

    soup      = BeautifulSoup(text, "html.parser")
    news_list = []

    for h in soup.select("h3"):
        title = h.text.strip()
        # กรอง: ต้องมี title, ไม่มี class พิเศษ, ไม่ใช่ nav item
        if not title or h.get("class") or title.upper() in _NAV_KEYWORDS:
            continue
        url                = find_url(h, base)
        summary, image_url, md = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "Bangkok Post", url, image_url, md))
        if len(news_list) >= _LIMIT:
            break

    return news_list

# ── Matichon (ใช้ RSS Feed แทน Playwright) ───────────────────────

@register_source("Matichon", "https://www.matichon.co.th/news", "#2ecc71")
async def scrape_matichon() -> list[dict]:
    rss_url = "https://www.matichon.co.th/feed"
    base = "https://www.matichon.co.th"
    try:
        text, not_modified = await http_cache.fetch(rss_url, timeout=10)
        if not_modified or not text:
            return []
        return parse_rss_items(text, "Matichon", base_url=base, limit=_LIMIT)
    except Exception:
        return []


# ── 101 World (RSS Feed พร้อม Playwright Fallback) ───────────────

@register_source("101 World", "https://www.the101.world", "#9b59b6")
async def scrape_101world() -> list[dict]:
    rss_url = "https://www.the101.world/feed/"
    base = "https://www.the101.world"
    try:
        text, not_modified = await http_cache.fetch(rss_url, timeout=10)
        if not_modified:
            return []
        if text:
            items = parse_rss_items(text, "101 World", base_url=base, limit=_LIMIT)
            if items:
                return items
    except Exception:
        pass

    # Fallback to Playwright if RSS fails
    try:
        selectors = ["div.entry-content", "div.article-body", "div.post-content", "article"]
        html = await fetch_html_playwright(base, wait_tag="h2.entry-title")
        soup = BeautifulSoup(html, "html.parser")
        news_list = []

        for h in soup.select("h2.entry-title")[:_LIMIT]:
            title = h.text.strip()
            if not title:
                continue
            url = find_url(h, base)
            summary, image_url, md = await fetch_summary_and_image(url, selectors, base)
            news_list.append(make_article(title, summary, "101 World", url, image_url, md))

        return news_list
    except Exception:
        return []


# ── The Standard ─────────────────────────────────────────────────

@register_source("The Standard", "https://thestandard.co", "#e67e22")
async def scrape_thestandard() -> list[dict]:
    rss_url = "https://thestandard.co/feed"
    base = "https://thestandard.co"
    try:
        text, not_modified = await http_cache.fetch(rss_url, timeout=10)
        if not_modified or not text:
            return []
        return parse_rss_items(text, "The Standard", base_url=base, limit=_LIMIT)
    except Exception:
        return []


# ── Khaosod ───────────────────────────────────────────────────────

@register_source("Khaosod", "https://www.khaosod.co.th", "#e74c3c")
async def scrape_khaosod() -> list[dict]:
    rss_url = "https://www.khaosod.co.th/feed"
    base = "https://www.khaosod.co.th"
    try:
        text, not_modified = await http_cache.fetch(rss_url, timeout=10)
        if not_modified or not text:
            return []
        items = parse_rss_items(text, "Khaosod", base_url=base, limit=_LIMIT * 2)
        # กรองข่าวภาษาอังกฤษ khaosodenglish.com ออกทั้งหมด
        return [
            item for item in items
            if "khaosodenglish.com" not in item.get("url", "").lower()
        ][:_LIMIT]
    except Exception:
        return []


# ── Thairath (ไทยรัฐ) ──────────────────────────────────────────────

@register_source("Thairath", "https://www.thairath.co.th", "#00b16a")
async def scrape_thairath() -> list[dict]:
    rss_url = "https://www.thairath.co.th/rss/news"
    base = "https://www.thairath.co.th"
    try:
        text, not_modified = await http_cache.fetch(rss_url, timeout=10)
        if not_modified or not text:
            return []
        return parse_rss_items(text, "Thairath", base_url=base, limit=_LIMIT)
    except Exception:
        return []


# ── Thai Post (ไทยโพสต์) ──────────────────────────────────────────

@register_source("Thai Post", "https://www.thaipost.net", "#d35400")
async def scrape_thaipost() -> list[dict]:
    rss_url = "https://www.thaipost.net/feed/"
    base = "https://www.thaipost.net"
    try:
        text, not_modified = await http_cache.fetch(rss_url, timeout=10)
        if not_modified or not text:
            return []
        return parse_rss_items(text, "Thai Post", base_url=base, limit=_LIMIT)
    except Exception:
        return []


# ── Daily News (เดลินิวส์) ────────────────────────────────────────

@register_source("Daily News", "https://www.dailynews.co.th", "#e74c3c")
async def scrape_dailynews() -> list[dict]:
    base = "https://www.dailynews.co.th"
    selectors = ["div.entry-content", "div.article-content", "article", "div.content-all"]
    try:
        text, not_modified = await http_cache.fetch(f"{base}/news/", timeout=10)
        if not_modified or not text:
            return []
        soup = BeautifulSoup(text, "html.parser")
        news_list = []
        seen = set()
        for h in soup.select("h3 a, .entry-title a, article h3, article a"):
            title = h.text.strip()
            url = find_url(h, base)
            if not title or len(title) < 15 or not url or url in seen or "/news/" not in url:
                continue
            seen.add(url)
            summary, image_url, md = await fetch_summary_and_image(url, selectors, base)
            news_list.append(make_article(title, summary, "Daily News", url, image_url, md))
            if len(news_list) >= _LIMIT:
                break
        return news_list
    except Exception:
        return []


# ── Komchadluek (คมชัดลึกออนไลน์) ──────────────────────────────────

@register_source("Komchadluek", "https://www.komchadluek.net", "#c0392b")
async def scrape_komchadluek() -> list[dict]:
    base = "https://www.komchadluek.net"
    selectors = ["div.article-body", "div.content-detail", "article"]
    try:
        html = await fetch_html_playwright(base, wait_tag="a", wait_ms=2000)
        soup = BeautifulSoup(html, "html.parser")
        news_list = []
        seen = set()
        for a in soup.find_all("a"):
            raw_href = a.get("href", "")
            href = raw_href[0] if isinstance(raw_href, list) else str(raw_href)
            title = a.text.strip()
            if not href or not title or len(title) < 15:
                continue
            if not any(x in href for x in ["/news/", "/general-news/", "/politics/", "/entertainment/"]):
                continue
            if not href.startswith("http"):
                href = base.rstrip("/") + "/" + href.lstrip("/")
            if href in seen:
                continue
            seen.add(href)
            summary, image_url, md = await fetch_summary_and_image(href, selectors, base)
            news_list.append(make_article(title, summary, "Komchadluek", href, image_url, md))
            if len(news_list) >= _LIMIT:
                break
        return news_list
    except Exception:
        return []


# ── Nation Online (เนชั่นออนไลน์) ──────────────────────────────────

@register_source("Nation Online", "https://www.nationtv.tv", "#16a085")
async def scrape_nationtv() -> list[dict]:
    base = "https://www.nationtv.tv"
    selectors = ["div.article-body", "div.content-detail", "article"]
    try:
        text, not_modified = await http_cache.fetch(f"{base}/news", timeout=10)
        if not_modified or not text:
            return []
        soup = BeautifulSoup(text, "html.parser")
        news_list = []
        seen = set()
        for a in soup.select('a[href*="/news/"]'):
            title = a.text.strip()
            raw_href = a.get("href", "")
            href = raw_href[0] if isinstance(raw_href, list) else str(raw_href)
            if not title or len(title) < 15 or not href:
                continue
            if not href.startswith("http"):
                href = base.rstrip("/") + "/" + href.lstrip("/")
            if href in seen:
                continue
            seen.add(href)
            summary, image_url, md = await fetch_summary_and_image(href, selectors, base)
            news_list.append(make_article(title, summary, "Nation Online", href, image_url, md))
            if len(news_list) >= _LIMIT:
                break
        return news_list
    except Exception:
        return []


# ── Bangkokbiznews (กรุงเทพธุรกิจ) ──────────────────────────────────

@register_source("Bangkokbiznews", "https://www.bangkokbiznews.com", "#1f3a93")
async def scrape_bangkokbiznews() -> list[dict]:
    base = "https://www.bangkokbiznews.com"
    selectors = ["div.article-body", "div.content-detail", "article"]
    try:
        text, not_modified = await http_cache.fetch(base, timeout=10)
        if not_modified or not text:
            return []
        soup = BeautifulSoup(text, "html.parser")
        news_list = []
        seen = set()
        for a in soup.select('a[href*="/business/"], a[href*="/finance/"], a[href*="/politics/"], a[href*="/tech/"], a[href*="/category/"]'):
            title = a.text.strip()
            raw_href = a.get("href", "")
            href = raw_href[0] if isinstance(raw_href, list) else str(raw_href)
            if not title or len(title) < 15 or not href:
                continue
            if not href.startswith("http"):
                href = base.rstrip("/") + "/" + href.lstrip("/")
            if href in seen:
                continue
            seen.add(href)
            summary, image_url, md = await fetch_summary_and_image(href, selectors, base)
            news_list.append(make_article(title, summary, "Bangkokbiznews", href, image_url, md))
            if len(news_list) >= _LIMIT:
                break
        return news_list
    except Exception:
        return []


