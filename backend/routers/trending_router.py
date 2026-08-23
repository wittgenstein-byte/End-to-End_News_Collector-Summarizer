"""
routers/trending_router.py
─────────────────────────────────────────────────────────────────
SOLID  I — Focused route handlers for trending news & reader telemetry
SOLID  D — Injects TrendingService & FileEngagementRepository via Depends()
GRASP  Controller — Coordinates HTTP requests with domain services
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.repo.engagement_repo import (
    FileEngagementRepository,
    get_engagement_repository,
)
from backend.schemas.trending_schema import (
    EngagementEvent,
    TrendingListResponse,
)
from backend.services.trending_service import (
    TrendingService,
    get_trending_service,
)

router = APIRouter(prefix="/api/news", tags=["trending"])


@router.get("/trending", response_model=TrendingListResponse)
async def get_trending(
    limit: int = Query(default=5, ge=1, le=50, description="Max trending items to return"),
    category: str | None = Query(default=None, description="Filter by category"),
    service: TrendingService = Depends(get_trending_service),
) -> TrendingListResponse:
    """
    Get top ranked trending news articles with hero highlight, multi-source
    consensus cluster metadata, and visual status badges.
    """
    return service.get_trending_articles(category=category, limit=limit)


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
