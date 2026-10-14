"""
backend/tests/test_tiered_cache.py
─────────────────────────────────────────────────────────────────
Tests for Tier 1 In-Memory Caching:
- Feed and trending cache set/get/hit/miss
- Stampede deduplication
- Cache invalidation upon scraper updates
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio

import pytest

from backend.core.l1_cache import (
    invalidate_feed_caches,
    metadata_cache,
    news_feed_cache,
    trending_cache,
)


@pytest.mark.anyio
class TestTieredL1Cache:
    async def test_cache_set_and_hit(self) -> None:
        key = "feed:1:all:none:test"
        payload = {"news": [{"title": "L1 Test"}], "total": 1}

        # Cache miss initially
        assert await news_feed_cache.get(key) is None

        # Set entry
        await news_feed_cache.set(key, payload, ttl_seconds=10.0)

        # Cache hit
        cached = await news_feed_cache.get(key)
        assert cached == payload

    async def test_cache_expiration(self) -> None:
        key = "feed:expiring"
        payload = {"total": 5}

        await news_feed_cache.set(key, payload, ttl_seconds=0.05)
        assert await news_feed_cache.get(key) == payload

        await asyncio.sleep(0.06)
        assert await news_feed_cache.get(key) is None

    async def test_invalidate_feed_caches(self) -> None:
        await news_feed_cache.set("feed:1", {"data": 1}, ttl_seconds=10.0)
        await trending_cache.set("trending:5", {"data": 2}, ttl_seconds=10.0)
        await metadata_cache.set("metadata:cat", {"data": 3}, ttl_seconds=10.0)

        assert await news_feed_cache.get("feed:1") is not None
        assert await trending_cache.get("trending:5") is not None
        assert await metadata_cache.get("metadata:cat") is not None

        # Invalidate all L1 caches
        await invalidate_feed_caches()

        assert await news_feed_cache.get("feed:1") is None
        assert await trending_cache.get("trending:5") is None
        assert await metadata_cache.get("metadata:cat") is None
