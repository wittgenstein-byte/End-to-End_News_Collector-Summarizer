"""
backend/tests/test_adversarial_layer2_layer3.py
─────────────────────────────────────────────────────────────────
Adversarial stress testing and empirical challenge suite for:
- Layer 2: AI News Summary In-Memory Cache (AsyncInMemoryCache & SummarizerService)
- Layer 3: In-App Browser HTML Snapshot Cache (BrowserSnapshotCache & BrowserService)

Covers:
1. Concurrency Stress & Stampede Protection (50-100+ concurrent coroutines)
2. Monotonic TTL Precision & Sub-second Boundary Expiration
3. LRU Eviction Stress (1000+ items, 100+ snapshots, capacity invariants)
4. Comprehensive Error Isolation (LLM exceptions, CDP navigation failures, blank payloads)
5. URL Normalization Robustness & Edge Cases (casing, ports, query params, fragments)
6. Dependency Injection & Falsy Object Evaluation Invariants
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.cache import AsyncInMemoryCache
from backend.schemas.news_schema import NewsSummary
from backend.services.browser_service import (
    BrowserService,
    BrowserSnapshotCache,
    UnsafeUrlError,
    normalize_browser_url,
)
from backend.services.summarizer_service import (
    SummarizerService,
    normalize_article_url,
)


def make_dummy_summary(title: str = "Test Headline", url: str = "https://news.example.com/1") -> NewsSummary:
    return NewsSummary(
        title=title,
        source_url=url,
        published_at="2026-08-21T15:00:00Z",
        language="th",
        summary="Adversarial stress test summary content paragraph.",
        bullets=["Point A", "Point B", "Point C"],
        category="technology",
        sentiment="neutral",
        keywords=["ai", "cache", "stress"],
    )


# ═════════════════════════════════════════════════════════════════
# 1. HIGH-CONCURRENCY STAMPEDE PROTECTION (50+ Coroutines)
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_layer2_high_concurrency_stampede_100_identical_keys() -> None:
    """
    Stress test 100 concurrent coroutines requesting the exact same uncached key.
    The expensive backend compute must be invoked EXACTLY ONCE.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=1000, default_ttl_seconds=86400.0)
    compute_count = 0

    async def slow_compute() -> str:
        nonlocal compute_count
        compute_count += 1
        await asyncio.sleep(0.05)  # Simulate LLM latency
        return "expensive_result_100"

    tasks = [cache.get_or_compute("heavy_stampede_key", slow_compute) for _ in range(100)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 100
    assert all(r == "expensive_result_100" for r in results)
    assert compute_count == 1
    assert cache.size() == 1


@pytest.mark.anyio
async def test_layer2_high_concurrency_stampede_varying_keys_burst() -> None:
    """
    Stress test 100 concurrent coroutines across 10 distinct keys (10 requests per key).
    Exactly 10 compute calls must be executed.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=1000, default_ttl_seconds=86400.0)
    compute_counts: dict[str, int] = {}
    lock = asyncio.Lock()

    async def compute_for_key(key: str) -> str:
        async with lock:
            compute_counts[key] = compute_counts.get(key, 0) + 1
        await asyncio.sleep(0.03)
        return f"val_{key}"

    # 10 keys x 10 requests = 100 coroutines
    tasks = []
    for i in range(100):
        k = f"key_{i % 10}"

        def make_factory(target_k: str) -> Callable[[], Coroutine[Any, Any, str]]:
            return lambda: compute_for_key(target_k)

        tasks.append(cache.get_or_compute(k, make_factory(k)))

    results = await asyncio.gather(*tasks)

    assert len(results) == 100
    for k, count in compute_counts.items():
        assert count == 1, f"Key {k} was computed {count} times instead of 1"
    assert cache.size() == 10


@pytest.mark.anyio
async def test_layer2_concurrency_task_cancellation_resilience() -> None:
    """
    Verify that if a coroutine waiting on an in-flight computation is cancelled,
    the cache does not deadlock, leak _in_flight state, or leave corrupted state.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=60.0)
    started = asyncio.Event()

    async def slow_compute() -> str:
        started.set()
        await asyncio.sleep(0.1)
        return "completed_after_cancellation"

    # Start first caller (the creator)
    task1 = asyncio.create_task(cache.get_or_compute("cancel_key", slow_compute))
    await started.wait()

    # Start second caller (waiter)
    task2 = asyncio.create_task(cache.get_or_compute("cancel_key", slow_compute))
    await asyncio.sleep(0.01)

    # Cancel waiter
    task2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task2

    # Creator finishes successfully
    res1 = await task1
    assert res1 == "completed_after_cancellation"

    # In-flight map must be empty
    assert len(cache._in_flight) == 0

    # Subsequent call immediately gets cached value
    res3 = await cache.get("cancel_key")
    assert res3 == "completed_after_cancellation"


