"""
main.py
─────────────────────────────────────────────────────────────────
SOLID  S — App factory เท่านั้น: สร้าง app, register middleware,
           mount routers, จัดการ lifespan
           ไม่มี business logic แม้แต่บรรทัดเดียว
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# On Windows, Playwright requires ProactorEventLoop for subprocesses
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ── Import Fix ────────────────────────────────────────────────────
# Ensure the parent directory is in sys.path so 'import backend.xxx' works
# even when running from within the backend directory.
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import httpx
import socketio  # type: ignore[import-untyped]
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# register socket events (side-effect import)
import backend.sockets.events  # noqa: F401
from backend.config import settings
from backend.core.socket_manager import emit, sio
from backend.repo.news_repo import get_news_repository
from backend.routers.collect_router import router as collect_router
from backend.routers.macro_event_router import router as macro_event_router
from backend.routers.monitoring_router import router as monitoring_router
from backend.routers.news_router import router as news_router
from backend.routers.story_router import router as story_router
from backend.routers.trending_router import router as trending_router
from backend.services.scraper_service import ScraperService

# Check CLI flag for headless operation
if "--headless" in sys.argv:
    settings.headless = True


def get_service_catalog() -> dict[str, Any]:
    """Return JSON service catalog for headless root endpoint."""
    return {
        "service": "News Collector & Summarizer API",
        "status": "ok",
        "mode": "headless",
        "version": "2.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "endpoints": [
            "/api/news",
            "/api/news/trending",
            "/api/stories",
            "/api/stories/trending",
            "/api/macro-events",
            "/api/macro-events/trending",
            "/api/sources",
            "/api/categories",
            "/api/status",
            "/api/monitoring",
            "/livez",
            "/readyz",
        ],
    }


def _playwright_health_url(service_url: str) -> str:
    parsed = urlsplit(service_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "/healthz", "", ""))


def _check_storage_ready() -> tuple[bool, str | None]:
    try:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe_file = settings.DATA_DIR / ".readyz"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        return True, None
    except Exception as exc:
        return False, str(exc)


async def _check_playwright_ready() -> tuple[bool, str | None]:
    health_url = _playwright_health_url(settings.playwright_service_url)
    if not health_url:
        return False, "PLAYWRIGHT_SERVICE_URL is invalid"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(health_url)
            response.raise_for_status()
        return True, None
    except Exception as exc:
        return False, str(exc)


# ── Lifespan — start / stop background scraper ────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = get_news_repository()
    scraper = ScraperService(
        repo=repo,
        emit_fn=emit,  # inject ผ่าน core.socket_manager
        interval_minutes=settings.interval_minutes,
    )
    task = asyncio.create_task(scraper.run_loop())
    yield
    task.cancel()


class _NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        if settings.headless:
            return JSONResponse({"error": "Static files disabled in headless mode"}, status_code=404)
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


# ── App Factory ───────────────────────────────────────────────────


def create_app(headless: bool | None = None) -> FastAPI:
    """
    App Factory for FastAPI application.
    Supports headless mode (REST/WebSocket API only, no static/HTML routes).
    """
    is_headless = settings.headless if headless is None else headless

    app_instance = FastAPI(
        title="News Collector & Summarizer",
        version="2.0.0",
        lifespan=lifespan,
    )

    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # ── Routers (Registered in all modes) ─────────────────────────
    app_instance.include_router(story_router)
    app_instance.include_router(macro_event_router)
    app_instance.include_router(news_router)
    app_instance.include_router(collect_router)
    app_instance.include_router(trending_router)
    app_instance.include_router(monitoring_router)

    # Issue Explorer — optional vertical slice (lazy import keeps core boot independent)
    if settings.issue_explorer_enabled:
        from backend.issue_explorer.router import router as issue_explorer_router

        app_instance.include_router(issue_explorer_router)

    # ── Kubernetes Health Probes (Registered in all modes) ─────────
    @app_instance.get("/livez", response_model=None)
    async def livez() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app_instance.get("/readyz", response_model=None)
    async def readyz() -> JSONResponse:
        storage_ok, storage_error = await asyncio.to_thread(_check_storage_ready)
        playwright_ok, playwright_error = await _check_playwright_ready()

        checks = {
            "storage": {
                "ok": storage_ok,
                "path": str(settings.DATA_DIR),
            },
            "playwright": {
                "ok": playwright_ok,
                "url": _playwright_health_url(settings.playwright_service_url),
            },
        }
        if storage_error:
            checks["storage"]["error"] = storage_error
        if playwright_error:
            checks["playwright"]["error"] = playwright_error

        is_ready = storage_ok and playwright_ok
        return JSONResponse(
            {
                "status": "ready" if is_ready else "not_ready",
                "checks": checks,
            },
            status_code=200 if is_ready else 503,
        )

    # ── Headless Mode vs Frontend Static Serving ───────────────────
    if is_headless:
        @app_instance.get("/", response_model=None)
        async def root_headless() -> JSONResponse:
            return JSONResponse(get_service_catalog())
    else:
        _INDEX = settings.frontend_dir / "index.html"
        _MONITORING_PAGE = settings.frontend_dir / "monitoring.html"
        _ISSUES_PAGE = settings.frontend_dir / "issues.html"

        @app_instance.get("/", response_model=None)
        async def index() -> FileResponse | JSONResponse:
            if settings.headless:
                return JSONResponse(get_service_catalog())
            if _INDEX.exists():
                return FileResponse(str(_INDEX))
            return JSONResponse({"error": f"index.html not found at {_INDEX}"}, status_code=404)

        @app_instance.get("/monitoring", response_model=None)
        @app_instance.get("/monitoring.html", response_model=None)
        async def monitoring() -> FileResponse | JSONResponse:
            if settings.headless:
                return JSONResponse({"error": "Monitoring page not available in headless mode"}, status_code=404)
            if _MONITORING_PAGE.exists():
                return FileResponse(str(_MONITORING_PAGE))
            return JSONResponse({"error": f"monitoring.html not found at {_MONITORING_PAGE}"}, status_code=404)

        @app_instance.get("/issues", response_model=None)
        @app_instance.get("/issues.html", response_model=None)
        async def issues() -> FileResponse | JSONResponse:
            if settings.headless:
                return JSONResponse({"error": "Issue Explorer page not available in headless mode"}, status_code=404)
            if not settings.issue_explorer_enabled:
                return JSONResponse({"error": "Issue Explorer feature is disabled"}, status_code=404)
            if _ISSUES_PAGE.exists():
                return FileResponse(str(_ISSUES_PAGE))
            return JSONResponse({"error": f"issues.html not found at {_ISSUES_PAGE}"}, status_code=404)

        @app_instance.get("/manifest.webmanifest", response_model=None)
        async def manifest() -> FileResponse | JSONResponse:
            if settings.headless:
                return JSONResponse({"error": "manifest.webmanifest not available in headless mode"}, status_code=404)
            manifest_path = settings.frontend_dir / "manifest.webmanifest"
            if manifest_path.exists():
                return FileResponse(
                    str(manifest_path),
                    media_type="application/manifest+json",
                )
            return JSONResponse({"error": "manifest.webmanifest not found"}, status_code=404)

        @app_instance.get("/sw.js", response_model=None)
        async def service_worker() -> FileResponse | JSONResponse:
            if settings.headless:
                return JSONResponse({"error": "sw.js not available in headless mode"}, status_code=404)
            sw_path = settings.frontend_dir / "sw.js"
            if sw_path.exists():
                return FileResponse(
                    str(sw_path),
                    media_type="application/javascript",
                    headers={
                        "Service-Worker-Allowed": "/",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )
            return JSONResponse({"error": "sw.js not found"}, status_code=404)

        if settings.frontend_dir.exists() and settings.serve_frontend:
            app_instance.mount(
                "/frontend", _NoCacheStaticFiles(directory=str(settings.frontend_dir)), name="frontend"
            )

    return app_instance


# ── Module Exports (Full Backward Compatibility) ───────────────────

app = create_app()
app_asgi = socketio.ASGIApp(sio, other_asgi_app=app)


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print("🚀 FastAPI Server starting...")
    uvicorn.run(
        "main:app_asgi",
        host=settings.host,
        port=settings.port,
        reload=True,
        loop="asyncio",
    )
