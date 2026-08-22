"""
schemas/trending_schema.py
─────────────────────────────────────────────────────────────────
SOLID  I — Focused Pydantic schemas for trending news and reader
          engagement telemetry.
GRASP  Information Expert — Holds structured representations of
          trending metrics, badges, and response models.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EngagementEvent(BaseModel):
    """Reader engagement telemetry event."""
    url: str
    event_type: Literal["click", "summary", "bookmark"]


class TrendingScoreBreakdown(BaseModel):
    """Detailed mathematical breakdown of an article's trending score."""
    base_score: float = 1.0
    engagement_score: float = 0.0
    cluster_multiplier: float = 1.0
    time_decay: float = 1.0
    breaking_boost: float = 0.0
    raw_trending_score: float = 0.0


class TrendingArticle(BaseModel):
    """Ranked trending news article with cluster consensus and badges."""
    title: str
    summary: str
    source: str
    url: str
    image_url: str = ""
    category: str | None = None
    fetched_at: str
    trending_score: float
    cluster_size: int = 1
    cluster_sources: list[str] = Field(default_factory=list)
    badges: list[str] = Field(default_factory=list)
    breakdown: TrendingScoreBreakdown | None = None


class TrendingListResponse(BaseModel):
    """API response model for GET /api/news/trending."""
    total: int
    updated: str
    trending: list[TrendingArticle] = Field(default_factory=list)
    articles: list[TrendingArticle] = Field(default_factory=list)
    hero: TrendingArticle | None = None

    @model_validator(mode="before")
    @classmethod
    def sync_trending_and_articles(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "trending" in data and "articles" not in data:
                data["articles"] = data["trending"]
            elif "articles" in data and "trending" not in data:
                data["trending"] = data["articles"]
        return data