# ═════════════════════════════════════════════════════════════════
# 2. MONOTONIC TTL PRECISION & BOUNDARY TESTING
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_layer2_monotonic_ttl_subsecond_precision() -> None:
    """
    Verify sub-second TTL expiration boundary in AsyncInMemoryCache.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=0.06)

    await cache.set("ttl_key", "active_value")

    # 1. Immediate lookup -> hit
    assert await cache.get("ttl_key") == "active_value"

    # 2. Lookup right before expiry (30ms) -> still active
    await asyncio.sleep(0.03)
    assert await cache.get("ttl_key") == "active_value"

    # 3. Lookup after expiry (additional 40ms -> total 70ms > 60ms) -> expired and None
    await asyncio.sleep(0.04)
    assert await cache.get("ttl_key") is None
    assert cache.size() == 0


@pytest.mark.anyio
async def test_layer2_ttl_custom_override_per_entry() -> None:
    """
    Verify custom per-entry TTL overrides default_ttl_seconds.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=10, default_ttl_seconds=100.0)

    # Short custom TTL of 50ms
    await cache.set("short_ttl_key", "short_val", ttl_seconds=0.05)
    # Long default TTL
    await cache.set("long_ttl_key", "long_val")

    await asyncio.sleep(0.08)

    assert await cache.get("short_ttl_key") is None
    assert await cache.get("long_ttl_key") == "long_val"


# ═════════════════════════════════════════════════════════════════
# 3. LRU EVICTION STRESS TEST (Capacity Invariants)
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_layer2_lru_stress_rapid_insertions_exceeding_capacity() -> None:
    """
    Rapidly insert 2,500 items into AsyncInMemoryCache with max_size=1,000.
    Verify:
    1. Size never exceeds max_size (1000).
    2. Evictions counter accurately equals 1500.
    3. The first 1500 items are evicted in exact FIFO order.
    4. The remaining 1000 items (1500 to 2499) are present.
    """
    max_size = 1000
    cache: AsyncInMemoryCache[int] = AsyncInMemoryCache(max_size=max_size, default_ttl_seconds=3600.0)

    for i in range(2500):
        await cache.set(f"item_{i}", i)

    assert cache.size() == 1000
    assert cache.evictions == 1500

    # Verify first 1500 were evicted
    for i in range(1500):
        assert await cache.get(f"item_{i}") is None

    # Verify last 1000 are present
    for i in range(1500, 2500):
        assert await cache.get(f"item_{i}") == i


