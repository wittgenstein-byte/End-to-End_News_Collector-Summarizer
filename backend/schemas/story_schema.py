"""
schemas/story_schema.py
─────────────────────────────────────────────────────────────────
SOLID  I — Focused domain & API schemas for persistent stories.
GRASP  Information Expert — StoryRecord encapsulates story state,
           member articles, centroid EMA, and lifecycle status.
Pydantic v2 — Type-safe validation, UTC datetime normalization,
           and dual persistence (JSON / MongoDB).
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.news_schema import ArticleRecord

StoryStatus = Literal["active", "dormant"]


def _now_utc() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _parse_utc_datetime(v: Any) -> datetime:
    """
    Robust datetime parser ensuring timezone-aware UTC datetime.
    Supports datetime objects (naive or aware) and string formats
    (ISO 8601 with 'Z' or '+00:00', space-separated '%Y-%m-%d %H:%M:%S').
    Compatible with Python 3.10, 3.11, and 3.12.
    """
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    if isinstance(v, str):
        clean_str = v.strip()
        if not clean_str:
            return _now_utc()
        # Python 3.10 compatibility: replace 'Z' with '+00:00' before fromisoformat
        iso_str = clean_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                return datetime.strptime(clean_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    return _now_utc()


# ── Timeline & Developments Schema ────────────────────────────────

class TimelineEvent(BaseModel):
    """
    Chronological development milestone within a story cluster.
    Synthesized by LLM or heuristic fallback from representative member articles.
    """
    model_config = ConfigDict(extra="ignore")

    timestamp: str = Field(description="Formatted timestamp e.g. '2026-08-23 14:35:08' or ISO format")
    event: str = Field(description="Summary of the specific development or milestone")
    title: str = Field(default="", description="Optional headline for this event development")
    source: str = Field(default="", description="Reporting news outlet (e.g. 'ThaiPBS')")
    url: str = Field(default="", description="Outbound link to source article")
    citation: str | None = Field(default=None, description="Direct quote or citation excerpt from source")

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, v: Any) -> str:
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.strftime("%Y-%m-%d %H:%M:%S")
        return str(v).strip() if v else ""


# ── Story Domain Record (Persistence & Services) ──────────────────

class StoryRecord(BaseModel):
    """
    Persistent domain model representing a real-world story event cluster.
    Survives server restarts in JSON and MongoDB backends.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    story_id: str = Field(
        default_factory=lambda: f"story_{uuid4().hex[:12]}",
        description="Unique story cluster identifier",
    )
    title: str = Field(description="Representative or seed article title")
    category: str = Field(default="society", description="Primary category tag (soft signal, not hard barrier)")
    status: StoryStatus = Field(default="active", description="Lifecycle state ('active' vs 'dormant')")
    created_at: datetime = Field(default_factory=_now_utc, description="Story creation timestamp (UTC)")
    updated_at: datetime = Field(default_factory=_now_utc, description="Timestamp of latest article added to story (UTC)")
    article_urls: list[str] = Field(default_factory=list, description="List of member article URLs")
    article_count: int = Field(default=0, description="Total number of articles in story")
    outlet_count: int = Field(default=0, description="Number of distinct news publishers")
    outlets: list[str] = Field(default_factory=list, description="Unique publisher names reporting on this story")
    centroid: list[float] | None = Field(default=None, description="Incremental 768-d WangchanBERTa embedding centroid")
    entities: list[str] = Field(default_factory=list, description="Accumulated named entities (people, orgs, places)")
    macro_event_id: str | None = Field(
        default=None,
        description="Enclosing MacroEventRecord identifier (Single Source of Truth)",
    )

    # Presentation enrichment fields (cached LLM outputs with heuristic fallback)
    headline: str | None = Field(default=None, description="LLM-generated story headline (falls back to title)")
    summary: str | None = Field(default=None, description="Synthesized multi-article summary")
    timeline: list[TimelineEvent] = Field(default_factory=list, description="Chronological timeline developments")
    first_article_at: datetime | None = Field(default=None, description="Timestamp of earliest member article")
    last_article_at: datetime | None = Field(default=None, description="Timestamp of newest member article")
    enriched_at: datetime | None = Field(default=None, description="Timestamp of LLM presentation enrichment")

    # Extensible metadata (routine report flags, custom metrics)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata and plugin flags")

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_utc_timestamps(cls, v: Any) -> datetime:
        return _parse_utc_datetime(v)

    @field_validator("first_article_at", "last_article_at", "enriched_at", mode="before")
    @classmethod
    def validate_optional_utc_timestamps(cls, v: Any) -> datetime | None:
        if v is None or v == "":
            return None
        return _parse_utc_datetime(v)

    # ── GRASP Information Expert Domain Methods ───────────────────

    def add_article(
        self,
        url: str,
        source: str,
        article_time: datetime | str | None = None,
        article_entities: list[str] | None = None,
    ) -> None:
        """
        Incrementally add an article to this story cluster.
        Updates membership, publisher diversity, timeline bounds, and reactivates status.
        """
        if url not in self.article_urls:
            self.article_urls.append(url)
            self.article_count = len(self.article_urls)

        if source and source not in self.outlets:
            self.outlets.append(source)
            self.outlet_count = len(self.outlets)

        if article_entities:
            self.merge_entities(article_entities)

        if article_time is not None:
            parsed_time = _parse_utc_datetime(article_time)
            if self.first_article_at is None or parsed_time < self.first_article_at:
                self.first_article_at = parsed_time
            if self.last_article_at is None or parsed_time > self.last_article_at:
                self.last_article_at = parsed_time
            self.updated_at = max(self.updated_at, parsed_time)
        else:
            self.updated_at = _now_utc()

        # Adding an article always refreshes story to active state
        self.status = "active"

    def update_centroid_ema(self, new_embedding: list[float], alpha: float = 0.85) -> None:
        """
        Incrementally update 768-d centroid embedding using Exponential Moving Average.
        Centroid_new = alpha * Centroid_old + (1 - alpha) * Embedding_new.
        """
        if not new_embedding:
            return
        if self.centroid is None or len(self.centroid) != len(new_embedding):
            self.centroid = [float(x) for x in new_embedding]
            return

        self.centroid = [
            float(alpha * c + (1.0 - alpha) * e)
            for c, e in zip(self.centroid, new_embedding)
        ]

    def merge_entities(self, new_entities: list[str]) -> None:
        """Merge newly discovered named entities preserving order and uniqueness."""
        existing_set = set(self.entities)
        for ent in new_entities:
            clean = ent.strip()
            if clean and clean not in existing_set:
                self.entities.append(clean)
                existing_set.add(clean)

    def is_active_dynamic(
        self,
        current_time: datetime | None = None,
        inactivity_threshold_hours: float = 72.0,
        now: datetime | None = None,
    ) -> bool:
        """
        Dynamically evaluate story active status against actual article activity.
        Uses last_article_at (or first_article_at) as authoritative timestamp.
        updated_at is NOT used to prevent presentation/enrichment updates from reviving dormant stories.
        """
        ref_ts = self.last_article_at or self.first_article_at or self.updated_at or self.created_at
        if ref_ts is None:
            return False
        eval_now = now if now is not None else (current_time if current_time is not None else _now_utc())
        if eval_now.tzinfo is None:
            eval_now = eval_now.replace(tzinfo=timezone.utc)
        delta_seconds = (eval_now - ref_ts).total_seconds()
        threshold_seconds = inactivity_threshold_hours * 3600.0
        return 0.0 <= delta_seconds <= threshold_seconds

    def refresh_status(
        self,
        current_time: datetime | None = None,
        inactivity_threshold_hours: float = 72.0,
        now: datetime | None = None,
    ) -> StoryStatus:
        """
        Evaluate story lifecycle: marked 'dormant' if no new article within inactivity window.
        Uses is_active_dynamic() as single source of truth.
        """
        eval_now = now if now is not None else current_time
        if self.is_active_dynamic(current_time=eval_now, inactivity_threshold_hours=inactivity_threshold_hours):
            self.status = "active"
        else:
            self.status = "dormant"
        return self.status


