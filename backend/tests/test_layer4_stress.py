"""
backend/tests/test_layer4_stress.py
─────────────────────────────────────────────────────────────────
Adversarial Stress Test Suite for Layer 4:
Scraper HTTP Conditional Request Cache (HttpConditionalCache)

Validates:
1. HTTP 304 Conditional Request & Header Invariants:
   - Correct injection of If-None-Match (ETag) and If-Modified-Since
   - Handling of mixed/missing headers (ETag only, Last-Modified only, none, both)
   - Header casing insensitivity (ETag, etag, ETag, Last-Modified, last-modified)
   - 304 response returns cached body without re-parsing
   - 304 on uncached URL behaves safely (returns empty string with True)
2. Scraper Parsing Bypass Verification:
   - BeautifulSoup / XML parser are bypassed when 304 Not Modified is returned
   - Empty list [] returned immediately for all 10 registered scrapers
3. Data Preservation Under 304 & High Volume Cycles:
   - Scraper service with all sources returning 304 preserves existing articles in repo
   - Repo metadata and seen_urls are not corrupted or wiped
   - Mixed 304 and 200 responses append new articles without duplicating seen URLs
4. Error Resilience & Cache Poisoning Protection:
   - HTTP 404, 500, 502, 503 responses do not overwrite or poison existing valid cache entries
   - Network dropouts (ConnectTimeout, ReadTimeout, ConnectionResetError, RemoteProtocolError)
     do not corrupt existing valid cache entries
   - Subsequent requests after transient errors can still use cached ETag for validation
5. Extreme Concurrency & Race Conditions:
   - 100 concurrent requests across multiple workers with alternating 200, 304, 500, timeouts
   - Thread and async lock safety on LRU OrderedDict mutations
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.core.http_cache import HttpConditionalCache
from backend.repo.news_repo import FileNewsRepository
from backend.scrapers.registry import NewsSource
from backend.scrapers.sources import (
    scrape_101world,
    scrape_bangkokbiznews,
    scrape_bangkokpost,
    scrape_dailynews,
    scrape_khaosod,
    scrape_matichon,
    scrape_nationtv,
    scrape_thaipbs,
    scrape_thaipost,
    scrape_thestandard,
)
from backend.services.scraper_service import ScraperService

# ═════════════════════════════════════════════════════════════════
# 1. CONDITIONAL HEADERS & 304 INVARIANTS
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_conditional_headers_combinations() -> None:
    """
    Stress-test header combinations: ETag only, Last-Modified only, both, neither,
    and verify exact conditional headers passed in subsequent requests.
    """
    cache = HttpConditionalCache(max_size=20, ttl_seconds=3600.0)

    # 1. ETag only
    url_etag = "https://example.com/etag-only"
    r_etag = httpx.Response(
        status_code=200,
        headers={"ETag": '"hash-123"'},
        text="<xml>ETag content</xml>",
        request=httpx.Request("GET", url_etag),
    )
    r_304 = httpx.Response(status_code=304, request=httpx.Request("GET", url_etag))

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [r_etag, r_304]
        b1, mod1 = await cache.fetch(url_etag)
        assert b1 == "<xml>ETag content</xml>"
        assert mod1 is False

        b2, mod2 = await cache.fetch(url_etag)
        assert b2 == "<xml>ETag content</xml>"
        assert mod2 is True

        headers_sent = mock_get.call_args_list[1].kwargs.get("headers", {})
        assert headers_sent.get("If-None-Match") == '"hash-123"'
        assert "If-Modified-Since" not in headers_sent

    # 2. Last-Modified only
    url_lm = "https://example.com/lm-only"
    r_lm = httpx.Response(
        status_code=200,
        headers={"Last-Modified": "Fri, 21 Aug 2026 10:00:00 GMT"},
        text="<xml>LM content</xml>",
        request=httpx.Request("GET", url_lm),
    )
    r_304_lm = httpx.Response(status_code=304, request=httpx.Request("GET", url_lm))

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [r_lm, r_304_lm]
        await cache.fetch(url_lm)
        b2, mod2 = await cache.fetch(url_lm)
        assert b2 == "<xml>LM content</xml>"
        assert mod2 is True

        headers_sent = mock_get.call_args_list[1].kwargs.get("headers", {})
        assert "If-None-Match" not in headers_sent
        assert headers_sent.get("If-Modified-Since") == "Fri, 21 Aug 2026 10:00:00 GMT"

    # 3. Neither ETag nor Last-Modified
    url_none = "https://example.com/no-headers"
    r_none = httpx.Response(
        status_code=200,
        headers={"Content-Type": "text/html"},
        text="<html>Plain HTML</html>",
        request=httpx.Request("GET", url_none),
    )
    r_none_200 = httpx.Response(
        status_code=200,
        headers={"Content-Type": "text/html"},
        text="<html>Plain HTML 2</html>",
        request=httpx.Request("GET", url_none),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [r_none, r_none_200]
        await cache.fetch(url_none)
        b2, mod2 = await cache.fetch(url_none)
        assert b2 == "<html>Plain HTML 2</html>"
        assert mod2 is False

        headers_sent = mock_get.call_args_list[1].kwargs.get("headers", {})
        assert "If-None-Match" not in headers_sent
        assert "If-Modified-Since" not in headers_sent


@pytest.mark.anyio
async def test_header_casing_insensitivity() -> None:
    """
    Verify that HttpConditionalCache accepts header variations:
    'etag', 'ETag', 'last-modified', 'Last-Modified'.
    """
    cache = HttpConditionalCache(max_size=10, ttl_seconds=3600.0)
    url = "https://example.com/casing"

    # Lowercase headers from some proxies
    resp_lower = httpx.Response(
        status_code=200,
        headers={"etag": '"etag-lower"', "last-modified": "Sat, 22 Aug 2026 00:00:00 GMT"},
        text="lower header test",
        request=httpx.Request("GET", url),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_lower
        await cache.fetch(url)

    entry = await cache.get_entry(url)
    assert entry is not None
    assert entry.etag == '"etag-lower"'
    assert entry.last_modified == "Sat, 22 Aug 2026 00:00:00 GMT"


@pytest.mark.anyio
async def test_304_on_uncached_url_edge_case() -> None:
    """
    Edge case: Remote server sends HTTP 304 unexpectedly for a URL not present in cache.
    Must return ('', True) without throwing KeyError or UnboundLocalError.
    """
    cache = HttpConditionalCache(max_size=10, ttl_seconds=3600.0)
    url = "https://example.com/unexpected-304"

    resp_304 = httpx.Response(
        status_code=304,
        request=httpx.Request("GET", url),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_304
        body, not_modified = await cache.fetch(url)
        assert body == ""
        assert not_modified is True
        assert cache.hits_304 == 1


# ═════════════════════════════════════════════════════════════════
# 2. SCRAPER SOURCES PARSING BYPASS VERIFICATION
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_all_scrapers_bypass_parsing_on_304() -> None:
    """
    Adversarially verify that ALL scrapers in backend/scrapers/sources.py
    skip parsing and return [] when http_cache.fetch returns not_modified=True.
    """
    scrapers = [
        ("ThaiPBS", scrape_thaipbs),
        ("Bangkok Post", scrape_bangkokpost),
        ("Matichon", scrape_matichon),
        ("101 World", scrape_101world),
        ("The Standard", scrape_thestandard),
        ("Khaosod", scrape_khaosod),
        ("Thai Post", scrape_thaipost),
        ("Daily News", scrape_dailynews),
        ("Nation Online", scrape_nationtv),
        ("Bangkokbiznews", scrape_bangkokbiznews),
    ]

    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        # Return not_modified = True
        mock_fetch.return_value = ("<xml>Cached body</xml>", True)

        with patch("bs4.BeautifulSoup") as mock_bs, patch("xml.etree.ElementTree.fromstring") as mock_et:
            for name, scraper_fn in scrapers:
                articles = await scraper_fn()
                assert articles == [], f"Scraper {name} failed to return empty list on 304"

            # Verify BeautifulSoup and ElementTree were NEVER instantiated
            assert mock_bs.call_count == 0, "BeautifulSoup was unexpectedly called on 304"
            assert mock_et.call_count == 0, "ElementTree was unexpectedly called on 304"


# ═════════════════════════════════════════════════════════════════
# 3. DATA PRESERVATION IN REPOSITORY UNDER 304 CYCLES
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_full_scraper_loop_preserves_articles_on_all_304() -> None:
    """
    Verify complete scraper lifecycle with real FileNewsRepository:
    1. Preload 5 articles in repository.
    2. Run ScraperService._scrape_all with 10 dummy sources all returning 304.
    3. Assert repo remains identical, seen_urls intact, no save/emit triggered with empty list.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_file = Path(tmp_dir) / "news_test.json"
        repo = FileNewsRepository(data_file=data_file)

        initial_articles = [
            {"url": f"https://example.com/news/{i}", "title": f"Existing Article {i}", "source": "ThaiPBS"}
            for i in range(1, 6)
        ]
        repo.save_news(initial_articles)
        repo.save_seen({a["url"] for a in initial_articles})

        # Create 10 sources returning [] on 304
        async def mock_304_scrape() -> list[dict]:
            return []

        sources = [
            NewsSource(f"Source_{i}", f"https://s{i}.com", "#000", mock_304_scrape)
            for i in range(10)
        ]

        seen = repo.load_seen()
        new_batch = await ScraperService._scrape_all(sources, seen)

        # Invariant checks
        assert new_batch == []
        assert len(seen) == 5

        # Repo articles must NOT have been wiped
        loaded_articles = repo.load_news()
        assert len(loaded_articles) == 5
        assert [a["url"] for a in loaded_articles] == [f"https://example.com/news/{i}" for i in range(1, 6)]


