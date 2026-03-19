"""
main.py
─────────────────────────────────────────────────────────────────
SOLID  S — App factory เท่านั้น: สร้าง app, register middleware,
           mount routers, จัดการ lifespan
           ไม่มี business logic แม้แต่บรรทัดเดียว
─────────────────────────────────────────────────────────────────
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from core.socket_manager import sio, emit

# register socket events (side-effect import)
import sockets.events  # noqa: F401

from repo.news_repo import get_news_repository
from routers.news_router import router as news_router
from routers.collect_router import router as collect_router
from services.scraper_service import ScraperService


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
