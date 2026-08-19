"""
routers/event_router.py
────────────────────────────────────────────────────────────────
SOLID  S — ปลายทาง HTTP สำหรับ anonymous event tracking เท่านั้น
GRASP  Controller — รับ request → บันทึกลง SQLite → คืน status
────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from backend.repo.event_repo import EventRepository, get_event_repository
from backend.schemas.event_schema import EventRecordRequest

router = APIRouter(prefix="/api", tags=["events"])


@router.post("/events")
async def track_event(
    req: EventRecordRequest,
    repo: EventRepository = Depends(get_event_repository),
) -> JSONResponse:
    if not req.user_id or not req.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    user_id = req.user_id.strip()
    repo.upsert_user(user_id, consented=req.consented)
    repo.record_event(
        user_id=user_id,
        event_name=req.event_name,
        article_url=req.article_url,
        article_title=req.article_title,
        source=req.source,
        category=req.category,
        metadata=req.metadata,
    )
    return JSONResponse({"ok": True, "event": req.event_name, "user_id": user_id})


@router.get("/events/health")
async def event_health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "event-tracker"})
