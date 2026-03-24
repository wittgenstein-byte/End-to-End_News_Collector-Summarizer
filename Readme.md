# 📰 NEWSROOM — Thai News Aggregator

ระบบดึงข่าวอัตโนมัติและสรุปจากหลายสำนักข่าวไทย แสดงผลแบบ Real-time บนเว็บ

---

## 🗂️ โครงสร้างไฟล์

```
backend/
├── main.py              — FastAPI app factory
├── config.py            — Settings (env vars, paths)
├── .env / .env.example  — API keys, adjustable params
├── core/
│   ├── browser.py       — Playwright HTML fetcher
│   ├── constants.py      — BROWSER_HEADERS
│   ├── fetcher_service.py
│   └── socket_manager.py — Socket.IO singleton
├── schemas/
│   └── news_schema.py   — Pydantic models (ArticleRecord, NewsSummary, ...)
├── repo/
│   └── news_repo.py     — JSON persistence (NewsRepositoryPort)
├── routers/
│   ├── news_router.py   — /news, /sources, /status
│   └── collect_router.py — /collect-md
├── services/
│   ├── scraper_service.py  — background loop
│   ├── summarizer_service.py — LLM summarizer
│   ├── classifier_service.py — keyword-based categorizer
│   └── fetcher_service.py
├── scrapers/
│   ├── registry.py   — @register_source decorator
│   ├── helpers.py    — HTML parse, image, URL utilities
│   └── sources.py    — source scrapers (ThaiPBS, Bangkok Post, Matichon, ...)
└── sockets/
    └── events.py     — connect / disconnect

frontend/
├── index.html
├── package.json
└── static/
    ├── app.css    — all styles (CSS variables)
    ├── config.js  — API_BASE, CATEGORIES, SOURCE_COLORS
    ├── api.js     — fetch/socket helpers
    ├── ui.js      — render, DOM only
    └── main.js    — controller, module-level state

data/                  — created at runtime
├── news_data.json     — persisted articles
└── collected_md/      — downloaded Markdown files
```

---

## ✅ ความต้องการของระบบ

- Python **3.10** ขึ้นไป
- Node.js **18+** (for frontend dev server)
- Chromium / Chrome (for Playwright)

---

## 📦 ติดตั้ง Dependencies

```bash
# Python
pip install requests beautifulsoup4 playwright fastapi trafilatura uvicorn \
  socketio httpx openai pythainlp pydantic

# Playwright browser
playwright install chromium

# Frontend
cd frontend && npm install && cd ..
```

---

## ⚙️ Environment Setup

Copy `backend/.env.example` → `backend/.env` แล้วกำหนดค่าตามต้องการ:

```env
# LLM (required for summarization)
LLM_API=your_api_key_here
LLM_BASE_URL=https://gen.ai.kku.ac.th/api/v1
LLM_MODEL=gemini-3.1-flash-lite-preview
LLM_TEMPERATURE=0.3

# Scraper
INTERVAL_MINUTES=15
MAX_ARTICLES_PER_SOURCE=10
SUMMARY_SENTENCES=3
PAGE_SIZE=20

# Server (optional)
HOST=0.0.0.0
PORT=5000
```

---

## 🚀 วิธีรัน

```bash
python backend/main.py
```

เปิดเบราว์เซอร์ → http://localhost:5000

---

## 📡 สำนักข่าวที่รองรับ

| สำนัก | URL | วิธีดึงข่าว |
|---|---|---|
| ThaiPBS | https://www.thaipbs.or.th/news | HTML |
| Bangkok Post | https://www.bangkokpost.com/thailand/general | HTML |
| Matichon | https://www.matichon.co.th/news | RSS |
| 101 World | https://www.the101.world | Playwright |
| The Standard | https://thestandard.co | RSS |

---

## 🏷️ Categories

politics, economy, technology, health, environment, society, sports, entertainment, world

---

## 🔍 Lint / Type Check

```bash
ruff check backend/
mypy backend/
```

---

## 🧪 Test

```bash
# ติดตั้ง pytest ก่อน (ถ้ายังไม่มี)
pip install pytest

# รันทุก test
pytest backend/tests/ -v

# รันไฟล์เดียว
pytest backend/tests/test_news_repo.py -v

# รัน test ที่มีชื่อตรงกับ pattern
pytest -k "test_load" -v
```

---

## 📝 หมายเหตุ

- รอบแรกใช้เวลา **2-5 นาที** สำหรับการดึงข่าวครั้งแรก
- โฟลเดอร์ `data/` ถูกสร้างอัตโนมัติเมื่อรัน อย่า push ขึ้น git
- ดู `AGENTS.md` สำหรับ code style และ guidelines สำหรับ agentic coding
