"""
server.py — FastAPI + WebSocket + BackgroundTasks
ติดตั้ง: pip install fastapi uvicorn python-socketio httpx
"""

import asyncio
import json
import os
import uvicorn
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import socketio

from news_scraper import SOURCES
from md_collector import collect_markdown_with_jina

# ── config ───────────────────────────────────────────────────
INTERVAL_MINUTES = 15
PAGE_SIZE        = 20
OUTPUT_FILE      = "news_output.json"
SEEN_FILE        = "seen_urls.json"

sio      = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# ── file helpers ─────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)

def load_all_news() -> list[dict]:
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_all_news(data: list[dict]) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── background scraper ────────────────────────────────────────

async def scrape_loop():
    seen = load_seen()
    while True:
        print(f"\n[{datetime.now():%H:%M:%S}] 🔄 กำลังดึงข่าว...")
        all_news  = load_all_news()
        new_batch = []

        for source in SOURCES:
            try:
                articles = await source.scrape_fn()
                fresh    = [a for a in articles if a.get("url") and a["url"] not in seen]
                for a in fresh:
                    seen.add(a["url"])
                new_batch.extend(fresh)
                print(f"  ✅ {source.name}: {len(fresh)} ใหม่")
            except Exception as e:
                print(f"  ❌ {source.name}: {e}")

        if new_batch:
            all_news.extend(new_batch)
            save_all_news(all_news)
            save_seen(seen)
            print(f"  💾 {len(new_batch)} บทความใหม่ (รวม {len(all_news)})")
            await sio.emit("new_articles", {
                "count":    len(new_batch),
                "total":    len(all_news),
                "articles": new_batch,
                "updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            print("  — ไม่มีข่าวใหม่")

        try:
            await asyncio.sleep(INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            print("\n👋 scraper task halted")
            break

# ── server lifecycle ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task when startup
    scrape_task = asyncio.create_task(scrape_loop())
    yield
    # Cancel task on shutdown
    scrape_task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount ASGI SocketIO Server at /socket.io
app_asgi = socketio.ASGIApp(sio, other_asgi_app=app)


# ── serve frontend ────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse("index.html")

# mount static files if exist to serve assets
if os.path.exists("frontend"):
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


# ── REST API ──────────────────────────────────────────────────

@app.get("/api/news")
async def get_news(page: int = 1, source: str = "", q: str = ""):
    page   = max(1, page)
    source_val = source.strip()
    query  = q.strip().lower()

    news = load_all_news()
    news.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)

    if source_val:
        news = [n for n in news if n["source"].lower() == source_val.lower()]
    if query:
        news = [n for n in news if query in n["title"].lower() or query in n.get("summary", "").lower()]

    total       = len(news)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    start       = (page - 1) * PAGE_SIZE
    page_items  = news[start: start + PAGE_SIZE]

    return JSONResponse({
        "total":       total,
        "page":        page,
        "page_size":   PAGE_SIZE,
        "total_pages": total_pages,
        "has_next":    page < total_pages,
        "has_prev":    page > 1,
        "updated":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "news":        page_items,
    })

@app.get("/api/sources")
async def get_sources():
    news   = load_all_news()
    counts = {}
    for n in news:
        counts[n["source"]] = counts.get(n["source"], 0) + 1
    return JSONResponse({"sources": counts})

@app.get("/api/status")
async def get_status():
    return JSONResponse({
        "status":   "running",
        "interval": f"{INTERVAL_MINUTES} minutes",
        "total":    len(load_all_news()),
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

@app.post("/api/collect-md")
async def collect_md(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    
    url = data.get("url")
    if not url:
        return JSONResponse({"ok": False, "error": "No URL provided"}, status_code=400)
    try:
        filepath = await collect_markdown_with_jina(url)
        return JSONResponse({"ok": True, "path": filepath})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ── WebSocket ─────────────────────────────────────────────────

@sio.event
async def connect(sid, environ):
    news = load_all_news()
    await sio.emit("init", {
        "total":   len(news),
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }, to=sid)
    print(f"  🔌 client เชื่อมต่อแล้ว ({sid})")

@sio.event
async def disconnect(sid):
    print(f"  🔌 client ตัดการเชื่อมต่อ ({sid})")


# ── main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 FastAPI Server starting...")
    uvicorn.run("server:app_asgi", host="0.0.0.0", port=5000, reload=True)