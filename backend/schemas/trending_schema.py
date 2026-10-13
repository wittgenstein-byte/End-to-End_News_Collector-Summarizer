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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas.story_schema import TimelineEvent


class EngagementEvent(BaseModel):
    """Reader engagement telemetry event."""
    url: str
    event_type: Literal["click", "summary", "bookmark"]


class TrendingScoreBreakdown(BaseModel):
    """
    Detailed mathematical breakdown of a story or article's trending score.
    Combines legacy cluster metrics with explainable signal components:
    - volume_score: recent article count contribution
    - velocity_score: burst rate of new articles vs older baseline
    - diversity_score: distinct publisher count with syndication discount
    - recency_score: exponential half-life decay factor
    - novelty_score: uniqueness relative to other tracked active stories
    - engagement_score: reader engagement from clicks, summaries, bookmarks
    - routine_penalty: dampening penalty applied to routine/recurring reports
    - final_score: compound deterministic score
    """
    model_config = ConfigDict(extra="ignore")

    # Legacy fields (maintained for 100% backward compatibility)
    base_score: float = 1.0
    engagement_score: float = 0.0
    cluster_multiplier: float = 1.0
    time_decay: float = 1.0
    breaking_boost: float = 0.0
    raw_trending_score: float = 0.0

    # Deterministic signal components (Milestone 3)
    volume_score: float = 0.0
    velocity_score: float = 0.0
    diversity_score: float = 0.0
    recency_score: float = 0.0
    novelty_score: float = 0.0
    routine_penalty: float = 1.0
    is_routine: bool = False
    final_score: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_scores(self) -> TrendingScoreBreakdown:
        # Keep raw_trending_score and final_score synchronized
        if self.final_score != 0.0 and self.raw_trending_score == 0.0:
            self.raw_trending_score = self.final_score
        elif self.raw_trending_score != 0.0 and self.final_score == 0.0:
            self.final_score = self.raw_trending_score

        # Keep time_decay and recency_score synchronized if one is populated
        if self.recency_score != 0.0 and self.time_decay == 1.0:
            self.time_decay = self.recency_score
        elif self.time_decay != 1.0 and self.recency_score == 0.0:
            self.recency_score = self.time_decay

        return self


class TrendingStoryCluster(BaseModel):
    """
    Ranked active story cluster with deterministic trending scoring,
    publisher diversity metrics, and explainable signal breakdown.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    story_id: str = Field(description="Unique story cluster identifier")
    title: str = Field(description="Representative or seed article title")
    category: str = Field(default="society", description="Primary category tag")
    status: str = Field(default="active", description="Lifecycle state ('active' vs 'dormant')")
    created_at: str = Field(description="Story creation timestamp")
    updated_at: str = Field(description="Timestamp of latest article in story")
    article_urls: list[str] = Field(default_factory=list, description="Member article URLs")
    article_count: int = Field(default=0, description="Total number of articles in story")
    outlet_count: int = Field(default=0, description="Number of distinct publishers")
    outlets: list[str] = Field(default_factory=list, description="Unique publisher names")
    entities: list[str] = Field(default_factory=list, description="Accumulated named entities")
    trending_score: float = Field(default=0.0, description="Final deterministic trending score")
    rank: int = Field(default=0, description="Ordinal trending rank (1-indexed)")
    breakdown: TrendingScoreBreakdown = Field(default_factory=TrendingScoreBreakdown, description="Signal breakdown")
    articles: list[Any] = Field(default_factory=list, description="Member articles")
    headline: str | None = Field(default=None, description="LLM or heuristic story headline")
    summary: str | None = Field(default=None, description="Synthesized multi-article summary")
    timeline: list[TimelineEvent] = Field(default_factory=list, description="Developments timeline")
    badges: list[str] = Field(default_factory=list, description="Visual status badges")
    is_routine: bool = Field(default=False, description="Flag indicating routine/recurring report")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata and plugin flags")


class TrendingStoryListResponse(BaseModel):
    """API response model for story-based trending endpoints."""
    model_config = ConfigDict(extra="ignore")

    total: int
    updated: str
    stories: list[TrendingStoryCluster] = Field(default_factory=list)


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
    cluster_id: str | None = None
    cluster_size: int = 1
    cluster_sources: list[str] = Field(default_factory=list)
    is_multi_source: bool = False
    badges: list[str] = Field(default_factory=list)
    breakdown: TrendingScoreBreakdown | None = None
    topic_title: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    cluster_summary: str | None = None


class TrendingCluster(BaseModel):
    """Semantic story cluster aggregating articles across publishers."""
    cluster_id: str
    topic_title: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    cluster_summary: str | None = None
    source_count: int = 1
    article_count: int = 1
    avg_similarity: float = 1.0
    trend_score: float = 0.0
    is_multi_source: bool = False
    articles: list[TrendingArticle] = Field(default_factory=list)


class TrendingListResponse(BaseModel):
    """API response model for GET /api/news/trending."""
    total: int
    updated: str
    trending: list[TrendingArticle] = Field(default_factory=list)
    articles: list[TrendingArticle] = Field(default_factory=list)
    clusters: list[TrendingCluster] = Field(default_factory=list)
    trending_hashtags: list[str] = Field(default_factory=list)
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
