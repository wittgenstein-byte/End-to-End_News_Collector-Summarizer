"""
routers/monitoring_router.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ endpoints /api/monitoring/* สำหรับ Admin/Dev เท่านั้น
SOLID  D — inject repositories, caches, และ scraper service
GRASP  Controller — ตรวจสอบสิทธิ์ (Auth Guard) และรวบรวม metrics
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import settings
from backend.core.http_cache import http_cache
from backend.repo.engagement_repo import (
    FileEngagementRepository,
    get_engagement_repository,
)
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.services.scraper_service import get_scraper_service
from backend.services.summarizer_service import get_summary_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

# Timestamp when the app process loaded
_PROCESS_START_TIME: float = time.time()

# Active admin session tokens: {token: expires_at_timestamp}
_VALID_SESSIONS: dict[str, float] = {}
_MAX_ACTIVE_SESSIONS: int = 100


def _prune_sessions(now: float) -> None:
    """Remove expired session tokens and enforce maximum active session cap."""
    expired = [tok for tok, exp in _VALID_SESSIONS.items() if exp <= now]
    for tok in expired:
        _VALID_SESSIONS.pop(tok, None)

    while len(_VALID_SESSIONS) >= _MAX_ACTIVE_SESSIONS:
        oldest_tok = min(_VALID_SESSIONS, key=_VALID_SESSIONS.get)  # type: ignore[arg-type]
        _VALID_SESSIONS.pop(oldest_tok, None)


# ── Pydantic Request Models ───────────────────────────────────────

class AuthRequest(BaseModel):
    key: str


class SourceTestRequest(BaseModel):
    source: str


# ── Auth Guard Dependency ─────────────────────────────────────────

def verify_monitoring_auth(
    authorization: str | None = Header(default=None),
    x_admin_key: str | None = Header(default=None),
) -> bool:
    """
    Guards monitoring routes. Requires:
    - Bearer <session_token> OR
    - Direct X-Admin-Key matching settings.monitoring_admin_key OR
    - Bearer <settings.monitoring_admin_key>
    """
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_admin_key:
        token = x_admin_key.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for admin monitoring",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time master key comparison (prevents timing attacks)
    if settings.monitoring_admin_key and secrets.compare_digest(
        token.encode("utf-8"),
        settings.monitoring_admin_key.encode("utf-8"),
    ):
        return True

    # Check session token
    now = time.time()
    expires_at = _VALID_SESSIONS.get(token)
    if expires_at and expires_at > now:
        return True

    # Cleanup expired tokens occasionally
    if expires_at and expires_at <= now:
        _VALID_SESSIONS.pop(token, None)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired admin authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── Routes ────────────────────────────────────────────────────────

@router.post("/auth")
async def login(req: AuthRequest) -> JSONResponse:
    """Validate admin key and return session token."""
    cleaned_key = req.key.strip()
    if (
        not cleaned_key
        or not settings.monitoring_admin_key
        or not secrets.compare_digest(
            cleaned_key.encode("utf-8"),
            settings.monitoring_admin_key.encode("utf-8"),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="รหัสผ่าน Admin / Dev Key ไม่ถูกต้อง",
        )

    # Issue session token with bounded session storage
    now = time.time()
    _prune_sessions(now)
    token = secrets.token_hex(24)
    expires_at = now + float(settings.monitoring_session_ttl_seconds)
    _VALID_SESSIONS[token] = expires_at

    return JSONResponse(
        {
            "ok": True,
            "token": token,
            "expires_in": settings.monitoring_session_ttl_seconds,
            "message": "เข้าสู่ระบบสำเร็จ",
        }
    )


@router.get("/verify")
async def verify_auth(
    _is_authed: bool = Depends(verify_monitoring_auth),
) -> JSONResponse:
    """Check if current token is still valid."""
    return JSONResponse({"ok": True, "status": "authenticated"})


@router.get("/stats")
async def get_monitoring_stats(
    _is_authed: bool = Depends(verify_monitoring_auth),
    repo: NewsRepositoryPort = Depends(get_news_repository),
    engagement_repo: FileEngagementRepository = Depends(get_engagement_repository),
) -> JSONResponse:
    """Return comprehensive system, scraper, cache, and telemetry metrics."""
    uptime_seconds = int(time.time() - _PROCESS_START_TIME)

    # Storage counts
    total_news = 0
    total_seen = 0
    try:
        total_news = len(repo.load_news())
        total_seen = len(repo.load_seen())
    except Exception:
        pass

    # Collected MD count
    collected_md_count = 0
    if settings.collected_md_dir.exists():
        try:
            collected_md_count = len(list(settings.collected_md_dir.glob("*.md")))
        except Exception:
            pass

    # Scraper metrics
    scraper = get_scraper_service()
    scraper_metrics = scraper.get_metrics() if scraper else {
        "is_scraping": False,
        "interval_minutes": settings.interval_minutes,
        "total_cycles_completed": 0,
        "last_cycle_started_at": None,
        "last_cycle_finished_at": None,
        "sources": [],
        "recent_logs": [],
    }

    # Cache stats
    summary_cache = get_summary_cache()
    summary_stats = summary_cache.stats() if hasattr(summary_cache, "stats") else {}
    http_stats = http_cache.stats() if hasattr(http_cache, "stats") else {}

    # Reader telemetry
    all_engagements = engagement_repo.get_all_engagements()
    total_clicks = sum(e.get("clicks", 0) for e in all_engagements.values())
    total_summaries = sum(e.get("summaries", 0) for e in all_engagements.values())
    total_bookmarks = sum(e.get("bookmarks", 0) for e in all_engagements.values())

    # Top engaged
    top_items = sorted(
        [
            {"url": u, **stats, "total": stats.get("clicks", 0) + stats.get("summaries", 0) * 2 + stats.get("bookmarks", 0) * 3}
            for u, stats in all_engagements.items()
        ],
        key=lambda x: int(x["total"]),
        reverse=True,
    )[:5]

    return JSONResponse(
        {
            "ok": True,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "system": {
                "uptime_seconds": uptime_seconds,
                "data_dir": str(settings.DATA_DIR),
                "total_news_articles": total_news,
                "total_seen_urls": total_seen,
                "collected_md_count": collected_md_count,
            },
            "scraper": scraper_metrics,
            "caches": {
                "http_cache": http_stats,
                "summary_cache": summary_stats,
            },
            "engagement": {
                "total_clicks": total_clicks,
                "total_summaries": total_summaries,
                "total_bookmarks": total_bookmarks,
                "top_articles": top_items,
            },
        }
    )


@router.post("/scrape-now")
async def trigger_scrape_now(
    _is_authed: bool = Depends(verify_monitoring_auth),
) -> JSONResponse:
    """Manually trigger background scraper cycle."""
    scraper = get_scraper_service()
    if not scraper:
        raise HTTPException(status_code=500, detail="Scraper service not initialized")

    started = scraper.trigger_scrape()
    return JSONResponse(
        {
            "ok": True,
            "started": started,
            "message": "สั่งดึงข่าวเรียบร้อยแล้ว กำลังเริ่มทำงาน..." if started else "Scraper กำลังทำงานอยู่ในขณะนี้ กรุณารอสักครู่",
        }
    )


@router.post("/clear-cache")
async def clear_caches(
    _is_authed: bool = Depends(verify_monitoring_auth),
) -> JSONResponse:
    """Clear in-memory HTTP cache and AI summary cache."""
    await http_cache.clear()
    summary_cache = get_summary_cache()
    await summary_cache.clear()

    scraper = get_scraper_service()
    if scraper:
        scraper.log_event("INFO", "Caches (HTTP 304 & AI Summary) cleared by admin", "admin")

    return JSONResponse(
        {
            "ok": True,
            "message": "ล้างข้อมูลแคชทั้งหมดเรียบร้อยแล้ว",
        }
    )


@router.post("/test-source")
async def test_source(
    req: SourceTestRequest,
    _is_authed: bool = Depends(verify_monitoring_auth),
) -> JSONResponse:
    """Run an isolated test scrape for a single news source."""
    scraper = get_scraper_service()
    if not scraper:
        raise HTTPException(status_code=500, detail="Scraper service not initialized")

    result = await scraper.test_single_source(req.source)
    return JSONResponse(result)
