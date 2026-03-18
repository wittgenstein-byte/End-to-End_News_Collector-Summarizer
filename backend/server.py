"""
server.py — FastAPI + WebSocket + BackgroundTasks
ติดตั้ง: pip install fastapi uvicorn python-socketio httpx
"""

import asyncio
import json
import os
import re
import sys
import httpx
import trafilatura
import uvicorn
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import socketio

from news_scraper import SOURCES
from jina import collect_markdown_with_jina
from openai import OpenAI, http_client
from playwright.sync_api import sync_playwright

# Base directory is End-to-End_News_Collector-Summarizer
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Load api_key from .env directly since python-dotenv might not be installed
api_key = os.environ.get("LLM_API", "")
if not api_key and os.path.exists(ENV_PATH):
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k.strip() == "LLM_API":
                        api_key = v.strip().strip('"').strip("'")
    except Exception:
        pass

client = OpenAI(api_key=api_key, base_url="https://gen.ai.kku.ac.th/api/v1")

SYSTEM_PROMPT = """You are a professional news summarizer. Your task is to read news articles written in Markdown format and produce structured summaries.

## Language Rule
Always respond in the SAME language as the article. Do not translate.

## Output Format
Return ONLY a valid JSON object with this exact structure — no preamble, no markdown fences.

{
  "title": "...",
  "source_url": "...",
  "published_at": "...",
  "language": "...",
  "summary": "2–3 sentence paragraph summarizing the article.",
  "bullets": [
    "Key point 1 (concise, one sentence)",
    "Key point 2",
    "Key point 3",
    "Key point 4 (optional)",
    "Key point 5 (optional)"
  ],
  "category": "...",
  "sentiment": "positive | neutral | negative",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}

## Rules
- `bullets`: 3–5 items. Each bullet must be a complete, standalone sentence.
- `summary`: dense, factual, no filler words.
- `sentiment`: infer from overall tone and content.
- `keywords`: 3–5 most important topic keywords.
- `category`: one of: politics, economy, technology, health, environment, society, sports, entertainment, world
- If any field is unknown or unavailable, use null.
- Never include commentary, opinions, or content outside the JSON."""

