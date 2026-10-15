"""
schemas/event_evidence_schema.py
─────────────────────────────────────────────────────────────────
SOLID  I — Focused interface schemas for evidence modeling and
           progression synthesis.
GRASP  Information Expert — Models encapsulate structured claims,
           event timeline milestones, verified facts, conflict
           matrices, uncertainties, and cluster outlier detection.
Pydantic v2 — Type-safe validation, serialization, and JSON schemas.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Layer 1: Input Evidence Schemas ───────────────────────────────

ClaimType = Literal[
    "official_statement",  # คำแถลงอย่างเป็นทางการ
    "fact_report",         # รายงานข้อเท็จจริง
    "accusation",          # ข้อกล่าวหา / การร้องเรียน
    "opinion",             # ความคิดเห็น / มุมมอง
    "forecast",            # การคาดการณ์ / ประมาณการ
]


class EvidenceClaim(BaseModel):
    """
    Granular claim or statement extracted from a news article.
    Enables traceable attribution and verification.
    """
    model_config = ConfigDict(extra="ignore")

    claim_id: str = Field(description="Unique claim identifier e.g. 'clm_01'")
    text: str = Field(description="Normalized statement or claim text")
    claim_type: ClaimType = Field(default="fact_report", description="Category of statement")
    speaker: str = Field(default="", description="Who made the claim or official statement")
    evidence_quote: str = Field(default="", description="Direct quotation or factual sentence from source")


class EvidenceArticle(BaseModel):
    """
    Structured article object containing pre-extracted evidence, claims,
    and metadata before being sent to the LLM.
    """
    model_config = ConfigDict(extra="ignore")

    article_id: str = Field(description="Short reference ID e.g. 'art_01'")
    source: str = Field(description="News publisher name e.g. 'ThaiPBS'")
    published_at: str = Field(description="ISO or formatted publication timestamp")
    event_time: str | None = Field(default=None, description="Actual time event occurred if specified")
    title: str = Field(description="Article headline")
    summary: str = Field(default="", description="Article summary text")
    claims: list[EvidenceClaim] = Field(default_factory=list, description="Extracted claims and quotes")
    canonical_url: str = Field(default="", description="Direct URL to article source")


class EvidenceInputPayload(BaseModel):
    """
    Layer 1 Input Payload passed to LLM for Event Progression Synthesis.
    Provides structured evidence rather than unstructured text blobs.
    """
    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(description="Unique event or story identifier")
    title: str = Field(description="Primary topic or event title")
    first_seen_at: str = Field(description="Earliest report timestamp")
    updated_at: str = Field(description="Latest report timestamp")
    articles: list[EvidenceArticle] = Field(default_factory=list, description="Structured member articles")


# ── Layer 2 & 3: Output Synthesis & Executive Dossier Schemas ─────

class ProgressionMilestone(BaseModel):
    """
    Chronological milestone in the development of the event.
    Must trace back to supporting evidence article IDs.
    """
    model_config = ConfigDict(extra="ignore")

    milestone_id: str = Field(default="", description="Identifier e.g. 'm_01'")
    event_time: str = Field(description="Time of this development or reporting timestamp")
    description: str = Field(description="Objective factual description of the development")
    evidence_ids: list[str] = Field(default_factory=list, description="Source article IDs supporting this milestone e.g. ['art_01']")


class ConfirmedFact(BaseModel):
    """
    Factual point corroborated by independent reporting or official documentation.
    """
    model_config = ConfigDict(extra="ignore")

    fact_id: str = Field(default="", description="Identifier e.g. 'f_01'")
    fact: str = Field(description="Confirmed factual assertion")
    evidence_ids: list[str] = Field(default_factory=list, description="Article IDs corroborating this fact")
    corroborating_sources: list[str] = Field(default_factory=list, description="News outlets that confirmed this fact")


class DisputeSide(BaseModel):
    """
    One perspective or stance within a disputed issue.
    """
    model_config = ConfigDict(extra="ignore")

    speaker: str = Field(description="Person, agency, or group holding this stance")
    source: str = Field(description="News outlet that reported this stance")
    claim_type: str = Field(default="opinion", description="Type of statement (accusation, statement, opinion)")
    stance: str = Field(description="Summary of the stance or argument")
    evidence_quote: str = Field(default="", description="Direct quote or excerpt supporting this stance")
    evidence_id: str = Field(default="", description="Article ID containing this claim e.g. 'art_01'")


class DisputeIssue(BaseModel):
    """
    Claim-vs-Claim Issue Matrix: A specific topic where sources or stakeholders differ.
    """
    model_config = ConfigDict(extra="ignore")

    topic_in_dispute: str = Field(description="The core disagreement or question in dispute")
    status: str = Field(default="กำลังตรวจสอบ", description="Status e.g. 'ต่างฝ่ายต่างยืนยัน', 'รอผลสอบสวน', 'ข้อกล่าวหาข้างเดียว'")
    sides: list[DisputeSide] = Field(default_factory=list, description="Differing perspectives or conflicting claims")


class UnknownPoint(BaseModel):
    """
    Critical unknown, unverified claim, or unanswered question that cannot be concluded yet.
    Prevents the LLM from hallucinating closure.
    """
    model_config = ConfigDict(extra="ignore")

    question: str = Field(description="The key unanswered question or gap in information")
    why_unknown: str = Field(description="Why evidence is currently insufficient or contradictory")
    pending_action: str | None = Field(default=None, description="What event or investigation will clarify this")


class IrrelevantArticle(BaseModel):
    """
    Outlier article detected by LLM that does not belong to the core macro-event topic.
    Protects the cluster from noisy or irrelevant additions.
    """
    model_config = ConfigDict(extra="ignore")

    article_id: str = Field(description="Article reference ID e.g. 'art_03'")
    source: str = Field(default="", description="Publisher name")
    title: str = Field(default="", description="Headline of the unrelated article")
    reason: str = Field(description="Why this article is irrelevant to the central event")


class EventProgressionSynthesis(BaseModel):
    """
    Full 3-Layer Event Progression Intelligence Model.
    Provides Executive Overview, Chronological Timeline, Confirmed Facts,
    Dispute Matrix, Blindspots/Unknowns, and Outlier Article Detection.
    """
    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(description="Story or Macro-Event ID")
    executive_summary: str = Field(description="2-3 sentence authoritative Thai executive summary")
    progression_timeline: list[ProgressionMilestone] = Field(
        default_factory=list,
        description="Chronological development milestones with evidence links",
    )
    confirmed_facts: list[ConfirmedFact] = Field(
        default_factory=list,
        description="Corroborated facts backed by evidence",
    )
    conflicts: list[DisputeIssue] = Field(
        default_factory=list,
        description="Claim-vs-Claim dispute matrix showing divergent stances",
    )
    unknowns: list[UnknownPoint] = Field(
        default_factory=list,
        description="Unresolved questions, blindspots, and pending investigations",
    )
    irrelevant_articles: list[IrrelevantArticle] = Field(
        default_factory=list,
        description="Outlier articles in this cluster that do not belong to the macro-event",
    )
    is_fallback: bool = Field(default=False, description="True if generated via deterministic heuristic")
    cached: bool = Field(default=False, description="True if served from cache")
    generated_at: str | None = Field(default=None, description="Generation timestamp UTC")
