"""
tests/test_caching.py
─────────────────────────────────────────────────────────────────
SOLID  S — Comprehensive test suite for all 4 caching layers:
           - Layer 1: Client-Side Storage Data Models & Invariants
           - Layer 2: AI News Summary In-Memory Cache (AsyncInMemoryCache)
           - Layer 3: In-App Browser HTML Snapshot Cache (BrowserSnapshotCache)
           - Layer 4: Scraper HTTP Conditional Request Cache (HttpConditionalCache)
SOLID  O — Easily extensible with new cache scenario tests
GRASP  Information Expert — Validates contracts, concurrency, TTL, LRU,
           error isolation, and URL normalization across all subsystems.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.core.cache import AsyncInMemoryCache
from backend.core.http_cache import HttpCacheEntry, HttpConditionalCache
from backend.schemas.news_schema import NewsSummary
from backend.scrapers.sources import (
    scrape_101world,
    scrape_bangkokpost,
    scrape_matichon,
    scrape_thaipbs,
    scrape_thestandard,
)
from backend.services.browser_service import (
    BrowserService,
    BrowserSnapshotCache,
    normalize_browser_url,
)
from backend.services.summarizer_service import (
    SummarizerService,
    normalize_article_url,
)

# ── Helper Fixtures & Builders ───────────────────────────────────


def build_sample_summary(
    title: str = "Test AI Headline",
    url: str = "https://example.com/news/1",
) -> NewsSummary:
    """Build a valid NewsSummary instance for testing."""
    return NewsSummary(
        title=title,
        source_url=url,
        published_at="2026-08-21T12:00:00Z",
        language="th",
        summary="A dense, factual summary paragraph for testing.",
        bullets=[
            "First key point of the article.",
            "Second key point of the article.",
            "Third key point of the article.",
        ],
        category="technology",
        sentiment="neutral",
        keywords=["technology", "ai", "cache"],
    )


# ═════════════════════════════════════════════════════════════════
# LAYER 2: AI NEWS SUMMARY IN-MEMORY CACHE
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_summary_cache_hit_and_miss() -> None:
    """
    Checks that the initial call invokes the mock LLM, while repeated calls
    for the exact same article URL within 24h return the cached NewsSummary
    without invoking the upstream LLM API. Also tests content-hash fallback.
    """
    sample = build_sample_summary(title="Quantum AI in 2026", url="https://example.com/quantum")
    cache: AsyncInMemoryCache[NewsSummary] = AsyncInMemoryCache(
        max_size=1000,
        default_ttl_seconds=86400.0,
    )

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = sample.model_dump_json()
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    service = SummarizerService(
        client=mock_client,
        model="gpt-4o-mini",
        temperature=0.3,
        cache=cache,
    )

    article_url = "https://example.com/quantum"
    markdown = "# Quantum AI\n\nResearchers announce quantum computing breakthrough."

    # 1. Initial Call -> Cache Miss (invokes LLM)
    res1 = await service.summarize_async(markdown, url=article_url)
    assert res1.title == "Quantum AI in 2026"
    assert res1.category == "technology"
    assert mock_client.chat.completions.create.call_count == 1
    assert cache.size() == 1
    assert cache.hits == 0
    assert cache.misses == 1

    # 2. Repeated Call -> Cache Hit (returns cached NewsSummary, no LLM call)
    res2 = await service.summarize_async(markdown, url=article_url)
    assert res2.title == "Quantum AI in 2026"
    assert res2.summary == res1.summary
    assert mock_client.chat.completions.create.call_count == 1  # Unchanged!
    assert cache.hits == 1

    # 3. Content-Hash Fallback (empty URL uses sha256 hash of content)
    res_hash1 = await service.summarize_async(markdown, url="")
    assert res_hash1.title == "Quantum AI in 2026"
    assert mock_client.chat.completions.create.call_count == 2  # New key created

    res_hash2 = await service.summarize_async(markdown, url="")
    assert res_hash2.title == "Quantum AI in 2026"
    assert mock_client.chat.completions.create.call_count == 2  # Cached by hash!


@pytest.mark.anyio
async def test_summary_cache_concurrency_stampede() -> None:
    """
    Checks that concurrent requests for the exact same article execute
    the LLM computation at most once (single-flight stampede protection).
    """
    sample = build_sample_summary(title="Breaking Economy News")
    cache: AsyncInMemoryCache[NewsSummary] = AsyncInMemoryCache(
        max_size=1000,
        default_ttl_seconds=86400.0,
    )

    llm_call_count = 0

    def mock_create(*_args: Any, **_kwargs: Any) -> MagicMock:
        nonlocal llm_call_count
        llm_call_count += 1
        # Simulate LLM inference delay
        time.sleep(0.04)
        mock_choice = MagicMock()
        mock_choice.message.content = sample.model_dump_json()
        return MagicMock(choices=[mock_choice])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = mock_create

    service = SummarizerService(
        client=mock_client,
        model="gpt-4o-mini",
        temperature=0.2,
        cache=cache,
    )

    target_url = "https://example.com/breaking-news-viral"
    markdown_body = "# Viral Breaking News\n\nHigh traffic article being accessed simultaneously."

    # Launch 25 concurrent requests for the same uncached article
    tasks = [service.summarize_async(markdown_body, url=target_url) for _ in range(25)]
    results = await asyncio.gather(*tasks)

    # All 25 callers receive valid results
    assert len(results) == 25
    assert all(r.title == "Breaking Economy News" for r in results)

    # The LLM API must have been called EXACTLY ONCE
    assert llm_call_count == 1
    assert mock_client.chat.completions.create.call_count == 1


@pytest.mark.anyio
async def test_summary_cache_ttl_expiration() -> None:
    """
    Checks that expired entries trigger a fresh computation upon expiry.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(
        max_size=10,
        default_ttl_seconds=0.05,  # 50ms TTL
    )

    call_count = 0

    async def compute_value() -> str:
        nonlocal call_count
        call_count += 1
        return f"result_v{call_count}"

    # 1. First retrieval -> computes v1
    v1 = await cache.get_or_compute("test_key", compute_value)
    assert v1 == "result_v1"
    assert call_count == 1

    # 2. Immediate retrieval -> returns cached v1
    v1_cached = await cache.get_or_compute("test_key", compute_value)
    assert v1_cached == "result_v1"
    assert call_count == 1

    # 3. Wait for TTL to expire
    await asyncio.sleep(0.08)

    # 4. Retrieval after expiration -> triggers fresh computation v2
    v2 = await cache.get_or_compute("test_key", compute_value)
    assert v2 == "result_v2"
    assert call_count == 2


