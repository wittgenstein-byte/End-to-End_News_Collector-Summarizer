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
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import settings
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.schemas.macro_event_schema import MacroEventRecord, MacroTimelineEvent
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import StoryRecord
from backend.schemas.story_schema import TimelineEvent as SchemaTimelineEvent
from backend.schemas.trending_schema import TrendingStoryCluster

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
        client: OpenAI | None = None,
        models: list[str] | None = None,
        temperature: float = 0.2,
        news_repo: NewsRepositoryPort | None = None,
        cache_max_size: int = 500,
        cache_file: Path | None = None,
    ) -> None:
        self._client = client
        self._models = list(models) if models else list(settings.llm_cascade_models)
        self._temperature = temperature
        self._news_repo = news_repo
        self._cache_max_size = cache_max_size
        self._cache_file = cache_file or (getattr(settings, "DATA_DIR", Path("data")) / "presentation_cache.json")

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

    @property
    def client(self) -> OpenAI | None:
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
        resolved_articles = list(articles or [])
        if not resolved_articles and self._news_repo is not None:
            all_urls: list[str] = []
            for cs in child_stories:
                all_urls.extend(cs.article_urls)
            if all_urls:
                unique_urls = list(dict.fromkeys(all_urls))
                if hasattr(self._news_repo, "get_by_urls"):
                    resolved_articles = self._news_repo.get_by_urls(unique_urls)
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

    # ── Presentation Formatting ───────────────────────────────────

    def present_story(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
        articles: Sequence[ArticleRecord | dict[str, Any]] | None = None,
    ) -> StoryPresentation:
        """
        Generate or retrieve cached presentation for a story event.
        Returns StoryPresentation containing Thai headline, summary,
        chronological developments timeline, and source citations.
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

        # 4. Attempt LLM generation via tiered cascade
        presentation: StoryPresentation | None = None
        if self._should_attempt_llm():
            presentation = self._generate_llm_presentation(
                story_id=story_id,
                title=title,
                category=category,
                articles=resolved_articles,
                updated_at=norm_updated_at,
            )

        # 5. Robust Fallback if LLM failed, disabled, or returned invalid output
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
    ) -> StoryPresentation:
        """Asynchronous wrapper for present_story."""
        return await asyncio.to_thread(self.present_story, story, articles)

    # ── Story Enrichment (In-Place / Object Return) ────────────────

    def enrich_story(
        self,
        story: StoryRecord | TrendingStoryCluster | dict[str, Any],
        articles: Sequence[ArticleRecord | dict[str, Any]] | None = None,
    ) -> StoryRecord | TrendingStoryCluster | dict[str, Any]:
        """
        Enrich a story record or cluster with presentation metadata
        (headline, summary, timeline, and citations).
        """
        presentation = self.present_story(story, articles)

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
    ) -> StoryRecord | TrendingStoryCluster | dict[str, Any]:
        """Asynchronous wrapper for enrich_story."""
        return await asyncio.to_thread(self.enrich_story, story, articles)

    def enrich_top_stories(
        self,
        stories: list[TrendingStoryCluster],
        top_n: int = 5,
    ) -> list[TrendingStoryCluster]:
        """
        Enrich top N trending story clusters with LLM presentation metadata.
        Falls back gracefully to heuristic presentation without throwing exceptions.
        """
        if not stories:
            return []

        limit = max(0, min(top_n, len(stories)))
        for idx in range(limit):
            self.enrich_story(stories[idx])
        return stories

    async def enrich_top_stories_async(
        self,
        stories: list[TrendingStoryCluster],
        top_n: int = 5,
    ) -> list[TrendingStoryCluster]:
        """Asynchronous wrapper for enrich_top_stories."""
        return await asyncio.to_thread(self.enrich_top_stories, stories, top_n)

    # ── Private Generation Helpers ────────────────────────────────

    def _should_attempt_llm(self) -> bool:
        """Check if LLM client is configured with an active API key."""
        if self._client is None:
            return False
        key = getattr(settings, "llm_api_key", "")
        return bool(key and str(key).strip() and str(key).strip() != "dummy_key")

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

        # Tiered Cascading Call
        for model_idx, model_name in enumerate(self._models):
            try:
                assert self._client is not None
                response = self._client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": STORY_PRESENTATION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=self._temperature,
                    timeout=25.0,
                    stream=False,
                )

                raw_text = (response.choices[0].message.content or "").strip()
                if not raw_text:
                    continue

                parsed = self._parse_llm_json(raw_text)
                if parsed is not None:
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

                    # If timeline from LLM is empty, generate from articles
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

                    if model_idx > 0:
                        logger.info(
                            "StoryPresentationService: succeeded using cascade model '%s' (attempt %d/%d)",
                            model_name,
                            model_idx + 1,
                            len(self._models),
                        )

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

            except Exception as exc:
                logger.warning(
                    "StoryPresentationService: model '%s' failed (%s). Cascading...",
                    model_name,
                    exc,
                )
                continue

        logger.warning("StoryPresentationService: all cascade models failed. Falling back to deterministic heuristics.")
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

        client: OpenAI | None = None
        if settings.llm_api_key and settings.llm_api_key.strip():
            client = OpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
            )

        _PRESENTATION_SERVICE_INSTANCE = StoryPresentationService(
            client=client,
            models=list(settings.llm_cascade_models),
            temperature=settings.llm_temperature,
            news_repo=get_news_repository(),
        )
        return _PRESENTATION_SERVICE_INSTANCE


def reset_story_presentation_service() -> None:
    """Reset presentation service singleton (used in testing)."""
    global _PRESENTATION_SERVICE_INSTANCE
    with _PRESENTATION_LOCK:
        _PRESENTATION_SERVICE_INSTANCE = None
