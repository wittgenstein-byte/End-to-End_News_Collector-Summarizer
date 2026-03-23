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

from backend.config import settings
from backend.core.browser import fetch_html_playwright
from backend.core.constants import BROWSER_HEADERS
from backend.scrapers.registry import register_source
from backend.scrapers.helpers import (
    fetch_summary_and_image,
    find_image,
    find_url,
    make_article,
)

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
        summary, image_url, md = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "ThaiPBS", url, image_url, md))

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
        summary, image_url, md = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "Bangkok Post", url, image_url, md))
        if len(news_list) >= _LIMIT:
            break

    return news_list

# ── Matichon (ใช้ RSS Feed แทน Playwright) ───────────────────────

@register_source("Matichon", "https://www.matichon.co.th/news", "#2ecc71")
async def scrape_matichon() -> list[dict]:
    rss_url = "https://www.matichon.co.th/feed"
    import xml.etree.ElementTree as ET
    from html import unescape
    import re

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(rss_url, headers=BROWSER_HEADERS, timeout=10)

    root = ET.fromstring(resp.text)
    news_list = []

    for item in root.findall(".//item")[:_LIMIT]:
        title = unescape(item.findtext("title", "").strip())
        url   = item.findtext("link", "").strip()

        raw_desc = item.findtext("description", "")
        summary  = unescape(re.sub(r"<[^>]+>", "", raw_desc)).strip()

        # ── ดึงรูป (เพิ่ม fallback หลายชั้น) ──────────────────────
        image_url = ""

        # 1. media:content namespace
        media = item.find("{http://search.yahoo.com/mrss/}content")
        if media is not None:
            image_url = media.get("url", "")

        # 2. enclosure tag
        if not image_url:
            enclosure = item.find("enclosure")
            if enclosure is not None:
                image_url = enclosure.get("url", "")

        # 3. <img src> ใน description
        if not image_url:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_desc)
            if img_match:
                image_url = img_match.group(1)

        # 4. fallback ดึง og:image จาก article page
        if not image_url and url:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    r = await client.get(url, headers=BROWSER_HEADERS, timeout=5)
                s = BeautifulSoup(r.text, "html.parser")
                og = s.find("meta", property="og:image")
                if og:
                    image_url = og.get("content", "")
            except Exception:
                pass
        # ───────────────────────────────────────────────────────────

        if not title:
            continue

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
        summary, image_url, md = await fetch_summary_and_image(url, selectors, base)
        news_list.append(make_article(title, summary, "101 World", url, image_url, md))

    return news_list

# ── The Standard ─────────────────────────────────────────────────

@register_source("The Standard", "https://thestandard.co", "#e67e22")
async def scrape_thestandard() -> list[dict]:
    base = "https://thestandard.co"
    rss_url = "https://thestandard.co/feed"
    import xml.etree.ElementTree as ET
    from html import unescape
    import re

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(rss_url, headers=BROWSER_HEADERS, timeout=10)

    root = ET.fromstring(resp.text)
    news_list = []

    

    for item in root.findall(".//item")[:_LIMIT]:
        title = unescape(item.findtext("title", "").strip())
        url   = item.findtext("link", "").strip()

        raw_desc = item.findtext("description", "")
        summary  = unescape(re.sub(r"<[^>]+>", "", raw_desc)).strip()

        # ── ดึงรูป ──────────────────────────────────────────────
        image_url = ""

        # 1. media:content namespace
        media = item.find("{http://search.yahoo.com/mrss/}content")
        if media is not None:
            image_url = media.get("url", "")

        # 2. enclosure tag
        if not image_url:
            enclosure = item.find("enclosure")
            if enclosure is not None:
                image_url = enclosure.get("url", "")

        # 3. parse <img>  BeautifulSoup
        if not image_url:
            desc_soup = BeautifulSoup(raw_desc, "html.parser")
            image_url = find_image(desc_soup, base)

        # 4. content:encoded (feed)
        if not image_url:
            encoded = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            if encoded is not None and encoded.text:
                encoded_soup = BeautifulSoup(encoded.text, "html.parser")
                image_url = find_image(encoded_soup, base)

        # 5. fallback �ҡ article page
        if not image_url and url:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    r = await client.get(url, headers=BROWSER_HEADERS, timeout=5)
                s = BeautifulSoup(r.text, "html.parser")
                image_url = find_image(s, base)
            except Exception:
                pass
        if not title:
            continue

        news_list.append(make_article(title, summary, "The Standard", url, image_url))

    return news_list


