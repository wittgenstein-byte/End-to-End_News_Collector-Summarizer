# 📰 NEWSROOM — Thai News Aggregator

ระบบดึงข่าวอัตโนมัติ และสรุปจากหลายสำนักข่าวไทย แสดงผลบนเว็บแบบ Real-time
ระบบดึงข่าวอัตโนมัติ และสรุปจากหลายสำนักข่าวไทย แสดงผลบนเว็บแบบ Real-time

---

## 🗂️ โครงสร้างไฟล์

```
### Backend
├── backend/
│ ├── main.py — app factory
│ ├── config.py — settings / env
│ ├── .env.example
│ ├── core/
│ │ ├── browser.py — playwright HTML
│ │ ├── constants.py — BROWSER_HEADERS
│ │ └── socket_manager.py — sio singleton
│ ├── schemas/
│ │ └── news_schema.py — Pydantic models
│ ├── repositories/
│ │ └── news_repository.py — JSON file I/O
│ ├── services/
│ │ ├── fetcher_service.py — 3-tier fetch
│ │ ├── summarizer_service.py — LLM
│ │ └── scraper_service.py — bg loop
│ ├── scrapers/
│ │ ├── __init__.py — export SOURCES
│ │ ├── registry.py — NewsSource + register
│ │ ├── helpers.py — find_url / find_image
│ │ └── sources.py — 4 scrapers
│ ├── routers/
│ │ ├── news_router.py — /news /sources /status
│ │ └── collect_router.py — /collect-md
│ └── sockets/
│ └── events.py — connect / disconnect

### Frontend
├── frontend/
│ ├── index.html — HTML shell (55 บรรทัด)
│ └── static/
│ ├── app.css — all styles
│ ├── config.js — API_BASE, SOURCE_COLORS
│ ├── api.js — fetchNews, socket
│ ├── ui.js — render, DOM only
│ └── main.js — controller, state
```

---

## ✅ ความต้องการของระบบ

- Python **3.10** ขึ้นไป
- Google Chrome หรือ Chromium (สำหรับ Playwright)

---

## 📦 ติดตั้ง Dependencies

```bash
pip install requests beautifulsoup4 playwright fastapi trafilatura uvicorn socketio httpx openai pythainlp
```

จากนั้นติดตั้ง browser สำหรับ Playwright:

```bash
playwright install chromium
```

---

## 🚀 วิธีรัน

```bash
cd backend
python main.py
```

จากนั้นเปิดเบราว์เซอร์ไปที่:

```
http://localhost:5000
```

.env example
```
LLM_API = "your api key"
```
---

## ⚙️ ปรับค่าได้ใน `news_scraper.py`

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `INTERVAL_MINUTES` | `15` | ดึงข่าวใหม่ทุกกี่นาที |
| `MAX_ARTICLES_PER_SOURCE` | `10` | บทความสูงสุดต่อสำนัก |
| `SUMMARY_SENTENCES` | `3` | จำนวนประโยคใน summary |

---

## 📡 สำนักข่าวที่รองรับ

| สำนัก | URL |
|---|---|
| ThaiPBS | https://www.thaipbs.or.th/news |
| Bangkok Post | https://www.bangkokpost.com/thailand/general |
| Matichon | https://www.matichon.co.th/news |
| 101 World | https://www.the101.world |

---

## 📝 หมายเหตุ

- ครั้งแรกที่รันจะใช้เวลา **2-5 นาที** ในการดึงข่าวรอบแรก
- ไฟล์ `news_output.json` และ `seen_urls.json` จะถูกสร้างอัตโนมัติ ไม่ต้อง push ขึ้น git
