"""
backend/tests/test_cors_and_socket.py
─────────────────────────────────────────────────────────────────
Comprehensive automated test suite for Milestone 1:
1. REST API CORS Preflight (OPTIONS) & Simple Requests (GET/POST)
   - Explicit whitelist origin matching
   - Regex-based origin pattern matching (dev ports)
   - Disallowed origin rejection (400 Bad Request / omitted header)
   - Preflight headers reflection (methods, credentials, custom headers)
2. Socket.IO Engine.IO CORS Handshake & Polling
   - Polling OPTIONS preflight from allowed origin
   - Polling GET handshake from allowed origin (returns 200 + Engine.IO session packet)
   - Polling handshake from disallowed origin (returns 400 Bad Request)
   - Polling without Origin header (returns 200 for native / server clients)
3. Dynamic Origin Checking Logic (_is_origin_allowed & is_origin_allowed unit tests)
   - Whitelist resolution
   - Wildcard support
   - Regex security (prevention of subdomain prefix spoofs like localhost.evil.com)
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.core.socket_manager import _is_origin_allowed, is_origin_allowed
from backend.main import app_asgi


@pytest.fixture
def cors_client() -> Generator[TestClient, None, None]:
    """Test client wrapping the root ASGI app (handling both REST and Socket.IO)."""
    with TestClient(app_asgi) as client:
        yield client


# ── Test Suite 1: REST API CORS ─────────────────────────────────────


class TestRestCors:
    def test_preflight_explicit_origin_allowed(self, cors_client: TestClient) -> None:
        """OPTIONS on REST endpoint with explicit origin returns 200 and CORS headers."""
        resp = cors_client.options(
            "/api/news",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"
        assert "GET" in resp.headers.get("access-control-allow-methods", "")
        assert "authorization" in resp.headers.get("access-control-allow-headers", "").lower()

    def test_preflight_regex_origin_allowed(self, cors_client: TestClient) -> None:
        """OPTIONS on REST endpoint with dynamic localhost port matches cors_origin_regex."""
        resp = cors_client.options(
            "/api/news",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:4173"
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_disallowed_origin_rejected(self, cors_client: TestClient) -> None:
        """OPTIONS on REST endpoint with unauthorized origin returns 400 without allow-origin."""
        resp = cors_client.options(
            "/api/news",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_simple_get_allowed_origin(self, cors_client: TestClient) -> None:
        """GET on REST endpoint with allowed origin includes CORS headers."""
        resp = cors_client.get(
            "/api/news",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_simple_get_disallowed_origin_no_cors_headers(self, cors_client: TestClient) -> None:
        """GET on REST endpoint with disallowed origin omits access-control-allow-origin."""
        resp = cors_client.get(
            "/api/news",
            headers={"Origin": "http://evil.com"},
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers


# ── Test Suite 2: Socket.IO Engine.IO CORS ──────────────────────────


class TestSocketIOCors:
    def test_socketio_options_preflight_allowed(self, cors_client: TestClient) -> None:
        """OPTIONS on /socket.io/ with allowed origin returns 200 and Engine.IO CORS headers."""
        resp = cors_client.options(
            "/socket.io/?EIO=4&transport=polling",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"
        assert "OPTIONS" in resp.headers.get("access-control-allow-methods", "")

    def test_socketio_options_preflight_regex_allowed(self, cors_client: TestClient) -> None:
        """OPTIONS on /socket.io/ with regex-matched port returns 200."""
        resp = cors_client.options(
            "/socket.io/?EIO=4&transport=polling",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_socketio_options_preflight_disallowed(self, cors_client: TestClient) -> None:
        """OPTIONS on /socket.io/ with unauthorized origin returns 400 without allow-origin."""
        resp = cors_client.options(
            "/socket.io/?EIO=4&transport=polling",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_socketio_polling_handshake_allowed(self, cors_client: TestClient) -> None:
        """GET on /socket.io/ polling handshake with allowed origin succeeds with session packet."""
        resp = cors_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"
        # Engine.IO open packet format: 0{"sid":"...","upgrades":[...],...}
        assert resp.text.startswith("0{")
        assert "sid" in resp.text

    def test_socketio_polling_handshake_disallowed(self, cors_client: TestClient) -> None:
        """GET on /socket.io/ polling handshake with disallowed origin returns 400."""
        resp = cors_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://evil.com"},
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_socketio_polling_without_origin(self, cors_client: TestClient) -> None:
        """GET on /socket.io/ polling without Origin header (native client) returns 200."""
        resp = cors_client.get("/socket.io/?EIO=4&transport=polling")
        assert resp.status_code == 200
        assert resp.text.startswith("0{")


# ── Test Suite 3: Unit Tests for Dynamic Origin Checker ─────────────


class TestDynamicOriginChecker:
    def test_origin_allowed_empty_or_none(self) -> None:
        assert is_origin_allowed(None) is True
        assert is_origin_allowed("") is True
        assert _is_origin_allowed(None) is True
        assert _is_origin_allowed("") is True

    def test_origin_allowed_explicit_whitelist(self) -> None:
        assert is_origin_allowed("http://localhost:5173") is True
        assert is_origin_allowed("http://127.0.0.1:5500") is True

    def test_origin_allowed_regex_local_ports(self) -> None:
        assert is_origin_allowed("http://localhost:8080") is True
        assert is_origin_allowed("http://127.0.0.1:3000") is True
        assert is_origin_allowed("https://localhost:4173") is True

    def test_origin_disallowed_external_and_spoofs(self) -> None:
        assert is_origin_allowed("http://evil.com") is False
        assert is_origin_allowed("https://malicious.org") is False
        # Prevent subdomain prefix bypasses
        assert is_origin_allowed("http://localhost.evil.com") is False
        assert is_origin_allowed("http://127.0.0.1.attacker.com") is False

    def test_wildcard_origin_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "cors_origins", ["*"])
        assert is_origin_allowed("http://any-domain.com") is True
        assert is_origin_allowed("https://random-site.org") is True