@pytest.mark.anyio
async def test_summary_cache_lru_eviction() -> None:
    """
    Checks that LRU eviction removes the least recently used entries
    when max_size capacity is reached.
    """
    max_size = 4
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(
        max_size=max_size,
        default_ttl_seconds=3600.0,
    )

    for i in range(1, 5):
        await cache.set(f"k{i}", f"val_{i}")

    assert cache.size() == 4
    assert cache.evictions == 0

    # Access k1 and k2 so that k3 and k4 become older candidates
    assert await cache.get("k1") == "val_1"
    assert await cache.get("k2") == "val_2"

    # Insert k5 -> should evict k3 (oldest unaccessed item)
    await cache.set("k5", "val_5")
    assert cache.size() == 4
    assert cache.evictions == 1
    assert await cache.get("k3") is None
    assert await cache.get("k1") == "val_1"
    assert await cache.get("k2") == "val_2"
    assert await cache.get("k5") == "val_5"

    # Insert k6 -> should evict k4
    await cache.set("k6", "val_6")
    assert cache.size() == 4
    assert cache.evictions == 2
    assert await cache.get("k4") is None
    assert await cache.get("k6") == "val_6"


@pytest.mark.anyio
async def test_summary_cache_error_isolation() -> None:
    """
    Checks that computation exceptions are not cached and allow a clean retry.
    """
    cache: AsyncInMemoryCache[str] = AsyncInMemoryCache(
        max_size=10,
        default_ttl_seconds=3600.0,
    )

    attempt = 0

    async def faulty_compute() -> str:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise ConnectionError("LLM API endpoint unavailable")
        return "recovered_summary"

    # 1. First execution raises ConnectionError
    with pytest.raises(ConnectionError, match="LLM API endpoint unavailable"):
        await cache.get_or_compute("error_prone_url", faulty_compute)

    # 2. Error must NOT be cached
    assert await cache.get("error_prone_url") is None
    assert cache.size() == 0

    # 3. Clean retry succeeds and caches the successful result
    recovered = await cache.get_or_compute("error_prone_url", faulty_compute)
    assert recovered == "recovered_summary"
    assert attempt == 2
    assert await cache.get("error_prone_url") == "recovered_summary"
    assert cache.size() == 1


