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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.url_utils import compute_cluster_fingerprint, compute_synthesis_cache_key
from backend.schemas.event_evidence_schema import EventProgressionSynthesis
from backend.schemas.news_schema import ArticleRecord

StoryStatus = Literal["active", "dormant"]
StoryVerificationStatus = Literal["verified", "pending_review"]
MacroAssociationStatus = Literal["linked", "new_macro", "pending_macro"]
TemporalPrecision = Literal["datetime", "date", "relative_interval", "ambiguous", "none"]
EventTimeConfidence = Literal["explicit", "relative", "ambiguous", "none"]


class EventTimeEvidence(BaseModel):
    """
    Interval-based incident time evidence preserving UTC timestamps,
    granularity precision, and year-ambiguity semantics.
    """
    model_config = ConfigDict(extra="ignore")

    start_utc: datetime | None = Field(default=None, description="Inclusive start of incident window (UTC)")
    end_utc: datetime | None = Field(default=None, description="Inclusive end of incident window (UTC)")
    precision: TemporalPrecision = Field(default="none")
    confidence: EventTimeConfidence = Field(default="none")
    evidence_span: str | None = Field(default=None)

    @field_validator("start_utc", "end_utc", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime | None:
        if v is None or v == "":
            return None
        return _parse_utc_datetime(v)

    def interval_gap_hours(self, other: EventTimeEvidence) -> float | None:
        """
        Calculate interval distance in hours between self and other.
        Overlapping intervals yield 0.0.
        Returns None if either interval lacks start_utc or end_utc.
        """
        if self.start_utc is None or self.end_utc is None:
            return None
        if other.start_utc is None or other.end_utc is None:
            return None
        gap_sec = max(
            0.0,
            (self.start_utc - other.end_utc).total_seconds(),
            (other.start_utc - self.end_utc).total_seconds(),
        )
        return gap_sec / 3600.0


class TypedEventAnchors(BaseModel):
    """
    Structured typed entity anchors separating hierarchical locations,
    proper actor names, generic roles, targets, actions, and storyline anchors.
    """
    model_config = ConfigDict(extra="ignore")

    event_locations: list[str] = Field(default_factory=list, description="All normalized locations")
    provinces: list[str] = Field(default_factory=list, description="Canonical province names (77 provinces)")
    districts: list[str] = Field(default_factory=list, description="Canonical district/amphoe names")
    sub_locations: list[str] = Field(default_factory=list, description="Specific venues, rivers, temples, subdistricts")
    actor_names: list[str] = Field(default_factory=list, description="Specific proper names of individuals/entities")
    actor_roles: list[str] = Field(default_factory=list, description="Generic functional roles (e.g. นายกรัฐมนตรี, ตำรวจ)")
    targets: list[str] = Field(default_factory=list, description="Victims, objects, or targets of action")
    actions: list[str] = Field(default_factory=list, description="Incident actions or progression actions")
    storyline_anchor: str | None = Field(default=None, description="Base storyline crisis/campaign anchor e.g. น้ำท่วมน่าน")
    storyline_episode_key: str | None = Field(default=None, description="Time/episode-scoped anchor e.g. น้ำท่วมน่าน:2026-08")


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

    # Stage A Verification and Conflict Tracking (v4)
    verification_status: StoryVerificationStatus = Field(
        default="verified",
        description="Verification state of story event cluster ('verified' vs 'pending_review')",
    )
    conflict_type: str | None = Field(
        default=None,
        description="Conflict classification if pending review e.g. same_event_tie, same_vs_followup_tie",
    )
    competing_candidate_ids: list[str] = Field(
        default_factory=list,
        description="IDs of competing candidate stories during ambiguous assignment",
    )

    # Stage B Macro-Event Association Tracking (v4)
    macro_association_status: MacroAssociationStatus = Field(
        default="new_macro",
        description="Association state to MacroEvent: linked, new_macro, or pending_macro",
    )
    candidate_macro_ids: list[str] = Field(
        default_factory=list,
        description="Candidate macro-event IDs when macro association is pending",
    )
    pending_macro_reason: str | None = Field(
        default=None,
        description="Reason why macro association was held as pending",
    )

    # Fingerprinting & Synthesis Cache Invalidation (v4)
    cluster_fingerprint: str = Field(
        default="fp_empty",
        description="Deterministic 16-hex hash of canonical member article URLs",
    )
    synthesis_cache_key: str | None = Field(
        default=None,
        description="Deterministic 24-hex hash of story ID, fingerprint, article digest, and prompt version",
    )

    # Typed Anchors & Temporal Evidence (v4)
    event_time: EventTimeEvidence = Field(
        default_factory=EventTimeEvidence,
        description="Incident window time evidence with UTC bounds and precision",
    )
    typed_anchors: TypedEventAnchors = Field(
        default_factory=TypedEventAnchors,
        description="Typed event anchors for cross-story verification and conflict resolution",
    )
    medoid_embedding: list[float] | None = Field(
        default=None,
        description="Embedding of medoid article closest to centroid",
    )
    seed_embedding: list[float] | None = Field(
        default=None,
        description="Embedding of original seed article",
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

    @field_validator("event_time", mode="before")
    @classmethod
    def validate_event_time(cls, v: Any) -> Any:
        if v is None or not (isinstance(v, (EventTimeEvidence, dict))):
            return EventTimeEvidence()
        return v

    @field_validator("typed_anchors", mode="before")
    @classmethod
    def validate_typed_anchors(cls, v: Any) -> Any:
        if v is None or not (isinstance(v, (TypedEventAnchors, dict))):
            return TypedEventAnchors()
        return v

    @model_validator(mode="after")
    def sync_fingerprint(self) -> StoryRecord:
        if (not self.cluster_fingerprint or self.cluster_fingerprint == "fp_empty") and self.article_urls:
            self.cluster_fingerprint = compute_cluster_fingerprint(self.article_urls)
        return self

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
            self.cluster_fingerprint = compute_cluster_fingerprint(self.article_urls)

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
    verification_status: StoryVerificationStatus = "verified"
    cluster_fingerprint: str = "fp_empty"
    synthesis_cache_key: str | None = None
    created_at: str
    updated_at: str
    article_count: int
    outlet_count: int
    article_urls: list[str] = Field(default_factory=list)
    outlets: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    macro_event_id: str | None = None
    event_time: EventTimeEvidence = Field(default_factory=EventTimeEvidence)
    typed_anchors: TypedEventAnchors = Field(default_factory=TypedEventAnchors)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_story(cls, story: StoryRecord) -> StorySummary:
        cache_key = story.synthesis_cache_key or compute_synthesis_cache_key(
            story.story_id, story.cluster_fingerprint
        )
        return cls(
            story_id=story.story_id,
            title=story.title,
            headline=story.headline,
            summary=story.summary,
            category=story.category,
            status=story.status,
            verification_status=story.verification_status,
            cluster_fingerprint=story.cluster_fingerprint,
            synthesis_cache_key=cache_key,
            created_at=story.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=story.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            article_count=story.article_count,
            outlet_count=story.outlet_count,
            article_urls=list(story.article_urls),
            outlets=list(story.outlets),
            entities=list(story.entities),
            macro_event_id=story.macro_event_id,
            event_time=story.event_time,
            typed_anchors=story.typed_anchors,
            metadata=dict(story.metadata),
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
    verification_status: StoryVerificationStatus = "verified"
    cluster_fingerprint: str = "fp_empty"
    synthesis_cache_key: str | None = None
    created_at: str
    updated_at: str
    article_count: int
    outlet_count: int
    outlets: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    articles: list[ArticleRecord] = Field(default_factory=list)
    macro_event_id: str | None = None
    event_time: EventTimeEvidence = Field(default_factory=EventTimeEvidence)
    typed_anchors: TypedEventAnchors = Field(default_factory=TypedEventAnchors)
    metadata: dict[str, Any] = Field(default_factory=dict)
    synthesis: EventProgressionSynthesis | None = None
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
        synthesis: EventProgressionSynthesis | None = None,
    ) -> StoryDetailResponse:
        sorted_articles = sorted(
            articles,
            key=lambda a: a.fetched_at or "",
            reverse=False,
        )
        cache_key = story.synthesis_cache_key or compute_synthesis_cache_key(
            story.story_id, story.cluster_fingerprint
        )
        return cls(
            story_id=story.story_id,
            title=story.title,
            headline=story.headline,
            summary=story.summary,
            category=story.category,
            status=story.status,
            verification_status=story.verification_status,
            cluster_fingerprint=story.cluster_fingerprint,
            synthesis_cache_key=cache_key,
            created_at=story.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=story.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            article_count=story.article_count,
            outlet_count=story.outlet_count,
            outlets=list(story.outlets),
            entities=list(story.entities),
            timeline=list(story.timeline),
            articles=sorted_articles,
            macro_event_id=story.macro_event_id,
            event_time=story.event_time,
            typed_anchors=story.typed_anchors,
            metadata=dict(story.metadata),
            synthesis=synthesis,
            trending_score=trending_score,
            breakdown=breakdown,
        )
