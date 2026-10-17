"""
backend/tests/test_decoupling.py
─────────────────────────────────────────────────────────────────
Automated Unit and Integration Test Suite for Milestone 1:
Server-Level & Network Decoupling (Headless Mode, Dynamic CORS,
Socket.IO CORS Integration, Image Proxy, and Service Catalog).

SOLID Principles:
- Single Responsibility: Tests isolate networking, headless state,
  and CORS from business logic domains.
- Interface Segregation: Validates headless REST & Socket.IO contracts.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, settings
from backend.core.socket_manager import _is_origin_allowed
from backend.main import app, app_asgi, create_app
from backend.routers.news_router import _proxy_image_url

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def default_client() -> Generator[TestClient, None, None]:
    """Standard FastAPI TestClient instance (non-headless default)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def headless_client() -> Generator[TestClient, None, None]:
    """TestClient instance configured specifically for headless mode."""
    headless_app = create_app(headless=True)
    with TestClient(headless_app) as client:
        yield client


@pytest.fixture
def asgi_client() -> Generator[TestClient, None, None]:
    """TestClient wrapping root ASGI app (handling both REST and Socket.IO)."""
    with TestClient(app_asgi) as client:
        yield client


# ── Test Suite 1: Headless Mode & Service Catalog ───────────────────


class TestHeadlessServiceCatalog:
    """Verifies headless root endpoint behavior and static file isolation."""

    def test_headless_root_service_catalog_json(self, headless_client: TestClient) -> None:
        """In headless mode, GET / must return 200 JSON documenting API endpoints."""
        res = headless_client.get("/")
        assert res.status_code == 200
        assert "application/json" in res.headers.get("content-type", "")

        data = res.json()
        assert data.get("service") == "News Collector & Summarizer API"
        assert data.get("mode") == "headless"
        assert data.get("status") in {"ok", "online"}
        assert data.get("version") == "2.0.0"
        assert data.get("docs") == "/docs"
        assert data.get("openapi") == "/openapi.json"

        endpoints = data.get("endpoints")
        assert isinstance(endpoints, list)
        assert "/api/news" in endpoints
        assert "/api/stories" in endpoints
        assert "/api/macro-events" in endpoints
        assert "/api/monitoring" in endpoints
        assert "/livez" in endpoints
        assert "/readyz" in endpoints

    def test_headless_mode_disables_frontend_routes(self, headless_client: TestClient) -> None:
        """In headless mode, UI page routes and static assets must return 404."""
        for path in [
            "/monitoring",
            "/monitoring.html",
            "/issues",
            "/issues.html",
            "/manifest.webmanifest",
            "/sw.js",
        ]:
            res = headless_client.get(path)
            assert res.status_code == 404, f"Expected 404 for route {path} in headless mode, got {res.status_code}"

    def test_headless_mode_static_frontend_mount_not_available(self, headless_client: TestClient) -> None:
        """Static /frontend files must return 404 in headless mode."""
        res = headless_client.get("/frontend/static/app.css")
        assert res.status_code == 404

    def test_headless_mode_rest_endpoints_functional(self, headless_client: TestClient) -> None:
        """All REST endpoints and health probes must remain functional in headless mode."""
        assert headless_client.get("/livez").status_code == 200
        assert headless_client.get("/api/sources").status_code == 200
        assert headless_client.get("/api/categories").status_code == 200
        assert headless_client.get("/api/status").status_code == 200

    def test_headless_monkeypatch_on_default_app(self, default_client: TestClient) -> None:
        """When settings.headless is dynamically set to True, default app route handler returns catalog."""
        with patch.object(settings, "headless", True):
            res = default_client.get("/")
            assert res.status_code == 200
            data = res.json()
            assert data["mode"] == "headless"
            assert data["service"] == "News Collector & Summarizer API"

            # HTML routes should also return 404 under headless
            assert default_client.get("/monitoring").status_code == 404
            assert default_client.get("/issues").status_code == 404