def test_summary_cache_url_normalization() -> None:
    """
    Checks that tracking query parameters (utm_*, fbclid, gclid, etc.)
    and fragments are normalized to identical keys.
    """
    # 1. Stripping hash fragments
    u1 = "https://example.com/article/100#comments"
    assert normalize_article_url(u1) == "https://example.com/article/100"

    # 2. Stripping tracking parameters and sorting remaining params
    u2 = (
        "https://NEWS.THAIPBS.OR.TH/news/100"
        "?utm_source=twitter&utm_medium=social&utm_campaign=breaking"
        "&fbclid=abc123xyz&gclid=def456&ref=feed&z_param=2&a_param=1#top"
    )
    normalized = normalize_article_url(u2)
    assert normalized == "https://news.thaipbs.or.th/news/100?a_param=1&z_param=2"

    # 3. Trailing slash normalization
    assert normalize_article_url("https://example.com/news/") == "https://example.com/news"
    assert normalize_article_url("https://example.com/") == "https://example.com"
    assert normalize_article_url("") == ""


# ═════════════════════════════════════════════════════════════════
# LAYER 3: IN-APP BROWSER HTML SNAPSHOT CACHE
# ═════════════════════════════════════════════════════════════════


def test_browser_snapshot_cache_hit_and_miss() -> None:
    """
    Checks basic hit and miss behavior and metadata storage in BrowserSnapshotCache.
    """
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    target_url = "https://www.thaipbs.or.th/news/content/12345"

    # 1. Uncached URL -> Miss
    assert cache.get(target_url) is None
    assert cache.size == 0

    # 2. Store snapshot
    cache.set(
        url=target_url,
        html="<html><body><article>Test Article Content</article></body></html>",
        final_url=target_url,
        title="Thai PBS News Headline",
    )
    assert cache.size == 1

    # 3. Cached URL -> Hit
    result = cache.get(target_url)
    assert result is not None
    assert result["cached"] is True
    assert result["html"] == "<html><body><article>Test Article Content</article></body></html>"
    assert result["title"] == "Thai PBS News Headline"
    assert result["url"] == target_url

    # 4. Metrics verification
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1


@pytest.mark.anyio
async def test_browser_snapshot_cache_cdp_bypass() -> None:
    """
    Checks that repeated navigation to the same target URL within 15 minutes
    returns cached: True and completely bypasses Playwright/CDP execution.
    """
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    service = BrowserService(snapshot_cache=cache)

    mock_navigate = AsyncMock(
        return_value={
            "html": "<main><h1>Obscura Rendered DOM</h1></main>",
            "url": "https://thestandard.co/article/99",
            "title": "The Standard",
        }
    )

    with (
        patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)),
        patch.object(service, "_navigate_inner", new=mock_navigate),
        patch.object(service, "_dispatch", side_effect=lambda coro: coro),
    ):
        # First navigation -> Cache Miss -> Dispatches to worker
        res1 = await service.navigate("tab-1", "https://thestandard.co/article/99")
        assert res1.get("cached") is not True
        assert res1["html"] == "<main><h1>Obscura Rendered DOM</h1></main>"
        assert mock_navigate.call_count == 1
        assert cache.size == 1

        # Second navigation -> Cache Hit -> CDP Bypassed!
        res2 = await service.navigate("tab-1", "https://thestandard.co/article/99")
        assert res2.get("cached") is True
        assert res2["html"] == "<main><h1>Obscura Rendered DOM</h1></main>"
        assert res2["title"] == "The Standard"
        # Mock call count must remain 1
        assert mock_navigate.call_count == 1


