"""
─────────────────────────────────────────────────────────────────
SOLID  S — HTML parsing utilities เท่านั้น
           ไม่รู้จัก source ใด ๆ ไม่เก็บ state
GRASP  Information Expert — รู้วิธี extract ข้อมูลจาก BeautifulSoup

ทำไมแยกออกจาก fetcher_service?
  fetcher_service → HTML → Trafilatura → Markdown  (LLM pipeline)
  helpers         → HTML → BeautifulSoup → structured dict (news list)
  คนละ output format — ไม่ควรรวมกัน
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup, Tag

from backend.config import settings
from backend.core.http_cache import http_cache
from backend.services.classifier_service import classify_article

# คำที่บ่งว่า src นั้นไม่ใช่รูปข่าวจริง
_IMAGE_SKIP_KEYWORDS = frozenset(["logo", "icon", "avatar", "ads", "banner", "pixel"])

# ── Image extraction ──────────────────────────────────────────────

def find_image(soup: BeautifulSoup, base_url: str) -> str:
    """
    หารูป og:image ก่อน ถ้าไม่มีค่อยหา img แรกที่ไม่ใช่ icon/logo
    """
    og = soup.find("meta", property="og:image")
    if not og:
        og = soup.find("meta", property="og:image:secure_url")
    if not og:
        og = soup.find("meta", attrs={"name": "twitter:image"})
    if og and og.get("content"):
        content_val = og["content"]
        content_str = content_val[0] if isinstance(content_val, list) else str(content_val)
        return _abs_url(content_str, base_url)

    for img in soup.find_all("img"):
        src = _pick_img_url(img)
        if not src or len(src) < 10:
            continue
        if any(k in src.lower() for k in _IMAGE_SKIP_KEYWORDS):
            continue
        return _abs_url(src, base_url)
    return ""


def _pick_img_url(img: Tag) -> str:
    for key in ("src", "data-src", "data-lazy-src", "data-original"):
        val = img.get(key)
        if val:
            return val[0] if isinstance(val, list) else str(val)
    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        srcset_str = srcset[0] if isinstance(srcset, list) else str(srcset)
        return srcset_str.split(",")[0].strip().split(" ")[0]
    return ""


def _abs_url(url: str, base_url: str) -> str:
    if url.startswith("http"):
        return url
    return urljoin(base_url.rstrip("/") + "/", url)

# ── URL extraction ────────────────────────────────────────────────

def find_url(tag, base_url: str) -> str:
    """
    หา href ที่ใกล้ที่สุดจาก tag — ลองหลาย strategy ตามลำดับ
    """
    a = tag.find("a") or tag.find_parent("a") or tag.find_next_sibling("a")
    if not a:
        parent = tag.find_parent(["div", "article", "li"])
        if parent:
            a = parent.find("a")

    if not a or not a.get("href"):
        return ""

    raw_href = a["href"]
    href: str = raw_href[0] if isinstance(raw_href, list) else str(raw_href)
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return base_url.rstrip("/") + href
    return ""


# ── Article builder ───────────────────────────────────────────────

def make_article(
    title: str,
    summary: str,
    source: str,
    url: str,
    image_url: str = "",
    md: str = "",
) -> dict:
    """
    สร้าง article dict พร้อม category ที่จำแนกอัตโนมัติ
    classifier_service ทำงานใน <1ms ไม่ต้องรอ
    """
    # ถ้าดึง md ไม่ได้ ให้ใช้ summary แทน
    content_for_classification = md if md else summary
    category, method = classify_article(title, content_for_classification, url=url)
    return {
        "title": title.strip(),
        "summary": summary.strip() if summary else "(ไม่มีเนื้อหา)",
        "source": source,
        "url": url,
        "image_url": image_url,
        "category": category,
        "classification_method": method,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Article detail fetcher ────────────────────────────────────────

async def fetch_summary_and_image(
    url: str,
    content_selectors: list[str],
    base_url: str,
) -> tuple[str, str, str]:
    """
    ดึงหน้าข่าวจริง → extract summary + image_url + full_markdown
    คืน ("", "", "") ถ้า url ไม่ถูกต้องหรือ network ล้มเหลว
    """
    if not url or not url.startswith("http"):
        return "", "", ""
    try:
        text, _ = await http_cache.fetch(url, timeout=10)
        if not text:
            return "", "", ""

        soup = BeautifulSoup(text, "html.parser")
        image_url = find_image(soup, base_url)
        summary = _extract_summary(soup, content_selectors)
        md = trafilatura.extract(text) or ""
        return summary, image_url, md

    except Exception:
        return "", "", ""

def _extract_summary(soup: BeautifulSoup, selectors: list[str]) -> str:
    """ลอง selector ตามลำดับ — คืน paragraph แรก ๆ รวมกัน"""
    n = getattr(settings, "summary_sentences", 3)  # fallback = 3
    for selector in selectors:
        container = soup.select_one(selector)
        if not container:
            continue
        paragraphs = [p.text.strip() for p in container.select("p") if p.text.strip()]
        if paragraphs:
            return ". ".join(paragraphs[:n])[:400]
    return ""


# ── RSS Feed Parsing ───────────────────────────────────────────────

def _parse_rss_root(xml_text: str) -> ET.Element:
    """
    Parse RSS defensively because some feeds append trailing junk after </rss>.
    """
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        end_index = xml_text.lower().rfind("</rss>")
        if end_index == -1:
            raise
        return ET.fromstring(xml_text[: end_index + len("</rss>")])


def parse_rss_items(
    xml_text: str,
    source_name: str,
    base_url: str = "",
    limit: int = 10,
) -> list[dict]:
    """
    Parse RSS feed XML into standard article dicts.
    Extracts image strictly from RSS XML fields (media:content, enclosure,
    description <img>, content:encoded <img>) without external HTTP calls.
    """
    root = _parse_rss_root(xml_text)
    news_list = []

    for item in root.findall(".//item")[:limit]:
        title = unescape(item.findtext("title", "").strip())
        url = item.findtext("link", "").strip()

        raw_desc = item.findtext("description", "")
        summary = unescape(re.sub(r"<[^>]+>", "", raw_desc)).strip()

        # ── Extract Image from RSS XML ────────────────────────────────────
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

        # 3. <img> in description tag
        if not image_url and raw_desc:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_desc)
            if img_match:
                image_url = img_match.group(1)

        # 4. <img> in content:encoded namespace
        if not image_url:
            encoded = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            if encoded is not None and encoded.text:
                img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', encoded.text)
                if img_match:
                    image_url = img_match.group(1)

        if image_url and base_url:
            image_url = _abs_url(image_url, base_url)

        if not title:
            continue

        news_list.append(make_article(title, summary, source_name, url, image_url))

    return news_list


