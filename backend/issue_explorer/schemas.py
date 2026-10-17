"""
backend/issue_explorer/schemas.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ Pydantic schemas สำหรับ Issue Explorer request & response
GRASP  Information Expert — นิยามโครงสร้างข้อมูลสำหรับ API contract
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    storage: str = "sqlite"
    readonly: bool = True
    total_articles: int = 0


class QueryInfo(BaseModel):
    raw: str
    expanded_terms: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)


class StatsInfo(BaseModel):
    total_matches: int
    analyzed: int
    sources_count: int
    categories_count: int
    first_seen: str | None = None
    last_seen: str | None = None
    elapsed_ms: float


class IssueCluster(BaseModel):
    id: str
    label: str
    top_terms: list[str] = Field(default_factory=list)
    size: int
    first_seen: str | None = None
    last_seen: str | None = None
    sources: dict[str, int] = Field(default_factory=dict)
    article_ids: list[int] = Field(default_factory=list)


class IssueArticle(BaseModel):
    id: int
    url: str
    title: str
    source: str
    fetched_at: str
    category: str | None = None
    summary: str = ""
    score: float = 1.0
    cluster_id: str | None = None
    matched_terms: list[str] = Field(default_factory=list)


class PossiblyUnrelatedArticle(BaseModel):
    id: int
    title: str
    url: str
    source: str
    fetched_at: str
    category: str | None = None
    reason: str


class TimelinePoint(BaseModel):
    date: str
    count: int


class CountItem(BaseModel):
    name: str
    count: int


class RelatedTerm(BaseModel):
    term: str
    df: int
    score: float


class IssueSearchResponse(BaseModel):
    query: QueryInfo
    stats: StatsInfo
    clusters: list[IssueCluster] = Field(default_factory=list)
    possibly_unrelated: list[PossiblyUnrelatedArticle] = Field(default_factory=list)
    timeline: list[TimelinePoint] = Field(default_factory=list)
    sources: list[CountItem] = Field(default_factory=list)
    categories: list[CountItem] = Field(default_factory=list)
    related_terms: list[RelatedTerm] = Field(default_factory=list)
    articles: list[IssueArticle] = Field(default_factory=list)
    data_version: str = ""