# ── Story Summary & List Schema (Network-Optimized) ───────────────

class StorySummary(BaseModel):
    """
    Lightweight story card projection for list endpoints.
    Excludes the heavy 768-d centroid vector to minimize response payload.
    """
    model_config = ConfigDict(extra="ignore")

    story_id: str
    title: str
    headline: str | None = None
    summary: str | None = None
    category: str
    status: StoryStatus
    created_at: str
    updated_at: str
    article_count: int
    outlet_count: int
    outlets: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    macro_event_id: str | None = None

    @classmethod
    def from_story(cls, story: StoryRecord) -> StorySummary:
        return cls(
            story_id=story.story_id,
            title=story.title,
            headline=story.headline,
            summary=story.summary,
            category=story.category,
            status=story.status,
            created_at=story.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=story.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            article_count=story.article_count,
            outlet_count=story.outlet_count,
            outlets=list(story.outlets),
            entities=list(story.entities),
            macro_event_id=story.macro_event_id,
        )


class StoryListResponse(BaseModel):
    """Paginated response for GET /api/stories."""
    model_config = ConfigDict(extra="ignore")

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    updated: str
    stories: list[StorySummary] = Field(default_factory=list)


# ── Story Detail Schema (Full View with Articles & Timeline) ──────

class StoryDetailResponse(BaseModel):
    """
    Complete story details for GET /api/stories/{story_id}.
    Includes all member articles in chronological order, developments timeline,
    and coverage-vs-interest disclaimer.
    """
    model_config = ConfigDict(extra="ignore")

    story_id: str
    title: str
    headline: str | None = None
    summary: str | None = None
    category: str
    status: StoryStatus
    created_at: str
    updated_at: str
    article_count: int
    outlet_count: int
    outlets: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    articles: list[ArticleRecord] = Field(default_factory=list)
    macro_event_id: str | None = None
    trending_score: float | None = None
    breakdown: dict[str, Any] | None = None
    coverage_disclaimer: str = (
        "Trending reflects how widely and frequently collected news outlets "
        "are covering a story, not verified public interest."
    )

    @classmethod
    def from_story_and_articles(
        cls,
        story: StoryRecord,
        articles: list[ArticleRecord],
        trending_score: float | None = None,
        breakdown: dict[str, Any] | None = None,
    ) -> StoryDetailResponse:
        sorted_articles = sorted(
            articles,
            key=lambda a: a.fetched_at or "",
            reverse=False,
        )
        return cls(
            story_id=story.story_id,
            title=story.title,
            headline=story.headline,
            summary=story.summary,
            category=story.category,
            status=story.status,
            created_at=story.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=story.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            article_count=story.article_count,
            outlet_count=story.outlet_count,
            outlets=list(story.outlets),
            entities=list(story.entities),
            timeline=list(story.timeline),
            articles=sorted_articles,
            macro_event_id=story.macro_event_id,
            trending_score=trending_score,
            breakdown=breakdown,
        )
