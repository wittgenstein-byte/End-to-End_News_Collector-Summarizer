"""
server.py — Flask + WebSocket + Pagination
ติดตั้ง: pip install flask flask-cors flask-socketio eventlet
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json, os, threading, time
from datetime import datetime

from news_scraper import SOURCES

# ── config ───────────────────────────────────────────────────
INTERVAL_MINUTES = 15
PAGE_SIZE        = 20
OUTPUT_FILE      = "news_output.json"
SEEN_FILE        = "seen_urls.json"

app      = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")


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

def scrape_loop():
    seen = load_seen()
    while True:
        print(f"\n[{datetime.now():%H:%M:%S}] 🔄 กำลังดึงข่าว...")
        all_news  = load_all_news()
        new_batch = []

        for source in SOURCES:
            try:
                articles = source.scrape_fn()
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
            socketio.emit("new_articles", {
                "count":    len(new_batch),
                "total":    len(all_news),
                "articles": new_batch,
                "updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            print("  — ไม่มีข่าวใหม่")

        time.sleep(INTERVAL_MINUTES * 60)


# ── serve frontend ────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ── REST API ──────────────────────────────────────────────────

@app.route("/api/news")
def get_news():
    page   = max(1, int(request.args.get("page", 1)))
    source = request.args.get("source", "").strip()
    query  = request.args.get("q", "").strip().lower()

    news = load_all_news()
    news.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)

    if source:
        news = [n for n in news if n["source"].lower() == source.lower()]
    if query:
        news = [n for n in news if query in n["title"].lower() or query in n.get("summary", "").lower()]

    total       = len(news)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    start       = (page - 1) * PAGE_SIZE
    page_items  = news[start: start + PAGE_SIZE]

    return jsonify({
        "total":       total,
        "page":        page,
        "page_size":   PAGE_SIZE,
        "total_pages": total_pages,
        "has_next":    page < total_pages,
        "has_prev":    page > 1,
        "updated":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "news":        page_items,
    })

@app.route("/api/sources")
def get_sources():
    news   = load_all_news()
    counts = {}
    for n in news:
        counts[n["source"]] = counts.get(n["source"], 0) + 1
    return jsonify({"sources": counts})

@app.route("/api/status")
def get_status():
    return jsonify({
        "status":   "running",
        "interval": f"{INTERVAL_MINUTES} minutes",
        "total":    len(load_all_news()),
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


# ── WebSocket ─────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    news = load_all_news()
    emit("init", {
        "total":   len(news),
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    print("  🔌 client เชื่อมต่อแล้ว")

@socketio.on("disconnect")
def on_disconnect():
    print("  🔌 client ตัดการเชื่อมต่อ")


# ── main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    t = threading.Thread(target=scrape_loop, daemon=True)
    t.start()
    print("🚀 Server: http://localhost:5000")
    socketio.run(app, debug=False, port=5000)