"""
main.py
─────────────────────────────────────────────────────────────────
SOLID  S — App factory เท่านั้น: สร้าง app, register middleware,
           mount routers, จัดการ lifespan
           ไม่มี business logic แม้แต่บรรทัดเดียว
─────────────────────────────────────────────────────────────────
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# ── Import Fix ────────────────────────────────────────────────────
# Ensure the parent directory is in sys.path so 'import backend.xxx' works
# even when running from within the backend directory.
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import socketio
import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.core.socket_manager import sio, emit

# register socket events (side-effect import)
import backend.sockets.events  # noqa: F401

from backend.repo.news_repo import get_news_repository
from backend.routers.news_router import router as news_router
from backend.routers.collect_router import router as collect_router
from backend.services.scraper_service import ScraperService


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


# ── FastAPI app ───────────────────────────────────────────────────

app = FastAPI(
    title="News Collector & Summarizer",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────

app.include_router(news_router)
app.include_router(collect_router)


# ── Frontend static files ─────────────────────────────────────────

_INDEX = settings.frontend_dir / "index.html"


@app.get("/", response_model=None)
async def index() -> FileResponse | JSONResponse:
    if _INDEX.exists():
        return FileResponse(str(_INDEX))
    return JSONResponse({"error": f"index.html not found at {_INDEX}"}, status_code=404)


@app.get("/livez", response_model=None)
async def livez() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/readyz", response_model=None)
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


if settings.frontend_dir.exists():
    app.mount(
        "/frontend", StaticFiles(directory=str(settings.frontend_dir)), name="frontend"
    )


# ── ASGI app (Socket.IO wrapper) ──────────────────────────────────

app_asgi = socketio.ASGIApp(sio, other_asgi_app=app)


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 FastAPI Server starting...")
    uvicorn.run(
        "main:app_asgi",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
