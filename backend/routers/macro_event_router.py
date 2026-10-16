"""
routers/macro_event_router.py
─────────────────────────────────────────────────────────────────
SOLID  S — HTTP routing and request validation for Macro-Event storylines.
SOLID  D — Injects MacroEventRepositoryPort, StoryRepositoryPort, TrendingService,
           and StoryPresentationService via FastAPI Depends().
GRASP  Controller — Coordinates storyline domain queries, presentation
           synthesis, and chronological timeline assembly.
POLICY Zero Crash Guarantee — Always returns HTTP 200 with fallback
           presentation when LLM is unavailable.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.config import settings
from backend.core.l1_cache import trending_cache
from backend.repo.macro_event_repo import (
    MacroEventRepositoryPort,
    get_macro_event_repository,
)
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.event_evidence_schema import EventProgressionSynthesis
from backend.schemas.macro_event_schema import (
    MacroEventDetailResponse,
    MacroEventListResponse,
    MacroEventSummary,
)
from backend.schemas.story_schema import StorySummary
from backend.services.story_presentation_service import (
    StoryPresentationService,
    get_story_presentation_service,
)
from backend.services.trending_service import (
    TrendingService,
    get_trending_service,
)

router = APIRouter(prefix="/api/macro-events", tags=["macro-events"])


@router.get("", response_model=MacroEventListResponse)
@router.get("/", response_model=MacroEventListResponse, include_in_schema=False)
async def list_macro_events(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by lifecycle status ('active', 'dormant', or 'all')",
    ),
    category: str | None = Query(
        default=None,
        description="Filter by primary category tag",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of macro-events to return per page",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of macro-events to skip",
    ),
    macro_repo: MacroEventRepositoryPort = Depends(get_macro_event_repository),
) -> MacroEventListResponse:
    """List macro-events with pagination and filtering."""
    all_macros = await asyncio.to_thread(macro_repo.list_macro_events, status=status_filter, limit=1000, offset=0)

    if category and category.strip().lower() not in ("", "all"):
        target_cat = category.strip().lower()
        all_macros = [m for m in all_macros if m.category.strip().lower() == target_cat]

    total = len(all_macros)
    paged_macros = all_macros[offset : offset + limit]

    page_size = max(1, limit)
    current_page = (offset // page_size) + 1
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

    summaries = [MacroEventSummary.from_macro(m) for m in paged_macros]

    return MacroEventListResponse(
        total=total,
        page=current_page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=(offset + limit) < total,
        has_prev=offset > 0,
        updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        macro_events=summaries,
    )


@router.get("/trending", response_model=list[dict[str, Any]])
async def get_trending_macro_events(
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of trending macro storylines to return",
    ),
    category: str | None = Query(
        default=None,
        description="Filter trending macro-events by category tag",
    ),
    trending_service: TrendingService = Depends(get_trending_service),
) -> list[dict[str, Any]]:
    """Get ranked trending macro-events (storylines) with full score breakdown."""
    cache_key = f"trending_macro:{limit}:{category or 'all'}"
    cached = await trending_cache.get(cache_key)
    if cached is not None:
        return cached

    res = await asyncio.to_thread(trending_service.get_trending_macro_events, limit=limit, category=category)
    await trending_cache.set(cache_key, res, ttl_seconds=float(settings.trending_cache_ttl_seconds))
    return res


@router.get("/{macro_id}", response_model=MacroEventDetailResponse)
async def get_macro_event_detail(
    macro_id: str,
    macro_repo: MacroEventRepositoryPort = Depends(get_macro_event_repository),
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> MacroEventDetailResponse:
    """Get full details of a macro-event storyline with child events, timeline, and relations."""
    macro = macro_repo.get_macro_event(macro_id)
    if macro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Macro-event '{macro_id}' not found",
        )

    # Fetch member child events (StoryRecords)
    child_stories = story_repo.get_stories_by_macro_id(macro.macro_event_id)
    if not child_stories and macro.child_event_ids:
        child_stories = story_repo.get_stories_by_ids(macro.child_event_ids)

    # Synthesize or update presentation
    macro = presentation_service.present_macro_event(macro, child_stories)

    child_summaries = [StorySummary.from_story(s) for s in child_stories]

    # Collect member articles across child stories for synthesis
    article_urls: list[str] = []
    for cs in child_stories:
        for u in cs.article_urls:
            if u and u.strip() and u.strip() not in article_urls:
                article_urls.append(u.strip())

    news_repo = get_news_repository()
    raw_news = news_repo.load_news()
    news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}

    member_articles: list[dict[str, Any]] = []
    for u in article_urls:
        if u in news_map:
            member_articles.append(news_map[u])
        else:
            member_articles.append({
                "url": u,
                "title": macro.title,
                "source": "สำนักข่าว",
                "summary": macro.summary or macro.title,
                "fetched_at": macro.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            })

    synthesis = presentation_service.synthesize_event_progression(
        event_id=macro.macro_event_id,
        title=macro.title,
        articles=member_articles,
        allow_llm=False,
    )

    return MacroEventDetailResponse(
        macro_event_id=macro.macro_event_id,
        title=macro.title,
        headline=macro.headline,
        summary=macro.summary,
        category=macro.category,
        status=macro.status,
        created_at=macro.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        updated_at=macro.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        child_event_count=len(child_summaries),
        entities=list(macro.entities),
        child_events=child_summaries,
        relations=list(macro.relations),
        timeline=list(macro.timeline),
        articles=member_articles,
        synthesis=synthesis,
    )

class SynthesisRequestPayload(BaseModel):
    title: str | None = None
    headline: str | None = None
    articles: list[dict[str, Any]] = Field(default_factory=list)
    article_urls: list[str] = Field(default_factory=list)


@router.get("/{macro_id}/synthesis", response_model=EventProgressionSynthesis)
async def get_macro_event_synthesis(
    macro_id: str,
    macro_repo: MacroEventRepositoryPort = Depends(get_macro_event_repository),
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
    news_repo: NewsRepositoryPort = Depends(get_news_repository),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> EventProgressionSynthesis:
    """
    Get Evidence-Grounded Event Progression Synthesis for a Macro-Event storyline.
    Decoupled LLM: Uses cache (ID, signature, overlap) or deterministic heuristic by default.
    """
    # 1. Multi-tier cache check first (ID, signature, overlap)
    cached = presentation_service.find_cached_synthesis(event_id=macro_id)
    if cached is not None:
        return cached

    # 2. Try macro_repo
    macro = macro_repo.get_macro_event(macro_id)
    if macro is not None:
        child_stories = story_repo.get_stories_by_macro_id(macro.macro_event_id)
        if not child_stories and macro.child_event_ids:
            child_stories = story_repo.get_stories_by_ids(macro.child_event_ids)

        article_urls: list[str] = []
        for cs in child_stories:
            for u in cs.article_urls:
                if u and u.strip() and u.strip() not in article_urls:
                    article_urls.append(u.strip())

        raw_news = news_repo.load_news()
        news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}

        member_articles: list[dict[str, Any]] = []
        for u in article_urls:
            if u in news_map:
                member_articles.append(news_map[u])
            else:
                member_articles.append({
                    "url": u,
                    "title": macro.title,
                    "source": "สำนักข่าว",
                    "summary": macro.summary or macro.title,
                    "fetched_at": macro.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                })

        return presentation_service.synthesize_event_progression(
            event_id=macro.macro_event_id,
            title=macro.title,
            articles=member_articles,
            allow_llm=False,
        )

    # 3. Try story_repo fallback
    story = story_repo.get_story(macro_id)
    if story is not None:
        raw_news = news_repo.load_news()
        news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
        member_articles = [news_map[u.strip()] for u in story.article_urls if u and u.strip() in news_map]
        return presentation_service.synthesize_event_progression(
            event_id=story.story_id,
            title=story.title,
            articles=member_articles,
            allow_llm=False,
        )

    # 4. Try news_repo cluster_id match
    raw_news = news_repo.load_news()
    clustered = [item for item in raw_news if isinstance(item, dict) and str(item.get("cluster_id") or "") == macro_id]
    if clustered:
        return presentation_service.synthesize_event_progression(
            event_id=macro_id,
            title=clustered[0].get("title") or "ประเด็นข่าว",
            articles=clustered,
            allow_llm=False,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Macro-event or Storyline '{macro_id}' not found",
    )


@router.post("/{macro_id}/synthesis", response_model=EventProgressionSynthesis)
async def trigger_macro_event_synthesis(
    macro_id: str,
    payload: SynthesisRequestPayload | None = None,
    force_refresh: bool = Query(default=False, description="Force LLM re-synthesis"),
    macro_repo: MacroEventRepositoryPort = Depends(get_macro_event_repository),
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
    news_repo: NewsRepositoryPort = Depends(get_news_repository),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> EventProgressionSynthesis:
    """
    On-Demand Deep Event Progression Synthesis via LLM.
    Triggered when user clicks 'สังเคราะห์ความคืบหน้าด้วย AI'.
    Extracts evidence, constructs claim-vs-claim matrix, checks corroborated facts,
    highlights unknowns, and detects outlier/irrelevant articles in the cluster.
    """
    title = ""
    member_articles: list[dict[str, Any]] = []

    # A. Check payload.articles first
    if payload and payload.articles:
        member_articles = list(payload.articles)
        title = payload.title or payload.headline or ""

    # B. Check macro_repo
    if not member_articles:
        macro = macro_repo.get_macro_event(macro_id)
        if macro is not None:
            title = macro.title
            child_stories = story_repo.get_stories_by_macro_id(macro.macro_event_id)
            if not child_stories and macro.child_event_ids:
                child_stories = story_repo.get_stories_by_ids(macro.child_event_ids)

            article_urls: list[str] = []
            for cs in child_stories:
                for u in cs.article_urls:
                    if u and u.strip() and u.strip() not in article_urls:
                        article_urls.append(u.strip())

            raw_news = news_repo.load_news()
            news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}

            for u in article_urls:
                if u in news_map:
                    member_articles.append(news_map[u])
                else:
                    member_articles.append({
                        "url": u,
                        "title": macro.title,
                        "source": "สำนักข่าว",
                        "summary": macro.summary or macro.title,
                        "fetched_at": macro.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                    })

    # C. Check story_repo
    if not member_articles:
        story = story_repo.get_story(macro_id)
        if story is not None:
            title = story.title
            raw_news = news_repo.load_news()
            news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
            member_articles = [news_map[u.strip()] for u in story.article_urls if u and u.strip() in news_map]

    # D. Check payload.article_urls
    if not member_articles and payload and payload.article_urls:
        raw_news = news_repo.load_news()
        news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
        member_articles = [news_map[u.strip()] for u in payload.article_urls if u and u.strip() in news_map]

    # E. Check news_repo by cluster_id
    if not member_articles:
        raw_news = news_repo.load_news()
        member_articles = [item for item in raw_news if isinstance(item, dict) and str(item.get("cluster_id") or "") == macro_id]
        if member_articles:
            title = member_articles[0].get("title") or "ประเด็นข่าว"

    if not member_articles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cannot synthesize: No articles found for '{macro_id}'",
        )

    if not title:
        title = member_articles[0].get("title") or "ประเด็นข่าว"

    return await presentation_service.synthesize_event_progression_async(
        event_id=macro_id,
        title=title,
        articles=member_articles,
        allow_llm=True,
        force_refresh=force_refresh,
    )
