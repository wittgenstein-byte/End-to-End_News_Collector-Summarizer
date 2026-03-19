"""
schemas/news_schema.py
─────────────────────────────────────────────────────────────────
SOLID  I — แยก schema ตาม use-case (request / response / internal)
           ไม่ยัดทุก field ไว้ใน model เดียว
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, HttpUrl, field_validator


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


# ── LLM output schema ─────────────────────────────────────────────

SentimentType = Literal["positive", "neutral", "negative"]
CategoryType  = Literal[
    "politics", "economy", "technology", "health",
    "environment", "society", "sports", "entertainment", "world",
]


class NewsSummary(BaseModel):
    """ผลลัพธ์จาก LLM summarizer"""
    title: Optional[str]                = None
    source_url: Optional[str]           = None
    published_at: Optional[str]         = None
    language: Optional[str]             = None
    summary: Optional[str]              = None
    bullets: list[str]                  = []
    category: Optional[CategoryType]    = None
    sentiment: Optional[SentimentType]  = None
    keywords: list[str]                 = []


# ── Response schemas ──────────────────────────────────────────────

class CollectResponse(BaseModel):
    ok: bool
    path: Optional[str]         = None
    summary: Optional[NewsSummary] = None
    error: Optional[str]        = None
    fetch_method: Optional[str] = None


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