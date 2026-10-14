"""
tests/test_summary_cache.py
─────────────────────────────────────────────────────────────────
Unit tests for AI News Summary In-Memory Cache (R1 / Milestone 1)
Covers:
- AsyncInMemoryCache basic get/set/delete/clear/size/stats
- TTL expiration mechanics
- LRU max capacity eviction
- Single-flight stampede / thundering herd deduplication
- Error isolation and retry
- URL normalization for cache key generation
- SummarizerService caching and LLM call deduplication
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from backend.core.cache import AsyncInMemoryCache
from backend.schemas.news_schema import NewsSummary
from backend.services.summarizer_service import (
    SummarizerService,
    normalize_article_url,
)

# ── Fixtures & Helpers ────────────────────────────────────────────

def create_sample_summary(title: str = "Test Title", url: str = "https://example.com/test") -> NewsSummary:
    return NewsSummary(
        title=title,
        source_url=url,
        published_at="2026-08-21T10:00:00Z",
        language="th",
        summary="This is a test summary for testing the cache layer.",
        bullets=["Point 1", "Point 2", "Point 3"],
        category="technology",
        sentiment="positive",
        keywords=["test", "cache", "ai"],
    )


# ── Test AsyncInMemoryCache Core Mechanics ────────────────────────

@pytest.mark.anyio
async def test_cache_set_and_get():
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=60.0)
    await cache.set("k1", "val1")

    val = await cache.get("k1")
    assert val == "val1"
    assert cache.hits == 1
    assert cache.misses == 0
    assert cache.size() == 1


@pytest.mark.anyio
async def test_cache_miss():
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=60.0)
    val = await cache.get("nonexistent")
    assert val is None
    assert cache.hits == 0
    assert cache.misses == 1


@pytest.mark.anyio
async def test_cache_ttl_expiration():
    # Cache with very short TTL
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=0.05)
    await cache.set("k1", "val1")

    # Immediate get -> hit
    assert await cache.get("k1") == "val1"

    # Wait for TTL to expire
    await asyncio.sleep(0.08)

    # Expired get -> miss and purged
    assert await cache.get("k1") is None
    assert cache.size() == 0


@pytest.mark.anyio
async def test_cache_lru_eviction():
    # Max size = 3
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=3, default_ttl_seconds=60.0)
    await cache.set("k1", "v1")
    await cache.set("k2", "v2")
    await cache.set("k3", "v3")
    assert cache.size() == 3

    # Access k1 so k2 becomes the least recently used
    assert await cache.get("k1") == "v1"

    # Insert k4 -> should evict k2
    await cache.set("k4", "v4")
    assert cache.size() == 3
    assert await cache.get("k2") is None  # evicted
    assert await cache.get("k1") == "v1"  # kept
    assert await cache.get("k3") == "v3"  # kept
    assert await cache.get("k4") == "v4"  # kept
    assert cache.evictions == 1


@pytest.mark.anyio
async def test_cache_delete_and_clear():
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=5, default_ttl_seconds=60.0)
    await cache.set("k1", "v1")
    await cache.set("k2", "v2")

    deleted = await cache.delete("k1")
    assert deleted is True
    assert await cache.get("k1") is None

    not_deleted = await cache.delete("k999")
    assert not_deleted is False

    await cache.clear()
    assert cache.size() == 0
    stats = cache.stats()
    assert stats["size"] == 0
    assert stats["max_size"] == 5


# ── Test Single-Flight Concurrency & Stampede Deduplication ───────

@pytest.mark.anyio
async def test_cache_single_flight_stampede_deduplication():
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=60.0)
    call_count = 0

    async def expensive_compute() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # Simulate network / LLM delay
        return f"computed_result_{call_count}"

    # Launch 20 concurrent tasks for the exact same key
    tasks = [cache.get_or_compute("article_123", expensive_compute) for _ in range(20)]
    results = await asyncio.gather(*tasks)

    # All 20 callers must receive the exact same computed result
    assert len(results) == 20
    assert all(r == "computed_result_1" for r in results)
    # The expensive computation must have executed EXACTLY once
    assert call_count == 1

    # Subsequent call hits the cache directly
    subsequent = await cache.get_or_compute("article_123", expensive_compute)
    assert subsequent == "computed_result_1"
    assert call_count == 1


@pytest.mark.anyio
async def test_cache_error_isolation_and_retry():
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=60.0)
    attempt = 0

    async def failing_compute() -> str:
        nonlocal attempt
        attempt += 1
        await asyncio.sleep(0.02)
        if attempt == 1:
            raise RuntimeError("Upstream LLM API error")
        return "success_recovery"

    # Launch 5 concurrent tasks that will hit the failing compute
    tasks = [cache.get_or_compute("error_key", failing_compute) for _ in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # All callers should get the RuntimeError
    assert len(results) == 5
    for r in results:
        assert isinstance(r, RuntimeError)
        assert "Upstream LLM API error" in str(r)

    # The error must NOT be cached
    assert await cache.get("error_key") is None
    assert cache.size() == 0

    # Retry should succeed and execute the computation again
    recovered = await cache.get_or_compute("error_key", failing_compute)
    assert recovered == "success_recovery"
    assert attempt == 2
    assert await cache.get("error_key") == "success_recovery"


# ── Test URL Normalization ────────────────────────────────────────

def test_url_normalization():
    # 1. Strips fragment
    assert normalize_article_url("https://example.com/news/123#header") == "https://example.com/news/123"

    # 2. Strips UTM & tracking params
    raw = "https://WWW.Example.COM/news/123?utm_source=twitter&utm_medium=social&fbclid=XYZ123&keep=1#sec"
    normalized = normalize_article_url(raw)
    assert normalized == "https://www.example.com/news/123?keep=1"

    # 3. Sorts query params
    assert normalize_article_url("https://example.com/item?z=2&a=1") == "https://example.com/item?a=1&z=2"

    # 4. Normalizes trailing slash
    assert normalize_article_url("https://example.com/path/") == "https://example.com/path"
    assert normalize_article_url("https://example.com/") == "https://example.com"
    assert normalize_article_url("") == ""


# ── Test SummarizerService Integration with Cache ─────────────────

@pytest.mark.anyio
async def test_summarizer_service_caching():
    sample_summary = create_sample_summary(title="AI Breakthrough in 2026")
    cache: AsyncInMemoryCache[NewsSummary] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=60.0)

    mock_client = MagicMock()
    # Mock OpenAI chat completion
    mock_choice = MagicMock()
    mock_choice.message.content = sample_summary.model_dump_json()
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    summarizer = SummarizerService(
        client=mock_client,
        model="gemini-3.1-flash-lite-preview",
        temperature=0.3,
        cache=cache,
    )

    url = "https://www.thaipbs.or.th/news/content/999?utm_source=rss#top"
    md = "# AI Breakthrough\n\nFull article content here..."

    # Call 1: Cache Miss -> calls OpenAI
    res1 = await summarizer.summarize_async(md, url=url)
    assert res1.title == "AI Breakthrough in 2026"
    assert mock_client.chat.completions.create.call_count == 1

    # Call 2: Same URL (even with different tracking query params) -> Cache Hit -> NO OpenAI call
    url_variant = "https://www.thaipbs.or.th/news/content/999?fbclid=abc"
    res2 = await summarizer.summarize_async(md, url=url_variant)
    assert res2.title == "AI Breakthrough in 2026"
    assert mock_client.chat.completions.create.call_count == 1  # Still 1!


@pytest.mark.anyio
async def test_summarizer_service_concurrency_stampede():
    sample_summary = create_sample_summary(title="Stampede Defense Test")
    cache: AsyncInMemoryCache[NewsSummary] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=60.0)

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = sample_summary.model_dump_json()
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    summarizer = SummarizerService(
        client=mock_client,
        model="gemini-3.1-flash-lite-preview",
        temperature=0.3,
        cache=cache,
    )

    url = "https://example.com/hot-breaking-news"
    md = "# Hot Breaking News\n\nEveryone is reading this at the same time."

    # 15 concurrent requests for the exact same article
    tasks = [summarizer.summarize_async(md, url=url) for _ in range(15)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 15
    assert all(r.title == "Stampede Defense Test" for r in results)
    # OpenAI must be called at most ONCE despite 15 concurrent requests!
    assert mock_client.chat.completions.create.call_count == 1

