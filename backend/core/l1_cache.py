"""
core/l1_cache.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ Tier 1 In-Memory Caching สำหรับ API responses
SOLID  O — ขยาย cache categories ได้ผ่าน AsyncInMemoryCache
SOLID  D — Routers พึ่งพา L1 cache facade แทนการจัดการ RAM เอง
GRASP  Pure Fabrication — Shared caching infrastructure สำหรับ L1 RAM Tier
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.config import settings
from backend.core.cache import AsyncInMemoryCache

logger = logging.getLogger(__name__)

# ── L1 Singletons ─────────────────────────────────────────────────

# Feed cache: stores paginated JSON responses for /api/news
news_feed_cache: AsyncInMemoryCache[dict[str, Any]] = AsyncInMemoryCache(
    max_size=500,
    default_ttl_seconds=float(settings.news_cache_ttl_seconds),
)

# Trending cache: stores ranked trending responses for /api/news/trending and /api/stories/trending
trending_cache: AsyncInMemoryCache[dict[str, Any]] = AsyncInMemoryCache(
    max_size=100,
    default_ttl_seconds=float(settings.trending_cache_ttl_seconds),
)

# Metadata cache: stores category and source count distributions
metadata_cache: AsyncInMemoryCache[dict[str, Any]] = AsyncInMemoryCache(
    max_size=50,
    default_ttl_seconds=float(settings.metadata_cache_ttl_seconds),
)


# ── Invalidation Utilities ────────────────────────────────────────

async def invalidate_feed_caches() -> None:
    """Invalidate all L1 feed, trending, and metadata caches (e.g. after fresh scrape)."""
    try:
        await asyncio.gather(
            news_feed_cache.clear(),
            trending_cache.clear(),
            metadata_cache.clear(),
            return_exceptions=True,
        )
        logger.debug("L1 feed, trending, and metadata caches cleared.")
    except Exception as exc:
        logger.warning("Error clearing L1 caches: %s", exc)


def invalidate_feed_caches_sync() -> None:
    """Sync bridge to schedule L1 cache invalidation from synchronous threads or loops."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(invalidate_feed_caches())
    except RuntimeError:
        # No running event loop in current thread; run one-shot
        try:
            asyncio.run(invalidate_feed_caches())
        except Exception as exc:
            logger.warning("Failed to run sync L1 invalidation: %s", exc)
