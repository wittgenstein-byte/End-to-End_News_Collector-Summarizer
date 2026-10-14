"""
backend/tests/test_monitoring.py
─────────────────────────────────────────────────────────────────
Unit & integration tests for monitoring endpoints, authentication,
telemetry stats, and interactive control operations.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.scraper_service import ScraperService, get_scraper_service


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.monitoring_admin_key}"}


def test_monitoring_page_served(client: TestClient) -> None:
    """Ensure /monitoring and /monitoring.html serve the monitoring HTML file."""
    res1 = client.get("/monitoring")
    assert res1.status_code == 200
    assert "NEWSROOM" in res1.text
    assert "OPS" in res1.text or "Monitoring" in res1.text

    res2 = client.get("/monitoring.html")
    assert res2.status_code == 200


def test_auth_login_flow(client: TestClient) -> None:
    """Test login with valid and invalid admin keys."""
    # Invalid key
    bad_res = client.post("/api/monitoring/auth", json={"key": "wrong-key"})
    assert bad_res.status_code == 401
    assert "ไม่ถูกต้อง" in bad_res.json()["detail"]

    # Valid key
    ok_res = client.post("/api/monitoring/auth", json={"key": settings.monitoring_admin_key})
    assert ok_res.status_code == 200
    body = ok_res.json()
    assert body["ok"] is True
    assert "token" in body
    assert body["expires_in"] > 0

    token = body["token"]

    # Verify session token
    verify_res = client.get(
        "/api/monitoring/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "authenticated"


def test_auth_guard_blocks_unauthorized(client: TestClient) -> None:
    """Verify that unauthenticated requests to monitoring endpoints are rejected with 401."""
    assert client.get("/api/monitoring/verify").status_code == 401
    assert client.get("/api/monitoring/stats").status_code == 401
    assert client.post("/api/monitoring/scrape-now").status_code == 401
    assert client.post("/api/monitoring/clear-cache").status_code == 401
    assert client.post("/api/monitoring/test-source", json={"source": "ThaiPBS"}).status_code == 401


def test_auth_guard_accepts_x_admin_key(client: TestClient) -> None:
    """Verify that X-Admin-Key header is accepted."""
    res = client.get(
        "/api/monitoring/verify",
        headers={"X-Admin-Key": settings.monitoring_admin_key},
    )
    assert res.status_code == 200


def test_get_monitoring_stats(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Ensure stats endpoint returns well-structured metrics."""
    res = client.get("/api/monitoring/stats", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True

    # System metrics
    assert "system" in data
    assert "uptime_seconds" in data["system"]
    assert "total_news_articles" in data["system"]

    # Scraper metrics
    assert "scraper" in data
    assert "sources" in data["scraper"]
    assert isinstance(data["scraper"]["sources"], list)

    # Cache metrics
    assert "caches" in data
    assert "http_cache" in data["caches"]
    assert "summary_cache" in data["caches"]

    # Engagement metrics
    assert "engagement" in data
    assert "total_clicks" in data["engagement"]


def test_trigger_scrape_now(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Test manual trigger endpoint."""
    res = client.post("/api/monitoring/scrape-now", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "started" in body
    assert "message" in body


def test_clear_caches(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Test cache clear endpoint."""
    res = client.post("/api/monitoring/clear-cache", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_test_source_endpoint(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Test single source connectivity test."""
    # Non-existent source
    bad_res = client.post(
        "/api/monitoring/test-source",
        headers=admin_headers,
        json={"source": "NonExistentSource999"},
    )
    assert bad_res.status_code == 200
    assert bad_res.json()["success"] is False

    # Existing source (mocked test_single_source to avoid external network)
    scraper = get_scraper_service()
    with patch.object(
        scraper,
        "test_single_source",
        new_callable=AsyncMock,
        return_value={
            "source": "ThaiPBS",
            "success": True,
            "articles_count": 5,
            "duration_ms": 120,
            "sample": [],
            "error": None,
        },
    ):
        good_res = client.post(
            "/api/monitoring/test-source",
            headers=admin_headers,
            json={"source": "ThaiPBS"},
        )
        assert good_res.status_code == 200
        data = good_res.json()
        assert data["source"] == "ThaiPBS"
        assert data["success"] is True
        assert data["articles_count"] == 5


def test_scraper_telemetry_and_metrics() -> None:
    """Test ScraperService metrics, logging, and trigger APIs in isolation."""
    async def _run():
        mock_repo = AsyncMock()
        mock_repo.load_seen.return_value = set()
        mock_repo.load_news.return_value = []
        mock_emit = AsyncMock()

        service = ScraperService(repo=mock_repo, emit_fn=mock_emit, interval_minutes=10)

        # Metrics
        metrics = service.get_metrics()
        assert metrics["is_scraping"] is False
        assert metrics["interval_minutes"] == 10
        assert len(metrics["sources"]) > 0

        # Log event
        service.log_event("INFO", "Test log message", "tester")
        assert len(service._logs) > 0
        assert service._logs[-1]["message"] == "Test log message"

        # Trigger scrape
        started = service.trigger_scrape()
        assert started is True

    asyncio.run(_run())