class TestNonHeadlessBackwardCompatibility:
    """Verifies that non-headless mode retains 100% backward compatibility."""

    def test_root_serves_html(self, default_client: TestClient) -> None:
        """When not headless, GET / serves index.html (or fallback 404 if missing)."""
        res = default_client.get("/")
        assert res.status_code in {200, 404}
        if res.status_code == 200:
            assert "text/html" in res.headers.get("content-type", "")

    def test_monitoring_page_serves_html(self, default_client: TestClient) -> None:
        """When not headless, GET /monitoring serves monitoring.html."""
        res = default_client.get("/monitoring")
        assert res.status_code in {200, 404}
        if res.status_code == 200:
            assert "text/html" in res.headers.get("content-type", "")

    def test_issues_page_serves_html(self, default_client: TestClient) -> None:
        """When not headless and issues enabled, GET /issues serves issues.html."""
        res = default_client.get("/issues")
        assert res.status_code in {200, 404}
        if res.status_code == 200:
            assert "text/html" in res.headers.get("content-type", "")

    def test_static_frontend_mount_accessible(self, default_client: TestClient) -> None:
        """When not headless, /frontend/static/app.css is served with 200 OK."""
        res = default_client.get("/frontend/static/app.css")
        assert res.status_code in {200, 404}
        if res.status_code == 200:
            assert res.headers.get("content-type", "").startswith("text/css")


# ── Test Suite 2: Dynamic CORS Security ─────────────────────────────


