"""
backend/issue_explorer/router.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ HTTP endpoints /api/issues/* และ Rate Limiting เท่านั้น
SOLID  D — เรียกใช้งานผ่าน IssueExplorerService
GRASP  Controller — รับ HTTP parameters, ตรวจสอบ validation, และ map response
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from backend.config import settings
from backend.issue_explorer.schemas import HealthResponse, IssueSearchResponse
from backend.issue_explorer.service import IssueExplorerService, get_issue_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/issues", tags=["issue-explorer"])

# In-memory sliding window rate limiter: {ip: [timestamp, ...]}
_RATE_LIMIT_STORE: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_CLEANUP_INTERVAL = 60.0
_LAST_CLEANUP_TIME = time.time()


def _get_client_ip(request: Request) -> str:
    """Extract client IP prioritizing Cloudflare header with client.host fallback."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()

    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded and x_forwarded.strip():
        # First IP in chain is client IP
        return x_forwarded.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


def check_rate_limit(request: Request) -> None:
    """Sliding window rate limit enforcer (per minute)."""
    global _LAST_CLEANUP_TIME
    now = time.time()
    ip = _get_client_ip(request)

    # Periodic cleanup of old IPs
    if now - _LAST_CLEANUP_TIME > _RATE_LIMIT_CLEANUP_INTERVAL:
        expired_ips = [k for k, timestamps in _RATE_LIMIT_STORE.items() if not timestamps or timestamps[-1] < now - 60.0]
        for k in expired_ips:
            _RATE_LIMIT_STORE.pop(k, None)
        _LAST_CLEANUP_TIME = now

    window_start = now - 60.0
    timestamps = [t for t in _RATE_LIMIT_STORE[ip] if t > window_start]
    max_reqs = settings.issue_rate_limit_per_min

    if len(timestamps) >= max_reqs:
        logger.warning("Rate limit exceeded for IP %s (%d requests/min)", ip, len(timestamps))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="คำขอค้นหาบ่อยเกินไป กรุณารอสักครู่ (Rate limit exceeded)",
            headers={"Retry-After": "30"},
        )

    timestamps.append(now)
    _RATE_LIMIT_STORE[ip] = timestamps


@router.get("/health", response_model=HealthResponse)
async def issue_health(
    service: IssueExplorerService = Depends(get_issue_service),
) -> HealthResponse:
    """Health check for Issue Explorer storage and indexing."""
    if settings.db_type != "sqlite":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Issue Explorer requires SQLite storage (current: {settings.db_type})",
        )
    return await service.get_health()


@router.get("/search", response_model=IssueSearchResponse)
async def search_issues(
    request: Request,
    response: Response,
    q: str = Query(..., min_length=1, max_length=100, description="คำค้นหาหรือประเด็น เช่น 'สตง', 'ไทยพีบีเอส -กีฬา'"),
    expand: bool = Query(True, description="ขยายคำพ้องและคำย่ออัตโนมัติ"),
    date_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="วันที่เริ่มต้น YYYY-MM-DD"),
    date_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="วันที่สิ้นสุด YYYY-MM-DD"),
    source: str | None = Query(None, description="กรองสำนักข่าว เช่น Thairath, ThaiPBS"),
    category: str | None = Query(None, description="กรองหมวดหมู่ เช่น politics, economy"),
    deep: bool = Query(False, description="ค้นหาเนื้อหาบทความแบบเจาะลึก (reserved for future)"),
    limit: int = Query(200, ge=1, le=500, description="จำนวนข่าวสูงสุด"),
    service: IssueExplorerService = Depends(get_issue_service),
) -> IssueSearchResponse:
    """
    Search and analyze news issues deterministically without LLM.
    Returns sub-topic clusters, timeline distribution, outlier detection, and related keywords.
    """
    # 1. Enforce rate limiting
    check_rate_limit(request)

    # 2. Enforce storage compatibility
    if settings.db_type != "sqlite":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ฟีเจอร์เจาะประเด็นรองรับเฉพาะฐานข้อมูล SQLite (ปัจจุบันเป็น: {settings.db_type})",
        )

    # 3. Add Cache-Control header to prevent edge caching of search queries
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    try:
        return await service.search(
            q=q,
            expand=expand,
            date_from=date_from,
            date_to=date_to,
            source=source,
            category=category,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error during issue explorer search for query '%s'", q)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"เกิดข้อผิดพลาดในการประมวลผลเจาะประเด็น: {exc!s}",
        )
