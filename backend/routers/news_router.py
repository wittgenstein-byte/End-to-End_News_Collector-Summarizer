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

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from backend.config import settings
from backend.core.constants import BROWSER_HEADERS
from backend.core.l1_cache import metadata_cache, news_feed_cache
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.services.classifier_service import ensure_categories

router = APIRouter(prefix="/api", tags=["news"])

VALID_CATEGORIES = {
    "politics",
    "economy",
    "technology",
    "health",
    "environment",
    "sports",
    "entertainment",
    "society",
    "world",
}

_ALLOWED_IMAGE_HOSTS = {"thestandard.co", "www.thestandard.co"}


def _proxy_image_url(url: str, source: str) -> str:
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if source.lower() == "the standard" or parsed.netloc in _ALLOWED_IMAGE_HOSTS:
        return f"/api/image?url={quote(url, safe='')}"
    return url


@router.get("/news")
async def get_news(
    page: int = 1,
    source: str = "",
    q: str = "",
    category: str | None = None,
    repo: NewsRepositoryPort = Depends(get_news_repository),
) -> JSONResponse:
    page = max(1, page)
    source = source.strip()
    query = q.strip().lower()
    cat_filter = category if (category and category in VALID_CATEGORIES) else None

    # L1 In-Memory Cache Check (< 0.5 ms)
    cache_key = f"feed:{page}:{source}:{cat_filter}:{query}"
    cached_feed = await news_feed_cache.get(cache_key)
    if cached_feed is not None:
        return JSONResponse(cached_feed)

    page_items, total = await asyncio.to_thread(
        repo.query_news,
        page=page,
        page_size=settings.page_size,
        source=source,
        category=cat_filter,
        query=query,
    )

    # Ensure categories for returned page items
    updated = ensure_categories(page_items)
    if updated:
        await asyncio.to_thread(repo.save_news, page_items)

    total_pages = max(1, (total + settings.page_size - 1) // settings.page_size)
    for item in page_items:
        item["image_url"] = _proxy_image_url(
            item.get("image_url", ""),
            item.get("source", ""),
        )

    response_payload = {
        "total": total,
        "page": page,
        "page_size": settings.page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "news": page_items,
    }

    # Store in L1 RAM cache
    await news_feed_cache.set(cache_key, response_payload, ttl_seconds=float(settings.news_cache_ttl_seconds))
    return JSONResponse(response_payload)


@router.get("/news/content")
async def get_article_content(
    url: str,
    repo: NewsRepositoryPort = Depends(get_news_repository),
) -> JSONResponse:
    """Fetch decoupled heavy article body content/markdown by URL."""
    clean_url = url.strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="URL is required")

    content_data = await asyncio.to_thread(repo.get_article_content, clean_url)
    if not content_data:
        raise HTTPException(status_code=404, detail="Article content not found")
    return JSONResponse({"url": clean_url, **content_data})


@router.get("/categories")
async def get_categories(
    repo: NewsRepositoryPort = Depends(get_news_repository),
) -> JSONResponse:
    """
    คืนจำนวนข่าวในแต่ละหมวดหมู่สำหรับ badge บน category tabs
    """
    cache_key = "metadata:categories"
    cached_counts = await metadata_cache.get(cache_key)
    if cached_counts is not None:
        return JSONResponse(cached_counts)

    cat_counts = await asyncio.to_thread(repo.get_category_counts)
    counts: dict[str, int] = {cat: cat_counts.get(cat, 0) for cat in VALID_CATEGORIES}
    counts["all"] = cat_counts.get("all", sum(counts.values()))
    payload = {"categories": counts}

    await metadata_cache.set(cache_key, payload, ttl_seconds=float(settings.metadata_cache_ttl_seconds))
    return JSONResponse(payload)


@router.get("/sources")
async def get_sources(
    repo: NewsRepositoryPort = Depends(get_news_repository),
) -> JSONResponse:
    """
    คืนจำนวนข่าวในแต่ละแหล่งข่าว
    """
    cache_key = "metadata:sources"
    cached_sources = await metadata_cache.get(cache_key)
    if cached_sources is not None:
        return JSONResponse(cached_sources)

    src_counts = await asyncio.to_thread(repo.get_source_counts)
    payload = {"sources": src_counts}

    await metadata_cache.set(cache_key, payload, ttl_seconds=float(settings.metadata_cache_ttl_seconds))
    return JSONResponse(payload)


@router.get("/status")
async def get_status(
    repo: NewsRepositoryPort = Depends(get_news_repository),
) -> JSONResponse:
    cat_counts = await asyncio.to_thread(repo.get_category_counts)
    total_count = cat_counts.get("all", 0)
    return JSONResponse(
        {
            "status": "running",
            "interval": f"{settings.interval_minutes} minutes",
            "total": total_count,
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
    )




@router.get("/image")
async def proxy_image(url: str) -> StreamingResponse:
    """
    Proxy image to avoid hotlink protection (currently used for The Standard).
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in _ALLOWED_IMAGE_HOSTS:
        raise HTTPException(status_code=400, detail="Unsupported image host")

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers=BROWSER_HEADERS, timeout=10)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch image")
        media_type = resp.headers.get("content-type", "image/jpeg")
        return StreamingResponse(iter([resp.content]), media_type=media_type)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Image fetch error")