class TestDynamicCORSSecurity:
    """Verifies Cross-Origin Resource Sharing (CORS) headers for detached clients."""

    def test_cors_preflight_allowed_dev_origin_5173(self, asgi_client: TestClient) -> None:
        """Preflight OPTIONS request from Vite dev server on port 5173 must succeed."""
        res = asgi_client.options(
            "/api/news",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        assert res.status_code == 200
        allow_origin = res.headers.get("access-control-allow-origin")
        assert allow_origin in {"http://localhost:5173", "*"}
        assert res.headers.get("access-control-allow-credentials") == "true"
        assert "GET" in res.headers.get("access-control-allow-methods", "")

    def test_cors_get_allowed_dev_port_3000(self, asgi_client: TestClient) -> None:
        """GET request from React / Next dev server on port 3000 must include CORS origin."""
        res = asgi_client.get("/api/news?page=1", headers={"Origin": "http://localhost:3000"})
        assert res.status_code == 200
        allow_origin = res.headers.get("access-control-allow-origin")
        assert allow_origin in {"http://localhost:3000", "*"}
        assert res.headers.get("access-control-allow-credentials") == "true"

    def test_cors_get_allowed_dev_port_5500(self, asgi_client: TestClient) -> None:
        """GET request from Live Server on 127.0.0.1:5500 must include CORS origin."""
        res = asgi_client.get("/api/news?page=1", headers={"Origin": "http://127.0.0.1:5500"})
        assert res.status_code == 200
        allow_origin = res.headers.get("access-control-allow-origin")
        assert allow_origin in {"http://127.0.0.1:5500", "*"}
        assert res.headers.get("access-control-allow-credentials") == "true"

    def test_cors_disallowed_external_origin_rejected(self, asgi_client: TestClient) -> None:
        """When origin is not allowed, preflight OPTIONS must return 400 without allow-origin."""
        res = asgi_client.options(
            "/api/news",
            headers={
                "Origin": "https://malicious-attacker.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 400
        assert "access-control-allow-origin" not in res.headers

    def test_cors_image_proxy_endpoint(self, asgi_client: TestClient) -> None:
        """Preflight OPTIONS request to /api/image from detached client must be permitted."""
        res = asgi_client.options(
            "/api/image",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        allow_origin = res.headers.get("access-control-allow-origin")
        assert allow_origin in {"http://localhost:5173", "*"}


# ── Test Suite 3: Socket.IO CORS Integration ────────────────────────


class TestSocketIOCORS:
    """Verifies Socket.IO CORS configuration aligns with server settings."""

    def test_socketio_origin_allowed_logic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unit test _is_origin_allowed for local dev ports and unauthorized origins."""
        monkeypatch.setattr(settings, "cors_origins", ["http://localhost:5000"])
        monkeypatch.setattr(settings, "cors_origin_regex", r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")

        # Allowed origins
        assert _is_origin_allowed("http://localhost:5173") is True
        assert _is_origin_allowed("http://localhost:3000") is True
        assert _is_origin_allowed("http://127.0.0.1:5500") is True
        assert _is_origin_allowed("http://localhost:5000") is True
        assert _is_origin_allowed(None) is True
        assert _is_origin_allowed("") is True

        # Disallowed origins
        assert _is_origin_allowed("https://evil.com") is False
        assert _is_origin_allowed("http://attacker.org:5173") is False
        assert _is_origin_allowed("http://localhost.evil.com") is False

    def test_socketio_polling_handshake_allowed(self, asgi_client: TestClient) -> None:
        """Engine.IO polling handshake request from detached origin returns 200 with session."""
        res = asgi_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://localhost:5173"},
        )
        assert res.status_code == 200
        assert res.text.startswith("0{")  # Engine.IO OPEN packet prefix
        assert '"sid":' in res.text
        assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert res.headers.get("access-control-allow-credentials") == "true"

    def test_socketio_polling_handshake_disallowed(self, asgi_client: TestClient) -> None:
        """Engine.IO polling handshake from disallowed origin returns 400 Bad Request."""
        res = asgi_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://evil.com"},
        )
        assert res.status_code == 400
        assert "access-control-allow-origin" not in res.headers


# ── Test Suite 4: Image Proxy Resolution Contract ───────────────────


class TestImageProxyResolutionContract:
    """Verifies /api/image proxy behavior and security checks."""

    def test_proxy_image_url_allowed_host(self) -> None:
        """Hotlinked host 'The Standard' returns relative /api/image?url=... path."""
        url = "https://thestandard.co/assets/hero_photo.jpg"
        proxied = _proxy_image_url(url, "The Standard")
        assert proxied.startswith("/api/image?url=")
        assert "thestandard.co" in proxied

    def test_proxy_image_url_unproxied_host(self) -> None:
        """Non-hotlinked source returns raw original image URL unchanged."""
        url = "https://images.thaipbs.or.th/2026/08/news.jpg"
        result = _proxy_image_url(url, "ThaiPBS")
        assert result == url

    def test_proxy_image_blocks_disallowed_host(self, asgi_client: TestClient) -> None:
        """GET /api/image with unauthorized domain returns 400 Bad Request."""
        res = asgi_client.get("/api/image?url=https://unauthorized-domain.com/evil.jpg")
        assert res.status_code == 400
        assert "Unsupported image host" in res.json().get("detail", "")

    def test_proxy_image_blocks_invalid_scheme(self, asgi_client: TestClient) -> None:
        """GET /api/image with file/ftp scheme returns 400 Bad Request."""
        res = asgi_client.get("/api/image?url=file:///etc/passwd")
        assert res.status_code == 400


# ── Test Suite 5: Headless Configuration Parsing ────────────────────


class TestHeadlessSettingsConfiguration:
    """Verifies configuration parsing for headless decoupling settings."""

    def test_default_is_non_headless(self) -> None:
        """Default Settings instance has headless=False."""
        s = Settings()
        assert s.headless is False

    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "YES", "True"])
    def test_headless_truthy_values(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        """Truth values in HEADLESS env var must enable headless mode."""
        monkeypatch.setenv("HEADLESS", val)
        s = Settings()
        assert s.headless is True

    @pytest.mark.parametrize("val", ["0", "false", "FALSE", "no", "", "invalid"])
    def test_headless_falsy_values(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        """Falsy or empty values in HEADLESS env var must keep headless disabled."""
        monkeypatch.setenv("HEADLESS", val)
        s = Settings()
        assert s.headless is False

    def test_settings_cors_origin_regex_default(self) -> None:
        """Default cors_origin_regex correctly matches localhost and 127.0.0.1 ports."""
        pattern = settings.cors_origin_regex
        assert pattern is not None
        assert re.match(pattern, "http://localhost:5173")
        assert re.match(pattern, "http://localhost:3000")
        assert re.match(pattern, "http://127.0.0.1:5500")
        assert not re.match(pattern, "https://example.com")
