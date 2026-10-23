"""
backend/tests/test_adversarial_cors_socketio.py
─────────────────────────────────────────────────────────────────
Adversarial empirical stress testing suite for Milestone 1:
- CORS allowed vs disallowed origins (spoofing, subdomains, prefix attacks)
- Preflight OPTIONS requests across HTTP methods, headers, and endpoints
- Socket.IO origin validation with malformed, spoofed, and null origins
- Credentials handling when origins are regex, explicit whitelist, or wildcard
- IPv6, casing, trailing slashes, and boundary condition evaluation
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import ClassVar

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.core.socket_manager import _is_origin_allowed, is_origin_allowed
from backend.main import app_asgi, create_app


@pytest.fixture
def asgi_client() -> Generator[TestClient, None, None]:
    """Test client wrapping root ASGI app (handling both REST and Socket.IO)."""
    with TestClient(app_asgi) as client:
        yield client


@pytest.fixture
def headless_client() -> Generator[TestClient, None, None]:
    """Test client wrapping headless FastAPI app."""
    app_instance = create_app(headless=True)
    with TestClient(app_instance) as client:
        yield client


# ── Challenge Suite 1: Origin Validation & Spoofing Defense ────────


class TestOriginValidationAdversarial:
    """Stress-test _is_origin_allowed and REST/Socket.IO against malicious origins."""

    ADVERSARIAL_DISALLOWED_ORIGINS: ClassVar[list[str]] = [
        "http://evil.com",
        "https://evil.com",
        "http://attacker.org:5173",
        "http://localhost.evil.com",
        "https://localhost.evil.com:5173",
        "http://127.0.0.1.attacker.com",
        "http://127.0.0.1.attacker.com:3000",
        "http://not-localhost:5173",
        "http://evil-localhost:5173",
        "http://localhost5173.com",
        "http://localhost.com",
        "http://127.0.0.10:5000",
        "http://127.0.0.2:5173",
        "http://127.1.1.1:5173",
        "http://localhost:5173@attacker.com",
        "http://attacker.com#localhost:5173",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "null",
        "data:text/html,<html></html>",
    ]

    ALLOWED_LEGITIMATE_ORIGINS: ClassVar[list[str]] = [
        "http://localhost:5173",       # Explicit whitelist (Vite)
        "http://127.0.0.1:5500",      # Explicit whitelist (Live Server)
        "http://localhost:3000",       # Explicit whitelist (React/Node)
        "http://localhost:4173",       # Regex matched (Vite preview)
        "http://localhost:8080",       # Regex matched (Webpack/http-server)
        "http://127.0.0.1:3000",       # Regex matched
        "http://127.0.0.1:8000",       # Regex matched
        "http://localhost:65535",      # Regex matched (max port)
        "http://localhost:1",          # Regex matched (min port)
        "http://localhost",            # Regex matched (default port 80)
        "http://127.0.0.1",            # Regex matched (default port 80)
        "https://localhost:5173",      # Regex matched (HTTPS dev)
        "https://127.0.0.1:5173",      # Regex matched (HTTPS dev)
    ]

    @pytest.mark.parametrize("origin", ADVERSARIAL_DISALLOWED_ORIGINS)
    def test_origin_allowed_function_rejects_adversarial_origins(self, origin: str) -> None:
        """Dynamic origin checker must reject all adversarial and spoofed origins."""
        assert is_origin_allowed(origin) is False, f"Expected {origin} to be rejected"
        assert _is_origin_allowed(origin) is False

    @pytest.mark.parametrize("origin", ALLOWED_LEGITIMATE_ORIGINS)
    def test_origin_allowed_function_accepts_legitimate_dev_origins(self, origin: str) -> None:
        """Dynamic origin checker must accept legitimate dev origins and ports."""
        assert is_origin_allowed(origin) is True, f"Expected {origin} to be allowed"

    @pytest.mark.parametrize("origin", ADVERSARIAL_DISALLOWED_ORIGINS)
    def test_rest_api_rejects_adversarial_origin_header(self, asgi_client: TestClient, origin: str) -> None:
        """REST endpoint must not reflect Access-Control-Allow-Origin for adversarial origins."""
        resp = asgi_client.get("/api/news", headers={"Origin": origin})
        allow_origin = resp.headers.get("access-control-allow-origin")
        assert allow_origin is None, f"Leaked Access-Control-Allow-Origin for {origin}: {allow_origin}"
        assert allow_origin != origin

    @pytest.mark.parametrize("origin", ADVERSARIAL_DISALLOWED_ORIGINS)
    def test_socketio_handshake_rejects_adversarial_origin(self, asgi_client: TestClient, origin: str) -> None:
        """Socket.IO handshake must return 400 and omit allow-origin for adversarial origins."""
        resp = asgi_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": origin},
        )
        assert resp.status_code == 400, f"Expected 400 for {origin}, got {resp.status_code}"
        assert "access-control-allow-origin" not in resp.headers


# ── Challenge Suite 2: Preflight OPTIONS Deep Stress Test ──────────


class TestCorsPreflightStress:
    """Stress-test OPTIONS preflight across multiple HTTP methods, headers, and routes."""

    PREFLIGHT_METHODS: ClassVar[list[str]] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]

    @pytest.mark.parametrize("method", PREFLIGHT_METHODS)
    def test_rest_preflight_allows_standard_methods(self, asgi_client: TestClient, method: str) -> None:
        """Preflight OPTIONS must allow all standard HTTP methods for allowed origin."""
        resp = asgi_client.options(
            "/api/news",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": method,
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        assert method in allow_methods or "*" in allow_methods

    CUSTOM_HEADERS: ClassVar[list[str]] = [
        "authorization",
        "content-type",
        "x-requested-with",
        "x-api-key",
        "x-client-version",
        "sentry-trace",
        "baggage",
        "authorization, content-type, x-custom-trace-id",
    ]

    @pytest.mark.parametrize("headers_str", CUSTOM_HEADERS)
    def test_rest_preflight_allows_custom_headers(self, asgi_client: TestClient, headers_str: str) -> None:
        """Preflight OPTIONS must allow custom and tracking headers for allowed origin."""
        resp = asgi_client.options(
            "/api/news",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": headers_str,
            },
        )
        assert resp.status_code == 200
        allow_headers = resp.headers.get("access-control-allow-headers", "").lower()
        for h in headers_str.split(","):
            h_clean = h.strip().lower()
            assert h_clean in allow_headers or "*" in allow_headers

    ENDPOINTS: ClassVar[list[str]] = [
        "/api/news",
        "/api/news/trending",
        "/api/stories",
        "/api/stories/trending",
        "/api/macro-events",
        "/api/macro-events/trending",
        "/api/sources",
        "/api/categories",
        "/api/status",
        "/livez",
        "/readyz",
    ]

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_preflight_works_across_all_endpoints(self, asgi_client: TestClient, path: str) -> None:
        """Every public REST endpoint must respond cleanly to preflight OPTIONS."""
        resp = asgi_client.options(
            path,
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_preflight_disallowed_origin_returns_400(self, asgi_client: TestClient) -> None:
        """Preflight from disallowed origin must fail with 400 Bad Request."""
        resp = asgi_client.options(
            "/api/news",
            headers={
                "Origin": "https://malicious-attacker.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers


# ── Challenge Suite 3: Socket.IO Engine.IO Adversarial Test ─────────


class TestSocketIOAdversarial:
    """Stress-test Socket.IO protocol edge cases and malformed requests."""

    def test_socketio_polling_handshake_session_structure(self, asgi_client: TestClient) -> None:
        """Handshake packet must contain valid session id (sid), upgrades, and timeouts."""
        resp = asgi_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert resp.text.startswith("0{")
        payload = json.loads(resp.text[1:])
        assert "sid" in payload
        assert isinstance(payload["sid"], str)
        assert len(payload["sid"]) > 5
        assert "upgrades" in payload
        assert "websocket" in payload["upgrades"]
        assert "pingInterval" in payload
        assert "pingTimeout" in payload

    def test_socketio_options_preflight_post_method(self, asgi_client: TestClient) -> None:
        """Preflight OPTIONS for POST on Socket.IO polling endpoint with allowed origin."""
        resp = asgi_client.options(
            "/socket.io/?EIO=4&transport=polling",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_socketio_options_preflight_disallowed_origin(self, asgi_client: TestClient) -> None:
        """Preflight OPTIONS for POST on Socket.IO polling endpoint with disallowed origin returns 400."""
        resp = asgi_client.options(
            "/socket.io/?EIO=4&transport=polling",
            headers={
                "Origin": "http://evil-attacker.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_socketio_transport_fallback_default(self, asgi_client: TestClient) -> None:
        """Engine.IO defaults to polling when transport parameter is omitted in query."""
        resp = asgi_client.get(
            "/socket.io/?EIO=4",
            headers={"Origin": "http://localhost:5173"},
        )
        # Engine.IO spec defaults transport to polling, returning session packet 200
        assert resp.status_code == 200
        assert resp.text.startswith("0{")

    def test_socketio_unsupported_transport(self, asgi_client: TestClient) -> None:
        """Socket.IO request with invalid transport returns 400 error."""
        resp = asgi_client.get(
            "/socket.io/?EIO=4&transport=invalid_proto",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 400


# ── Challenge Suite 4: Credentials Handling: Regex vs Wildcard ──────


class TestCredentialsHandlingStress:
    """Stress-test credential exposure under regex, explicit whitelist, and wildcard configurations."""

    def test_regex_origin_credentials_reflection(self, asgi_client: TestClient) -> None:
        """When an origin matches cors_origin_regex, Starlette reflects that origin + credentials=true."""
        origin = "http://localhost:4173"  # Matches regex, not in explicit list
        resp = asgi_client.get("/api/news", headers={"Origin": origin})
        assert resp.status_code == 200
        # Specifically reflects the matching origin, NOT a wildcard
        assert resp.headers.get("access-control-allow-origin") == origin
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_explicit_origin_credentials_reflection(self, asgi_client: TestClient) -> None:
        """Explicit allowed origin returns exact origin + credentials=true."""
        origin = "http://localhost:5173"
        resp = asgi_client.get("/api/news", headers={"Origin": origin})
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == origin
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_disallowed_origin_does_not_leak_credentials(self, asgi_client: TestClient) -> None:
        """Disallowed origin must NOT receive access-control-allow-origin or credentials header."""
        origin = "http://evil-attacker.com"
        resp = asgi_client.get("/api/news", headers={"Origin": origin})
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers

    def test_starlette_wildcard_with_credentials_behavior(self) -> None:
        """
        Verify Starlette's behavior when allow_origins=['*'] and allow_credentials=True.
        CORS spec requires that allow-origin cannot be '*' with credentials.
        Starlette CORSMiddleware complies by reflecting the request's exact Origin.
        """
        test_app = FastAPI()
        test_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @test_app.get("/test")
        def endpoint() -> dict[str, str]:
            return {"status": "ok"}

        with TestClient(test_app) as client:
            resp = client.get("/test", headers={"Origin": "http://client.example.com"})
            assert resp.status_code == 200
            # Starlette reflects the origin instead of returning '*' to satisfy W3C credentials spec
            assert resp.headers.get("access-control-allow-origin") == "http://client.example.com"
            assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_trailing_slash_in_origin_header(self, asgi_client: TestClient) -> None:
        """Origin header with trailing slash should be handled cleanly."""
        resp = asgi_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://localhost:5173/"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") in {
            "http://localhost:5173/",
            "http://localhost:5173",
        }

    def test_empty_string_and_none_origin_behavior(self) -> None:
        """None or empty string Origin (same-origin/server calls) must be allowed."""
        assert is_origin_allowed(None) is True
        assert is_origin_allowed("") is True

    def test_ipv6_localhost_origin_caveat(self) -> None:
        r"""
        Adversarial Boundary Check: IPv6 localhost (http://[::1]:5173).
        Empirically document that the default regex (^https?://(localhost|127\.0\.0\.1)(:\d+)?$)
        does NOT match IPv6 [::1].
        """
        assert is_origin_allowed("http://[::1]:5173") is False
        assert is_origin_allowed("http://[::1]") is False


# ── Challenge Suite 5: Headless Service Catalog Contract Analysis ──


class TestHeadlessServiceCatalogContract:
    """Verify that headless mode service catalog accurately reflects live endpoints."""

    def test_catalog_functional_endpoints(self, headless_client: TestClient) -> None:
        """Verify key functional endpoints listed in service catalog."""
        functional_endpoints: list[str] = [
            "/api/news",
            "/api/news/trending",
            "/api/stories",
            "/api/stories/trending",
            "/api/macro-events",
            "/api/macro-events/trending",
            "/api/sources",
            "/api/categories",
            "/api/status",
            "/livez",
            "/readyz",
        ]
        for ep in functional_endpoints:
            res = headless_client.get(ep, headers={"Origin": "http://localhost:5173"})
            assert res.status_code in {200, 503}, f"Endpoint {ep} failed with {res.status_code}"
            assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_catalog_discrepancy_api_monitoring_404(self, headless_client: TestClient) -> None:
        """
        Adversarial Observation: In get_service_catalog(), '/api/monitoring' is listed.
        However, monitoring_router defines subroutes (/api/monitoring/stats, /api/monitoring/auth)
        and has NO bare '/api/monitoring' root route, resulting in 404.
        """
        catalog_resp = headless_client.get("/")
        catalog = catalog_resp.json()
        assert "/api/monitoring" in catalog["endpoints"]

        # Directly requesting /api/monitoring returns 404
        bare_monitoring_res = headless_client.get("/api/monitoring")
        assert bare_monitoring_res.status_code == 404

        # Subroute /api/monitoring/stats requires auth and returns 401 (not 404)
        stats_res = headless_client.get("/api/monitoring/stats")
        assert stats_res.status_code == 401