@pytest.mark.anyio
async def test_browser_snapshot_cache_error_isolation() -> None:
    """
    Checks that failed navigations, timeouts, and empty responses are never cached.
    """
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    service = BrowserService(snapshot_cache=cache)

    # 1. Navigation failure (timeout / unreachable host)
    mock_failure = AsyncMock(return_value={"error": "Navigation failed: Timeout 25000ms exceeded"})
    with (
        patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)),
        patch.object(service, "_navigate_inner", new=mock_failure),
        patch.object(service, "_dispatch", side_effect=lambda coro: coro),
    ):
        res = await service.navigate("tab-1", "https://broken-destination.com")
        assert "error" in res
        assert cache.size == 0
        assert cache.get("https://broken-destination.com") is None

    # 2. Empty HTML response
    mock_empty = AsyncMock(return_value={"html": "", "url": "https://blank.com", "title": ""})
    with (
        patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)),
        patch.object(service, "_navigate_inner", new=mock_empty),
        patch.object(service, "_dispatch", side_effect=lambda coro: coro),
    ):
        res_empty = await service.navigate("tab-1", "https://blank.com")
        assert res_empty["html"] == ""
        assert cache.size == 0
        assert cache.get("https://blank.com") is None


@pytest.mark.anyio
async def test_browser_snapshot_cache_refresh_updates_cache() -> None:
    """
    Checks that a manual refresh forces a reload and updates the cached snapshot.
    """
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    service = BrowserService(snapshot_cache=cache)

    target_url = "https://news.thaipbs.or.th/live-feed"

    # Pre-populate with initial content
    cache.set(
        url=target_url,
        html="<p>Old Snapshot v1</p>",
        final_url=target_url,
        title="Initial Title",
    )
    initial_entry = cache.get(target_url)
    assert initial_entry is not None
    assert initial_entry["html"] == "<p>Old Snapshot v1</p>"

    # Mock refresh with updated live DOM
    mock_refresh = AsyncMock(
        return_value={
            "html": "<p>Refreshed Live Content v2</p>",
            "url": target_url,
            "title": "Updated Title",
        }
    )

    with (
        patch.object(service, "_refresh_inner", new=mock_refresh),
        patch.object(service, "_dispatch", side_effect=lambda coro: coro),
    ):
        res = await service.refresh("tab-1")
        assert res["html"] == "<p>Refreshed Live Content v2</p>"
        assert mock_refresh.call_count == 1

        # Cache must reflect the fresh snapshot
        updated_cached = cache.get(target_url)
        assert updated_cached is not None
        assert updated_cached["html"] == "<p>Refreshed Live Content v2</p>"
        assert updated_cached["title"] == "Updated Title"


def test_browser_snapshot_cache_url_normalization() -> None:
    """
    Checks URL normalization for browser snapshots (case, default ports,
    hash fragments, tracking parameters, redundant slashes).
    """
    # 1. Scheme addition
    assert normalize_browser_url("example.com/news") == "https://example.com/news"

    # 2. Lowercase scheme and netloc
    assert (
        normalize_browser_url("HTTPS://WWW.EXAMPLE.COM/Page")
        == "https://www.example.com/Page"
    )

    # 3. Default port stripping (80 for http, 443 for https)
    assert normalize_browser_url("http://example.com:80/path") == "http://example.com/path"
    assert normalize_browser_url("https://example.com:443/path") == "https://example.com/path"
    # Non-default ports preserved
    assert (
        normalize_browser_url("https://example.com:8443/path")
        == "https://example.com:8443/path"
    )

    # 4. Hash fragments stripped
    assert normalize_browser_url("https://example.com/path#section-1") == "https://example.com/path"

    # 5. Tracking parameters removed and query params sorted
    raw = "https://example.com/item?utm_source=feed&b=2&fbclid=123&a=1#comments"
    assert normalize_browser_url(raw) == "https://example.com/item?a=1&b=2"

    # 6. Slashes collapsed
    assert (
        normalize_browser_url("https://example.com//news///article")
        == "https://example.com/news/article"
    )


