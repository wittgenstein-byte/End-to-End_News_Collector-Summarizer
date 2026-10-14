from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.core.http_cache import HttpConditionalCache
from backend.scrapers.registry import NewsSource
from backend.scrapers.sources import (
    scrape_dailynews,
    scrape_matichon,
    scrape_thaipbs,
    scrape_thestandard,
)
from backend.services.scraper_service import ScraperService


@pytest.fixture
def clean_cache() -> HttpConditionalCache:
    return HttpConditionalCache(max_size=10, ttl_seconds=3600.0)


@pytest.mark.anyio
async def test_http_cache_initial_fetch_stores_etag_and_last_modified(clean_cache: HttpConditionalCache) -> None:
    test_url = "https://example.com/rss/feed"
    mock_body = "<rss><channel><title>Test Feed</title></channel></rss>"
    mock_headers = {
        "etag": '"etag-v1"',
        "last-modified": "Wed, 21 Oct 2025 07:28:00 GMT",
        "content-type": "application/xml",
    }

    mock_resp = httpx.Response(
        status_code=200,
        headers=mock_headers,
        text=mock_body,
        request=httpx.Request("GET", test_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        body, not_modified = await clean_cache.fetch(test_url)

        assert body == mock_body
        assert not_modified is False
        assert clean_cache.size() == 1

        entry = await clean_cache.get_entry(test_url)
        assert entry is not None
        assert entry.etag == '"etag-v1"'
        assert entry.last_modified == "Wed, 21 Oct 2025 07:28:00 GMT"
        assert entry.body == mock_body
        assert entry.status_code == 200


@pytest.mark.anyio
async def test_http_cache_sends_conditional_headers_on_subsequent_request(clean_cache: HttpConditionalCache) -> None:
    test_url = "https://example.com/rss/feed"
    mock_body = "<rss><channel><title>Test Feed</title></channel></rss>"

    # 1. Initial 200 response
    resp_200 = httpx.Response(
        status_code=200,
        headers={"ETag": '"etag-100"', "Last-Modified": "Thu, 22 Oct 2025 10:00:00 GMT"},
        text=mock_body,
        request=httpx.Request("GET", test_url),
    )

    # 2. Subsequent 304 response
    resp_304 = httpx.Response(
        status_code=304,
        headers={},
        request=httpx.Request("GET", test_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_200, resp_304]

        # First request (miss -> 200)
        body1, not_mod1 = await clean_cache.fetch(test_url)
        assert body1 == mock_body
        assert not_mod1 is False

        # Second request (hit -> 304)
        body2, not_mod2 = await clean_cache.fetch(test_url)
        assert body2 == mock_body
        assert not_mod2 is True

        # Verify second call included If-None-Match and If-Modified-Since
        assert mock_get.call_count == 2
        second_call_headers = mock_get.call_args_list[1].kwargs.get("headers", {})
        assert second_call_headers.get("If-None-Match") == '"etag-100"'
        assert second_call_headers.get("If-Modified-Since") == "Thu, 22 Oct 2025 10:00:00 GMT"


@pytest.mark.anyio
async def test_http_cache_handles_304_not_modified_returns_cached_text(clean_cache: HttpConditionalCache) -> None:
    test_url = "https://example.com/news"
    cached_content = "<html><body>Original Article</body></html>"

    # Pre-populate cache
    resp_200 = httpx.Response(
        status_code=200,
        headers={"ETag": '"abc"'},
        text=cached_content,
        request=httpx.Request("GET", test_url),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_200
        await clean_cache.fetch(test_url)

    # Now return 304
    resp_304 = httpx.Response(
        status_code=304,
        request=httpx.Request("GET", test_url),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_304
        body, not_modified = await clean_cache.fetch(test_url)

        assert body == cached_content
        assert not_modified is True

    stats = clean_cache.stats()
    assert stats["hits_304"] == 1
    assert stats["fetches_200"] == 1


@pytest.mark.anyio
async def test_http_cache_updates_when_server_returns_200_with_new_etag(clean_cache: HttpConditionalCache) -> None:
    test_url = "https://example.com/news"
    old_body = "Old HTML"
    new_body = "New HTML with fresh news"

    resp_v1 = httpx.Response(
        status_code=200,
        headers={"ETag": '"v1"'},
        text=old_body,
        request=httpx.Request("GET", test_url),
    )
    resp_v2 = httpx.Response(
        status_code=200,
        headers={"ETag": '"v2"'},
        text=new_body,
        request=httpx.Request("GET", test_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_v1, resp_v2]

        # First fetch
        b1, mod1 = await clean_cache.fetch(test_url)
        assert b1 == old_body
        assert mod1 is False

        # Second fetch returns new content
        b2, mod2 = await clean_cache.fetch(test_url)
        assert b2 == new_body
        assert mod2 is False

        entry = await clean_cache.get_entry(test_url)
        assert entry is not None
        assert entry.etag == '"v2"'
        assert entry.body == new_body


@pytest.mark.anyio
async def test_http_cache_non_200_error_isolation(clean_cache: HttpConditionalCache) -> None:
    test_url = "https://example.com/broken"

    resp_500 = httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=httpx.Request("GET", test_url),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp_500
        body, not_modified = await clean_cache.fetch(test_url)

        assert body == ""
        assert not_modified is False
        assert clean_cache.size() == 0
        assert (await clean_cache.get_entry(test_url)) is None

    # Test network exception
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Timeout")):
        body, not_modified = await clean_cache.fetch("https://example.com/timeout")
        assert body == ""
        assert not_modified is False
        assert clean_cache.size() == 0


@pytest.mark.anyio
async def test_http_cache_max_size_eviction() -> None:
    small_cache = HttpConditionalCache(max_size=3)

    for i in range(4):
        url = f"https://example.com/{i}"
        resp = httpx.Response(
            status_code=200,
            headers={"ETag": f'"etag-{i}"'},
            text=f"Body {i}",
            request=httpx.Request("GET", url),
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp
            await small_cache.fetch(url)

    assert small_cache.size() == 3
    stats = small_cache.stats()
    assert stats["evictions"] == 1
    assert (await small_cache.get_entry("https://example.com/0")) is None
    assert (await small_cache.get_entry("https://example.com/3")) is not None


@pytest.mark.anyio
async def test_http_cache_ttl_expiration() -> None:
    short_cache = HttpConditionalCache(max_size=10, ttl_seconds=0.05)
    test_url = "https://example.com/expiring"

    resp = httpx.Response(
        status_code=200,
        headers={"ETag": '"etag-exp"'},
        text="Content",
        request=httpx.Request("GET", test_url),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = resp
        await short_cache.fetch(test_url)

    assert (await short_cache.get_entry(test_url)) is not None

    # Wait for TTL to expire
    await asyncio.sleep(0.08)

    # Should be considered expired and purged
    assert (await short_cache.get_entry(test_url)) is None


@pytest.mark.anyio
async def test_http_cache_concurrency_safety(clean_cache: HttpConditionalCache) -> None:
    async def fetch_url(idx: int) -> tuple[str, bool]:
        url = f"https://example.com/item/{idx % 3}"
        resp = httpx.Response(
            status_code=200,
            headers={"ETag": f'"etag-{idx % 3}"'},
            text=f"Content {idx % 3}",
            request=httpx.Request("GET", url),
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp
            return await clean_cache.fetch(url)

    results = await asyncio.gather(*[fetch_url(i) for i in range(30)])
    assert len(results) == 30
    assert all(r[0].startswith("Content") for r in results)
    assert clean_cache.size() <= 3


@pytest.mark.anyio
async def test_scraper_source_rss_skips_parsing_on_304() -> None:
    # Test The Standard scraper when 304 is returned
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<rss><channel></channel></rss>", True)

        articles = await scrape_thestandard()
        assert articles == []
        mock_fetch.assert_called_once_with("https://thestandard.co/feed", timeout=10)


@pytest.mark.anyio
async def test_scraper_source_matichon_skips_parsing_on_304() -> None:
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<rss><channel></channel></rss>", True)

        articles = await scrape_matichon()
        assert articles == []


@pytest.mark.anyio
async def test_scraper_source_html_skips_parsing_on_304() -> None:
    # Test ThaiPBS scraper when 304 is returned
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<html><body><h3>News</h3></body></html>", True)

        articles = await scrape_thaipbs()
        assert articles == []
        mock_fetch.assert_called_once_with("https://www.thaipbs.or.th/news", timeout=10)


@pytest.mark.anyio
async def test_scraper_source_dailynews_skips_parsing_on_304() -> None:
    with patch("backend.scrapers.sources.http_cache.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<html><body><h3>News</h3></body></html>", True)

        articles = await scrape_dailynews()
        assert articles == []


@pytest.mark.anyio
async def test_scraper_service_preserves_articles_on_304() -> None:
    class DummyRepo:
        def __init__(self) -> None:
            self.saved_news: list[dict] = [{"url": "https://example.com/existing", "title": "Existing"}]
            self.saved_seen: set[str] = {"https://example.com/existing"}

        def load_news(self) -> list[dict]:
            return list(self.saved_news)

        def save_news(self, news: list[dict]) -> None:
            self.saved_news = list(news)

        def load_seen(self) -> set[str]:
            return set(self.saved_seen)

        def save_seen(self, seen: set[str]) -> None:
            self.saved_seen = set(seen)

    repo = DummyRepo()

    # Create dummy sources that return [] (simulating 304 Not Modified)
    async def mock_scrape_304() -> list[dict]:
        return []

    sources = [
        NewsSource("Source 1", "https://s1.com", "#111", mock_scrape_304),
        NewsSource("Source 2", "https://s2.com", "#222", mock_scrape_304),
    ]

    seen = repo.load_seen()
    new_batch = await ScraperService._scrape_all(sources, seen)

    assert new_batch == []
    assert len(seen) == 1
    # Existing articles in repo remain untouched
    assert len(repo.saved_news) == 1
    assert repo.saved_news[0]["url"] == "https://example.com/existing"
