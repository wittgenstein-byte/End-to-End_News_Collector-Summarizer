"""
scrapers/helpers.py
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

from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from config import settings
from core.constants import BROWSER_HEADERS

# คำที่บ่งว่า src นั้นไม่ใช่รูปข่าวจริง
_IMAGE_SKIP_KEYWORDS = frozenset(
    ["logo", "icon", "avatar", "ads", "banner", "pixel"]
)


# ── Image extraction ──────────────────────────────────────────────

def find_image(soup: BeautifulSoup, base_url: str) -> str:
    """
    หารูป og:image ก่อน ถ้าไม่มีค่อยหา img แรกที่ไม่ใช่ icon/logo
    """
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]

    for img in soup.find_all("img", src=True):
        src: str = img["src"]
        if len(src) < 10:
            continue
        if any(k in src.lower() for k in _IMAGE_SKIP_KEYWORDS):
            continue
        if src.startswith("http"):
            return src
        if src.startswith("/"):
            return base_url.rstrip("/") + src
    return ""


# ── URL extraction ────────────────────────────────────────────────

def find_url(tag, base_url: str) -> str:
    """
    หา href ที่ใกล้ที่สุดจาก tag — ลองหลาย strategy ตามลำดับ
    """
    a = (
        tag.find("a")
        or tag.find_parent("a")
        or tag.find_next_sibling("a")
    )
    if not a:
        parent = tag.find_parent(["div", "article", "li"])
        if parent:
            a = parent.find("a")

    if not a or not a.get("href"):
        return ""

    href: str = a["href"]
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return base_url.rstrip("/") + href
    return ""


# ── Article builder ───────────────────────────────────────────────

def make_article(
    title:     str,
    summary:   str,
    source:    str,
    url:       str,
    image_url: str = "",
) -> dict:
    return {
        "title":      title.strip(),
        "summary":    summary.strip() if summary else "(ไม่มีเนื้อหา)",
        "source":     source,
        "url":        url,
        "image_url":  image_url,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Article detail fetcher ────────────────────────────────────────

async def fetch_summary_and_image(
    url:               str,
    content_selectors: list[str],
    base_url:          str,
) -> tuple[str, str]:
    """
    ดึงหน้าข่าวจริง → extract summary + image_url
    คืน ("", "") ถ้า url ไม่ถูกต้องหรือ network ล้มเหลว
    """
    if not url or not url.startswith("http"):
        return "", ""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers=BROWSER_HEADERS, timeout=10)

        soup      = BeautifulSoup(resp.text, "html.parser")
        image_url = find_image(soup, base_url)
        summary   = _extract_summary(soup, content_selectors)
        return summary, image_url

    except Exception:
        return "", ""


def _extract_summary(soup: BeautifulSoup, selectors: list[str]) -> str:
    """ลอง selector ตามลำดับ — คืน paragraph แรก ๆ รวมกัน"""
    n = getattr(settings, "summary_sentences", 3)   # fallback = 3
    for selector in selectors:
        container = soup.select_one(selector)
        if not container:
            continue
        paragraphs = [p.text.strip() for p in container.select("p") if p.text.strip()]
        if paragraphs:
            return ". ".join(paragraphs[:n])[:400]
    return ""