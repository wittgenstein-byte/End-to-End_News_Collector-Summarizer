"""
schemas/macro_event_schema.py
─────────────────────────────────────────────────────────────────
SOLID  I — Domain, relation, and API schemas for Macro-Events (Storylines).
GRASP  Information Expert — MacroEventRecord encapsulates storyline state,
            child event references, directional event relations, and lifecycle.
Pydantic v2 — Type-safe validation, UTC datetime normalization,
            and dual persistence (JSON / MongoDB).
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.schemas.event_evidence_schema import EventProgressionSynthesis
from backend.schemas.story_schema import (
    StoryRecord,
    StorySummary,
    TypedEventAnchors,
    _now_utc,
    _parse_utc_datetime,
)

MacroEventStatus = Literal["active", "dormant"]
EventRelationType = Literal["precedes", "updates", "responds_to", "caused_by"]
RelationVerificationStatus = Literal["proposed", "verified", "rejected"]


# ── Membership and Relation Models ────────────────────────────────

class MacroEventMembership(BaseModel):
    """
    Explicit membership record connecting an Event to a Macro-Event.
    Separated from EventRelationRecord to avoid type conflation.
    """
    model_config = ConfigDict(extra="ignore")

    macro_event_id: str = Field(description="Enclosing MacroEvent identifier")
    event_id: str = Field(description="Member StoryRecord / Event identifier")
    relation_type: Literal["part_of"] = "part_of"
    created_at: datetime = Field(default_factory=_now_utc)

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return _parse_utc_datetime(v)


class EventRelationRecord(BaseModel):
    """
    Directional, typed semantic relation between two distinct Events within a storyline.
    Examples:
      - B responds_to A: Action/relief B responds to crisis/disaster A.
      - B updates A: Event B provides new developments on prior event A.
      - A precedes B: Pure chronological sequence.
      - B caused_by A: Causal attribution (evidence-backed only, never chronology alone).
    """
    model_config = ConfigDict(extra="ignore")

    source_event_id: str = Field(description="Subject event identifier")
    target_event_id: str = Field(description="Object / antecedent event identifier")
    relation_type: EventRelationType = Field(description="Directional semantic relation type")
    evidence_fact_ids: list[str] = Field(default_factory=list, description="Supporting fact or citation identifiers")
    verification_status: RelationVerificationStatus = Field(default="proposed")
    created_at: datetime = Field(default_factory=_now_utc)

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_utc(cls, v: Any) -> datetime:
        return _parse_utc_datetime(v)


class MacroTimelineEvent(BaseModel):
    """Chronological development milestone in the macro storyline."""
    model_config = ConfigDict(extra="ignore")

    timestamp: str = Field(description="Formatted timestamp e.g. '2026-08-23 14:35:08'")
    event_id: str = Field(description="Associated child Event identifier")
    headline: str = Field(description="Concise event headline")
    summary: str = Field(description="Summary of the specific milestone")
    source_outlets: list[str] = Field(default_factory=list, description="Reporting publishers")
    citation: str | None = Field(default=None, description="Direct quote or source citation")


# ── Macro-Event Domain Record (Persistence & Services) ────────────

class MacroEventRecord(BaseModel):
    """
    Persistent domain record representing a broad Macro-Event / Storyline.
    Organizes multiple discrete child Events across days, weeks, and categories.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    macro_event_id: str = Field(
        default_factory=lambda: f"macro_{uuid4().hex[:12]}",
        description="Unique macro-event storyline identifier",
    )
    title: str = Field(description="Storyline title or topic anchor")
    category: str = Field(default="society", description="Primary topic category")
    status: MacroEventStatus = Field(default="active", description="Lifecycle state ('active' vs 'dormant')")
    named_crisis_anchor: str | None = Field(
        default=None,
        description="Explicit crisis anchor (e.g. 'น้ำท่วมน่าน') allowing multi-week re-linking",
    )
    storyline_anchor: str | None = Field(
        default=None,
        description="Unified storyline crisis/campaign anchor matching typed_anchors.storyline_anchor",
    )
    typed_anchors: TypedEventAnchors = Field(
        default_factory=TypedEventAnchors,
        description="Typed event anchors aggregated across member stories",
    )
    cluster_fingerprint: str = Field(
        default="fp_empty",
        description="Deterministic 16-hex hash of member article/event URLs",
    )
    synthesis_cache_key: str | None = Field(
        default=None,
        description="Deterministic 24-hex hash of macro ID, fingerprint, content digest, and prompt version",
    )
    created_at: datetime = Field(default_factory=_now_utc, description="Storyline creation timestamp (UTC)")
    updated_at: datetime = Field(default_factory=_now_utc, description="Latest storyline metadata update (UTC)")
    last_activity_at: datetime | None = Field(
        default=None,
        description="Authoritative activity timestamp derived from member child events",
    )
    child_event_ids: list[str] = Field(
        default_factory=list,
        description="Derived index of member Event IDs (StoryRecord.macro_event_id is SST)",
    )
    relations: list[EventRelationRecord] = Field(
        default_factory=list,
        description="Directional relations between member events",
    )
    centroid: list[float] | None = Field(
        default=None,
        description="Incremental 768-d WangchanBERTa centroid embedding for the storyline",
    )
    entities: list[str] = Field(default_factory=list, description="Accumulated named entities")

    # Presentation enrichment fields
    headline: str | None = Field(default=None, description="Synthesized overarching Thai headline")
    summary: str | None = Field(default=None, description="Synthesized overarching storyline summary")
    timeline: list[MacroTimelineEvent] = Field(default_factory=list, description="Storyline developments timeline")
    enriched_at: datetime | None = Field(default=None, description="Timestamp of presentation synthesis")
    presentation_fingerprint: str | None = Field(default=None, description="Stable SHA-256 synthesis cache fingerprint")

    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata and plugin flags")

    @model_validator(mode="after")
    def sync_storyline_anchor(self) -> MacroEventRecord:
        if self.storyline_anchor and not self.named_crisis_anchor:
            self.named_crisis_anchor = self.storyline_anchor
        elif self.named_crisis_anchor and not self.storyline_anchor:
            self.storyline_anchor = self.named_crisis_anchor
        return self

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_utc_timestamps(cls, v: Any) -> datetime:
        return _parse_utc_datetime(v)

    @field_validator("last_activity_at", "enriched_at", mode="before")
    @classmethod
    def validate_optional_utc(cls, v: Any) -> datetime | None:
        if v is None or v == "":
            return None
        return _parse_utc_datetime(v)

    # ── GRASP Information Expert Domain Methods ───────────────────

    def add_child_event(
        self,
        event_id: str,
        event_time: datetime | str | None = None,
        entities: list[str] | None = None,
    ) -> None:
        """Add or update child event in the derived index and refresh activity."""
        if event_id not in self.child_event_ids:
            self.child_event_ids.append(event_id)

        if entities:
            self.merge_entities(entities)

        if event_time is not None:
            parsed_time = _parse_utc_datetime(event_time)
            if self.last_activity_at is None or parsed_time > self.last_activity_at:
                self.last_activity_at = parsed_time
            self.updated_at = max(self.updated_at, parsed_time)
        else:
            self.updated_at = _now_utc()

        self.status = "active"

    def remove_child_event(self, event_id: str) -> None:
        """Remove child event from derived index."""
        if event_id in self.child_event_ids:
            self.child_event_ids.remove(event_id)

    def add_relation(self, relation: EventRelationRecord) -> None:
        """Add a directional event-to-event relation, preventing duplicates."""
        for existing in self.relations:
            if (
                existing.source_event_id == relation.source_event_id
                and existing.target_event_id == relation.target_event_id
                and existing.relation_type == relation.relation_type
            ):
                return
        self.relations.append(relation)

    def update_centroid_ema(self, new_embedding: list[float], alpha: float = 0.85) -> None:
        """Incrementally update 768-d centroid embedding using Exponential Moving Average."""
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
        child_events: list[StoryRecord] | None = None,
        now: datetime | None = None,
        macro_window_days: float = 7.0,
    ) -> bool:
        """
        Dynamically evaluate storyline active status.
        A Macro-Event is active if ANY child event is currently active (<= 72h),
        OR if its latest child event activity occurred within macro_window_days.
        """
        ref_time = now or _now_utc()
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # If child events are provided, check their active states
        if child_events:
            for child in child_events:
                if child.is_active_dynamic(current_time=ref_time):
                    return True
            # Find newest article activity among children
            child_times = [
                c.last_article_at or c.first_article_at
                for c in child_events
                if (c.last_article_at or c.first_article_at) is not None
            ]
            if child_times:
                newest_child_time = max(child_times)
                delta_days = (ref_time - newest_child_time).total_seconds() / 86400.0
                return 0.0 <= delta_days <= macro_window_days

        # Fall back to self.last_activity_at
        if self.last_activity_at is not None:
            delta_days = (ref_time - self.last_activity_at).total_seconds() / 86400.0
            return 0.0 <= delta_days <= macro_window_days

        return False

    def refresh_status(
        self,
        child_events: list[StoryRecord] | None = None,
        now: datetime | None = None,
        macro_window_days: float = 7.0,
    ) -> MacroEventStatus:
        """Evaluate and refresh storyline status."""
        if self.is_active_dynamic(child_events=child_events, now=now, macro_window_days=macro_window_days):
            self.status = "active"
        else:
            self.status = "dormant"
        return self.status


