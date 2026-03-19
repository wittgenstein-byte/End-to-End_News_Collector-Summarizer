"""
routers/news_router.py
─────────────────────────────────────────────────────────────────
SOLID  I — แยก router ตาม concern:
           news_router  → อ่าน / filter ข่าว
           collect_router → ดึง + สรุปบทความ
SOLID  D — inject repository ผ่าน FastAPI Depends()
GRASP  Controller — รับ HTTP request → เรียก service/repo → คืน response
                   ไม่มี business logic ในนี้
─────────────────────────────────────────────────────────────────
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from config import settings
from repo.news_repo import FileNewsRepository, get_news_repository

router = APIRouter(prefix="/api", tags=["news"])


@router.get("/news")
async def get_news(
    page: int = 1,
    source: str = "",
    q: str = "",
    repo: FileNewsRepository = Depends(get_news_repository),
) -> JSONResponse:
    page   = max(1, page)
    source = source.strip()
    query  = q.strip().lower()

    news = repo.load_news()
    news.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)

    if source:
        news = [n for n in news if n.get("source", "").lower() == source.lower()]
    if query:
        news = [
            n for n in news
            if query in n.get("title", "").lower()
            or query in n.get("summary", "").lower()
        ]

    total       = len(news)
    total_pages = max(1, (total + settings.page_size - 1) // settings.page_size)
    start       = (page - 1) * settings.page_size
    page_items  = news[start : start + settings.page_size]

    return JSONResponse({
        "total":       total,
        "page":        page,
        "page_size":   settings.page_size,
        "total_pages": total_pages,
        "has_next":    page < total_pages,
        "has_prev":    page > 1,
        "updated":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "news":        page_items,
    })


@router.get("/sources")
async def get_sources(
    repo: FileNewsRepository = Depends(get_news_repository),
) -> JSONResponse:
    news   = repo.load_news()
    counts: dict[str, int] = {}
    for n in news:
        src = n.get("source", "unknown")
        counts[src] = counts.get(src, 0) + 1
    return JSONResponse({"sources": counts})


@router.get("/status")
async def get_status(
    repo: FileNewsRepository = Depends(get_news_repository),
) -> JSONResponse:
    return JSONResponse({
        "status":   "running",
        "interval": f"{settings.interval_minutes} minutes",
        "total":    len(repo.load_news()),
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })