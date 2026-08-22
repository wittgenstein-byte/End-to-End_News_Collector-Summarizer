"""
schemas/news_schema.py
─────────────────────────────────────────────────────────────────
SOLID  I — แยก schema ตาม use-case (request / response / internal)
           ไม่ยัดทุก field ไว้ใน model เดียว
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

# ── Category type ─────────────────────────────────────────────────
 
CategoryType = Literal[
    "politics", "economy", "technology", "health",
    "environment", "society", "sports", "entertainment", "world",
]
SentimentType = Literal["positive", "neutral", "negative"]

# ── Request schemas ───────────────────────────────────────────────

class CollectRequest(BaseModel):
    url: str                        # รับ str ธรรมดา — validate ใน service

    @field_validator("url")
    @classmethod
    def url_must_have_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url ต้องขึ้นต้นด้วย http:// หรือ https://")
        return v.strip()


# ── Internal / storage schemas ────────────────────────────────────

class ArticleRecord(BaseModel):
    """ข้าวที่เก็บใน news_output.json"""
    url: str
    title: str
    source: str
    fetched_at: str = ""
    summary: str = ""
    category: CategoryType | None = None

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