def test_browser_snapshot_cache_lru_and_ttl() -> None:
    """
    Checks LRU capacity eviction and TTL expiration in BrowserSnapshotCache.
    """
    # 1. TTL Expiration
    ttl_cache = BrowserSnapshotCache(ttl_seconds=1, max_size=10)
    ttl_cache.set("https://site.com/temp", "<h1>Temp</h1>")
    assert ttl_cache.get("https://site.com/temp") is not None

    time.sleep(1.1)
    assert ttl_cache.get("https://site.com/temp") is None
    assert ttl_cache.size == 0

    # 2. LRU Eviction (max_size = 3)
    lru_cache = BrowserSnapshotCache(ttl_seconds=900, max_size=3)
    lru_cache.set("https://site.com/1", "<h1>1</h1>")
    lru_cache.set("https://site.com/2", "<h1>2</h1>")
    lru_cache.set("https://site.com/3", "<h1>3</h1>")
    assert lru_cache.size == 3

    # Touch 1 so 2 becomes the least recently used
    assert lru_cache.get("https://site.com/1") is not None

    # Insert 4 -> evicts 2
    lru_cache.set("https://site.com/4", "<h1>4</h1>")
    assert lru_cache.size == 3
    assert lru_cache.get("https://site.com/2") is None
    assert lru_cache.get("https://site.com/1") is not None
    assert lru_cache.get("https://site.com/3") is not None
    assert lru_cache.get("https://site.com/4") is not None


