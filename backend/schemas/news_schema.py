"""
schemas/news_schema.py
─────────────────────────────────────────────────────────────────
SOLID  I — แยก schema ตาม use-case (request / response / internal)
           ไม่ยัดทุก field ไว้ใน model เดียว
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

# ── Category type ─────────────────────────────────────────────────

CategoryType = Literal[
    "politics", "economy", "technology", "health",
    "environment", "society", "sports", "entertainment", "world",
]
SentimentType = Literal["positive", "neutral", "negative"]


_BLOCKED_SSRF_HOSTS = frozenset({
    "localhost",
    "playwright",
    "mongodb",
    "obscura",
    "metadata.google.internal",
    "169.254.169.254",
})


def is_safe_public_url(raw_url: str) -> tuple[bool, str]:
    """Validate that a URL uses http/https and does not target private/internal/cloud-metadata addresses."""
    cleaned = (raw_url or "").strip()
    if not cleaned.startswith(("http://", "https://")):
        return False, "url ต้องขึ้นต้นด้วย http:// หรือ https://"

    try:
        parsed = urlparse(cleaned)
    except Exception:
        return False, "รูปแบบ URL ไม่ถูกต้อง"

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False, "URL ต้องระบุ hostname ที่ถูกต้อง"

    if hostname in _BLOCKED_SSRF_HOSTS or hostname.endswith((".local", ".internal")):
        return False, "ไม่อนุญาตให้เข้าถึงเครือข่ายภายใน (Internal/Private Host)"

    # Check if hostname is an IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, "ไม่อนุญาตให้เข้าถึง Private/Loopback/Metadata IP Address"
    except ValueError:
        pass

    return True, cleaned


class CollectRequest(BaseModel):
    url: str                        # รับ str ธรรมดา — พร้อมตรวจสอบ SSRF เบื้องต้น

    @field_validator("url")
    @classmethod
    def url_must_have_scheme(cls, v: str) -> str:
        ok, msg_or_url = is_safe_public_url(v)
        if not ok:
            raise ValueError(msg_or_url)
        return msg_or_url



# ── Internal / storage schemas ────────────────────────────────────

class ArticleRecord(BaseModel):
    """
    Article stored in data/news_data.json / MongoDB 'articles' collection.
    100% backward compatible with all existing 11,025 articles.
    """
    model_config = ConfigDict(extra="ignore")

    url: str
    title: str
    source: str
    fetched_at: str = ""
    summary: str = ""
    category: CategoryType | str | None = None
    story_id: str | None = None
    image_url: str = ""
    classification_method: str = ""

# ── LLM output schema ─────────────────────────────────────────────

class NewsSummary(BaseModel):
    """ผลลัพธ์จาก LLM summarizer"""
    title: str | None                = None
    source_url: str | None           = None
    published_at: str | None         = None
    language: str | None             = None
    summary: str | None              = None
    bullets: list[str]                  = []
    category: CategoryType | None    = None
    sentiment: SentimentType | None  = None
    keywords: list[str]                 = []
    provider: str | None             = None
    model: str | None                = None
    is_fallback: bool                = False


# ── Response schemas ──────────────────────────────────────────────

class CollectResponse(BaseModel):
    ok: bool
    path: str | None         = None
    summary: NewsSummary | None = None
    error: str | None        = None
    fetch_method: str | None = None


class NewsListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    updated: str
    news: list[dict]


class SourcesResponse(BaseModel):
    sources: dict[str, int]


class StatusResponse(BaseModel):
    status: str
    interval: str
    total: int
    time: str