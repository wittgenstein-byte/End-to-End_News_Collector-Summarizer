"""
routers/story_router.py
─────────────────────────────────────────────────────────────────
SOLID  S — HTTP routing and request validation for persistent stories.
SOLID  D — Injects StoryRepositoryPort, NewsRepositoryPort, TrendingService,
           and StoryPresentationService via FastAPI Depends().
GRASP  Controller — Coordinates story domain queries, presentation
           enrichment, and chronological member assembly.
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

from backend.config import settings
from backend.core.l1_cache import trending_cache
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.event_evidence_schema import EventProgressionSynthesis
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import (
    StoryDetailResponse,
    StoryListResponse,
    StorySummary,
)
from backend.schemas.trending_schema import (
    TrendingStoryListResponse,
)
from backend.services.story_presentation_service import (
    StoryPresentationService,
    get_story_presentation_service,
)
from backend.services.trending_service import (
    TrendingService,
    get_trending_service,
    parse_article_time,
)

router = APIRouter(prefix="/api/stories", tags=["stories"])


@router.get("", response_model=StoryListResponse)
@router.get("/", response_model=StoryListResponse, include_in_schema=False)
async def list_stories(
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
        description="Number of stories to return per page",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Zero-based index offset for pagination",
    ),
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
) -> StoryListResponse:
    """
    List tracked stories with optional lifecycle status and category filters.
    Returns lightweight StorySummary projections with pagination metadata.
    """
    clean_status = (
        status_filter.strip().lower()
        if status_filter and status_filter.strip()
        else None
    )
    if clean_status == "all":
        clean_status = None

    clean_category = (
        category.strip().lower()
        if category and category.strip()
        else None
    )
    if clean_category == "all":
        clean_category = None

    # Retrieve stories from repository
    if clean_category is not None:
        # Category acts as a soft signal filter over matching status stories
        all_status_stories = story_repo.list_stories(
            status=clean_status, limit=10000, offset=0
        )
        filtered = [
            s for s in all_status_stories
            if s.category.strip().lower() == clean_category
        ]
        total = len(filtered)
        paged_stories = filtered[offset : offset + limit]
    else:
        total = story_repo.count_stories(status=clean_status)
        paged_stories = story_repo.list_stories(
            status=clean_status, limit=limit, offset=offset
        )

    total_pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    current_page = (offset // limit) + 1
    has_next = (offset + limit) < total
    has_prev = offset > 0

    summaries: list[StorySummary] = []
    for s in paged_stories:
        summary = StorySummary.from_story(s)
        # Ensure headline fallback is populated even before LLM enrichment
        if not summary.headline:
            summary.headline = s.headline or s.title
        if not summary.summary:
            summary.summary = s.summary or f"ประเด็นข่าวเหตุการณ์: {s.title}"
        summaries.append(summary)

    return StoryListResponse(
        total=total,
        page=current_page,
        page_size=limit,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
        updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        stories=summaries,
    )


@router.get("/trending", response_model=TrendingStoryListResponse)
async def get_trending_stories(
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Max trending stories to return",
    ),
    category: str | None = Query(
        default=None,
        description="Filter by primary category",
    ),
    trending_service: TrendingService = Depends(get_trending_service),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> TrendingStoryListResponse:
    """
    Get deterministically ranked active stories with score breakdown and
    enriched presentation (headline, summary, timeline with citations).
    Guarantees HTTP 200 with fallback presentation when LLM is unavailable.
    """
    # L1 In-Memory Cache Check (< 0.5 ms)
    cache_key = f"trending_stories:{limit}:{category or 'all'}"
    cached_data = await trending_cache.get(cache_key)
    if cached_data is not None:
        return TrendingStoryListResponse(**cached_data)

    top_stories = await asyncio.to_thread(
        trending_service.get_trending_stories,
        limit=limit,
        category=category,
    )

    # Enrich top stories with presentation (Deterministic heuristic fallback, decoupled LLM)
    await asyncio.to_thread(
        presentation_service.enrich_top_stories,
        top_stories,
        top_n=min(limit, 5),
        allow_llm=False,
    )

    response = TrendingStoryListResponse(
        total=len(top_stories),
        updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        stories=top_stories,
    )
    await trending_cache.set(cache_key, response.model_dump(), ttl_seconds=float(settings.trending_cache_ttl_seconds))
    return response


@router.get("/{story_id}", response_model=StoryDetailResponse)
async def get_story_detail(
    story_id: str,
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
    news_repo: NewsRepositoryPort = Depends(get_news_repository),
    trending_service: TrendingService = Depends(get_trending_service),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
    macro_repo: Any = Depends(get_story_repository),
) -> StoryDetailResponse:
    """
    Get full details for a single story cluster:
    - Member articles assembled in chronological order (earliest to latest)
    - Presentation headline and synthesized summary
    - Chronological developments timeline with source citations
    - Mathematical TrendingScoreBreakdown
    - Mandatory coverage limitation disclaimer
    Guarantees HTTP 200 with fallback headline/summary when LLM is unavailable.
    """
    story = story_repo.get_story(story_id)
    if story is None:
        from backend.repo.macro_event_repo import get_macro_event_repository

        macro = get_macro_event_repository().get_macro_event(story_id)
        if macro is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"'{story_id}' is a Macro-Event identifier. "
                    f"Please query GET /api/macro-events/{story_id} for storyline details."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story with id '{story_id}' not found",
        )

    # 1. Resolve member articles from news repository
    raw_news = news_repo.load_news()
    news_map: dict[str, dict[str, Any]] = {}
    for item in raw_news:
        if isinstance(item, dict):
            u = str(item.get("url") or "").strip()
            if u:
                news_map[u] = item

    member_dicts: list[dict[str, Any]] = []
    member_records: list[ArticleRecord] = []

    for u in story.article_urls:
        clean_u = u.strip() if u else ""
        if not clean_u:
            continue
        if clean_u in news_map:
            raw_art = news_map[clean_u]
            member_dicts.append(raw_art)
            try:
                member_records.append(ArticleRecord.model_validate(raw_art))
            except Exception:
                pass
        else:
            # Synthetic fallback for referenced articles not yet in news store
            synth = {
                "url": clean_u,
                "title": story.title,
                "source": story.outlets[0] if story.outlets else "สำนักข่าว",
                "category": story.category,
                "fetched_at": story.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "summary": story.summary or story.title,
            }
            member_dicts.append(synth)
            try:
                member_records.append(ArticleRecord.model_validate(synth))
            except Exception:
                pass

    # 2. Chronological sorting: earliest to latest
    def _chronological_sort_key(art: ArticleRecord) -> float:
        dt = parse_article_time(art.fetched_at)
        return dt.timestamp()

    member_records.sort(key=_chronological_sort_key)

    # 3. Enrich presentation (Deterministic heuristic fallback or cache, decoupled LLM)
    presentation_service.enrich_story(story, member_dicts, allow_llm=False)

    # 4. Compute deterministic trending score & breakdown
    score, breakdown, _ = trending_service.calculate_story_score(
        story=story,
        articles=member_dicts,
    )

    breakdown_dict = breakdown.model_dump()
    if story.metadata.get("citations"):
        breakdown_dict["citations"] = list(story.metadata["citations"])

    synthesis = presentation_service.synthesize_event_progression(
        event_id=story.story_id,
        title=story.title,
        articles=member_dicts,
        allow_llm=False,
    )

    # 5. Build and return StoryDetailResponse
    return StoryDetailResponse.from_story_and_articles(
        story=story,
        articles=member_records,
        trending_score=score,
        breakdown=breakdown_dict,
        synthesis=synthesis,
    )


@router.post("/{story_id}/summarize", response_model=StoryDetailResponse)
async def summarize_story_on_demand(
    story_id: str,
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
    news_repo: NewsRepositoryPort = Depends(get_news_repository),
    trending_service: TrendingService = Depends(get_trending_service),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> StoryDetailResponse:
    """
    On-Demand Story Summarization:
    Explicitly triggered only when the user requests an AI summary for this story event.
    Calls LLM cascade, updates presentation cache, and returns refreshed StoryDetailResponse.
    """
    story = story_repo.get_story(story_id)
    if story is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story with id '{story_id}' not found",
        )

    raw_news = news_repo.load_news()
    news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}

    member_dicts: list[dict[str, Any]] = []
    member_records: list[ArticleRecord] = []

    for u in story.article_urls:
        clean_u = u.strip() if u else ""
        if not clean_u:
            continue
        if clean_u in news_map:
            raw_art = news_map[clean_u]
            member_dicts.append(raw_art)
            try:
                member_records.append(ArticleRecord.model_validate(raw_art))
            except Exception:
                pass

    def _chronological_sort_key(art: ArticleRecord) -> float:
        return parse_article_time(art.fetched_at).timestamp()

    member_records.sort(key=_chronological_sort_key)

    # On-demand LLM generation explicitly permitted here
    presentation_service.enrich_story(story, member_dicts, allow_llm=True)
    synthesis = presentation_service.synthesize_event_progression(
        event_id=story.story_id,
        title=story.title,
        articles=member_dicts,
        allow_llm=True,
    )

    score, breakdown, _ = trending_service.calculate_story_score(
        story=story,
        articles=member_dicts,
    )
    breakdown_dict = breakdown.model_dump()
    if story.metadata.get("citations"):
        breakdown_dict["citations"] = list(story.metadata["citations"])

    return StoryDetailResponse.from_story_and_articles(
        story=story,
        articles=member_records,
        trending_score=score,
        breakdown=breakdown_dict,
        synthesis=synthesis,
    )


from pydantic import BaseModel, Field


class SynthesisRequestPayload(BaseModel):
    title: str | None = None
    headline: str | None = None
    articles: list[dict[str, Any]] = Field(default_factory=list)
    article_urls: list[str] = Field(default_factory=list)


@router.get("/{story_id}/synthesis", response_model=EventProgressionSynthesis)
async def get_story_synthesis(
    story_id: str,
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
    news_repo: NewsRepositoryPort = Depends(get_news_repository),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> EventProgressionSynthesis:
    """Get Event Progression Synthesis for a story/cluster event (Decoupled LLM: cached or heuristic)."""
    # 1. Multi-tier cache check first (ID, signature, overlap)
    cached = presentation_service.find_cached_synthesis(event_id=story_id)
    if cached is not None:
        return cached

    # 2. Try story_repo
    story = story_repo.get_story(story_id)
    if story is not None:
        raw_news = news_repo.load_news()
        news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
        member_dicts = [news_map[u.strip()] for u in story.article_urls if u and u.strip() in news_map]
        return presentation_service.synthesize_event_progression(
            event_id=story.story_id,
            title=story.title,
            articles=member_dicts,
            allow_llm=False,
        )

    # 3. Try macro_event_repo
    from backend.repo.macro_event_repo import get_macro_event_repository
    macro = get_macro_event_repository().get_macro_event(story_id)
    if macro is not None:
        child_stories = story_repo.get_stories_by_macro_id(macro.macro_event_id)
        if not child_stories and macro.child_event_ids:
            child_stories = story_repo.get_stories_by_ids(macro.child_event_ids)
        urls = [u for cs in child_stories for u in cs.article_urls if u]
        raw_news = news_repo.load_news()
        news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
        member_dicts = [news_map[u.strip()] for u in urls if u and u.strip() in news_map]
        return presentation_service.synthesize_event_progression(
            event_id=macro.macro_event_id,
            title=macro.title,
            articles=member_dicts,
            allow_llm=False,
        )

    # 4. Try matching news by cluster_id
    raw_news = news_repo.load_news()
    clustered = [item for item in raw_news if isinstance(item, dict) and str(item.get("cluster_id") or "") == story_id]
    if clustered:
        return presentation_service.synthesize_event_progression(
            event_id=story_id,
            title=clustered[0].get("title") or "ประเด็นข่าว",
            articles=clustered,
            allow_llm=False,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Story or Cluster with id '{story_id}' not found",
    )


@router.post("/{story_id}/synthesis", response_model=EventProgressionSynthesis)
async def trigger_story_synthesis(
    story_id: str,
    payload: SynthesisRequestPayload | None = None,
    force_refresh: bool = Query(default=False, description="Force LLM re-synthesis"),
    story_repo: StoryRepositoryPort = Depends(get_story_repository),
    news_repo: NewsRepositoryPort = Depends(get_news_repository),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> EventProgressionSynthesis:
    """On-Demand Event Progression Synthesis via LLM for a story/cluster event."""
    title = ""
    member_dicts: list[dict[str, Any]] = []

    # A. Check payload.articles first if passed by client
    if payload and payload.articles:
        member_dicts = list(payload.articles)
        title = payload.title or payload.headline or ""

    # B. If not in payload, check story_repo
    if not member_dicts:
        story = story_repo.get_story(story_id)
        if story is not None:
            title = story.title
            raw_news = news_repo.load_news()
            news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
            member_dicts = [news_map[u.strip()] for u in story.article_urls if u and u.strip() in news_map]

    # C. If not in story_repo, check macro_repo
    if not member_dicts:
        from backend.repo.macro_event_repo import get_macro_event_repository
        macro = get_macro_event_repository().get_macro_event(story_id)
        if macro is not None:
            title = macro.title
            child_stories = story_repo.get_stories_by_macro_id(macro.macro_event_id)
            if not child_stories and macro.child_event_ids:
                child_stories = story_repo.get_stories_by_ids(macro.child_event_ids)
            urls = [u for cs in child_stories for u in cs.article_urls if u]
            raw_news = news_repo.load_news()
            news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
            member_dicts = [news_map[u.strip()] for u in urls if u and u.strip() in news_map]

    # D. If payload provided article_urls
    if not member_dicts and payload and payload.article_urls:
        raw_news = news_repo.load_news()
        news_map = {str(item.get("url") or "").strip(): item for item in raw_news if isinstance(item, dict)}
        member_dicts = [news_map[u.strip()] for u in payload.article_urls if u and u.strip() in news_map]

    # E. Check news_repo by cluster_id
    if not member_dicts:
        raw_news = news_repo.load_news()
        member_dicts = [item for item in raw_news if isinstance(item, dict) and str(item.get("cluster_id") or "") == story_id]
        if member_dicts:
            title = member_dicts[0].get("title") or "ประเด็นข่าว"

    if not member_dicts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cannot synthesize: No articles found for '{story_id}'",
        )

    if not title:
        title = member_dicts[0].get("title") or "ประเด็นข่าว"

    return await presentation_service.synthesize_event_progression_async(
        event_id=story_id,
        title=title,
        articles=member_dicts,
        allow_llm=True,
        force_refresh=force_refresh,
    )