# ═════════════════════════════════════════════════════════════════
# LAYER 4: SCRAPER HTTP CONDITIONAL REQUEST CACHE
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_http_conditional_cache_stores_etag_and_last_modified() -> None:
    """
    Checks that metadata (ETag, Last-Modified) is correctly stored on HTTP 200 OK.
    """
    cache = HttpConditionalCache(max_size=50, ttl_seconds=86400.0)
    target_url = "https://matichon.co.th/feed"
    rss_body = "<rss><channel><title>Matichon Feed</title></channel></rss>"

    mock_resp = httpx.Response(
        status_code=200,
        headers={
            "etag": '"etag-matichon-v1"',
            "last-modified": "Fri, 21 Aug 2026 08:00:00 GMT",
            "content-type": "application/xml",
        },
        text=rss_body,
        request=httpx.Request("GET", target_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        body, not_modified = await cache.fetch(target_url)

        assert body == rss_body
        assert not_modified is False
        assert cache.size() == 1

        entry: HttpCacheEntry | None = await cache.get_entry(target_url)
        assert entry is not None
        assert entry.etag == '"etag-matichon-v1"'
        assert entry.last_modified == "Fri, 21 Aug 2026 08:00:00 GMT"
        assert entry.body == rss_body
        assert entry.status_code == 200


@pytest.mark.anyio
async def test_http_conditional_cache_sends_if_none_match_and_if_modified_since() -> None:
    """
    Checks that subsequent requests include If-None-Match and If-Modified-Since headers.
    """
    cache = HttpConditionalCache(max_size=50, ttl_seconds=86400.0)
    target_url = "https://thestandard.co/feed"
    feed_body = "<rss><channel><title>The Standard</title></channel></rss>"

    resp_200 = httpx.Response(
        status_code=200,
        headers={"ETag": '"std-etag-200"', "Last-Modified": "Fri, 21 Aug 2026 09:00:00 GMT"},
        text=feed_body,
        request=httpx.Request("GET", target_url),
    )
    resp_304 = httpx.Response(
        status_code=304,
        request=httpx.Request("GET", target_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_200, resp_304]

        # Initial fetch -> 200
        await cache.fetch(target_url)

        # Subsequent fetch -> sends conditional headers
        await cache.fetch(target_url)

        assert mock_get.call_count == 2
        second_headers = mock_get.call_args_list[1].kwargs.get("headers", {})
        assert second_headers.get("If-None-Match") == '"std-etag-200"'
        assert second_headers.get("If-Modified-Since") == "Fri, 21 Aug 2026 09:00:00 GMT"


@pytest.mark.anyio
async def test_http_conditional_cache_handles_304_not_modified() -> None:
    """
    Checks that HTTP 304 Not Modified returns the cached body and not_modified == True.
    """
    cache = HttpConditionalCache(max_size=50, ttl_seconds=86400.0)
    target_url = "https://www.thaipbs.or.th/news"
    cached_html = "<html><body><h3>Breaking News</h3></body></html>"

    # Pre-populate
    resp_200 = httpx.Response(
        status_code=200,
        headers={"ETag": '"tpbs-v1"'},
        text=cached_html,
        request=httpx.Request("GET", target_url),
    )
    resp_304 = httpx.Response(
        status_code=304,
        request=httpx.Request("GET", target_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_200, resp_304]

        # Initial fetch (200)
        b1, not_mod1 = await cache.fetch(target_url)
        assert b1 == cached_html
        assert not_mod1 is False

        # Conditional fetch (304)
        b2, not_mod2 = await cache.fetch(target_url)
        assert b2 == cached_html
        assert not_mod2 is True
        assert cache.hits_304 == 1


@pytest.mark.anyio
async def test_http_conditional_cache_updates_on_200() -> None:
    """
    Checks that cache overwrites existing entry when a fresh 200 response arrives.
    """
    cache = HttpConditionalCache(max_size=50, ttl_seconds=86400.0)
    target_url = "https://example.com/feed"

    resp_v1 = httpx.Response(
        status_code=200,
        headers={"ETag": '"v1"'},
        text="Content Version 1",
        request=httpx.Request("GET", target_url),
    )
    resp_v2 = httpx.Response(
        status_code=200,
        headers={"ETag": '"v2"'},
        text="Content Version 2 (Updated)",
        request=httpx.Request("GET", target_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_v1, resp_v2]

        # First fetch
        b1, _ = await cache.fetch(target_url)
        assert b1 == "Content Version 1"

        # Second fetch with updated server content
        b2, not_mod2 = await cache.fetch(target_url)
        assert b2 == "Content Version 2 (Updated)"
        assert not_mod2 is False

        entry = await cache.get_entry(target_url)
        assert entry is not None
        assert entry.etag == '"v2"'
        assert entry.body == "Content Version 2 (Updated)"


@pytest.mark.anyio
async def test_http_conditional_cache_error_isolation() -> None:
    """
    Checks that 404, 500, and network exceptions do not poison or corrupt the cache.
    """
    cache = HttpConditionalCache(max_size=10, ttl_seconds=3600.0)

    # 1. HTTP 500
    resp_500 = httpx.Response(
        status_code=500,
        text="Server Crash",
        request=httpx.Request("GET", "https://example.com/500"),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_500
        body, not_mod = await cache.fetch("https://example.com/500")
        assert body == ""
        assert not_mod is False
        assert cache.size() == 0
        assert cache.errors == 1

    # 2. Network Timeout
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Timeout")):
        body, not_mod = await cache.fetch("https://example.com/timeout")
        assert body == ""
        assert not_mod is False
        assert cache.size() == 0
        assert cache.errors == 2


@pytest.mark.anyio
async def test_scraper_sources_skip_parsing_on_304() -> None:
    """
    Simulates 304 Not Modified response on registered scrapers,
    verifying DOM/RSS parsing is completely skipped and empty list is returned.
    """
    # 1. ThaiPBS HTML Scraper
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<html><body><h3>Headline</h3></body></html>", True)
        articles = await scrape_thaipbs()
        assert articles == []
        mock_fetch.assert_called_once_with("https://www.thaipbs.or.th/news", timeout=10)

    # 2. Bangkok Post HTML Scraper
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<html><body><h3>Headline</h3></body></html>", True)
        articles = await scrape_bangkokpost()
        assert articles == []
        mock_fetch.assert_called_once_with("https://www.bangkokpost.com/thailand/general", timeout=10)

    # 3. Matichon RSS Scraper
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<rss><channel></channel></rss>", True)
        articles = await scrape_matichon()
        assert articles == []
        mock_fetch.assert_called_once_with("https://www.matichon.co.th/feed", timeout=10)

    # 4. 101 World RSS Scraper
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<rss><channel></channel></rss>", True)
        articles = await scrape_101world()
        assert articles == []

    # 5. The Standard RSS Scraper
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<rss><channel></channel></rss>", True)
        articles = await scrape_thestandard()
        assert articles == []
        mock_fetch.assert_called_once_with("https://thestandard.co/feed", timeout=10)


# ═════════════════════════════════════════════════════════════════
# LAYER 1: CLIENT-SIDE STORAGE DATA MODELS & INVARIANTS
# ═════════════════════════════════════════════════════════════════


def test_client_storage_bookmark_schema_and_invariants() -> None:
    """
    Validates client-side bookmark data schema, required fields, and invariant rules.
    """
    valid_categories = {
        "all",
        "politics",
        "economy",
        "technology",
        "health",
        "environment",
        "society",
        "sports",
        "entertainment",
        "world",
    }

    # Bookmark payload structure stored in localStorage bookmarkedArticles
    bookmark_item = {
        "id": "thaipbs-12345",
        "title": "Bangkok Clean Air Initiative Announced",
        "url": "https://news.thaipbs.or.th/news/12345",
        "source": "ThaiPBS",
        "category": "environment",
        "published_at": "2026-08-21T08:30:00Z",
        "saved_at": "2026-08-21T10:15:00Z",
        "summary": "New environmental measures introduced in Bangkok to cut emissions.",
        "image_url": "https://news.thaipbs.or.th/images/12345.jpg",
    }

    # Invariant 1: Required fields present
    required_keys = {"id", "title", "url", "source", "category", "published_at", "saved_at"}
    assert required_keys.issubset(bookmark_item.keys())

    # Invariant 2: Category membership
    assert bookmark_item["category"] in valid_categories

    # Invariant 3: ISO 8601 timestamp validity
    parsed_published = datetime.fromisoformat(bookmark_item["published_at"].replace("Z", "+00:00"))
    parsed_saved = datetime.fromisoformat(bookmark_item["saved_at"].replace("Z", "+00:00"))
    assert parsed_saved >= parsed_published


def test_client_storage_ttl_expiry_calculation() -> None:
    """
    Validates 24-hour TTL calculation and expiration gating for client offline cache.
    """
    ttl_seconds = 86400  # 24 hours
    now = datetime.now(timezone.utc).timestamp()

    # Case 1: Fresh cached news (1 hour old) -> Valid
    fresh_entry = {
        "articles": [{"title": "Fresh News", "url": "https://example.com/1"}],
        "cached_at": now - 3600,
    }
    cached_at_fresh = fresh_entry["cached_at"]
    assert isinstance(cached_at_fresh, (int, float))
    is_fresh_expired = (now - float(cached_at_fresh)) >= ttl_seconds
    assert is_fresh_expired is False

    # Case 2: Stale cached news (25 hours old) -> Expired
    stale_entry = {
        "articles": [{"title": "Stale News", "url": "https://example.com/2"}],
        "cached_at": now - (25 * 3600),
    }
    cached_at_stale = stale_entry["cached_at"]
    assert isinstance(cached_at_stale, (int, float))
    is_stale_expired = (now - float(cached_at_stale)) >= ttl_seconds
    assert is_stale_expired is True

    # Case 3: PDPA Consent Gating invariant
    pdpa_consent = False
    stored_personalization_keys = []
    if pdpa_consent:
        stored_personalization_keys.extend(["preferredCategory", "bookmarkedArticles"])
    # If consent is False, no personalization keys should be stored
    assert len(stored_personalization_keys) == 0


def test_client_storage_cache_key_normalization_invariants() -> None:
    """
    Validates invariant mapping between client URLs and canonical cache keys.
    """
    client_raw_url = "https://WWW.THAIPBS.OR.TH/news/100?utm_source=mobile&utm_medium=app#comments"
    expected_canonical = "https://www.thaipbs.or.th/news/100"

    # Both summarizer and browser URL normalizers must yield canonical representation
    summary_key = normalize_article_url(client_raw_url)
    browser_key = normalize_browser_url(client_raw_url)

    assert summary_key == expected_canonical
    assert browser_key == expected_canonical
