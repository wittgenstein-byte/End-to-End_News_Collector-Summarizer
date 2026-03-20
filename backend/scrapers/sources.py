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

import httpx
from bs4 import BeautifulSoup

from config import settings
from core.browser import fetch_html_playwright
from core.constants import BROWSER_HEADERS
from scrapers.registry import register_source
from scrapers.helpers import fetch_summary_and_image, find_url, make_article

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

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(f"{base}/news", headers=BROWSER_HEADERS, timeout=10)

    soup      = BeautifulSoup(resp.text, "html.parser")
    news_list = []

    for h in soup.select("h3")[:_LIMIT]:
        title = h.text.strip()
        if not title:
            continue
        url                = find_url(h, base)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "ThaiPBS", url, image_url))

    return news_list


# ── Bangkok Post ──────────────────────────────────────────────────

@register_source("Bangkok Post", "https://www.bangkokpost.com/thailand/general", "#3498db")
async def scrape_bangkokpost() -> list[dict]:
    base      = "https://www.bangkokpost.com"
    selectors = ["div.article-content", "div.story-body", "article"]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(f"{base}/thailand/general", headers=BROWSER_HEADERS, timeout=10)

    soup      = BeautifulSoup(resp.text, "html.parser")
    news_list = []

    for h in soup.select("h3"):
        title = h.text.strip()
        # กรอง: ต้องมี title, ไม่มี class พิเศษ, ไม่ใช่ nav item
        if not title or h.get("class") or title.upper() in _NAV_KEYWORDS:
            continue
        url                = find_url(h, base)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "Bangkok Post", url, image_url))
        if len(news_list) >= _LIMIT:
            break

    return news_list


# ── Matichon (ต้องใช้ Playwright เพราะ JS-rendered) ───────────────
@register_source("Matichon", "https://www.matichon.co.th/politics", "#2ecc71")
async def scrape_matichon() -> list[dict]:
    base      = "https://www.matichon.co.th"
    selectors = ["div.entry-content", "div.article-content", "div.content", "article"]
    
    # ดึงจากหลาย section เพื่อให้ได้ข่าวหลากหลายและใหม่กว่า
    urls_to_scrape = [
        f"{base}/politics",
        f"{base}/news_and_report",
    ]
    
    all_headings = []
    for scrape_url in urls_to_scrape:
        html = await fetch_html_playwright(scrape_url, wait_tag="h2, h3")
        soup = BeautifulSoup(html, "html.parser")
        all_headings.extend(soup.select("h2, h3"))
    
    news_list = []
    seen_titles = set()
    
    for h in all_headings:
        if len(news_list) >= _LIMIT:
            break
        title = h.text.strip()
        if not title or len(title) <= 10 or title in seen_titles:
            continue
        url = find_url(h, base)
        if not url or not url.startswith(base):
            continue
        seen_titles.add(title)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "Matichon", url, image_url))
    
    return news_list


# ── 101 World (ต้องใช้ Playwright) ───────────────────────────────

@register_source("101 World", "https://www.the101.world", "#9b59b6")
async def scrape_101world() -> list[dict]:
    base      = "https://www.the101.world"
    selectors = ["div.entry-content", "div.article-body", "div.post-content", "article"]

    html      = await fetch_html_playwright(base, wait_tag="h2.entry-title")
    soup      = BeautifulSoup(html, "html.parser")
    news_list = []

    for h in soup.select("h2.entry-title")[:_LIMIT]:
        title = h.text.strip()
        if not title:
            continue
        url                = find_url(h, base)
        summary, image_url = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "101 World", url, image_url))

    return news_list