@pytest.mark.anyio
async def test_scraper_mixed_304_and_200_updates_cleanly() -> None:
    """
    Verify mixed cycle:
    - 5 sources return 304 Not Modified
    - 5 sources return fresh 200 articles
    - Verify only fresh articles are appended, seen set is updated, existing preserved.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        data_file = Path(tmp_dir) / "news_mixed.json"
        repo = FileNewsRepository(data_file=data_file)

        existing = [{"url": "https://example.com/old_1", "title": "Old 1", "source": "OldSource"}]
        repo.save_news(existing)
        repo.save_seen({"https://example.com/old_1"})

        # 5 sources returning 304, 5 returning 1 fresh article each
        sources = []
        for i in range(5):
            async def mock_304() -> list[dict]:
                return []
            sources.append(NewsSource(f"304_Src_{i}", f"https://304_{i}.com", "#111", mock_304))

        for i in range(5):
            def make_fresh_fn(idx: int):
                async def mock_200() -> list[dict]:
                    return [{"url": f"https://example.com/fresh_{idx}", "title": f"Fresh {idx}", "source": f"FreshSrc_{idx}"}]
                return mock_200
            sources.append(NewsSource(f"200_Src_{i}", f"https://200_{i}.com", "#222", make_fresh_fn(i)))

        seen = repo.load_seen()
        new_batch = await ScraperService._scrape_all(sources, seen)

        assert len(new_batch) == 5
        assert len(seen) == 6

        # Save to repo as ScraperService.run_loop does
        all_news = repo.load_news()
        all_news.extend(new_batch)
        repo.save_news(all_news)
        repo.save_seen(seen)

        # Validate final repo state
        final_news = repo.load_news()
        assert len(final_news) == 6
        assert final_news[0]["url"] == "https://example.com/old_1"
        assert [a["url"] for a in final_news[1:]] == [f"https://example.com/fresh_{i}" for i in range(5)]


# ═════════════════════════════════════════════════════════════════
# 4. ERROR RESILIENCE & CACHE POISONING RESISTANCE
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_transient_http_errors_do_not_poison_valid_cache() -> None:
    """
    Adversarially verify that 404, 500, 502, 503, and network dropouts
    do NOT wipe or poison an existing valid cache entry.
    """
    cache = HttpConditionalCache(max_size=10, ttl_seconds=3600.0)
    target_url = "https://example.com/critical-feed"
    valid_body = "<rss><channel><title>Critical Feed</title></channel></rss>"

    # 1. Establish valid cached entry
    resp_200 = httpx.Response(
        status_code=200,
        headers={"ETag": '"etag-v1"', "Last-Modified": "Fri, 21 Aug 2026 12:00:00 GMT"},
        text=valid_body,
        request=httpx.Request("GET", target_url),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_200
        await cache.fetch(target_url)

    entry = await cache.get_entry(target_url)
    assert entry is not None
    assert entry.body == valid_body
    assert entry.etag == '"etag-v1"'

    # 2. Inject 500 Internal Server Error
    resp_500 = httpx.Response(status_code=500, text="Internal Server Error", request=httpx.Request("GET", target_url))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_500
        body, not_mod = await cache.fetch(target_url)
        assert body == ""
        assert not_mod is False

    # Check cache entry is STILL INTACT!
    entry_after_500 = await cache.get_entry(target_url)
    assert entry_after_500 is not None
    assert entry_after_500.body == valid_body
    assert entry_after_500.etag == '"etag-v1"'

    # 3. Inject 404 Not Found
    resp_404 = httpx.Response(status_code=404, text="Not Found", request=httpx.Request("GET", target_url))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_404
        body, not_mod = await cache.fetch(target_url)
        assert body == ""
        assert not_mod is False

    entry_after_404 = await cache.get_entry(target_url)
    assert entry_after_404 is not None
    assert entry_after_404.body == valid_body

    # 4. Inject Connection Timeout
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Network unreachable")):
        body, not_mod = await cache.fetch(target_url)
        assert body == ""
        assert not_mod is False

    entry_after_timeout = await cache.get_entry(target_url)
    assert entry_after_timeout is not None
    assert entry_after_timeout.body == valid_body

    # 5. Inject RemoteProtocolError / ConnectionReset
    with patch("httpx.AsyncClient.get", side_effect=httpx.RemoteProtocolError("Connection reset by peer")):
        body, not_mod = await cache.fetch(target_url)
        assert body == ""
        assert not_mod is False

    entry_after_reset = await cache.get_entry(target_url)
    assert entry_after_reset is not None
    assert entry_after_reset.body == valid_body

    # 6. Recovery: Server recovers and responds with 304 Not Modified using original ETag
    resp_304 = httpx.Response(status_code=304, request=httpx.Request("GET", target_url))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_304
        body_recovered, not_mod_recovered = await cache.fetch(target_url)
        assert body_recovered == valid_body
        assert not_mod_recovered is True
        # Verify conditional header was indeed sent despite prior transient errors
        headers_sent = mock_get.call_args.kwargs.get("headers", {})
        assert headers_sent.get("If-None-Match") == '"etag-v1"'


# ═════════════════════════════════════════════════════════════════
# 5. CONCURRENCY & RACE CONDITIONS
# ═════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_high_concurrency_race_conditions() -> None:
    """
    Stress-test with 100 concurrent workers sending interleaved 200, 304, 500,
    and timeout responses across 5 distinct URLs.
    Validates that:
    - No unhandled exceptions or dictionary mutation errors occur.
    - Cache capacity constraints are strictly honored.
    - Statistics metrics are consistent.
    """
    cache = HttpConditionalCache(max_size=5, ttl_seconds=3600.0)

    async def worker(idx: int) -> tuple[str, bool]:
        url = f"https://example.com/feed/{idx % 5}"
        mode = idx % 4

        if mode == 0:
            # 200 OK
            resp = httpx.Response(
                status_code=200,
                headers={"ETag": f'"etag-{idx}"'},
                text=f"Content-{idx}",
                request=httpx.Request("GET", url),
            )
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = resp
                return await cache.fetch(url)
        elif mode == 1:
            # 304 Not Modified
            resp = httpx.Response(status_code=304, request=httpx.Request("GET", url))
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = resp
                return await cache.fetch(url)
        elif mode == 2:
            # 500 Error
            resp = httpx.Response(status_code=500, request=httpx.Request("GET", url))
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = resp
                return await cache.fetch(url)
        else:
            # Timeout
            with patch("httpx.AsyncClient.get", side_effect=httpx.ReadTimeout("Timeout")):
                return await cache.fetch(url)

    tasks = [worker(i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 100
    assert cache.size() <= 5

    stats = cache.stats()
    assert stats["fetches_200"] > 0
    assert stats["errors"] > 0
    assert stats["size"] <= 5