# ── API Response Schemas ──────────────────────────────────────────

class MacroEventSummary(BaseModel):
    """Lightweight projection for list endpoints."""
    model_config = ConfigDict(extra="ignore")

    macro_event_id: str
    title: str
    headline: str | None = None
    summary: str | None = None
    category: str
    status: MacroEventStatus
    cluster_fingerprint: str = "fp_empty"
    synthesis_cache_key: str | None = None
    storyline_anchor: str | None = None
    child_event_count: int
    created_at: str
    updated_at: str
    entities: list[str] = Field(default_factory=list)

    @classmethod
    def from_macro(cls, macro: MacroEventRecord) -> MacroEventSummary:
        return cls(
            macro_event_id=macro.macro_event_id,
            title=macro.title,
            headline=macro.headline,
            summary=macro.summary,
            category=macro.category,
            status=macro.status,
            cluster_fingerprint=macro.cluster_fingerprint,
            synthesis_cache_key=macro.synthesis_cache_key,
            storyline_anchor=macro.storyline_anchor or macro.named_crisis_anchor,
            child_event_count=len(macro.child_event_ids),
            created_at=macro.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=macro.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            entities=list(macro.entities),
        )


class MacroEventListResponse(BaseModel):
    """Paginated response for GET /api/macro-events."""
    model_config = ConfigDict(extra="ignore")

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
    updated: str
    macro_events: list[MacroEventSummary] = Field(default_factory=list)


class MacroEventDetailResponse(BaseModel):
    """Complete details for GET /api/macro-events/{macro_id}."""
    model_config = ConfigDict(extra="ignore")

    macro_event_id: str
    title: str
    headline: str | None = None
    summary: str | None = None
    category: str
    status: MacroEventStatus
    cluster_fingerprint: str = "fp_empty"
    synthesis_cache_key: str | None = None
    storyline_anchor: str | None = None
    typed_anchors: TypedEventAnchors = Field(default_factory=TypedEventAnchors)
    created_at: str
    updated_at: str
    child_event_count: int
    entities: list[str] = Field(default_factory=list)
    child_events: list[StorySummary] = Field(default_factory=list)
    relations: list[EventRelationRecord] = Field(default_factory=list)
    timeline: list[MacroTimelineEvent] = Field(default_factory=list)
    articles: list[dict[str, Any]] = Field(default_factory=list)
    synthesis: EventProgressionSynthesis | None = None
    trending_score: float | None = None
    breakdown: dict[str, Any] | None = None
    coverage_disclaimer: str = (
        "Trending reflects how widely and frequently collected news outlets "
        "are covering a storyline, not verified public interest."
    )
