"""
backend/tests/test_browser_cache.py
─────────────────────────────────────────────────────────────────
Unit and integration tests for In-App Browser HTML Snapshot Cache
and URL Normalization (Milestone 2 / Layer 3).
─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import concurrent.futures
import time
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.browser_service import (
    BrowserService,
    BrowserSnapshotCache,
    normalize_browser_url,
)

# ── 1. URL Normalization Unit Tests ─────────────────────────────


def test_normalize_browser_url_empty_and_whitespace() -> None:
    assert normalize_browser_url("") == ""
    assert normalize_browser_url("   ") == ""


def test_normalize_browser_url_scheme_and_hostname_lowercasing() -> None:
    url = "HTTPS://NEWS.THAiPBS.OR.TH/article/1"
    normalized = normalize_browser_url(url)
    assert normalized == "https://news.thaipbs.or.th/article/1"


def test_normalize_browser_url_adds_missing_scheme() -> None:
    url = "news.thaipbs.or.th/world"
    normalized = normalize_browser_url(url)
    assert normalized == "https://news.thaipbs.or.th/world"


def test_normalize_browser_url_default_ports_stripped() -> None:
    assert normalize_browser_url("http://example.com:80/news") == "http://example.com/news"
    assert normalize_browser_url("https://example.com:443/news") == "https://example.com/news"
    # Non-default ports must be preserved
    assert normalize_browser_url("https://example.com:8443/news") == "https://example.com:8443/news"
    assert normalize_browser_url("http://example.com:8080/news") == "http://example.com:8080/news"


def test_normalize_browser_url_hash_fragments_stripped() -> None:
    assert normalize_browser_url("https://example.com/news#comments") == "https://example.com/news"
    assert (
        normalize_browser_url("https://example.com/news?page=2#section-top")
        == "https://example.com/news?page=2"
    )


def test_normalize_browser_url_tracking_parameters_stripped_and_sorted() -> None:
    raw = (
        "https://example.com/news?utm_source=fb&z=last&utm_medium=social"
        "&a=first&fbclid=abc123xyz&gclid=def456&_ga=1.2.3&ref=twitter&m=middle"
    )
    normalized = normalize_browser_url(raw)
    assert normalized == "https://example.com/news?a=first&m=middle&z=last"


def test_normalize_browser_url_consecutive_slashes() -> None:
    assert normalize_browser_url("https://example.com//news///article//") == "https://example.com/news/article/"


# ── 2. BrowserSnapshotCache Unit Tests ──────────────────────────


def test_snapshot_cache_basic_hit_and_miss() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    url = "https://news.thaipbs.or.th/article/100"

    # 1. Miss initially
    assert cache.get(url) is None
    assert cache.size == 0

    # 2. Store snapshot
    cache.set(
        url=url,
        html="<html><body>News Content</body></html>",
        final_url=url,
        title="Breaking News",
    )
    assert cache.size == 1

    # 3. Hit
    result = cache.get(url)
    assert result is not None
    assert result["cached"] is True
    assert result["html"] == "<html><body>News Content</body></html>"
    assert result["title"] == "Breaking News"
    assert result["url"] == url

    # Stats
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1


def test_snapshot_cache_normalization_lookup_hit() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    stored_url = "https://example.com/article?utm_source=twitter&b=2&a=1#section1"
    cache.set(
        url=stored_url,
        html="<p>Article Body</p>",
        final_url="https://example.com/article?a=1&b=2",
        title="Article",
    )

    # Query using alternate casing, default port 443, different tracking param order, and different hash
    query_url = "HTTPS://EXAMPLE.COM:443/article?fbclid=999&a=1&b=2#comments"
    result = cache.get(query_url)

    assert result is not None
    assert result["cached"] is True
    assert result["html"] == "<p>Article Body</p>"


def test_snapshot_cache_redirect_indexing() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    initial_url = "http://short.url/123"
    final_url = "https://full-news.com/articles/2026/world-cup"

    cache.set(
        url=initial_url,
        html="<div>Final News</div>",
        final_url=final_url,
        title="World Cup",
    )

    # Both initial URL and redirected final URL should yield a cache hit
    hit_initial = cache.get(initial_url)
    assert hit_initial is not None
    assert hit_initial["html"] == "<div>Final News</div>"

    hit_final = cache.get(final_url)
    assert hit_final is not None
    assert hit_final["html"] == "<div>Final News</div>"


def test_snapshot_cache_ttl_expiration() -> None:
    # 0.2s TTL for fast test execution
    cache = BrowserSnapshotCache(ttl_seconds=1, max_size=100)
    url = "https://example.com/ephemeral"

    cache.set(url=url, html="<p>Ephemeral</p>", final_url=url, title="Test")
    assert cache.get(url) is not None

    # Wait for TTL to expire
    time.sleep(1.1)

    assert cache.get(url) is None
    assert cache.size == 0


def test_snapshot_cache_lru_eviction() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=3)

    cache.set("https://site.com/1", "<h1>1</h1>")
    cache.set("https://site.com/2", "<h1>2</h1>")
    cache.set("https://site.com/3", "<h1>3</h1>")
    assert cache.size == 3

    # Access item 1 (so 2 becomes the least recently used)
    assert cache.get("https://site.com/1") is not None

    # Insert item 4 -> item 2 should be evicted
    cache.set("https://site.com/4", "<h1>4</h1>")
    assert cache.size == 3

    assert cache.get("https://site.com/2") is None  # Evicted
    assert cache.get("https://site.com/1") is not None  # Preserved
    assert cache.get("https://site.com/3") is not None  # Preserved
    assert cache.get("https://site.com/4") is not None  # Preserved


def test_snapshot_cache_invalidate_and_clear() -> None:
    cache = BrowserSnapshotCache()
    cache.set("https://site.com/a", "<h1>A</h1>")
    cache.set("https://site.com/b", "<h1>B</h1>")
    assert cache.size == 2

    # Invalidate single
    assert cache.invalidate("https://site.com/a") is True
    assert cache.invalidate("https://site.com/a") is False
    assert cache.get("https://site.com/a") is None
    assert cache.get("https://site.com/b") is not None

    # Clear all
    cache.clear()
    assert cache.size == 0
    assert cache.stats()["hits"] == 0
    assert cache.stats()["misses"] == 0
    assert cache.get("https://site.com/b") is None
    assert cache.stats()["misses"] == 1


def test_snapshot_cache_invalid_inputs_ignored() -> None:
    cache = BrowserSnapshotCache()
    cache.set("", "<p>HTML</p>")
    assert cache.size == 0

    cache.set("https://example.com", "")
    assert cache.size == 0

    cache.set("https://example.com", "   ")
    assert cache.size == 0


def test_snapshot_cache_thread_concurrency() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=50)

    def worker(worker_id: int) -> int:
        hits = 0
        for i in range(50):
            url = f"https://example.com/item/{i % 10}"
            if i % 3 == 0:
                cache.set(url, f"<html>Item {i}</html>", final_url=url, title=f"Title {i}")
            elif i % 7 == 0:
                cache.invalidate(url)
            else:
                res = cache.get(url)
                if res is not None:
                    hits += 1
            _ = cache.stats()
        return hits

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert len(results) == 10
    assert cache.size <= 50


# ── 3. BrowserService Integration & Error Isolation Tests ───────


@pytest.mark.anyio
async def test_browser_service_navigate_cache_hit_bypasses_cdp() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    service = BrowserService(snapshot_cache=cache)

    mock_navigate_inner = AsyncMock(
        return_value={
            "html": "<html><body>Live Page</body></html>",
            "url": "https://news.thaipbs.or.th/article/500",
            "title": "Thai PBS News",
        }
    )

    with patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)), \
         patch.object(service, "_navigate_inner", new=mock_navigate_inner), \
         patch.object(service, "_dispatch", side_effect=lambda coro: coro):

        # First call: Cache Miss -> calls _navigate_inner
        res1 = await service.navigate("tab-1", "https://news.thaipbs.or.th/article/500")
        assert res1.get("cached") is not True
        assert res1["html"] == "<html><body>Live Page</body></html>"
        assert mock_navigate_inner.call_count == 1
        assert cache.size == 1

        # Second call: Cache Hit -> returns cached snapshot without invoking _navigate_inner
        res2 = await service.navigate("tab-1", "https://news.thaipbs.or.th/article/500")
        assert res2.get("cached") is True
        assert res2["html"] == "<html><body>Live Page</body></html>"
        assert res2["title"] == "Thai PBS News"
        # Call count must still be 1 (CDP bypassed!)
        assert mock_navigate_inner.call_count == 1


@pytest.mark.anyio
async def test_browser_service_error_isolation_never_caches_errors() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    service = BrowserService(snapshot_cache=cache)

    # 1. Navigation failure (timeout / unreachable)
    mock_fail = AsyncMock(return_value={"error": "Navigation failed: Timeout 25000ms exceeded"})
    with patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)), \
         patch.object(service, "_navigate_inner", new=mock_fail), \
         patch.object(service, "_dispatch", side_effect=lambda coro: coro):

        res = await service.navigate("tab-1", "https://timeout-site.com")
        assert "error" in res
        assert cache.size == 0
        assert cache.get("https://timeout-site.com") is None

    # 2. Empty HTML response
    mock_empty = AsyncMock(return_value={"html": "", "url": "https://empty.com", "title": ""})
    with patch.object(service, "_assert_safe_url", new=AsyncMock(return_value=None)), \
         patch.object(service, "_navigate_inner", new=mock_empty), \
         patch.object(service, "_dispatch", side_effect=lambda coro: coro):

        res = await service.navigate("tab-1", "https://empty.com")
        assert cache.size == 0
        assert cache.get("https://empty.com") is None


@pytest.mark.anyio
async def test_browser_service_refresh_updates_cache() -> None:
    cache = BrowserSnapshotCache(ttl_seconds=900, max_size=100)
    service = BrowserService(snapshot_cache=cache)

    # Pre-populate cache with older snapshot
    url = "https://news.thaipbs.or.th/live"
    cache.set(url=url, html="<p>Old Content</p>", final_url=url, title="Old Title")
    cached_entry = cache.get(url)
    assert cached_entry is not None
    assert cached_entry["html"] == "<p>Old Content</p>"

    # Refresh reloads live page with new content
    mock_refresh = AsyncMock(
        return_value={
            "html": "<p>Updated Live Content</p>",
            "url": url,
            "title": "Updated Title",
        }
    )

    with patch.object(service, "_refresh_inner", new=mock_refresh), \
         patch.object(service, "_dispatch", side_effect=lambda coro: coro):

        refresh_res = await service.refresh("tab-1")
        assert refresh_res["html"] == "<p>Updated Live Content</p>"

        # Cache should now have the updated content
        cached = cache.get(url)
        assert cached is not None
        assert cached["html"] == "<p>Updated Live Content</p>"
        assert cached["title"] == "Updated Title"


def test_browser_service_cache_management_methods() -> None:
    service = BrowserService()
    service.clear_snapshot_cache()

    service.snapshot_cache.set("https://site.com/1", "<h1>Content</h1>", title="Test")
    assert service.snapshot_cache_stats()["size"] == 1

    service.clear_snapshot_cache()
    assert service.snapshot_cache_stats()["size"] == 0
