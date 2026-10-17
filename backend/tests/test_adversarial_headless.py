"""
backend/tests/test_adversarial_headless.py
─────────────────────────────────────────────────────────────────
Adversarial Empirical Stress Test Suite for Milestone 1:
- Headless Mode Complete Isolation & Zero-Leakage Verification
- Root Service Catalog Schema & Endpoint Verification
- Non-Headless Backward Compatibility Preservation
- Dynamic CORS & Subdomain Spoof Prevention
- Engine.IO / Socket.IO Origin Gating
- Frontend Client Config Resolution Hierarchy & Edge Cases
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.core.socket_manager import _is_origin_allowed, is_origin_allowed
from backend.main import app_asgi, create_app

_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def headless_client() -> Generator[TestClient, None, None]:
    """TestClient configured in pure headless mode."""
    headless_app = create_app(headless=True)
    with TestClient(headless_app) as client:
        yield client


@pytest.fixture
def backward_compat_client() -> Generator[TestClient, None, None]:
    """TestClient configured in backward-compatible non-headless mode."""
    compat_app = create_app(headless=False)
    with TestClient(compat_app) as client:
        yield client


@pytest.fixture
def asgi_client() -> Generator[TestClient, None, None]:
    """Root ASGI test client handling both Starlette/FastAPI and Socket.IO."""
    with TestClient(app_asgi) as client:
        yield client


# ── Suite 1: Headless Mode Isolation & Zero-Leakage ─────────────────


class TestHeadlessIsolationAndLeakPrevention:
    """Verifies that headless mode never leaks static files, templates, or HTML."""

    STATIC_AND_PAGE_TARGETS: ClassVar[list[str]] = [
        "/frontend/static/UI.js",
        "/frontend/static/config.js",
        "/frontend/static/app.css",
        "/frontend/static/main.js",
        "/frontend/index.html",
        "/frontend/",
        "/frontend",
        "/index.html",
        "/monitoring",
        "/monitoring.html",
        "/issues",
        "/issues.html",
        "/sw.js",
        "/manifest.webmanifest",
    ]

    @pytest.mark.parametrize("route", STATIC_AND_PAGE_TARGETS)
    def test_headless_returns_404_and_no_html_leak(
        self, headless_client: TestClient, route: str
    ) -> None:
        """In headless mode, all UI page and static file routes must return 404."""
        resp = headless_client.get(route)
        assert resp.status_code == 404, (
            f"Expected 404 for route '{route}' in headless mode, got {resp.status_code}"
        )

        # Adversarial leakage check: ensure no HTML tags or source code leak in 404 body
        body = resp.text.lower()
        assert "<!doctype html>" not in body, f"Route '{route}' leaked HTML doctype"
        assert "<html" not in body, f"Route '{route}' leaked HTML tags"
        assert "<body" not in body, f"Route '{route}' leaked body tags"
        assert "export function" not in resp.text, f"Route '{route}' leaked JS source code"

    @pytest.mark.parametrize(
        "traversal_path",
        [
            "/frontend/..%2fbackend/main.py",
            "/frontend/%2e%2e/README.md",
            "/frontend/....//static/UI.js",
            "/frontend/static/../../../backend/config.py",
        ],
    )
    def test_headless_path_traversal_attempts_return_404(
        self, headless_client: TestClient, traversal_path: str
    ) -> None:
        """Path traversal attacks against /frontend must return 404 and not leak files."""
        resp = headless_client.get(traversal_path)
        assert resp.status_code in {400, 404}
        assert "FastAPI" not in resp.text
        assert "Settings" not in resp.text

    def test_headless_dynamic_monkeypatch_on_default_app(
        self, backward_compat_client: TestClient
    ) -> None:
        """Monkeypatching settings.headless = True on default app safely suppresses static serving."""
        with patch.object(settings, "headless", True):
            # Static files return 404 JSON
            res_css = backward_compat_client.get("/frontend/static/app.css")
            assert res_css.status_code == 404
            assert res_css.headers.get("content-type", "").startswith("application/json")
            assert "Static files disabled in headless mode" in res_css.text

            # Pages return 404 JSON
            res_mon = backward_compat_client.get("/monitoring")
            assert res_mon.status_code == 404
            assert "Monitoring page not available in headless mode" in res_mon.text

            # Root returns service catalog JSON instead of index.html
            res_root = backward_compat_client.get("/")
            assert res_root.status_code == 200
            assert res_root.json().get("mode") == "headless"


# ── Suite 2: Root Service Catalog & Endpoint Verification ───────────


class TestRootServiceCatalogSchemaAndEndpoints:
    """Verifies schema completeness and availability of cataloged endpoints."""

    def test_root_catalog_schema_compliance(self, headless_client: TestClient) -> None:
        """GET / returns complete JSON service catalog conforming to spec."""
        resp = headless_client.get("/")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

        catalog = resp.json()
        assert catalog.get("service") == "News Collector & Summarizer API"
        assert catalog.get("status") == "ok"
        assert catalog.get("mode") == "headless"
        assert catalog.get("version") == "2.0.0"
        assert catalog.get("docs") == "/docs"
        assert catalog.get("openapi") == "/openapi.json"

        endpoints = catalog.get("endpoints")
        assert isinstance(endpoints, list)
        assert len(endpoints) >= 10

    def test_core_catalog_endpoints_are_responsive(
        self, headless_client: TestClient
    ) -> None:
        """Verify that core declared REST endpoints respond without 500 server crashes."""
        core_endpoints = [
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
        ]
        for ep in core_endpoints:
            res = headless_client.get(ep)
            assert res.status_code == 200, (
                f"Catalog endpoint {ep} returned unexpected status code {res.status_code}"
            )

    def test_catalog_monitoring_endpoint_behavior(
        self, headless_client: TestClient
    ) -> None:
        """
        Adversarial test: checks behavior of '/api/monitoring' declared in service catalog.
        NOTE: /api/monitoring router mounts subpaths like /stats, /verify, /auth.
        Direct GET /api/monitoring returns 404 because no root route is registered on the router.
        """
        res = headless_client.get("/api/monitoring")
        # Documents empirical behavior: returns 404
        assert res.status_code == 404


# ── Suite 3: Backward Compatibility (headless=False) ────────────────


class TestBackwardCompatibilityMode:
    """Verifies full backward compatibility when headless=False."""

    def test_root_serves_html(self, backward_compat_client: TestClient) -> None:
        """GET / serves index.html with HTML content-type."""
        resp = backward_compat_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "<!DOCTYPE html>" in resp.text or "<html" in resp.text

    def test_static_ui_js_accessible(self, backward_compat_client: TestClient) -> None:
        """GET /frontend/static/UI.js is accessible with JS content-type."""
        resp = backward_compat_client.get("/frontend/static/UI.js")
        assert resp.status_code == 200
        assert "javascript" in resp.headers.get("content-type", "")

    def test_static_app_css_accessible(self, backward_compat_client: TestClient) -> None:
        """GET /frontend/static/app.css is accessible with CSS content-type."""
        resp = backward_compat_client.get("/frontend/static/app.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("content-type", "")

    def test_monitoring_html_accessible(self, backward_compat_client: TestClient) -> None:
        """GET /monitoring serves monitoring HTML."""
        resp = backward_compat_client.get("/monitoring")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_service_worker_and_manifest_accessible(
        self, backward_compat_client: TestClient
    ) -> None:
        """GET /sw.js and /manifest.webmanifest are accessible with appropriate headers."""
        sw_res = backward_compat_client.get("/sw.js")
        assert sw_res.status_code == 200
        assert sw_res.headers.get("Service-Worker-Allowed") == "/"

        man_res = backward_compat_client.get("/manifest.webmanifest")
        assert man_res.status_code == 200
        assert "manifest+json" in man_res.headers.get("content-type", "")


# ── Suite 4: Dynamic CORS & Subdomain Spoof Prevention ──────────────


class TestAdversarialCORSSecurity:
    """Adversarial testing against CORS misconfigurations and origin spoofing."""

    @pytest.mark.parametrize(
        ("malicious_origin", "description"),
        [
            ("http://localhost.attacker.com", "Subdomain prefix bypass"),
            ("http://127.0.0.1.malicious.net", "IP prefix bypass"),
            ("http://evil-localhost:5000", "Hyphenated hostname spoof"),
            ("http://localhost:5173.evil.org", "Port appended to spoofed domain"),
            ("https://attacker-site.com", "Generic external origin"),
            ("http://localhost:abc", "Non-numeric port spoof"),
            ("ftp://localhost:5173", "Disallowed scheme ftp"),
            ("file:///localhost:5173", "Disallowed scheme file"),
            ("javascript:alert(1)", "URI scheme injection"),
        ],
    )
    def test_disallowed_origin_checker(
        self, malicious_origin: str, description: str
    ) -> None:
        """Dynamic origin checker must reject spoofed or unauthorized origins."""
        assert _is_origin_allowed(malicious_origin) is False, f"Failed for: {description}"
        assert is_origin_allowed(malicious_origin) is False, f"Failed for: {description}"

    @pytest.mark.parametrize(
        "legit_origin",
        [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5500",
            "http://localhost:8080",
            "http://localhost:4173",
            "http://localhost",
            "http://127.0.0.1",
            "https://localhost:3000",
            "https://127.0.0.1:5500",
        ],
    )
    def test_allowed_origin_checker(self, legit_origin: str) -> None:
        """Dynamic origin checker must accept legitimate loopback development origins."""
        assert _is_origin_allowed(legit_origin) is True
        assert is_origin_allowed(legit_origin) is True

    def test_preflight_spoofed_origin_blocked(self, asgi_client: TestClient) -> None:
        """REST OPTIONS preflight from spoofed origin returns 400 Bad Request."""
        resp = asgi_client.options(
            "/api/news",
            headers={
                "Origin": "http://localhost.attacker.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_socketio_handshake_spoofed_origin_blocked(
        self, asgi_client: TestClient
    ) -> None:
        """Socket.IO Engine.IO polling handshake from spoofed origin returns 400."""
        resp = asgi_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://localhost.attacker.com"},
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_socketio_handshake_legit_origin_allowed(
        self, asgi_client: TestClient
    ) -> None:
        """Socket.IO Engine.IO polling handshake from Vite dev server returns 200 with open packet."""
        resp = asgi_client.get(
            "/socket.io/?EIO=4&transport=polling",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"
        assert resp.text.startswith("0{")
        assert "sid" in resp.text


# ── Suite 5: Frontend Client Config Resolution (Node.js) ────────────


class TestFrontendClientConfigResolution:
    """Runs the 37-case Node.js adversarial suite testing config.js."""

    def test_client_config_adversarial_suite_via_node(self) -> None:
        """Execute test_config_resolution_adversarial.mjs with Node.js."""
        script_path = _ROOT / "backend" / "tests" / "test_config_resolution_adversarial.mjs"
        assert script_path.exists(), f"Script not found at {script_path}"

        result = subprocess.run(
            ["node", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(_ROOT),
        )

        print("\n--- Node.js Test Output ---")
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        assert result.returncode == 0, f"Node.js config test failed with code {result.returncode}"
        assert "37 passed, 0 failed" in result.stdout
