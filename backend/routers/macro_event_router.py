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

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.repo.macro_event_repo import (
    MacroEventRepositoryPort,
    get_macro_event_repository,
)
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
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
    all_macros = macro_repo.list_macro_events(status=status_filter, limit=1000, offset=0)

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
    return trending_service.get_trending_macro_events(limit=limit, category=category)


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
    )