@pytest.mark.anyio
async def test_layer2_lru_access_order_preservation() -> None:
    """
    Verify that accessing items updates their LRU position and preserves them
    from eviction under capacity pressure.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(max_size=3, default_ttl_seconds=3600.0)

    await cache.set("k1", "v1")
    await cache.set("k2", "v2")
    await cache.set("k3", "v3")

    # Access k1 so the LRU order becomes [k2, k3, k1] (k2 oldest)
    assert await cache.get("k1") == "v1"

    # Insert k4 -> should evict k2
    await cache.set("k4", "v4")
    assert cache.size() == 3
    assert cache.evictions == 1
    assert await cache.get("k2") is None
    assert await cache.get("k1") == "v1"
    assert await cache.get("k3") == "v3"
    assert await cache.get("k4") == "v4"


def test_layer3_snapshot_cache_lru_stress_100_capacity() -> None:
    """
    Rapidly insert 300 snapshots into BrowserSnapshotCache (max_size=100).
    Verify size never exceeds 100 and older snapshots are evicted.
    """
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)

    for i in range(300):
        url = f"https://example.com/article/{i}"
        cache.set(url=url, html=f"<html>Article {i}</html>", final_url=url, title=f"Title {i}")

    assert cache.size == 100
    assert len(cache) == 100

    # Oldest 200 items (0..199) must be evicted
    for i in range(200):
        assert cache.get(f"https://example.com/article/{i}") is None

    # Newest 100 items (200..299) must be present
    for i in range(200, 300):
        res = cache.get(f"https://example.com/article/{i}")
        assert res is not None
        assert res["html"] == f"<html>Article {i}</html>"


# ═════════════════════════════════════════════════════════════════
# 4. ERROR ISOLATION (LLM & CDP Exceptions)
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_layer2_error_isolation_llm_exceptions_never_cached() -> None:
    """
    Test various LLM exceptions (Timeout, API error, JSON corruption)
    and ensure none are cached, allowing clean subsequent retries.
    """
    cache: AsyncInMemoryCache[NewsSummary] = AsyncInMemoryCache(max_size=100, default_ttl_seconds=3600.0)

    mock_client = MagicMock()
    service = SummarizerService(
        client=mock_client,
        model="gpt-4o-mini",
        temperature=0.2,
        cache=cache,
    )

    url = "https://news.example.com/error-test"
    md = "# Broken Article\n\nContent here..."

    # 1. API Connection Failure
    mock_client.chat.completions.create.side_effect = ConnectionError("OpenAI API unreachable")
    with pytest.raises(ConnectionError):
        await service.summarize_async(md, url=url)

    assert cache.size() == 0
    assert await cache.get(f"summary:url:{normalize_article_url(url)}") is None

    # 2. Corrupted JSON returned by LLM
    mock_choice = MagicMock()
    mock_choice.message.content = "INVALID_NON_JSON_RESPONSE {{"
    mock_client.chat.completions.create.side_effect = None
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    with pytest.raises(Exception):  # noqa: B017
        await service.summarize_async(md, url=url)

    assert cache.size() == 0

    # 3. Successful recovery -> caches valid summary
    valid_summary = make_dummy_summary(title="Recovered Headline", url=url)
    mock_choice.message.content = valid_summary.model_dump_json()
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    res = await service.summarize_async(md, url=url)
    assert res.title == "Recovered Headline"
    assert cache.size() == 1
    assert await cache.get(f"summary:url:{normalize_article_url(url)}") is not None


@pytest.mark.anyio
async def test_layer3_error_isolation_cdp_errors_and_unsafe_urls() -> None:
    """
    Test navigation failures, SSRF blocked URLs, CDP crashes, and empty payloads.
    Ensure none are cached in BrowserSnapshotCache.
    """
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    service = BrowserService(snapshot_cache=cache)

    # 1. CDP Timeout Error
    mock_timeout = AsyncMock(return_value={"error": "Navigation failed: Timeout 25000ms exceeded"})
    with (
        patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)),
        patch.object(service, "_navigate_inner", new=mock_timeout),
        patch.object(service, "_dispatch", side_effect=lambda coro: coro),
    ):
        res1 = await service.navigate("tab-1", "https://unreachable.example.com")
        assert "error" in res1
        assert cache.size == 0
        assert cache.get("https://unreachable.example.com") is None

    # 2. SSRF / Unsafe URL
    with patch.object(service, "_assert_safe_url", side_effect=UnsafeUrlError("Host is blocked")):
        res2 = await service.navigate("tab-1", "http://127.0.0.1:8000/internal")
        assert "error" in res2
        assert "Blocked URL" in res2["error"]
        assert cache.size == 0

    # 3. Blank / Whitespace snapshot
    mock_blank = AsyncMock(return_value={"html": "   \n\t  ", "url": "https://blank.example.com", "title": ""})
    with (
        patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)),
        patch.object(service, "_navigate_inner", new=mock_blank),
        patch.object(service, "_dispatch", side_effect=lambda coro: coro),
    ):
        await service.navigate("tab-1", "https://blank.example.com")
        assert cache.size == 0
        assert cache.get("https://blank.example.com") is None


# ═════════════════════════════════════════════════════════════════
# 5. URL NORMALIZATION ROBUSTNESS & BUG EXPOSURE
# ═════════════════════════════════════════════════════════════════


def test_layer2_normalize_article_url_adversarial_inputs() -> None:
    """
    Test normalize_article_url across bizarre URLs, tracking params, and casing.
    """
    # 1. Mixed casing in scheme and host
    url1 = "HTTPS://NEWS.EXAMPLE.COM/Article/Path"
    assert normalize_article_url(url1) == "https://news.example.com/Article/Path"

    # 2. Multi-value tracking params & sorting
    url2 = "https://example.com/news?utm_source=twitter&z=9&fbclid=abc&utm_medium=cpc&a=1&utm_campaign=winter#comments"
    assert normalize_article_url(url2) == "https://example.com/news?a=1&z=9"

    # 3. Trailing slash consistency
    assert normalize_article_url("https://example.com/news/") == "https://example.com/news"
    assert normalize_article_url("https://example.com/") == "https://example.com"
    assert normalize_article_url("") == ""
    assert normalize_article_url("   ") == ""


def test_layer3_normalize_browser_url_adversarial_casing() -> None:
    """
    ADVERSARIAL TEST: normalize_browser_url with uppercase and mixed case schemes.
    Checks if uppercase schemes (HTTPS://..., HTTP://...) are handled cleanly
    without prepending duplicate schemes.
    """
    # Uppercase scheme
    url = "HTTPS://WWW.EXAMPLE.COM/Page"
    normalized = normalize_browser_url(url)
    assert normalized == "https://www.example.com/Page", f"Expected 'https://www.example.com/Page', got '{normalized}'"

    # Mixed case scheme
    url2 = "hTtP://Example.Com:80/Index"
    normalized2 = normalize_browser_url(url2)
    assert normalized2 == "http://example.com/Index", f"Expected 'http://example.com/Index', got '{normalized2}'"


def test_layer3_browser_service_di_falsy_cache_bug() -> None:
    """
    ADVERSARIAL TEST: Verify Dependency Injection of an empty BrowserSnapshotCache
    into BrowserService.
    If BrowserService uses `snapshot_cache or BrowserSnapshotCache(...)`,
    an empty cache (len=0) evaluates as falsy in Python, silently discarding
    the injected cache and replacing it with a new instance.
    """
    custom_cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    assert len(custom_cache) == 0  # Initial empty cache has length 0

    service = BrowserService(snapshot_cache=custom_cache)

    # Injected cache MUST be the exact instance used by service
    assert service.snapshot_cache is custom_cache, (
        "BrowserService discarded the injected snapshot_cache because it evaluated to False in boolean context!"
    )