# ── config ───────────────────────────────────────────────────
INTERVAL_MINUTES = 15
PAGE_SIZE = 20
OUTPUT_FILE = os.path.join(BASE_DIR, "news_output.json")
SEEN_FILE = os.path.join(BASE_DIR, "seen_urls.json")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

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
        all_news = load_all_news()
        new_batch = []

        for source in SOURCES:
            try:
                articles = await source.scrape_fn()
                fresh = [a for a in articles if a.get("url") and a["url"] not in seen]
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
            await sio.emit(
                "new_articles",
                {
                    "count": len(new_batch),
                    "total": len(all_news),
                    "articles": new_batch,
                    "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
        else:
            print("  — ไม่มีข่าวใหม่")

        try:
            await asyncio.sleep(INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            print("\n👋 scraper task halted")
            break

# สร้างฟังก์ชันสำหรับดึงเว็บแยกต่างหาก
def fetch_with_playwright_sync(url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        context = browser.new_context(user_agent=user_agent)
        page = context.new_page()
        
        # ใช้ domcontentloaded เพื่อไม่ให้รอโหลดรูปภาพ/โฆษณา ช่วยลดโอกาส Timeout
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)
        
        html_content = page.content()
        browser.close()
        return html_content

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
INDEX_HTML_PATH = os.path.join(BASE_DIR, "frontend", "index.html")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


@app.get("/")
async def index():
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH)
    return JSONResponse({"error": f"index.html not found at {INDEX_HTML_PATH}"})


# mount static files if exist to serve assets
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


# ── REST API ──────────────────────────────────────────────────


@app.get("/api/news")
async def get_news(page: int = 1, source: str = "", q: str = ""):
    page = max(1, page)
    source_val = source.strip()
    query = q.strip().lower()

    news = load_all_news()
    news.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)

    if source_val:
        news = [n for n in news if n["source"].lower() == source_val.lower()]
    if query:
        news = [
            n
            for n in news
            if query in n["title"].lower() or query in n.get("summary", "").lower()
        ]

    total = len(news)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    start = (page - 1) * PAGE_SIZE
    page_items = news[start : start + PAGE_SIZE]

    return JSONResponse(
        {
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "news": page_items,
        }
    )


@app.get("/api/sources")
async def get_sources():
    news = load_all_news()
    counts = {}
    for n in news:
        counts[n["source"]] = counts.get(n["source"], 0) + 1
    return JSONResponse({"sources": counts})


@app.get("/api/status")
async def get_status():
    return JSONResponse(
        {
            "status": "running",
            "interval": f"{INTERVAL_MINUTES} minutes",
            "total": len(load_all_news()),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@app.post("/api/collect-md")
async def collect_md(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    url = data.get("url")
    if not url:
        return JSONResponse({"ok": False, "error": "No URL provided"}, status_code=400)
    
    md_content = None
    fetch_method = "None"

    # =======================================================
    # ⚡ TIER 1: httpx แบบปกติ (เร็วที่สุด)
    # =======================================================
    try:
        print(f"⚡ [Tier 1] ดึงข้อมูลด้วย httpx ปกติ: {url}")
        async with httpx.AsyncClient(follow_redirects=True) as http_client:
            resp = await http_client.get(url, timeout=10)
            if resp.status_code == 200:
                temp_md = trafilatura.extract(resp.text)
                if temp_md and len(temp_md) > 100: 
                    md_content = temp_md
                    fetch_method = "Tier 1 (HTTPX)"
    except Exception as e:
        print(f"  ❌ [Tier 1] ล้มเหลว: {e}")

    # =======================================================
    # 🛡️ TIER 2: httpx + ปลอม User-Agent (กรณี Tier 1 โดนบล็อก)
    # =======================================================
    if not md_content:
        try:
            print(f"🛡️ [Tier 2] ดึงข้อมูลด้วย httpx + Headers: {url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            async with httpx.AsyncClient(headers=headers, follow_redirects=True) as http_client:
                resp = await http_client.get(url, timeout=15)
                if resp.status_code == 200:
                    temp_md = trafilatura.extract(resp.text)
                    if temp_md and len(temp_md) > 100 and "Just a moment" not in temp_md and "Enable JavaScript" not in temp_md:
                        md_content = temp_md
                        fetch_method = "Tier 2 (HTTPX + Headers)"
        except Exception as e:
            print(f"  ❌ [Tier 2] ล้มเหลว: {e}")

    # =======================================================
    # 🎭 TIER 3: Playwright (ไม้ตายสุดท้าย กรณีเว็บป้องกันแน่นหนามาก)
    # =======================================================
    if not md_content:
        try:
            print(f"🎭 [Tier 3] ดึงข้อมูลด้วย Playwright: {url}")
            html_content = await asyncio.to_thread(fetch_with_playwright_sync, url)
           
                
            temp_md = trafilatura.extract(html_content)
            if temp_md:
                md_content = temp_md
                fetch_method = "Tier 3 (Playwright Sync)"
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ❌ [Tier 3] ล้มเหลว: {e}")

    # =======================================================
    # 🚨 ตรวจสอบผลลัพธ์สุดท้าย (ถอยออกมาอยู่นอกสุด)
    # =======================================================
    if not md_content:
        return JSONResponse({"ok": False, "error": "ดึงเนื้อหาไม่ได้จากทุกวิธี (เว็บอาจบล็อกรุนแรง หรือเนื้อหาไม่ใช่บทความ)"})

    print(f"✅ ดึงเนื้อหาสำเร็จด้วยวิธี: {fetch_method}")

    try:
        # 📁 บันทึกไฟล์ Markdown ลงเครื่อง
        save_dir = r"D:\Seminar_Project\End-to-End_News_Collector-Summarizer\collected_md"
        os.makedirs(save_dir, exist_ok=True)
        safe_url_name = re.sub(r'[\\/*?:"<>|]', "", url.split("/")[-1])
        if not safe_url_name:
            safe_url_name = "article"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_url_name}.md"
        filepath = os.path.join(save_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Source URL: {url}\n\n")
            f.write(md_content)
        print(f"  💾 บันทึก Markdown: {filepath}")

        # 🤖 ส่งให้ AI สรุปข่าว
        print("🤖 กำลังส่งเนื้อหาให้ AI สรุป...")
        response = client.chat.completions.create(
            model="gemini-3.1-flash-lite-preview",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": md_content},
            ],
            stream=False,
            temperature=0.3,
        )

        llm_output = response.choices[0].message.content.strip()

        # จัดการผลลัพธ์ที่เป็น Markdown Block (ถ้ามี)
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:-3].strip()
        elif llm_output.startswith("```"):
            llm_output = llm_output[3:-3].strip()

        summary_data = json.loads(llm_output)
        
        # คืนค่าสำเร็จกลับไปให้หน้าเว็บ
        return JSONResponse({
            "ok": True, 
            "path": filepath, 
            "summary": summary_data
        })

    except Exception as e:
        # ดักจับ Error ตอน AI พัง หรือแปลง JSON ไม่ได้
        import traceback
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": f"เกิดข้อผิดพลาดในการประมวลผล: {str(e)}"}, status_code=500)

# ── WebSocket ─────────────────────────────────────────────────


@sio.event
async def connect(sid, environ):
    news = load_all_news()
    await sio.emit(
        "init",
        {
            "total": len(news),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        to=sid,
    )
    print(f"  🔌 client เชื่อมต่อแล้ว ({sid})")


@sio.event
async def disconnect(sid):
    print(f"  🔌 client ตัดการเชื่อมต่อ ({sid})")


# ── main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 FastAPI Server starting...")
    uvicorn.run("server:app_asgi", host="0.0.0.0", port=5000, reload=True)
