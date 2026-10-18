"""
services/story_presentation_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Story presentation formatting via LLM and robust fallback only.
           The LLM NEVER decides story membership or trending rank.
SOLID  O — Pluggable tiered model cascade and customizable fallback heuristics.
SOLID  D — Injects OpenAI client, NewsRepositoryPort, and Settings.
GRASP  Information Expert — Formats Thai headline, synthesized multi-article
           summary, chronological development timeline, and source citations.
GRASP  Pure Fabrication — StoryPresentationService isolates LLM presentation
           formatting, in-memory caching keyed by (story_id, updated_at),
           and graceful offline heuristic fallback.
POLICY Zero Crash Guarantee — Graceful HTTP 200 fallback on LLM network error,
       timeout, 401/429/500, or missing API key.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import settings
from backend.core.cascading_client import CascadingLLMClient, get_cascading_client
from backend.core.url_utils import compute_cluster_fingerprint, compute_synthesis_cache_key
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.schemas.event_evidence_schema import (
    ConfirmedFact,
    DisputeIssue,
    DisputeSide,
    DossierMetrics,
    EventProgressionSynthesis,
    IrrelevantArticle,
    PoliticalContextItem,
    ProgressionMilestone,
    RelevanceGateResult,
    UnknownPoint,
)
from backend.schemas.macro_event_schema import MacroEventRecord, MacroTimelineEvent
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import StoryRecord
from backend.schemas.story_schema import TimelineEvent as SchemaTimelineEvent
from backend.schemas.trending_schema import TrendingStoryCluster
from backend.scrapers.helpers import clean_headline_date_suffix
from backend.services.evidence_extractor import EvidenceExtractor

logger = logging.getLogger(__name__)

# Boilerplate substrings to clean from article summaries and titles
_BOILERPLATE_PATTERNS: tuple[str, ...] = (
    "The post appeared first on",
    "appeared first on",
    "The post",
    "ความคืบหน้ากรณี",
    "อ่านรายละเอียดเพิ่มเติม",
    "คลิกอ่านข่าว",
    "ติดตามรายละเอียด",
    "อ่านต่อได้ที่",
)

_RELEVANCE_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "อภิปรายไม่ไว้วางใจ",
    "ซักฟอก",
    "ญัตติ",
    "ไม่ไว้วางใจ",
    "เปิดศึกซักฟอก",
    "การแถลงนโยบาย",
    "งบประมาณประจำปี",
    "ฝ่ายค้านยื่น",
    "ศึกซักฟอก",
    "ลงมติไม่ไว้วางใจ",
    "ญัตติอภิปราย",
)

_RELEVANCE_STOPWORDS: set[str] = {
    "การ", "ความ", "และ", "ใน", "ของ", "ที่", "มี", "เป็น", "ไป", "มา", "กับ", "ให้",
    "ได้", "โดย", "จาก", "เรื่อง", "กรณี", "ปม", "เปิด", "ชี้", "เผย", "สั่ง", "จ่อ",
    "ยัน", "ลั่น", "แจง", "เร่ง", "พบ", "เตือน", "แนะ", "รับ", "ส่ง", "ยื่น", "ขอ",
    "ข่าว", "รายงาน", "ล่าสุด", "วันนี้", "เมื่อวาน", "พรุ่งนี้", "เวลา", "นาที", "ชั่วโมง",
    "วัน", "เดือน", "ปี", "ด่วน", "คืบหน้า", "แล้ว", "อีก", "จะ", "ยัง", "แต่", "นี้", "นั้น",
    "ลง", "ขึ้น", "ใต้", "ออก", "เข้า", "ผ่าน", "ร่วม", "ตั้ง", "ทุก", "ทั้ง", "พวก", "หลัง", "ก่อน", "คน", "แห่ง", "ราย",
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
    "2565", "2566", "2567", "2568", "2569", "2570", "2023", "2024", "2025", "2026",
    # Broad institutional and generic role stopwords (prevent cross-incident chaining)
    "ตำรวจ", "สำนักงานตำรวจแห่งชาติ", "สตช", "ผบ.ตร.", "ผบ.ตร", "เจ้าหน้าที่ตำรวจ",
    "เจ้าหน้าที่", "รัฐบาล", "นายก", "นายกรัฐมนตรี", "นายกฯ", "รัฐมนตรี", "รมว.",
    "กระทรวง", "กรม", "กองทัพ", "ทหาร", "ศาล", "ครม", "ครม.", "สภา", "พรรค",
}


def _tokenize_thai_words(text: str) -> list[str]:
    """Tokenize Thai/English text using pythainlp with regex fallback. Strips trailing dates and numeric-only tokens."""
    if not text:
        return []
    cleaned = clean_headline_date_suffix(text)
    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(cleaned, engine="newmm")
        return [
            t.strip().lower() for t in tokens
            if len(t.strip()) > 1 and not re.match(r"^\d+$", t.strip()) and t.strip().lower() not in _RELEVANCE_STOPWORDS
        ]
    except Exception:
        return [
            w.lower() for w in re.findall(r"[\wก-๙]{2,}", cleaned)
            if not re.match(r"^\d+$", w) and w.lower() not in _RELEVANCE_STOPWORDS
        ]


def normalize_timestamp(ts: Any) -> str:
    """Normalize any timestamp value into '%Y-%m-%d %H:%M:%S' UTC string."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(ts, str):
        clean = ts.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                dt = datetime.strptime(clean, fmt).replace(tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        return clean
    return ""


def _normalize_and_sort_candidate_articles(articles: Sequence[Any]) -> list[Any]:
    """
    Ensure candidate articles have a stable chronological order if article_id is not preset.
    If all articles already have article_id preset, preserves incoming order for compatibility.
    """
    has_preset_ids = all(
        bool(a.get("article_id") if isinstance(a, dict) else getattr(a, "article_id", None))
        for a in articles
    )
    if has_preset_ids or not articles:
        return list(articles)

    def _sort_key(a: Any) -> tuple[str, str, str]:
        if isinstance(a, dict):
            ts = str(a.get("published_at") or a.get("fetched_at") or a.get("created_at") or "")
            t = str(a.get("title") or "")
            u = str(a.get("url") or "")
        else:
            ts = str(getattr(a, "published_at", None) or getattr(a, "fetched_at", None) or getattr(a, "created_at", None) or "")
            t = str(getattr(a, "title", None) or "")
            u = str(getattr(a, "url", None) or "")
        return (ts, t, u)

    return sorted(articles, key=_sort_key)


def _check_is_sports_collection(title: str, articles: Sequence[Any]) -> bool:
    """Detect whether a candidate collection is predominantly sports news."""
    if not articles:
        return False
    sports_kw = {
        "ucl", "ชปล", "พรีเมียร์ลีก", "ไทยลีก", "ฟุตบอล", "กีฬา", "วอลเลย์บอล",
        "ลูกยาง", "ผลบอล", "แข่ง", "แชมป์", "แต้ม", "สโมสร", "นักเตะ", "เอเอฟซี",
        "แชมเปียนส์", "แชมเปี้ยนส์", "พาราเกมส์", "เทนนิส", "แบดมินตัน",
    }
    sports_count = 0
    for a in articles:
        cat = getattr(a, "category", "") if not isinstance(a, dict) else a.get("category", "")
        u = getattr(a, "url", "") if not isinstance(a, dict) else a.get("url", "")
        t = getattr(a, "title", "") if not isinstance(a, dict) else a.get("title", "")
        if (
            cat == "sports"
            or "/sport" in str(u).lower()
            or "/football" in str(u).lower()
            or any(k in str(t).lower() for k in sports_kw)
        ):
            sports_count += 1
    return (sports_count / len(articles)) >= 0.35


# ── Presentation Schemas ──────────────────────────────────────────

class TimelineEvent(SchemaTimelineEvent):
    """
    Timeline development event within a story presentation.
    Dual-compatible with both property conventions:
    - event_description / event
    - source_name / source
    - source_url / url
    - source_title / title
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    event: str = Field(default="", description="Summary of specific development milestone")
    event_description: str = Field(default="", description="Summary of specific development milestone")
    source: str = Field(default="", description="Reporting news outlet (e.g. 'ThaiPBS')")
    source_name: str = Field(default="", description="Reporting news outlet (e.g. 'ThaiPBS')")
    url: str = Field(default="", description="Outbound link to source article")
    source_url: str = Field(default="", description="Outbound link to source article")
    title: str = Field(default="", description="Title of the source article")
    source_title: str = Field(default="", description="Title of the source article")

    @model_validator(mode="before")
    @classmethod
    def _sync_fields_before(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Event description <-> event
            ed = data.get("event_description")
            ev = data.get("event")
            if ed and not ev:
                data["event"] = ed
            elif ev and not ed:
                data["event_description"] = ev
            elif not ev and not ed:
                data["event"] = ""
                data["event_description"] = ""

            # 2. Source name <-> source
            sn = data.get("source_name")
            sc = data.get("source")
            if sn and not sc:
                data["source"] = sn
            elif sc and not sn:
                data["source_name"] = sc

            # 3. Source URL <-> url
            su = data.get("source_url")
            u = data.get("url")
            if su and not u:
                data["url"] = su
            elif u and not su:
                data["source_url"] = u

            # 4. Source title <-> title
            st = data.get("source_title")
            ti = data.get("title")
            if st and not ti:
                data["title"] = st
            elif ti and not st:
                data["source_title"] = ti
        return data

    @model_validator(mode="after")
    def _sync_fields_after(self) -> TimelineEvent:
        if not self.event and self.event_description:
            self.event = self.event_description
        if not self.event_description and self.event:
            self.event_description = self.event

        if not self.source and self.source_name:
            self.source = self.source_name
        if not self.source_name and self.source:
            self.source_name = self.source

        if not self.url and self.source_url:
            self.url = self.source_url
        if not self.source_url and self.url:
            self.source_url = self.url

        if not self.title and self.source_title:
            self.title = self.source_title
        if not self.source_title and self.title:
            self.source_title = self.title
        return self


class Citation(BaseModel):
    """Source citation attributing factual details back to member articles."""
    model_config = ConfigDict(extra="ignore")

    source_name: str = Field(description="Reporting news outlet")
    source_url: str = Field(description="Outbound link to source article")
    source_title: str = Field(default="", description="Title of the source article")
    quote: str | None = Field(default=None, description="Direct quote or factual excerpt")
    timestamp: str | None = Field(default=None, description="Reporting timestamp")


class StoryPresentation(BaseModel):
    """
    Presentation model for a top-ranked story event.
    Provides Thai headline, synthesized multi-article summary,
    chronological development timeline, and source citations.
    """
    model_config = ConfigDict(extra="ignore")

    story_id: str = Field(description="Unique story cluster identifier")
    headline: str = Field(description="Authoritative Thai story headline")
    summary: str = Field(description="Synthesized multi-article summary")
    timeline: list[TimelineEvent] = Field(default_factory=list, description="Chronological developments")
    citations: list[dict[str, Any]] = Field(default_factory=list, description="Citations back to source articles")
    is_fallback: bool = Field(default=False, description="Whether deterministic fallback was used")
    cached: bool = Field(default=False, description="Whether returned from cache")
    updated_at: str | None = Field(default=None, description="Story updated_at timestamp")

    @property
    def generated_headline(self) -> str:
        """Alias for compatibility with TrendingService and LLMStoryPresenter interface."""
        return self.headline

    @property
    def synthesized_summary(self) -> str:
        """Alias for compatibility with TrendingService and LLMStoryPresenter interface."""
        return self.summary

    @property
    def source_citations(self) -> list[dict[str, Any]]:
        """Alias for compatibility with TrendingService and LLMStoryPresenter interface."""
        return self.citations


# ── System Prompt for Presentation Generation ─────────────────────

STORY_PRESENTATION_SYSTEM_PROMPT = """You are a senior news editor for a professional Thai news agency.
Your task is to take a set of representative news articles reporting on a single real-world story event and create an authoritative presentation in Thai.

You must generate:
1. `headline`: A concise, authoritative Thai headline synthesizing all perspectives (50–120 characters).
2. `summary`: A 2–3 sentence synthesized summary in Thai explaining what occurred, latest developments, and overall impact.
3. `timeline`: A chronological list of key development milestones (earliest to latest). Each event must include:
   - `timestamp`: The date/time of this development (from the article).
   - `event_description`: A clear, factual Thai sentence describing the specific event.
   - `source_name`: The reporting outlet (e.g. ThaiPBS, Bangkok Post, etc.).
   - `source_url`: Outbound link to the source article.
   - `source_title`: Title of the source article.
4. `citations`: A list of citations citing each unique source article:
   - `source_name`: The reporting outlet.
   - `source_url`: Outbound link to the source article.
   - `source_title`: Title of the source article.
   - `quote`: A key factual statement or excerpt from that article.

Output MUST be strictly valid JSON matching this schema:
{
  "headline": "...",
  "summary": "...",
  "timeline": [
    {
      "timestamp": "YYYY-MM-DD HH:MM:SS",
      "event_description": "...",
      "source_name": "...",
      "source_url": "...",
      "source_title": "..."
    }
  ],
  "citations": [
    {
      "source_name": "...",
      "source_url": "...",
      "source_title": "...",
      "quote": "..."
    }
  ]
}

Rules:
- Respond in Thai (except proper names, sources, or English URLs).
- Chronological order for timeline (earliest to newest).
- Accurate citations back to the source articles.
- Return ONLY valid JSON, no markdown code block fences (no ```json)."""


RELEVANCE_GATE_SYSTEM_PROMPT = """You are a Senior News Verification and Relevance Gatekeeper for Thai News Intelligence.
Your task is to analyze candidate articles grouped into a news topic and strictly triage them into three categories:

1. `relevant_article_ids`: Articles reporting DIRECTLY on the central incident, core actors involved, and immediate factual developments.
2. `context_article_ids`: Articles providing political, historical, or background context (e.g., general parliamentary debates, censure motions, broader political power struggles) that mention key figures but are NOT about the specific incident itself.
3. `excluded_article_ids`: Articles that are completely off-topic, unrelated, or erroneously clustered.

You must also provide:
- `exclusion_reasons`: A dictionary mapping each context or excluded article_id to a concise Thai explanation of why it was categorized as context or excluded.

Output MUST be strictly valid JSON matching this schema:
{
  "relevant_article_ids": ["art_01"],
  "context_article_ids": ["art_23"],
  "excluded_article_ids": ["art_30"],
  "exclusion_reasons": {
    "art_23": "บริบทการเมือง: การอภิปรายไม่ไว้วางใจในสภาผู้แทนราษฎร",
    "art_30": "ข่าวนอกประเด็น: เนื้อหาไม่เกี่ยวข้องกับเหตุการณ์หลัก"
  }
}

Rules:
- Ground your triage strictly in the central incident stated in the title.
- Do NOT allow political background debates to dilute the direct incident evidence.
- Return ONLY valid JSON, no markdown code block fences (no ```json)."""


EVENT_PROGRESSION_SYSTEM_PROMPT = """You are an elite Senior Intelligence Analyst and News Verification Director.
Your task is NOT to write a generic summary of news articles.
Instead, you must construct an Evidence-Grounded Event Progression Model (แบบจำลองความคืบหน้าของเหตุการณ์จากหลักฐาน) from the structured evidence provided in JSON.

Your analytical goals:
1. Distinguish between what actually happened (Progression Timeline), what is independently corroborated (Confirmed Facts), what stakeholders dispute (Conflicts & Divergent Claims), and what is still unknown or blindspots (Unknowns & Uncertainties).
2. Ground every milestone and fact strictly in the provided evidence. Always cite supporting `evidence_ids` (e.g. ["art_01", "art_02"]).
3. NEVER assume two articles are independent confirmations if they cite the exact same press release or single quote. Do not state accusations or opinions as confirmed facts.
4. Separate the actual time an event occurred (`event_time`) from the time the news was published (`published_at`).
5. DETECT OUTLIER / IRRELEVANT ARTICLES: In macro-event topic clusters, sometimes an unrelated news article is accidentally grouped in by automated clustering. If any article in the input does NOT belong to the main real-world event/storyline, you MUST explicitly identify it in `irrelevant_articles` and state the exact reason why it is irrelevant.

Output MUST be strictly valid JSON matching this schema:
{
  "executive_summary": "2–3 sentence authoritative Thai executive briefing stating the core event, latest shift, and overall state.",
  "progression_timeline": [
    {
      "milestone_id": "m_01",
      "event_time": "YYYY-MM-DD HH:MM:SS or approximate time",
      "description": "Factual description of the milestone development in Thai",
      "evidence_ids": ["art_01"]
    }
  ],
  "confirmed_facts": [
    {
      "fact_id": "f_01",
      "fact": "Corroborated fact backed by evidence in Thai",
      "evidence_ids": ["art_01", "art_02"],
      "corroborating_sources": ["ThaiPBS", "Bangkok Post"]
    }
  ],
  "conflicts": [
    {
      "topic_in_dispute": "ประเด็นที่เห็นต่างหรือมีข้อโต้แย้งในเหตุการณ์",
      "status": "กำลังตรวจสอบ / ต่างฝ่ายต่างแถลงโต้แย้ง / ข้อกล่าวหาเบื้องต้น",
      "sides": [
        {
          "speaker": "ชื่อบุคคล หรือหน่วยงาน หรือกลุ่ม",
          "source": "สำนักข่าวที่รายงาน",
          "claim_type": "official_statement | accusation | opinion | forecast",
          "stance": "สรุปจุดยืนหรือข้อโต้แย้งสั้น ๆ ชัดเจน",
          "evidence_quote": "ข้อความอ้างอิงตรงจากหลักฐาน",
          "evidence_id": "art_01"
        }
      ]
    }
  ],
  "unknowns": [
    {
      "question": "คำถามสำคัญที่ยังไม่มีคำตอบหรือยังหาข้อสรุปไม่ได้",
      "why_unknown": "เหตุผลที่ยังสรุปไม่ได้ (เช่น ข้อมูลขัดแย้ง, รอผลชันสูตร/ผลสอบ, ยังไม่มีแถลง)",
      "pending_action": "เหตุการณ์หรือขั้นตอนที่จะชี้ขาดข้อเท็จจริงนี้ได้"
    }
  ],
  "irrelevant_articles": [
    {
      "article_id": "art_03",
      "source": "สำนักข่าว",
      "title": "หัวข้อข่าว",
      "reason": "เหตุผลที่ระบุว่าข่าวนี้นอกเรื่องหรือไม่เกี่ยวข้องกับประเด็นหลัก"
    }
  ]
}

Rules:
- Respond in Thai (except proper names, sources, or English terms).
- If there are no clear conflicts, provide an empty list for `conflicts`.
- If there are no irrelevant articles, provide an empty list `[]` for `irrelevant_articles`.
- If an article is unrelated, put it in `irrelevant_articles` and DO NOT include it in `confirmed_facts` or `progression_timeline`.
- Return ONLY valid JSON, no markdown code block fences (no ```json)."""


# ── Service Implementation ────────────────────────────────────────

class StoryPresentationService:
    """
    Presentation enrichment service generating Thai headline, summary,
    chronological development timeline, and source citations for top stories.

    Key Features:
    - LLM Separation: Zero influence on story membership or trending rank.
    - Tiered Model Cascade: Resilient multi-model fallback.
    - Composite Caching: Keyed by (story_id, updated_at). Metadata is not
      regenerated unless new articles are added to the story.
    - Zero-Crash Guarantee: Robust offline heuristic fallback ensuring
      clean presentations ready for HTTP 200 responses.
    """

    def __init__(
        self,
        client: CascadingLLMClient | OpenAI | None = None,
        models: list[str] | None = None,
        temperature: float = 0.2,
        news_repo: NewsRepositoryPort | None = None,
        cache_max_size: int = 500,
        cache_file: Path | None = None,
    ) -> None:
        self._temperature = temperature
        self._news_repo = news_repo
        self._cache_max_size = cache_max_size
        self._cache_file = cache_file or (getattr(settings, "DATA_DIR", Path("data")) / "presentation_cache.json")

        self._client: Any
        if isinstance(client, CascadingLLMClient):
            self._client = client
            self._cascading_client: CascadingLLMClient | None = client
            self._models = [t.model for t in client.targets]
        elif client is not None:
            self._client = client
            self._models = list(models) if models else list(settings.llm_cascade_models)
            self._cascading_client = CascadingLLMClient.from_client_and_models(
                client=client,
                models=self._models,
            )
        else:
            self._client = None
            self._cascading_client = None
            self._models = list(models) if models else list(settings.llm_cascade_models)

        # In-memory thread-safe presentation cache keyed by (story_id, updated_at)
        self._cache: dict[tuple[str, str], StoryPresentation] = {}
        self._disk_cache: dict[str, dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        self._load_disk_cache()

    def _load_disk_cache(self) -> None:
        """Load persistent presentation cache from disk JSON."""
        if not self._cache_file.exists():
            return
        try:
            content = self._cache_file.read_text(encoding="utf-8")
            if content.strip():
                data = json.loads(content)
                if isinstance(data, dict):
                    self._disk_cache = data
        except Exception as exc:
            logger.debug("Failed to read presentation_cache.json: %s", exc)

    def _save_disk_cache(self) -> None:
        """Atomically persist presentation cache to disk."""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=self._cache_file.parent,
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as tmp:
                json.dump(self._disk_cache, tmp, ensure_ascii=False, indent=2)
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, self._cache_file)
        except Exception as exc:
            logger.debug("Failed to persist presentation cache: %s", exc)

    @staticmethod
    def compute_sha256_fingerprint(
        target_id: str,
        articles: Sequence[dict[str, Any] | ArticleRecord],
        relations: list[str] | None = None,
        prompt_version: str = "1.0",
        model_name: str = "default",
        schema_version: str = "1.0",
    ) -> str:
        """Compute deterministic SHA-256 fingerprint on canonicalized inputs."""
        signatures: list[str] = []
        for a in articles:
            u = a.get("url") if isinstance(a, dict) else getattr(a, "url", "")
            t = a.get("title") if isinstance(a, dict) else getattr(a, "title", "")
            f = a.get("fetched_at") if isinstance(a, dict) else getattr(a, "fetched_at", "")
            signatures.append(f"{str(u or '').strip()}|{str(t or '').strip()[:60]}|{f or ''!s}")
        signatures.sort()

        canonical_dict = {
            "target_id": str(target_id).strip(),
            "articles": signatures,
            "relations": sorted(relations or []),
            "prompt_version": prompt_version,
            "model_name": model_name,
            "schema_version": schema_version,
        }
        raw_bytes = json.dumps(canonical_dict, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    @staticmethod
    def compute_articles_signature(articles: Sequence[dict[str, Any] | ArticleRecord]) -> str:
        """
        Compute a deterministic SHA-256 signature based solely on canonical article URLs/titles.
        This signature is 100% stable regardless of cluster_id, story_id, or event_id changes.
        """
        urls: list[str] = []
        for a in articles:
            u = a.get("url") if isinstance(a, dict) else getattr(a, "url", "")
            if u and str(u).strip():
                clean = str(u).strip().split("#")[0].rstrip("/").lower()
                urls.append(clean)
            else:
                t = a.get("title") if isinstance(a, dict) else getattr(a, "title", "")
                if t:
                    urls.append(f"title:{str(t).strip()[:80].lower()}")
        urls.sort()
        raw = "|".join(urls).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def find_cached_synthesis(
        self,
        event_id: str | None = None,
        articles: Sequence[dict[str, Any] | ArticleRecord] | None = None,
        title: str | None = None,
        require_metrics: bool = True,
        synthesis_cache_key: str | None = None,
    ) -> EventProgressionSynthesis | None:
        """
        Multi-tier cache lookup resilient to cluster_id re-grouping and shifting:
        0. Deterministic 24-hex synthesis_cache_key match
        1. Direct event_id match (f"synthesis_{event_id}")
        2. Content signature match (f"synthesis_sig_{articles_sig}")
        3. Jaccard / Overlap matching (>= 50% shared article URLs with any cached event)
        """
        with self._cache_lock:
            # 0. Deterministic 24-hex synthesis_cache_key match
            if synthesis_cache_key:
                entry = self._disk_cache.get(f"synth_key_{synthesis_cache_key}")
                if isinstance(entry, dict) and entry.get("data"):
                    try:
                        data = dict(entry["data"])
                        data["cached"] = True
                        return EventProgressionSynthesis.model_validate(data)
                    except Exception as err:
                        logger.debug("find_cached_synthesis: synthesis_cache_key validate failed: %s", err)

            # 1. Direct event_id match
            if event_id:
                cache_key = f"synthesis_{event_id}"
                entry = self._disk_cache.get(cache_key)
                if isinstance(entry, dict) and entry.get("data"):
                    is_consistent = True
                    if (
                        synthesis_cache_key
                        and entry.get("synthesis_cache_key")
                        and entry.get("synthesis_cache_key") != synthesis_cache_key
                    ):
                        is_consistent = False
                    if articles:
                        current_sig = self.compute_articles_signature(articles)
                        cached_sig = entry.get("articles_signature")
                        if cached_sig and cached_sig != current_sig:
                            is_consistent = False
                    if title and entry.get("title"):
                        cached_t = str(entry.get("title")).strip()
                        toks_c = set(_tokenize_thai_words(cached_t))
                        toks_cur = set(_tokenize_thai_words(title))
                        if toks_c and toks_cur and not (toks_c & toks_cur):
                            is_consistent = False
                    if is_consistent:
                        try:
                            data = dict(entry["data"])
                            if require_metrics and data.get("metrics") is None:
                                logger.debug("find_cached_synthesis: skipping legacy cache entry without metrics for %s", event_id)
                            else:
                                data["cached"] = True
                                return EventProgressionSynthesis.model_validate(data)
                        except Exception as err:
                            logger.debug("find_cached_synthesis: direct id validate failed: %s", err)

            # 2. Content signature match (independent of event_id!)
            if articles:
                articles_sig = self.compute_articles_signature(articles)
                sig_key = f"synthesis_sig_{articles_sig}"
                sig_entry = self._disk_cache.get(sig_key)
                if isinstance(sig_entry, dict) and sig_entry.get("data"):
                    try:
                        data = dict(sig_entry["data"])
                        if require_metrics and data.get("metrics") is None:
                            logger.debug("find_cached_synthesis: skipping legacy sig cache entry without metrics")
                        else:
                            data["cached"] = True
                            if event_id:
                                self._disk_cache[f"synthesis_{event_id}"] = sig_entry
                            return EventProgressionSynthesis.model_validate(data)
                    except Exception as err:
                        logger.debug("find_cached_synthesis: sig validate failed: %s", err)

                # 3. High Overlap matching (>= 75% overlap required to prevent cross-story collision)
                target_urls = set()
                for a in articles:
                    u = a.get("url") if isinstance(a, dict) else getattr(a, "url", "")
                    if u and str(u).strip():
                        target_urls.add(str(u).strip().split("#")[0].rstrip("/").lower())

                if target_urls:
                    best_match_entry = None
                    best_overlap_ratio = 0.0

                    for k, item in self._disk_cache.items():
                        if not k.startswith("synthesis_") or not isinstance(item, dict) or not item.get("data"):
                            continue
                        cached_urls = {
                            str(u).strip().split("#")[0].rstrip("/").lower()
                            for u in (item.get("article_urls") or [])
                            if u and str(u).strip()
                        }
                        if not cached_urls:
                            continue

                        intersection = target_urls & cached_urls
                        if not intersection:
                            continue

                        max_len = max(len(target_urls), len(cached_urls))
                        overlap_ratio = len(intersection) / max(1, max_len)

                        if overlap_ratio >= 0.75 and overlap_ratio > best_overlap_ratio:
                            if title and item.get("title"):
                                cached_t = str(item.get("title")).strip()
                                toks_c = set(_tokenize_thai_words(cached_t))
                                toks_cur = set(_tokenize_thai_words(title))
                                if toks_c and toks_cur and not (toks_c & toks_cur):
                                    continue
                            best_overlap_ratio = overlap_ratio
                            best_match_entry = item

                    if best_match_entry and best_match_entry.get("data"):
                        try:
                            data = dict(best_match_entry["data"])
                            if require_metrics and data.get("metrics") is None:
                                logger.debug("find_cached_synthesis: skipping legacy overlap cache entry without metrics")
                            else:
                                data["cached"] = True
                                if event_id:
                                    self._disk_cache[f"synthesis_{event_id}"] = best_match_entry
                                self._disk_cache[f"synthesis_sig_{articles_sig}"] = best_match_entry
                                self._save_disk_cache()
                                return EventProgressionSynthesis.model_validate(data)
                        except Exception as err:
                            logger.debug("find_cached_synthesis: overlap validate failed: %s", err)

        return None

    @property
    def client(self) -> Any:
        return self._client

    @property
    def models(self) -> list[str]:
        return list(self._models)

    @property
    def cache_size(self) -> int:
        with self._cache_lock:
            return len(self._cache)

    def clear_cache(self) -> None:
        """Clear presentation cache both in-memory and on disk."""
        with self._cache_lock:
            self._cache.clear()
            self._disk_cache.clear()
            self._save_disk_cache()

    def get_cached(self, story_id: str, updated_at: Any) -> StoryPresentation | None:
        """Lookup cached presentation for (story_id, updated_at)."""
        sid = str(story_id).strip()
        norm_ts = normalize_timestamp(updated_at)
        key = (sid, norm_ts)
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is not None:
                return entry.model_copy(update={"cached": True})

            # Check disk cache
            disk_entry = self._disk_cache.get(f"story_{sid}_{norm_ts}")
            if disk_entry and "presentation" in disk_entry:
                try:
                    loaded = StoryPresentation.model_validate(disk_entry["presentation"])
                    self._cache[key] = loaded
                    return loaded.model_copy(update={"cached": True})
                except Exception:
                    pass
        return None

    def set_cached(self, story_id: str, updated_at: Any, presentation: StoryPresentation) -> None:
        """Store presentation in cache for (story_id, updated_at) and persist to disk."""
        sid = str(story_id).strip()
        norm_ts = normalize_timestamp(updated_at)
        key = (sid, norm_ts)
        with self._cache_lock:
            if len(self._cache) >= self._cache_max_size:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key, None)
                self._disk_cache.pop(f"story_{oldest_key[0]}_{oldest_key[1]}", None)
            self._cache[key] = presentation

            self._disk_cache[f"story_{sid}_{norm_ts}"] = {
                "presentation": presentation.model_dump(mode="json"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_disk_cache()

    def present_macro_event(
        self,
        macro: MacroEventRecord,
        child_stories: list[StoryRecord],
        articles: Sequence[ArticleRecord | dict[str, Any]] | None = None,
    ) -> MacroEventRecord:
        """
        Synthesize overarching presentation for a MacroEventRecord storyline.
        Generates macro headline, multi-event summary, and chronological timeline.
        Uses SHA-256 fingerprint for persistent caching and cache invalidation.
        """
        resolved_articles: list[Any] = list(articles or [])
        if not resolved_articles and self._news_repo is not None:
            all_urls: list[str] = []
            for cs in child_stories:
                all_urls.extend(cs.article_urls)
            if all_urls:
                unique_urls = list(dict.fromkeys(all_urls))
                if hasattr(self._news_repo, "get_by_urls"):
                    resolved_articles = list(self._news_repo.get_by_urls(unique_urls))
                elif hasattr(self._news_repo, "load_news"):
                    u_set = set(unique_urls)
                    resolved_articles = [a for a in self._news_repo.load_news() if a.get("url") in u_set]

        # Format relations summary for fingerprint
        rel_strs = [
            f"{r.source_event_id}->{r.target_event_id}:{r.relation_type}"
            for r in macro.relations
        ]

        active_model = self._models[0] if self._models else "fallback"
        fingerprint = self.compute_sha256_fingerprint(
            target_id=macro.macro_event_id,
            articles=resolved_articles,
            relations=rel_strs,
            model_name=active_model,
        )

        with self._cache_lock:
            cached_macro = self._disk_cache.get(f"macro_{macro.macro_event_id}")
            if cached_macro and cached_macro.get("fingerprint") == fingerprint:
                macro.headline = cached_macro.get("headline")
                macro.summary = cached_macro.get("summary")
                if cached_macro.get("timeline"):
                    macro.timeline = [MacroTimelineEvent.model_validate(t) for t in cached_macro["timeline"]]
                macro.presentation_fingerprint = fingerprint
                macro.enriched_at = datetime.now(timezone.utc)
                return macro

        # Build timeline from child stories
        timeline_events: list[MacroTimelineEvent] = []
        for cs in sorted(child_stories, key=lambda s: s.first_article_at or s.created_at):
            ts_str = (cs.first_article_at or cs.created_at).strftime("%Y-%m-%d %H:%M:%S")
            h = cs.headline or cs.title
            s = cs.summary or f"เหตุการณ์ {cs.title} มีรายงานข่าว {cs.article_count} รายงาน"
            timeline_events.append(
                MacroTimelineEvent(
                    timestamp=ts_str,
                    event_id=cs.story_id,
                    headline=h,
                    summary=s,
                    source_outlets=list(cs.outlets),
                    citation=None,
                )
            )

        # Overview headline and summary
        macro_headline = macro.headline or (f"เกาะติดมหากาพย์ข่าว: {macro.title}")
        outlets_set = sorted({out for cs in child_stories for out in cs.outlets if out})
        outlets_str = " และ ".join(outlets_set[:3]) if outlets_set else "สำนักข่าวชั้นนำ"
        child_count = len(child_stories)
        macro_summary = (
            f"ติดตามสถานการณ์ความคืบหน้าต่อเนื่องในประเด็น {macro.title} "
            f"ครอบคลุม {child_count} เหตุการณ์ย่อย รวบรวมรายงานจาก {outlets_str}"
        )

        macro.headline = macro_headline
        macro.summary = macro_summary
        macro.timeline = timeline_events
        macro.presentation_fingerprint = fingerprint
        macro.enriched_at = datetime.now(timezone.utc)

        with self._cache_lock:
            self._disk_cache[f"macro_{macro.macro_event_id}"] = {
                "fingerprint": fingerprint,
                "headline": macro_headline,
                "summary": macro_summary,
                "timeline": [t.model_dump(mode="json") for t in timeline_events],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_disk_cache()

        return macro

    # ── Event Progression Synthesis (3-Layer Architecture) ───────────

    def evaluate_event_relevance(
        self,
        event_id: str,
        title: str,
        articles: Sequence[ArticleRecord | dict[str, Any]],
        allow_llm: bool = True,
    ) -> RelevanceGateResult:
        """
        Stage 1: Evaluate candidate articles and triage into direct relevant evidence,
        political/situational context, and excluded off-topic articles.
        Guarantees deterministic heuristic fallback when LLM is unavailable or offline.
        """
        if not articles:
            return RelevanceGateResult(
                event_id=event_id,
                relevant_article_ids=[],
                context_article_ids=[],
                excluded_article_ids=[],
                exclusion_reasons={},
            )

        ordered_articles = _normalize_and_sort_candidate_articles(articles)
        candidate_items: list[dict[str, Any]] = []
        for idx, art in enumerate(ordered_articles, start=1):
            if isinstance(art, dict):
                art_id = str(art.get("article_id") or f"art_{idx:02d}")
                t = str(art.get("title") or "").strip()
                s = str(art.get("summary") or "").strip()
                src = str(art.get("source") or "สำนักข่าว").strip()
                u = str(art.get("url") or "").strip()
                ts = str(art.get("fetched_at") or art.get("published_at") or "").strip()
                is_ctx = bool(art.get("is_context", False))
                is_excl = bool(art.get("is_excluded", False))
                is_rel = bool(art.get("is_relevant", False))
            else:
                art_id = str(getattr(art, "article_id", None) or f"art_{idx:02d}")
                t = getattr(art, "title", "")
                s = getattr(art, "summary", "")
                src = getattr(art, "source", "สำนักข่าว")
                u = getattr(art, "url", "")
                ts = str(getattr(art, "fetched_at", "") or getattr(art, "published_at", "") or "")
                is_ctx = bool(getattr(art, "is_context", False))
                is_excl = bool(getattr(art, "is_excluded", False))
                is_rel = bool(getattr(art, "is_relevant", False))

            candidate_items.append({
                "article_id": art_id,
                "title": t,
                "summary": s,
                "source": src,
                "url": u,
                "published_at": ts,
                "is_context": is_ctx,
                "is_excluded": is_excl,
                "is_relevant": is_rel,
            })

        all_ids = [item["article_id"] for item in candidate_items]

        # Multi-sport roundup gate: Sports collections combine distinct matches & disciplines.
        # Genuine sports reports must not be discarded as off-topic outliers.
        if _check_is_sports_collection(title, candidate_items):
            return RelevanceGateResult(
                event_id=event_id,
                relevant_article_ids=all_ids,
                context_article_ids=[],
                excluded_article_ids=[],
                exclusion_reasons={},
            )

        # 1. Attempt LLM Gatekeeper if allowed
        if allow_llm and self._should_attempt_llm():
            prompt_candidates = [
                {
                    "article_id": item["article_id"],
                    "title": item["title"],
                    "summary": item["summary"][:200],
                    "source": item["source"],
                    "published_at": item["published_at"],
                }
                for item in candidate_items
            ]
            user_content = (
                f"โปรดจำแนกความเกี่ยวข้องของข่าว (Event Relevance Gate) สำหรับเหตุการณ์: '{title}' (ID: {event_id})\n\n"
                f"รายการข่าวที่ต้องคัดกรอง ({len(candidate_items)} ข่าว):\n"
                f"{json.dumps(prompt_candidates, ensure_ascii=False, indent=2)}"
            )

            def _parse_relevance(raw_text: str) -> RelevanceGateResult:
                parsed = self._parse_llm_json(raw_text)
                if not isinstance(parsed, dict):
                    raise TypeError("Malformed relevance gate JSON response.")
                if "relevant_article_ids" not in parsed:
                    raise ValueError("Malformed relevance gate response: missing 'relevant_article_ids'")
                rel_ids = [str(x) for x in parsed.get("relevant_article_ids", []) if str(x) in all_ids]
                ctx_ids = [str(x) for x in parsed.get("context_article_ids", []) if str(x) in all_ids]
                excl_ids = [str(x) for x in parsed.get("excluded_article_ids", []) if str(x) in all_ids]
                reasons = {
                    str(k): str(v)
                    for k, v in parsed.get("exclusion_reasons", {}).items()
                    if str(k) in all_ids
                }

                accounted = set(rel_ids) | set(ctx_ids) | set(excl_ids)
                for cid in all_ids:
                    if cid not in accounted:
                        excl_ids.append(cid)
                        reasons[cid] = "ไม่ได้ระบุเป็นหลักฐานตรงของเหตุการณ์โดยระบบจำแนก"
                return RelevanceGateResult(
                    event_id=event_id,
                    relevant_article_ids=rel_ids,
                    context_article_ids=ctx_ids,
                    excluded_article_ids=excl_ids,
                    exclusion_reasons=reasons,
                )

            try:
                assert self._cascading_client is not None
                res = self._cascading_client.complete(
                    messages=[
                        {"role": "system", "content": RELEVANCE_GATE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    validator=_parse_relevance,
                    temperature=0.1,
                )
                if isinstance(res.parsed, RelevanceGateResult):
                    return res.parsed
            except Exception as exc:
                logger.debug("evaluate_event_relevance cascade error: %s", exc)

        # 2. Robust Deterministic Heuristic Gatekeeper
        return self._evaluate_event_relevance_heuristic(event_id, title, candidate_items)

    def _evaluate_event_relevance_heuristic(
        self,
        event_id: str,
        title: str,
        candidate_items: list[dict[str, Any]],
    ) -> RelevanceGateResult:
        """
        Deterministic heuristic triage for candidate articles.
        Separates direct incident evidence, political context (e.g. censure debate),
        and excluded off-topic outliers.
        """
        relevant_ids: list[str] = []
        context_ids: list[str] = []
        excluded_ids: list[str] = []
        reasons: dict[str, str] = {}

        # Tokenize event title
        title_raw_tokens = _tokenize_thai_words(title)
        title_tokens = [w for w in title_raw_tokens if w not in _RELEVANCE_STOPWORDS and len(w) > 1]
        core_incident_tokens = [
            w for w in title_tokens
            if not any(ck in w for ck in _RELEVANCE_CONTEXT_KEYWORDS) and len(w) > 1
        ]
        if not core_incident_tokens:
            core_incident_tokens = list(title_tokens)

        for item in candidate_items:
            art_id = item["article_id"]

            # Explicit flags take precedence if provided
            if item.get("is_relevant"):
                relevant_ids.append(art_id)
                continue
            if item.get("is_context"):
                context_ids.append(art_id)
                reasons[art_id] = "บริบทการเมือง: การอภิปรายไม่ไว้วางใจหรือเวทีสภาที่แวดล้อมเหตุการณ์"
                continue
            if item.get("is_excluded"):
                excluded_ids.append(art_id)
                reasons[art_id] = "ข่าวนอกประเด็น: เนื้อหาไม่เกี่ยวข้องกับเหตุการณ์หลัก"
                continue

            content = f"{item['title']} {item['summary']}".lower()
            art_tokens = set(_tokenize_thai_words(content))

            has_context = any(ck in content for ck in _RELEVANCE_CONTEXT_KEYWORDS)
            matched_incident = [
                w for w in core_incident_tokens
                if w in art_tokens or (len(w) >= 5 and w in content)
            ]
            matched_title = [
                w for w in title_tokens
                if w in art_tokens or (len(w) >= 5 and w in content)
            ]

            # 1. Check if article is political context (mentions censure/parliament debate but not the specific incident)
            if has_context and not matched_incident:
                context_ids.append(art_id)
                reasons[art_id] = "บริบทการเมือง: ข่าวการอภิปรายไม่ไว้วางใจหรือเวทีสภาที่เกิดขึ้นแวดล้อมเหตุการณ์"
            # 2. Check if article is off-topic:
            # - shares 0 tokens with title, OR
            # - only matches generic/broad tokens without matching any core incident tokens
            elif len(candidate_items) > 2 and (
                (title_tokens and len(matched_title) == 0)
                or (core_incident_tokens and len(matched_incident) == 0)
            ):
                excluded_ids.append(art_id)
                reasons[art_id] = "ข่าวนอกประเด็น: เนื้อหาและหัวข้อข่าวไม่มีคำสำคัญเฉพาะเจาะจงร่วมกับเหตุการณ์หลัก"
            # 3. Direct incident evidence
            else:
                relevant_ids.append(art_id)

        # Honest accounting: If 0 articles match, record all candidates as excluded with reasons
        if not relevant_ids and candidate_items:
            for item in candidate_items:
                aid = item["article_id"]
                if aid not in context_ids and aid not in excluded_ids:
                    excluded_ids.append(aid)
                    reasons[aid] = "ข่าวนอกประเด็น: เนื้อหาข่าวไม่สอดคล้องกับเหตุการณ์ในพาดหัว"

        return RelevanceGateResult(
            event_id=event_id,
            relevant_article_ids=relevant_ids,
            context_article_ids=context_ids,
            excluded_article_ids=excluded_ids,
            exclusion_reasons=reasons,
        )

    def validate_dossier_citations(
        self,
        synthesis: EventProgressionSynthesis | dict[str, Any],
        allowed_article_ids: Sequence[str] | set[str],
        disallowed_article_ids: Sequence[str] | set[str] | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Stage 3 Output Validator: Verifies that every milestone, confirmed fact,
        and conflict stance strictly cites ONLY article IDs from allowed_article_ids,
        and NEVER cites any ID from disallowed_article_ids (irrelevant/context articles).
        Returns (is_valid, list_of_errors).
        """
        allowed = {str(aid).strip().lower() for aid in allowed_article_ids}
        disallowed = {str(did).strip().lower() for did in (disallowed_article_ids or [])}
        errors: list[str] = []

        if isinstance(synthesis, EventProgressionSynthesis):
            timeline = synthesis.progression_timeline
            facts = synthesis.confirmed_facts
            conflicts = synthesis.conflicts
            if not disallowed:
                disallowed = {
                    str(irr.article_id).strip().lower()
                    for irr in synthesis.irrelevant_articles
                    if getattr(irr, "article_id", None)
                }
        else:
            timeline = synthesis.get("progression_timeline") or []
            facts = synthesis.get("confirmed_facts") or []
            conflicts = synthesis.get("conflicts") or []
            if not disallowed:
                disallowed = {
                    str(irr.get("article_id") or irr.get("id") or "").strip().lower()
                    for irr in (synthesis.get("irrelevant_articles") or [])
                    if isinstance(irr, dict)
                }

        for m in timeline:
            m_id = getattr(m, "milestone_id", "") if not isinstance(m, dict) else m.get("milestone_id", "")
            ev_ids = getattr(m, "evidence_ids", []) if not isinstance(m, dict) else m.get("evidence_ids", [])
            for eid in ev_ids:
                clean_eid = str(eid).strip().lower()
                if clean_eid not in allowed:
                    errors.append(f"Milestone '{m_id}' cited disallowed article ID '{eid}'")
                elif clean_eid in disallowed:
                    errors.append(f"Milestone '{m_id}' cited excluded/irrelevant article ID '{eid}'")

        for f in facts:
            f_id = getattr(f, "fact_id", "") if not isinstance(f, dict) else f.get("fact_id", "")
            ev_ids = getattr(f, "evidence_ids", []) if not isinstance(f, dict) else f.get("evidence_ids", [])
            for eid in ev_ids:
                clean_eid = str(eid).strip().lower()
                if clean_eid not in allowed:
                    errors.append(f"Fact '{f_id}' cited disallowed article ID '{eid}'")
                elif clean_eid in disallowed:
                    errors.append(f"Fact '{f_id}' cited excluded/irrelevant article ID '{eid}'")

        for c in conflicts:
            sides = getattr(c, "sides", []) if not isinstance(c, dict) else c.get("sides", [])
            for s in sides:
                eid = getattr(s, "evidence_id", "") if not isinstance(s, dict) else s.get("evidence_id", "")
                if eid:
                    clean_eid = str(eid).strip().lower()
                    if clean_eid not in allowed:
                        errors.append(f"Conflict stance cited disallowed article ID '{eid}'")
                    elif clean_eid in disallowed:
                        errors.append(f"Conflict stance cited excluded/irrelevant article ID '{eid}'")

        return (len(errors) == 0, errors)

    def verify_headline_evidence_alignment(
        self,
        title: str,
        relevant_articles: Sequence[Any],
    ) -> tuple[bool, list[str], str]:
        """
        Layer 3 Pre-Synthesis Guardrail:
        Verifies that surviving candidate articles actually align with the incident in the headline.
        Prevents synthesizing unrelated events (e.g. Temasek startup funding under a Sri Sakhon shooting headline).
        Returns:
        - is_aligned: bool
        - aligned_article_ids: list[str]
        - reason: str
        """
        if not relevant_articles:
            return False, [], "ไม่มีข่าวที่เกี่ยวข้องกับเหตุการณ์"

        clean_title = clean_headline_date_suffix(title)
        title_tokens = _tokenize_thai_words(clean_title)
        core_incident_tokens = [
            w for w in title_tokens
            if not any(ck in w for ck in _RELEVANCE_CONTEXT_KEYWORDS)
        ]
        if not core_incident_tokens:
            core_incident_tokens = list(title_tokens)

        # Multi-sport roundup allows broad pairing across sports disciplines
        if _check_is_sports_collection(title, relevant_articles):
            all_ids = [
                str(a.get("article_id") if isinstance(a, dict) else getattr(a, "article_id", f"art_{i:02d}"))
                for i, a in enumerate(relevant_articles, 1)
            ]
            return True, all_ids, "Sports collection: multi-discipline alignment accepted"

        aligned_ids: list[str] = []
        for idx, art in enumerate(relevant_articles, start=1):
            art_id = str(art.get("article_id") if isinstance(art, dict) else getattr(art, "article_id", f"art_{idx:02d}"))
            t = str(art.get("title") if isinstance(art, dict) else getattr(art, "title", ""))
            s = str(art.get("summary") if isinstance(art, dict) else getattr(art, "summary", ""))
            content = f"{t} {s}".lower()
            art_tokens = set(_tokenize_thai_words(content))
            matched = [
                w for w in core_incident_tokens
                if w in art_tokens or (len(w) >= 5 and w in content)
            ]
            if matched:
                aligned_ids.append(art_id)

        if not aligned_ids:
            return False, [], "ไม่มีข่าวใดในชุดหลักฐานที่สอดคล้องกับพาดหัวเหตุการณ์"

        return True, aligned_ids, f"พบข่าวที่สอดคล้องกับพาดหัว {len(aligned_ids)} รายการ"

    def _log_pipeline_diagnostic_trace(
        self,
        event_id: str,
        title: str,
        candidate_articles: Sequence[Any],
        gate_result: RelevanceGateResult,
        aligned_ids: Sequence[str],
        synthesis: EventProgressionSynthesis,
    ) -> None:
        """
        5-Step Pipeline Diagnostic Logger (Observability)
        Logs structured trace across all 3 layers of event verification.
        """
        candidates_summary = [
            {
                "id": str(a.get("article_id") if isinstance(a, dict) else getattr(a, "article_id", f"art_{i:02d}")),
                "source": str(a.get("source") if isinstance(a, dict) else getattr(a, "source", "สำนักข่าว")),
                "title": str(a.get("title") if isinstance(a, dict) else getattr(a, "title", ""))[:60],
            }
            for i, a in enumerate(candidate_articles, 1)
        ]
        trace_data = {
            "step_1_identity": {
                "event_id": event_id,
                "title": title,
                "candidates_count": len(candidate_articles),
            },
            "step_2_candidates": candidates_summary[:10],
            "step_3_exclusions": {
                "context_count": len(gate_result.context_article_ids),
                "excluded_count": len(gate_result.excluded_article_ids),
                "reasons": gate_result.exclusion_reasons,
            },
            "step_4_alignment": {
                "relevant_count": len(gate_result.relevant_article_ids),
                "aligned_count": len(aligned_ids),
                "is_single_source": synthesis.is_single_source,
            },
            "step_5_synthesis": {
                "status": synthesis.synthesis_status,
                "message": synthesis.status_message,
                "milestones": len(synthesis.progression_timeline),
                "facts": len(synthesis.confirmed_facts),
            },
        }
        logger.info(
            "[PIPELINE_TRACE] Event '%s' (%s): status=%s, aligned=%d/%d candidates",
            title[:40], event_id, synthesis.synthesis_status, len(aligned_ids), len(candidate_articles)
        )
        logger.debug("[PIPELINE_TRACE_DETAIL] %s", trace_data)

    def synthesize_event_progression(
        self,
        event_id: str,
        title: str,
        articles: Sequence[ArticleRecord | dict[str, Any]],
        allow_llm: bool = True,
        force_refresh: bool = False,
    ) -> EventProgressionSynthesis:
        """
        Synthesize an evidence-grounded Event Progression Intelligence Model
        from member articles (Layer 1: Evidence -> Layer 2: Synthesis -> Layer 3: Executive Dossier).
        Three-stage pipeline with Headline-Evidence Alignment Guardrail:
        Stage 1: Event Relevance Gate triages articles into relevant evidence, political context, and excluded outliers.
        Stage 2: Headline-Evidence Alignment verifies candidate congruence. If 0 align -> halt; if 1 -> single_source.
        Stage 3: LLM Progression Synthesis receives ONLY aligned relevant evidence articles.
        Stage 4: Output Validator enforces citation integrity via Hard Reject + Bounded Retry + Fallback.
        Cached by (event_id, fingerprint) with 100% resilient heuristic fallback.
        """
        fingerprint = self.compute_sha256_fingerprint(event_id, articles)
        cache_key = f"synthesis_{event_id}"

        # Compute deterministic cluster fingerprint and synthesis cache key
        raw_article_urls = [
            str(a.get("url") if isinstance(a, dict) else getattr(a, "url", ""))
            for a in articles
        ]
        cluster_fp = compute_cluster_fingerprint(raw_article_urls)
        dict_articles = [
            a if isinstance(a, dict) else a.model_dump()
            for a in articles
        ]
        synth_cache_key = compute_synthesis_cache_key(event_id, cluster_fp, dict_articles)

        # 1. Check multi-tier disk / in-memory cache (event_id, content signature, overlap matching)
        if not force_refresh:
            cached = self.find_cached_synthesis(
                event_id=event_id,
                articles=articles,
                title=title,
                synthesis_cache_key=synth_cache_key,
            )
            if cached is not None:
                return cached

        # 2. Stage 1: Event Relevance Gate Triage
        ordered_articles = _normalize_and_sort_candidate_articles(articles)
        gate_result = self.evaluate_event_relevance(
            event_id=event_id,
            title=title,
            articles=ordered_articles,
            allow_llm=allow_llm,
        )

        # Build candidate item index with stable article IDs
        candidate_articles_by_id: dict[str, Any] = {}
        for idx, a in enumerate(ordered_articles, start=1):
            existing_id = (
                a.get("article_id") if isinstance(a, dict) else getattr(a, "article_id", None)
            )
            art_id = existing_id or f"art_{idx:02d}"
            if isinstance(a, dict):
                a_copy = dict(a)
                a_copy["article_id"] = art_id
                candidate_articles_by_id[art_id] = a_copy
            else:
                candidate_articles_by_id[art_id] = a

        candidate_publishers: set[str] = {
            str(a.get("source") if isinstance(a, dict) else getattr(a, "source", "") or "").strip()
            for a in articles
            if str(a.get("source") if isinstance(a, dict) else getattr(a, "source", "") or "").strip()
        }

        # Construct PoliticalContextItem and IrrelevantArticle lists from gate results
        political_contexts: list[PoliticalContextItem] = []
        for cid in gate_result.context_article_ids:
            art = candidate_articles_by_id.get(cid)
            if art:
                t = str((art.get("title") if isinstance(art, dict) else getattr(art, "title", "")) or "")
                s = str((art.get("summary") if isinstance(art, dict) else getattr(art, "summary", "")) or "")
                src = str((art.get("source") if isinstance(art, dict) else getattr(art, "source", "สำนักข่าว")) or "สำนักข่าว")
                reason = str(gate_result.exclusion_reasons.get(cid, "บริบทการเมืองแวดล้อมเหตุการณ์"))
                political_contexts.append(
                    PoliticalContextItem(
                        article_id=cid,
                        source=src,
                        title=t,
                        context_summary=s or t,
                        relation_to_event=reason,
                    )
                )

        irrelevant_articles: list[IrrelevantArticle] = []
        for xid in gate_result.excluded_article_ids:
            art = candidate_articles_by_id.get(xid)
            if art:
                t = str((art.get("title") if isinstance(art, dict) else getattr(art, "title", "")) or "")
                src = str((art.get("source") if isinstance(art, dict) else getattr(art, "source", "สำนักข่าว")) or "สำนักข่าว")
                reason = str(gate_result.exclusion_reasons.get(xid, "ข่าวนอกประเด็นหลัก"))
                irrelevant_articles.append(
                    IrrelevantArticle(
                        article_id=xid,
                        source=src,
                        title=t,
                        reason=reason,
                    )
                )

        initial_relevant = [
            candidate_articles_by_id[aid]
            for aid in gate_result.relevant_article_ids
            if aid in candidate_articles_by_id
        ]

        # 3. Layer 3 Alignment Guardrail: Verify Candidate-Headline Congruence
        is_aligned, aligned_ids, alignment_reason = self.verify_headline_evidence_alignment(title, initial_relevant)

        # ── Case 1: 0 articles aligned with headline -> Halt Synthesis ──
        if not is_aligned or len(aligned_ids) == 0:
            logger.warning(
                "synthesize_event_progression: Candidate mismatch halted for event_id=%s, title='%s'. %s",
                event_id, title, alignment_reason,
            )
            halted_status_message = (
                "ระบบระงับการสังเคราะห์อัตโนมัติ: ชุดข่าวที่รวบรวมได้ (Candidate Set) "
                "ไม่สอดคล้องกับเหตุการณ์ในพาดหัว เพื่อป้องกันการสังเคราะห์ข้อมูลผิดเรื่อง"
            )
            dossier_metrics = DossierMetrics(
                candidate_count=len(articles),
                excluded_count=len(articles),
                synthesized_evidence_count=0,
                candidate_publishers_count=len(candidate_publishers),
                synthesized_publishers_count=0,
                synthesized_publishers=[],
                synthesis_status="halted_mismatch",
                status_message=halted_status_message,
            )
            # Create a clean halted synthesis without hallucinations
            halted_synth = EventProgressionSynthesis(
                event_id=event_id,
                executive_summary="",
                progression_timeline=[],
                confirmed_facts=[],
                conflicts=[],
                unknowns=[],
                irrelevant_articles=irrelevant_articles,
                political_contexts=political_contexts,
                metrics=dossier_metrics,
                synthesis_status="halted_mismatch",
                status_message=halted_status_message,
                is_single_source=False,
                is_fallback=True,
                cached=False,
                generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            )
            self._log_pipeline_diagnostic_trace(
                event_id=event_id,
                title=title,
                candidate_articles=ordered_articles,
                gate_result=gate_result,
                aligned_ids=[],
                synthesis=halted_synth,
            )
            return halted_synth

        # Restrict relevant_articles strictly to aligned ones
        relevant_articles = [
            candidate_articles_by_id[aid]
            for aid in aligned_ids
            if aid in candidate_articles_by_id
        ]
        relevant_ids_set = set(aligned_ids)

        is_single_source = len(relevant_articles) == 1
        synthesis_status_val: Literal["synthesized", "single_source"] = (
            "single_source" if is_single_source else "synthesized"
        )
        single_source_msg = (
            "สรุปจากแหล่งข่าวเดียว: ข้อมูลอ้างอิงจากรายงานของสำนักข่าวเพียงแหล่งเดียว "
            "ยังไม่สามารถเปรียบเทียบหรือยืนยันข้อมูลตรงกันทุกสื่อได้"
            if is_single_source else ""
        )

        synthesized_publishers_set: set[str] = {
            str(a.get("source") if isinstance(a, dict) else getattr(a, "source", "") or "").strip()
            for a in relevant_articles
            if str(a.get("source") if isinstance(a, dict) else getattr(a, "source", "") or "").strip()
        }
        synthesized_publishers = sorted(synthesized_publishers_set)

        dossier_metrics = DossierMetrics(
            candidate_count=len(articles),
            excluded_count=len(articles) - len(relevant_articles),
            synthesized_evidence_count=len(relevant_articles),
            candidate_publishers_count=len(candidate_publishers),
            synthesized_publishers_count=len(synthesized_publishers),
            synthesized_publishers=synthesized_publishers,
            synthesis_status=synthesis_status_val,
            status_message=single_source_msg,
        )

        # 4. Extract structured evidence payload ONLY for aligned evidence articles
        evidence_payload = EvidenceExtractor.build_payload(
            event_id=event_id,
            title=title,
            articles=relevant_articles,
        )

        # 5. Attempt LLM Synthesis (Layer 2) with Stage 3 Output Validator
        synthesis: EventProgressionSynthesis | None = None
        if allow_llm and self._should_attempt_llm() and evidence_payload.articles:
            payload_json = evidence_payload.model_dump_json(indent=2)
            single_source_directive = (
                "\n\n[ข้อกำหนดสำคัญ]: มีแหล่งข่าวเพียงแหล่งเดียว ห้ามใช้คำว่า 'ทุกสื่อยืนยันตรงกัน' "
                "หรือสรุปว่าสำนักข่าวหลายแห่งเห็นพ้อง ให้ระบุชัดเจนว่าเป็นรายงานจากแหล่งข่าวนั้น"
                if is_single_source else ""
            )
            user_content = (
                f"โปรดวิเคราะห์หลักฐานข่าวและสร้างแบบจำลองความคืบหน้าของเหตุการณ์ (Event Progression Synthesis) "
                f"สำหรับเหตุการณ์: '{title}' (ID: {event_id}){single_source_directive}\n\n"
                f"ชุดข้อมูลหลักฐานเฉพาะที่ผ่านเกณฑ์ (Evidence Input JSON):\n{payload_json}"
            )

            disallowed_ids_set = {str(irr.article_id).strip().lower() for irr in irrelevant_articles} | {
                str(ctx.article_id).strip().lower() for ctx in political_contexts
            }

            def _parse_synthesis(raw_text: str) -> dict[str, Any]:
                parsed_dict = self._parse_llm_json(raw_text)
                if parsed_dict is None or not isinstance(parsed_dict, dict):
                    raise ValueError("Malformed dossier synthesis JSON.")
                is_valid, errors = self.validate_dossier_citations(
                    parsed_dict,
                    allowed_article_ids=relevant_ids_set,
                    disallowed_article_ids=disallowed_ids_set,
                )
                if not is_valid:
                    raise ValueError(f"Citation validation failed: {errors}")
                return parsed_dict

            parsed: dict[str, Any] | None = None
            try:
                assert self._cascading_client is not None
                res = self._cascading_client.complete(
                    messages=[
                        {"role": "system", "content": EVENT_PROGRESSION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    validator=_parse_synthesis,
                    temperature=self._temperature,
                )
                if isinstance(res.parsed, dict):
                    parsed = res.parsed
            except Exception as exc:
                logger.warning("synthesize_event_progression cascade failed: %s", exc)

            if parsed is not None:
                parsed["event_id"] = event_id
                parsed["is_fallback"] = False
                parsed["cached"] = False
                parsed["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                parsed["synthesis_status"] = synthesis_status_val
                parsed["is_single_source"] = is_single_source
                parsed["status_message"] = single_source_msg
                parsed["metrics"] = dossier_metrics.model_dump(mode="json")
                parsed["political_contexts"] = [p.model_dump(mode="json") for p in political_contexts]
                if not parsed.get("irrelevant_articles"):
                    parsed["irrelevant_articles"] = [i.model_dump(mode="json") for i in irrelevant_articles]
                else:
                    existing_excl_ids = {
                        str(irr.get("article_id") or irr.get("id") or "").strip().lower()
                        for irr in parsed["irrelevant_articles"]
                        if isinstance(irr, dict)
                    }
                    for irr in irrelevant_articles:
                        if irr.article_id.lower() not in existing_excl_ids:
                            parsed["irrelevant_articles"].append(irr.model_dump(mode="json"))

                synthesis = EventProgressionSynthesis.model_validate(parsed)

        # 6. Deterministic Heuristic Fallback if LLM disabled, failed, or hard-rejected
        if synthesis is None:
            synthesis = self._build_fallback_event_synthesis(
                event_id=event_id,
                title=title,
                articles=relevant_articles,
                payload=evidence_payload,
                fingerprint=fingerprint,
                metrics=dossier_metrics,
                political_contexts=political_contexts,
                irrelevant_articles=irrelevant_articles,
            )
            synthesis.synthesis_status = synthesis_status_val
            synthesis.is_single_source = is_single_source
            synthesis.status_message = single_source_msg

        # 6.1 Strict Mutual Exclusion Enforcement: Ensure 0 overlap between timeline/facts and irrelevant articles
        excluded_ids_set = {str(irr.article_id).strip().lower() for irr in synthesis.irrelevant_articles} | {
            str(ctx.article_id).strip().lower() for ctx in synthesis.political_contexts
        }
        if excluded_ids_set:
            # Strip excluded IDs from timeline milestones
            cleaned_timeline: list[ProgressionMilestone] = []
            for m in synthesis.progression_timeline:
                clean_evs = [eid for eid in m.evidence_ids if str(eid).strip().lower() not in excluded_ids_set]
                if clean_evs:
                    m.evidence_ids = clean_evs
                    cleaned_timeline.append(m)
            synthesis.progression_timeline = cleaned_timeline

            # Strip excluded IDs from confirmed facts
            cleaned_facts: list[ConfirmedFact] = []
            for f in synthesis.confirmed_facts:
                clean_evs = [eid for eid in f.evidence_ids if str(eid).strip().lower() not in excluded_ids_set]
                if clean_evs:
                    f.evidence_ids = clean_evs
                    cleaned_facts.append(f)
            synthesis.confirmed_facts = cleaned_facts

            # Strip excluded IDs from conflict stances
            cleaned_conflicts: list[DisputeIssue] = []
            for c in synthesis.conflicts:
                clean_sides = [s for s in c.sides if not s.evidence_id or str(s.evidence_id).strip().lower() not in excluded_ids_set]
                if clean_sides:
                    c.sides = clean_sides
                    cleaned_conflicts.append(c)
            synthesis.conflicts = cleaned_conflicts

            # Sync DossierMetrics to exact clean counts
            if synthesis.metrics is not None:
                synthesis.metrics.candidate_count = len(articles)
                synthesis.metrics.excluded_count = len(synthesis.irrelevant_articles) + len(synthesis.political_contexts)
                synthesis.metrics.synthesized_evidence_count = max(0, len(articles) - synthesis.metrics.excluded_count)

        # 7. Diagnostic Observability Trace
        self._log_pipeline_diagnostic_trace(
            event_id=event_id,
            title=title,
            candidate_articles=ordered_articles,
            gate_result=gate_result,
            aligned_ids=aligned_ids,
            synthesis=synthesis,
        )

        # 8. Persist to cache (both by event_id AND by content signature and URL list)
        articles_sig = self.compute_articles_signature(articles)
        article_urls = [
            str(a.get("url") if isinstance(a, dict) else getattr(a, "url", "")).strip()
            for a in articles
            if (a.get("url") if isinstance(a, dict) else getattr(a, "url", ""))
        ]

        cache_entry = {
            "fingerprint": fingerprint,
            "articles_signature": articles_sig,
            "synthesis_cache_key": synth_cache_key,
            "article_urls": article_urls,
            "title": title,
            "event_id": event_id,
            "data": synthesis.model_dump(mode="json"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with self._cache_lock:
            self._disk_cache[cache_key] = cache_entry
            self._disk_cache[f"synthesis_sig_{articles_sig}"] = cache_entry
            if synth_cache_key:
                self._disk_cache[f"synth_key_{synth_cache_key}"] = cache_entry
            self._save_disk_cache()

        return synthesis

    async def synthesize_event_progression_async(
        self,
        event_id: str,
        title: str,
        articles: Sequence[ArticleRecord | dict[str, Any]],
        allow_llm: bool = True,
        force_refresh: bool = False,
    ) -> EventProgressionSynthesis:
        """Asynchronous non-blocking wrapper for synthesize_event_progression."""
        return await asyncio.to_thread(
            self.synthesize_event_progression,
            event_id,
            title,
            articles,
            allow_llm,
            force_refresh,
        )

    def _build_fallback_event_synthesis(
        self,
        event_id: str,
        title: str,
        articles: Sequence[Any],
        payload: Any,
        fingerprint: str = "",
        metrics: DossierMetrics | None = None,
        political_contexts: list[PoliticalContextItem] | None = None,
        irrelevant_articles: list[IrrelevantArticle] | None = None,
    ) -> EventProgressionSynthesis:
        """
        Deterministic heuristic fallback for Event Progression Synthesis.
        Guarantees 100% Zero-Crash and produces a structured 4-section intelligence dossier
        even when LLM is offline or disabled.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if not payload.articles:
            return EventProgressionSynthesis(
                event_id=event_id,
                executive_summary=f"รายงานสรุปความคืบหน้าสถานการณ์: {title}",
                progression_timeline=[],
                confirmed_facts=[],
                conflicts=[],
                unknowns=[
                    UnknownPoint(
                        question="รายละเอียดและพัฒนาการเพิ่มเติมของเหตุการณ์",
                        why_unknown="อยู่ระหว่างการรวบรวมหลักฐานและรายงานจากสำนักข่าว",
                        pending_action="รอการอัปเดตข้อมูลเพิ่มเติม",
                    )
                ],
                irrelevant_articles=list(irrelevant_articles or []),
                political_contexts=list(political_contexts or []),
                metrics=metrics,
                is_fallback=True,
                cached=False,
                generated_at=now_str,
            )

        is_single_source = len(payload.articles) == 1
        synthesis_status: Literal["synthesized", "single_source"] = (
            "single_source" if is_single_source else "synthesized"
        )
        status_message = (
            "สรุปจากแหล่งข่าวเดียว: ข้อมูลอ้างอิงจากรายงานของสำนักข่าวเพียงแหล่งเดียว "
            "ยังไม่สามารถเปรียบเทียบหรือยืนยันข้อมูลตรงกันทุกสื่อได้"
            if is_single_source else ""
        )

        # 1. Executive Summary
        rep_articles = payload.articles[:6]
        lead_summary = rep_articles[0].summary or rep_articles[0].title
        sources = sorted({a.source for a in payload.articles if a.source})
        sources_str = ", ".join(sources[:3])
        if _check_is_sports_collection(title, payload.articles):
            exec_summary = (
                f"ศูนย์รวมข่าวกีฬาเด่น ผลการแข่งขัน และไฮไลต์สำคัญประจำวัน รวบรวมรายงานจาก {sources_str} "
                f"รวม {len(payload.articles)} รายการ ครอบคลุมการแข่งขันฟุตบอลยุโรป ฟุตบอลไทย วอลเลย์บอล "
                f"และความเคลื่อนไหวล่าสุดของทัพนักกีฬา"
            )
        elif is_single_source:
            exec_summary = (
                f"รายงานข่าวเบื้องต้นเกี่ยวกับ '{title}' อ้างอิงจาก {sources_str} (รายงานฉบับเดียว): "
                f"{self._clean_text(lead_summary)[:220]}"
            )
        else:
            exec_summary = (
                f"เกาะติดสถานการณ์สำคัญ '{title}' รวบรวมหลักฐานจาก {sources_str} "
                f"รวม {len(payload.articles)} รายงาน ล่าสุดมีพัฒนาการต่อเนื่องเกี่ยวกับ: "
                f"{self._clean_text(lead_summary)[:180]}..."
            )

        # 2. Progression Timeline
        timeline: list[ProgressionMilestone] = []
        for i, art in enumerate(payload.articles[:8], start=1):
            t_str = art.published_at or art.event_time or now_str
            timeline.append(
                ProgressionMilestone(
                    milestone_id=f"m_{i:02d}",
                    event_time=t_str,
                    description=art.title,
                    evidence_ids=[art.article_id],
                )
            )

        # 3. Confirmed Facts (corroborate from claims or articles)
        facts: list[ConfirmedFact] = []
        fact_idx = 1
        for art in payload.articles:
            for clm in art.claims:
                if clm.claim_type in ("official_statement", "fact_report") and len(clm.text) >= 20:
                    facts.append(
                        ConfirmedFact(
                            fact_id=f"f_{fact_idx:02d}",
                            fact=clm.text,
                            evidence_ids=[art.article_id],
                            corroborating_sources=[art.source],
                        )
                    )
                    fact_idx += 1
                    if len(facts) >= 4:
                        break
            if len(facts) >= 4:
                break

        if not facts and payload.articles:
            for art in payload.articles[:3]:
                facts.append(
                    ConfirmedFact(
                        fact_id=f"f_{fact_idx:02d}",
                        fact=art.title,
                        evidence_ids=[art.article_id],
                        corroborating_sources=[art.source],
                    )
                )
                fact_idx += 1

        # 4. Conflicts Matrix (search for accusations or differing perspectives)
        conflicts: list[DisputeIssue] = []
        sides: list[DisputeSide] = []
        for art in payload.articles:
            for clm in art.claims:
                if clm.claim_type in ("accusation", "opinion") or clm.speaker not in ("", "แหล่งข่าว"):
                    sides.append(
                        DisputeSide(
                            speaker=clm.speaker or art.source,
                            source=art.source,
                            claim_type=clm.claim_type,
                            stance=clm.text[:120],
                            evidence_quote=clm.evidence_quote or clm.text,
                            evidence_id=art.article_id,
                        )
                    )
                    if len(sides) >= 3:
                        break
            if len(sides) >= 3:
                break

        if len(sides) >= 2:
            conflicts.append(
                DisputeIssue(
                    topic_in_dispute=f"มุมมองและข้อสังเกตต่อประเด็น {title}",
                    status="ต่างฝ่ายต่างนำเสนอข้อเท็จจริง",
                    sides=sides,
                )
            )

        # 5. Unknowns (realistic uncertainty gaps)
        unknowns: list[UnknownPoint] = [
            UnknownPoint(
                question="ผลการตรวจสอบข้อเท็จจริงหรือข้อสรุปอย่างเป็นทางการจากหน่วยงานกำกับดูแล",
                why_unknown="ยังไม่มีแถลงการณ์ชี้ขาดฉบับสมบูรณ์จากเจ้าหน้าที่หรือหน่วยงานที่รับผิดชอบ",
                pending_action="รอรายงานผลการตรวจสอบอย่างเป็นทางการ",
            ),
            UnknownPoint(
                question="มาตรการแก้ไขและผลกระทบระยะยาวต่อผู้เกี่ยวข้อง",
                why_unknown="สถานการณ์ยังอยู่ในช่วงเริ่มต้นของการคลี่คลาย",
                pending_action="ติดตามการประชุมและการบังคับใช้มาตรการในระยะถัดไป",
            ),
        ]

        # 6. Irrelevant & Context Articles Passthrough
        # Candidate triage is exclusively performed upstream by Stage 1 Relevance Gate.
        # Payload articles passed here have already been validated as relevant evidence;
        # do NOT re-flag them as irrelevant outliers.
        final_irrelevant: list[IrrelevantArticle] = list(irrelevant_articles or [])

        final_metrics = metrics
        if final_metrics is None:
            publishers = sorted({a.source for a in payload.articles if a.source})
            final_metrics = DossierMetrics(
                candidate_count=len(payload.articles) + len(final_irrelevant) + len(political_contexts or []),
                excluded_count=len(final_irrelevant) + len(political_contexts or []),
                synthesized_evidence_count=len(payload.articles),
                candidate_publishers_count=len(publishers),
                synthesized_publishers_count=len(publishers),
                synthesized_publishers=publishers,
                synthesis_status=synthesis_status,
                status_message=status_message,
            )
        else:
            final_metrics.synthesis_status = synthesis_status
            final_metrics.status_message = status_message

        return EventProgressionSynthesis(
            event_id=event_id,
            executive_summary=exec_summary,
            progression_timeline=timeline,
            confirmed_facts=facts,
            conflicts=conflicts,
            unknowns=unknowns,
            irrelevant_articles=final_irrelevant,
            political_contexts=list(political_contexts or []),
            metrics=final_metrics,
            synthesis_status=synthesis_status,
            status_message=status_message,
            is_single_source=is_single_source,
            is_fallback=True,
            cached=False,
            generated_at=now_str,
        )

    # ── Presentation Formatting ───────────────────────────────────

    def present_story(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
        articles: Sequence[ArticleRecord | dict[str, Any]] | None = None,
        allow_llm: bool = True,
    ) -> StoryPresentation:
        """
        Generate or retrieve cached presentation for a story event.
        Returns StoryPresentation containing Thai headline, summary,
        chronological developments timeline, and source citations.
        Decoupled LLM: If allow_llm=False (critical trending path), uses cached
        presentation or deterministic fallback immediately without LLM network call.
        """
        # 1. Extract story attributes
        story_id, title, category, updated_at_val, story_urls = self._extract_story_info(story)
        norm_updated_at = normalize_timestamp(updated_at_val)

        # 2. Check composite cache keyed by (story_id, updated_at)
        cached_presentation = self.get_cached(story_id, norm_updated_at)
        if cached_presentation is not None:
            return cached_presentation

        # 3. Resolve member articles
        resolved_articles = self._resolve_articles(story, articles, story_urls)

        # 4. Attempt LLM generation via tiered cascade (Only if allowed & configured)
        presentation: StoryPresentation | None = None
        if allow_llm and self._should_attempt_llm():
            presentation = self._generate_llm_presentation(
                story_id=story_id,
                title=title,
                category=category,
                articles=resolved_articles,
                updated_at=norm_updated_at,
            )

        # 5. Robust Fallback if LLM disabled, failed, or returned invalid output
        if presentation is None:
            presentation = self._build_fallback_presentation(
                story_id=story_id,
                title=title,
                category=category,
                articles=resolved_articles,
                updated_at=norm_updated_at,
            )

        # 6. Save in cache
        self.set_cached(story_id, norm_updated_at, presentation)
        return presentation

    async def present_story_async(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
        articles: Sequence[ArticleRecord | dict[str, Any]] | None = None,
        allow_llm: bool = True,
    ) -> StoryPresentation:
        """Asynchronous wrapper for present_story."""
        return await asyncio.to_thread(self.present_story, story, articles, allow_llm)

    # ── Story Enrichment (In-Place / Object Return) ────────────────

    def enrich_story(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
        articles: Sequence[ArticleRecord | dict[str, Any]] | None = None,
        allow_llm: bool = True,
    ) -> StoryRecord | TrendingStoryCluster | dict[str, Any]:
        """
        Enrich a story record or cluster with presentation metadata
        (headline, summary, timeline, and citations).
        """
        presentation = self.present_story(story, articles, allow_llm=allow_llm)

        if isinstance(story, StoryRecord):
            story.headline = presentation.headline
            story.summary = presentation.summary
            story.timeline = list(presentation.timeline)
            story.metadata["citations"] = list(presentation.citations)
            story.metadata["is_fallback"] = presentation.is_fallback
            story.metadata["presentation_cached"] = presentation.cached
            story.enriched_at = datetime.now(timezone.utc)
        elif isinstance(story, TrendingStoryCluster):
            story.headline = presentation.headline
            story.summary = presentation.summary
            story.timeline = list(presentation.timeline)
            story.metadata["citations"] = list(presentation.citations)
            story.metadata["is_fallback"] = presentation.is_fallback
            story.metadata["presentation_cached"] = presentation.cached
        elif isinstance(story, dict):
            story["headline"] = presentation.headline
            story["summary"] = presentation.summary
            story["timeline"] = [t.model_dump() for t in presentation.timeline]
            story["citations"] = list(presentation.citations)
            if "metadata" not in story or not isinstance(story["metadata"], dict):
                story["metadata"] = {}
            story["metadata"]["citations"] = list(presentation.citations)
            story["metadata"]["is_fallback"] = presentation.is_fallback
            story["metadata"]["presentation_cached"] = presentation.cached

        return story

    async def enrich_story_async(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
        articles: Sequence[ArticleRecord | dict[str, Any]] | None = None,
        allow_llm: bool = True,
    ) -> StoryRecord | TrendingStoryCluster | dict[str, Any]:
        """Asynchronous wrapper for enrich_story."""
        return await asyncio.to_thread(self.enrich_story, story, articles, allow_llm)

    def enrich_top_stories(
        self,
        stories: list[TrendingStoryCluster],
        top_n: int = 5,
        allow_llm: bool = False,
    ) -> list[TrendingStoryCluster]:
        """
        Enrich top N trending story clusters with presentation metadata.
        Decoupled LLM principle: Uses deterministic fallback / cached presentation
        on the critical trending path (allow_llm=False) to ensure 100% deterministic,
        instant responses without LLM latency.
        """
        if not stories:
            return []

        limit = max(0, min(top_n, len(stories)))
        for idx in range(limit):
            self.enrich_story(stories[idx], allow_llm=allow_llm)
        return stories

    async def enrich_top_stories_async(
        self,
        stories: list[TrendingStoryCluster],
        top_n: int = 5,
        allow_llm: bool = False,
    ) -> list[TrendingStoryCluster]:
        """Asynchronous wrapper for enrich_top_stories."""
        return await asyncio.to_thread(self.enrich_top_stories, stories, top_n, allow_llm)

    # ── Private Generation Helpers ────────────────────────────────

    def _should_attempt_llm(self) -> bool:
        """Check if LLM client is configured with an active API key."""
        if self._cascading_client is None:
            return False
        if not self._cascading_client.targets:
            return False
        if not isinstance(self._client, CascadingLLMClient):
            key = getattr(settings, "llm_api_key", "")
            return bool(key and str(key).strip() and str(key).strip() != "dummy_key")
        return True

    def _generate_llm_presentation(
        self,
        story_id: str,
        title: str,
        category: str,
        articles: list[dict[str, Any]],
        updated_at: str,
    ) -> StoryPresentation | None:
        """
        Call LLM using tiered cascading fallback to generate structured presentation.
        Returns None on any unhandled exception or parsing failure.
        """
        if not articles:
            return None

        # Build prompt with representative articles (sorted chronologically)
        sorted_articles = self._sort_articles_chronological(articles)
        prompt_lines: list[str] = [
            f"โปรดสังเคราะห์พรีเซนเทชันข่าวภาษาไทยสำหรับเหตุการณ์: {title}",
            f"Story ID: {story_id}",
            f"หมวดหมู่หลัก: {category}",
            f"จำนวนบทความในเหตุการณ์: {len(sorted_articles)}",
            "\nรายการบทความที่รายงานเหตุการณ์นี้ (เรียงตามลำดับเวลา):",
        ]

        # Use up to 8 representative articles to keep context concise
        rep_articles = sorted_articles[:8]
        for idx, art in enumerate(rep_articles, start=1):
            source = str(art.get("source") or "สำนักข่าว").strip()
            art_title = str(art.get("title") or "").strip()
            ts = normalize_timestamp(art.get("fetched_at") or art.get("published_at"))
            summary = self._clean_text(str(art.get("summary") or ""))[:250]
            url = str(art.get("url") or "").strip()

            prompt_lines.append(f"[{idx}] สำนักข่าว: {source} | เวลา: {ts}")
            prompt_lines.append(f"    หัวข้อ: {art_title}")
            if summary:
                prompt_lines.append(f"    เนื้อหาย่อ: {summary}")
            if url:
                prompt_lines.append(f"    URL: {url}")
            prompt_lines.append("")

        user_content = "\n".join(prompt_lines)
        messages = [
            {"role": "system", "content": STORY_PRESENTATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        def _parse(raw: str) -> StoryPresentation:
            parsed = self._parse_llm_json(raw)
            if parsed is None or not isinstance(parsed, dict):
                raise ValueError("Malformed story presentation JSON from LLM output.")

            headline = str(parsed.get("headline") or "").strip() or title
            summary = str(parsed.get("summary") or "").strip()
            if not summary:
                summary = self._clean_text(str(rep_articles[0].get("summary") or title))

            # Parse timeline events
            timeline_events: list[TimelineEvent] = []
            raw_timeline = parsed.get("timeline")
            if isinstance(raw_timeline, list):
                for item in raw_timeline:
                    if isinstance(item, dict):
                        timeline_events.append(TimelineEvent.model_validate(item))

            if not timeline_events:
                timeline_events = self._build_timeline_from_articles(rep_articles)

            # Parse citations
            citations: list[dict[str, Any]] = []
            raw_citations = parsed.get("citations")
            if isinstance(raw_citations, list):
                for item in raw_citations:
                    if isinstance(item, dict) and item.get("source_url"):
                        citations.append(item)

            if not citations:
                citations = self._build_citations_from_articles(rep_articles)

            return StoryPresentation(
                story_id=story_id,
                headline=headline,
                summary=summary,
                timeline=timeline_events,
                citations=citations,
                is_fallback=False,
                cached=False,
                updated_at=updated_at,
            )

        try:
            assert self._cascading_client is not None
            res = self._cascading_client.complete(
                messages=messages,
                validator=_parse,
                temperature=self._temperature,
            )
            return res.parsed
        except Exception as exc:
            logger.warning(
                "StoryPresentationService: all cascade candidates failed (%s). Falling back to heuristics.",
                exc,
            )
            return None

    def _build_fallback_presentation(
        self,
        story_id: str,
        title: str,
        category: str,
        articles: list[dict[str, Any]],
        updated_at: str,
    ) -> StoryPresentation:
        """
        Deterministic, zero-crash heuristic fallback.
        Produces representative title, synthesized excerpt summary,
        chronological developments timeline, and source citations.
        """
        try:
            if not articles:
                clean_title = title.strip() or "รายงานความคืบหน้าสถานการณ์ข่าว"
                return StoryPresentation(
                    story_id=story_id,
                    headline=clean_title,
                    summary="เกาะติดรายงานสถานการณ์ความคืบหน้าล่าสุด",
                    timeline=[],
                    citations=[],
                    is_fallback=True,
                    cached=False,
                    updated_at=updated_at,
                )

            sorted_articles = self._sort_articles_chronological(articles)

            # 1. Headline selection
            headline = self._pick_representative_headline(sorted_articles, default_title=title)

            # 2. Synthesized summary
            summary = self._synthesize_excerpt_summary(sorted_articles, default_headline=headline)

            # 3. Chronological timeline
            timeline = self._build_timeline_from_articles(sorted_articles)

            # 4. Source citations
            citations = self._build_citations_from_articles(sorted_articles)

            return StoryPresentation(
                story_id=story_id,
                headline=headline,
                summary=summary,
                timeline=timeline,
                citations=citations,
                is_fallback=True,
                cached=False,
                updated_at=updated_at,
            )

        except Exception as exc:
            # Absolute safety net: never crash under any condition
            logger.error("StoryPresentationService: error in heuristic fallback: %s", exc)
            fallback_title = title.strip() or "รายงานสถานการณ์ข่าว"
            return StoryPresentation(
                story_id=story_id,
                headline=fallback_title,
                summary="สรุปสถานการณ์ความคืบหน้าจากสำนักข่าวที่เกี่ยวข้อง",
                timeline=[],
                citations=[],
                is_fallback=True,
                cached=False,
                updated_at=updated_at,
            )

    # ── Heuristic Utilities ────────────────────────────────────────

    def _pick_representative_headline(
        self,
        articles: list[dict[str, Any]],
        default_title: str,
    ) -> str:
        """Select and clean representative headline from member articles."""
        candidates: list[str] = []
        for art in articles:
            t = str(art.get("title") or "").strip()
            if t:
                # Strip publisher suffixes e.g. " | ThaiPBS", " - The Standard"
                clean_t = re.sub(r"\s*[-|–]\s*(ThaiPBS|The Standard|Matichon|Bangkok Post|Khaosod|101 World).*$", "", t, flags=re.IGNORECASE).strip()
                if clean_t:
                    candidates.append(clean_t)

        if candidates:
            # Pick the most informative headline (prefer length between 30 and 120 chars)
            candidates.sort(key=lambda s: (30 <= len(s) <= 120, len(s)), reverse=True)
            return candidates[0]

        return default_title.strip() or "รายงานสถานการณ์ข่าว"

    def _synthesize_excerpt_summary(
        self,
        articles: list[dict[str, Any]],
        default_headline: str,
    ) -> str:
        """Synthesize 1–3 informative Thai sentences from distinct member articles."""
        sentences: list[str] = []
        seen_stems: set[str] = set()

        for art in articles:
            raw_summary = str(art.get("summary") or "").strip()
            clean_s = self._clean_text(raw_summary)
            if not clean_s:
                continue

            # Split into Thai sentences or clauses
            clauses = [c.strip() for c in re.split(r"[\n\r]+|\.\s+", clean_s) if c.strip()]
            for clause in clauses:
                if len(clause) < 25:
                    continue
                # Simple deduplication stem
                stem = clause[:20]
                if stem not in seen_stems:
                    seen_stems.add(stem)
                    sentences.append(clause)
                    if len(sentences) >= 3:
                        break
            if len(sentences) >= 3:
                break

        if sentences:
            combined = " ".join(sentences)
            if not combined.endswith((".", "ฯ", "ๆ")):
                combined += ""
            return combined

        unique_sources = sorted({str(a.get("source") or "").strip() for a in articles if str(a.get("source") or "").strip()})
        source_str = " และ ".join(unique_sources[:3]) if unique_sources else "สำนักข่าว"
        return f"เกาะติดรายงานความคืบหน้าเหตุการณ์ {default_headline} รวบรวมข้อมูลจาก {source_str} รวม {len(articles)} รายงาน"

    def _build_timeline_from_articles(
        self,
        articles: list[dict[str, Any]],
    ) -> list[TimelineEvent]:
        """Construct chronological timeline from member articles."""
        events: list[TimelineEvent] = []
        for art in articles:
            ts = normalize_timestamp(art.get("fetched_at") or art.get("published_at"))
            src = str(art.get("source") or "").strip()
            u = str(art.get("url") or "").strip()
            t = str(art.get("title") or "").strip()
            raw_s = str(art.get("summary") or "").strip()
            clean_s = self._clean_text(raw_s)

            desc = clean_s[:160] if clean_s else t
            quote = clean_s[:200] if clean_s else None

            event = TimelineEvent(
                timestamp=ts,
                event_description=desc,
                source_name=src,
                source_url=u,
                source_title=t,
                citation=quote,
            )
            events.append(event)
        return events

    def _build_citations_from_articles(
        self,
        articles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Construct citations list from member articles."""
        citations: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for art in articles:
            u = str(art.get("url") or "").strip()
            if not u or u in seen_urls:
                continue
            seen_urls.add(u)

            src = str(art.get("source") or "").strip()
            t = str(art.get("title") or "").strip()
            raw_s = str(art.get("summary") or "").strip()
            clean_s = self._clean_text(raw_s)
            ts = normalize_timestamp(art.get("fetched_at") or art.get("published_at"))

            citations.append({
                "source_name": src,
                "source_url": u,
                "source_title": t,
                "quote": clean_s[:180] if clean_s else None,
                "timestamp": ts,
            })
        return citations

    def _sort_articles_chronological(
        self,
        articles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Sort articles in chronological order (earliest to latest)."""
        def _get_sort_key(a: dict[str, Any]) -> str:
            ts = a.get("fetched_at") or a.get("published_at")
            return normalize_timestamp(ts) or "9999-99-99 99:99:99"

        return sorted(articles, key=_get_sort_key)

    def _clean_text(self, text: str) -> str:
        """Strip boilerplate text and normalize whitespace."""
        res = text
        for bp in _BOILERPLATE_PATTERNS:
            res = res.replace(bp, "")
        # Remove consecutive whitespace
        return re.sub(r"\s+", " ", res).strip()

    def _parse_llm_json(self, raw_text: str) -> dict[str, Any] | None:
        """Strip markdown fences and parse valid JSON."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        cleaned = cleaned.removesuffix("```").strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            # Fallback regex search for JSON object
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
        return None

    def _extract_story_info(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
    ) -> tuple[str, str, str, Any, list[str]]:
        """Extract story_id, title, category, updated_at, article_urls."""
        if isinstance(story, (StoryRecord, TrendingStoryCluster)):
            story_id = getattr(story, "story_id", "")
            title = getattr(story, "title", "")
            category = getattr(story, "category", "general")
            updated_at = getattr(story, "updated_at", None)
            article_urls = getattr(story, "article_urls", [])
            return str(story_id), str(title), str(category), updated_at, list(article_urls)
        elif isinstance(story, dict):
            story_id = str(story.get("story_id") or "")
            title = str(story.get("title") or "")
            category = str(story.get("category") or "general")
            updated_at = story.get("updated_at")
            article_urls = list(story.get("article_urls") or [])
            return story_id, title, category, updated_at, article_urls
        return "", "", "general", None, []

    def _resolve_articles(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
        explicit_articles: Sequence[ArticleRecord | dict[str, Any]] | None,
        story_urls: list[str],
    ) -> list[dict[str, Any]]:
        """Gather article dicts from arguments, story object, or news repo."""
        result: list[dict[str, Any]] = []

        if explicit_articles:
            for a in explicit_articles:
                if isinstance(a, ArticleRecord):
                    result.append(a.model_dump())
                elif isinstance(a, dict):
                    result.append(dict(a))
            if result:
                return result

        # Check if story object already has articles attached
        attached = None
        if hasattr(story, "articles"):
            attached = story.articles
        elif isinstance(story, dict) and "articles" in story:
            attached = story.get("articles")

        if attached and isinstance(attached, list) and len(attached) > 0:
            for a in attached:
                if isinstance(a, ArticleRecord):
                    result.append(a.model_dump())
                elif isinstance(a, dict):
                    result.append(dict(a))
            if result:
                return result

        # Lookup from news repository using story_urls
        if story_urls:
            repo = self._news_repo or get_news_repository()
            try:
                raw_news = repo.load_news()
                url_set = {u.strip() for u in story_urls if u and u.strip()}
                for item in raw_news:
                    if isinstance(item, dict):
                        u = str(item.get("url") or "").strip()
                        if u in url_set:
                            result.append(dict(item))
            except Exception as exc:
                logger.debug("Failed loading articles from repo: %s", exc)

        return result


# ── Dependency Injection & Factory ────────────────────────────────

_PRESENTATION_SERVICE_INSTANCE: StoryPresentationService | None = None
_PRESENTATION_LOCK = threading.Lock()

# Interface alias required by PROJECT.md
LLMStoryPresenter = StoryPresentationService


def get_story_presentation_service() -> StoryPresentationService:
    """Thread-safe singleton factory for StoryPresentationService."""
    global _PRESENTATION_SERVICE_INSTANCE
    if _PRESENTATION_SERVICE_INSTANCE is not None:
        return _PRESENTATION_SERVICE_INSTANCE

    with _PRESENTATION_LOCK:
        if _PRESENTATION_SERVICE_INSTANCE is not None:
            return _PRESENTATION_SERVICE_INSTANCE

        cascading_client = get_cascading_client()
        _PRESENTATION_SERVICE_INSTANCE = StoryPresentationService(
            client=cascading_client,
            temperature=settings.llm_temperature,
            news_repo=get_news_repository(),
        )
        return _PRESENTATION_SERVICE_INSTANCE


def reset_story_presentation_service() -> None:
    """Reset presentation service singleton (used in testing)."""
    global _PRESENTATION_SERVICE_INSTANCE
    with _PRESENTATION_LOCK:
        _PRESENTATION_SERVICE_INSTANCE = None
