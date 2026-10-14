"""
routers/trending_router.py
─────────────────────────────────────────────────────────────────
SOLID  I — Focused route handlers for trending news & reader telemetry
SOLID  D — Injects TrendingService, StoryPresentationService & FileEngagementRepository
GRASP  Controller — Coordinates HTTP requests with domain services
POLICY Backward Compatibility — 100% compatible with legacy consumers
POLICY Zero Crash Guarantee — Always returns HTTP 200 with fallback
           presentation when LLM is unavailable.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field

from backend.config import settings
from backend.core.l1_cache import trending_cache
from backend.repo.engagement_repo import (
    FileEngagementRepository,
    get_engagement_repository,
)
from backend.schemas.trending_schema import (
    EngagementEvent,
    TrendingArticle,
    TrendingCluster,
    TrendingListResponse,
    TrendingStoryCluster,
)
from backend.services.story_presentation_service import (
    StoryPresentationService,
    get_story_presentation_service,
)
from backend.services.trending_service import (
    TrendingService,
    get_trending_service,
)

router = APIRouter(prefix="/api/news", tags=["trending"])


class EnrichedTrendingResponse(TrendingListResponse):
    """
    Backward-compatible response model for GET /api/news/trending.
    Maintains all legacy fields (total, updated, trending, articles, clusters,
    trending_hashtags, hero) while attaching deterministic TrendingScoreBreakdown,
    ranked trending story clusters, and coverage limitation disclaimer.
    """
    model_config = ConfigDict(extra="allow")

    stories: list[TrendingStoryCluster] = Field(
        default_factory=list,
        description="Ranked active story clusters with deterministic score breakdown",
    )
    coverage_disclaimer: str = Field(
        default=(
            "Trending reflects how widely and frequently the collected outlets "
            "are covering a story, not verified public interest."
        ),
        description="Mandatory coverage limitation disclaimer",
    )


@router.get("/trending", response_model=EnrichedTrendingResponse)
async def get_trending(
    limit: int = Query(default=5, ge=1, le=50, description="Max trending items to return"),
    category: str | None = Query(default=None, description="Filter by category"),
    service: TrendingService = Depends(get_trending_service),
    presentation_service: StoryPresentationService = Depends(get_story_presentation_service),
) -> EnrichedTrendingResponse:
    """
    Get top ranked trending news with backward-compatible legacy article projection,
    explainable TrendingScoreBreakdown, multi-source consensus, and enriched
    story presentation (headline, summary, timeline with citations).
    Guarantees HTTP 200 even if LLM is unavailable (graceful heuristic fallback).
    """
    # L1 In-Memory Cache Check (< 0.5 ms)
    cache_key = f"trending_legacy:{limit}:{category or 'all'}"
    cached_data = await trending_cache.get(cache_key)
    if cached_data is not None:
        return EnrichedTrendingResponse(**cached_data)

    # 1. Fetch legacy article-based trending clusters (with TrendingScoreBreakdown)
    legacy_resp = await asyncio.to_thread(service.get_trending_articles, category=category, limit=limit)

    # 2. Fetch active story-based clusters from the persistent Story Identification layer
    top_stories = await asyncio.to_thread(service.get_trending_stories, limit=limit, category=category)

    # 3. Enrich top stories with presentation (Deterministic heuristic fallback, decoupled LLM)
    await asyncio.to_thread(presentation_service.enrich_top_stories, top_stories, top_n=min(limit, 5), allow_llm=False)

    trending_articles = list(legacy_resp.trending)
    articles_list = list(legacy_resp.articles)
    clusters_list = list(legacy_resp.clusters)
    hashtags = list(legacy_resp.trending_hashtags)
    hero = legacy_resp.hero

    # 4. If legacy article clustering yielded no items but active stories exist,
    # synthesize backward-compatible TrendingArticle objects from top_stories
    if not trending_articles and top_stories:
        for idx, story in enumerate(top_stories):
            primary_outlet = story.outlets[0] if story.outlets else "สำนักข่าว"
            first_url = story.article_urls[0] if story.article_urls else ""
            t_art = TrendingArticle(
                title=story.headline or story.title,
                summary=story.summary or f"ประเด็นข่าว: {story.title}",
                source=primary_outlet,
                url=first_url,
                image_url="",
                category=story.category,
                fetched_at=story.updated_at,
                trending_score=story.trending_score,
                cluster_id=story.story_id,
                cluster_size=story.article_count,
                cluster_sources=story.outlets,
                is_multi_source=story.outlet_count > 1,
                badges=list(story.badges),
                breakdown=story.breakdown,
                topic_title=story.headline or story.title,
                hashtags=[],
                cluster_summary=story.summary,
            )
            trending_articles.append(t_art)
            articles_list.append(t_art)

            t_cluster = TrendingCluster(
                cluster_id=story.story_id,
                topic_title=story.headline or story.title,
                hashtags=[],
                cluster_summary=story.summary,
                source_count=story.outlet_count,
                article_count=story.article_count,
                avg_similarity=1.0,
                trend_score=story.trending_score,
                is_multi_source=story.outlet_count > 1,
                articles=[t_art],
            )
            clusters_list.append(t_cluster)

        hero = trending_articles[0] if trending_articles else None

    # 5. Cross-enrich legacy articles with story headlines and summaries when matching
    story_map = {s.story_id: s for s in top_stories}
    for art in trending_articles:
        if art.cluster_id and art.cluster_id in story_map:
            st = story_map[art.cluster_id]
            art.topic_title = st.headline or st.title
            art.cluster_summary = st.summary
            if not art.breakdown or art.breakdown.final_score == 0.0:
                art.breakdown = st.breakdown
                art.trending_score = st.trending_score

    resp = EnrichedTrendingResponse(
        total=len(trending_articles),
        updated=legacy_resp.updated,
        trending=trending_articles[:limit],
        articles=articles_list[:limit],
        clusters=clusters_list[:limit],
        trending_hashtags=hashtags,
        hero=hero,
        stories=top_stories,
        coverage_disclaimer=(
            "Trending reflects how widely and frequently the collected outlets "
            "are covering a story, not verified public interest."
        ),
    )
    await trending_cache.set(cache_key, resp.model_dump(), ttl_seconds=float(settings.trending_cache_ttl_seconds))
    return resp


@router.post("/engage")
async def record_engagement(
    event: EngagementEvent,
    repo: FileEngagementRepository = Depends(get_engagement_repository),
) -> JSONResponse:
    """
    Record an anonymous reader engagement event (click, summary, or bookmark)
    without collecting any PII.
    """
    stats = repo.record_event(url=event.url, event_type=event.event_type)
    return JSONResponse(
        {
            "ok": True,
            "url": event.url,
            "event_type": event.event_type,
            "stats": stats,
        }
    )


@router.post("/engagement")
async def record_engagement_alias(
    event: EngagementEvent,
    repo: FileEngagementRepository = Depends(get_engagement_repository),
) -> JSONResponse:
    """
    Alias endpoint for /api/news/engage.
    """
    return await record_engagement(event=event, repo=repo)
