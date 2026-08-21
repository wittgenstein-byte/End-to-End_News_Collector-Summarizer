# 📰 NEWSROOM — Thai News Aggregator & Summarizer

ระบบดึงข่าวอัตโนมัติ จัดหมวดหมู่อัจฉริยะ (Multi-tier Classification + Fast-Path URL Priority) และสรุปเนื้อหาข่าวจาก 12 สำนักข่าวชั้นนำในประเทศไทย แสดงผลแบบ Real-time บนเว็บด้วย FastAPI และ Socket.IO

---

## 🗂️ โครงสร้างโปรเจกต์

```
backend/
├── main.py              — FastAPI app factory & Socket.IO mounting
├── config.py            — Settings (env vars, paths, defaults)
├── .env / .env.example  — API keys, adjustable params
├── core/
│   ├── browser.py       — Playwright fetcher (Service + Local Fallback)
│   ├── constants.py     — BROWSER_HEADERS, constants
│   ├── fetcher_service.py — HTML to Markdown extraction
│   └── socket_manager.py — Socket.IO singleton manager
├── schemas/
│   └── news_schema.py   — Pydantic models (ArticleRecord, NewsSummary, CollectRequest)
├── repo/
│   └── news_repo.py     — JSON persistence (NewsRepositoryPort)
├── routers/
│   ├── news_router.py   — Endpoints: /api/news, /api/sources, /api/categories, /api/status
│   └── collect_router.py — Endpoint: /api/collect-md (LLM Summarization)
├── services/
│   ├── scraper_service.py    — Background loop for periodic scraping
│   ├── summarizer_service.py — LLM summarizer service
│   └── classifier_service.py — 3-Tier Multi-strategy Category Classifier
├── scrapers/
│   ├── registry.py      — @register_source decorator & SOURCES collection
│   ├── helpers.py       — HTML/RSS parsing, image, URL, article builder
│   └── sources.py       — 12 news source scrapers
├── model/
│   ├── tfidf_vectorizer.pkl — TF-IDF text vectorizer
│   └── svm_classifier.pkl   — Pre-trained SVM model for category classification
├── tests/
│   ├── conftest.py                — Test configuration & path setup
│   ├── test_classifier_service.py — URL Priority & classification test suite
│   └── test_sources.py            — News sources registration test suite
└── sockets/
    └── events.py        — WebSocket event handlers

frontend/
├── index.html
├── package.json
└── static/
    ├── app.css          — Styles & CSS variables
    ├── config.js        — API_BASE, CATEGORIES, SOURCE_COLORS
    ├── api.js           — REST & Socket.IO client helpers
    ├── UI.js            — Pure DOM manipulation & UI rendering
    └── main.js          — Application controller & state management

data/                    — Runtime generated directory
├── news_data.json       — Persisted news articles
└── collected_md/        — Downloaded Markdown files
```

---

## 🧠 ระบบจำแนกหมวดหมู่ข่าว (3-Tier Classification Engine)

1. **Tier 1: Fast-Path URL Priority (< 0.1ms)**
   - ตรวจจับหมวดหมู่จาก URL path / slug อัตโนมัติ (เช่น `/politics`, `/business`, `/sport`, `/tech`, `/foreign`, `/local` รวมถึง URL ภาษาไทยแบบ Percent-encoded)
   - หากตรงกับเงื่อนไข จะจัดหมวดหมู่ทันทีโดยไม่ต้องผ่านกระบวนการ NLP หรือ Machine Learning ประหยัดทรัพยากรและเร็วที่สุด
2. **Tier 2: Rule-based Domain Expert Scoring**
   - ตัดคำด้วย PyThaiNLP และคำนวณคะแนน Keyword + Compound Rules แบบถ่วงน้ำหนัก สำหรับกรณีที่ URL ไม่ระบุหมวด
3. **Tier 3: Machine Learning Model (TF-IDF + SVM)**
   - ใช้โมเดล Machine Learning ในการวิเคราะห์บริบทเชิงลึกสำหรับหมวดที่มีความคาบเกี่ยวสูง (การเมือง, เศรษฐกิจ, สังคม)

---

## 📡 สำนักข่าวที่รองรับ (12 สำนักข่าว)

| สำนักข่าว | Base URL | รูปแบบการดึงข้อมูล | หมวดหมู่หลักผ่าน URL Priority |
| :--- | :--- | :--- | :--- |
| **ไทยรัฐ (Thairath)** | `https://www.thairath.co.th` | RSS Feed | การเมือง, เศรษฐกิจ, ต่างประเทศ, ท้องถิ่น |
| **ไทยโพสต์ (Thai Post)** | `https://www.thaipost.net` | RSS Feed | การเมือง, เศรษฐกิจ, ทั่วไป |
| **มติชน (Matichon)** | `https://www.matichon.co.th` | RSS Feed | การเมือง, เศรษฐกิจ, บันเทิง, กีฬา, ต่างประเทศ |
| **เดลินิวส์ (Daily News)** | `https://www.dailynews.co.th` | HTTP Scraping | ทั่วไป, อาชญากรรม, การเมือง, กีฬา |
| **ข่าวสด (Khaosod)** | `https://www.khaosod.co.th` | RSS Feed (กรอง EN ออก) | การเมือง, กีฬา, บันเทิง, รอบโลก |
| **The Standard** | `https://thestandard.co` | RSS Feed | การเมือง, ธุรกิจ, เทคโนโลยี, สิ่งแวดล้อม |
| **101 World (The 101 World)** | `https://www.the101.world` | RSS + Playwright Fallback | สังคม, การเมือง, ความคิดเห็น |
| **ThaiPBS** | `https://www.thaipbs.or.th` | HTTP Scraping | การเมือง, เศรษฐกิจ, กีฬา, วิทยาศาสตร์ |
| **Bangkok Post** | `https://www.bangkokpost.com` | HTTP Scraping | Politics, Business, Sports, Tech, World |
| **คมชัดลึก (Komchadluek)** | `https://www.komchadluek.net` | Playwright Browser Fetch | กีฬา, บันเทิง, การเมือง, อาชญากรรม |
| **เนชั่นออนไลน์ (Nation Online)** | `https://www.nationtv.tv` | HTTP Scraping | สังคม, กีฬา, การเมือง |
| **กรุงเทพธุรกิจ (Bangkokbiznews)** | `https://www.bangkokbiznews.com` | HTTP Scraping | ธุรกิจ, การเงิน, เทคโนโลยี, ตลาดหุ้น |

---

## 🏷️ หมวดหมู่ข่าว (Categories)

- 🏛️ **politics** (การเมือง)
- 📈 **economy** (เศรษฐกิจ / ธุรกิจ / การเงิน)
- 💻 **technology** (เทคโนโลยี / ไอที / AI)
- 💊 **health** (สุขภาพ / สาธารณสุข)
- 🌿 **environment** (สิ่งแวดล้อม / สภาพภูมิอากาศ)
- 👥 **society** (สังคม / คุณภาพชีวิต / การศึกษา)
- ⚽ **sports** (กีฬา / ฟุตบอล)
- 🎬 **entertainment** (บันเทิง / ดารา / ภาพยนตร์)
- 🌍 **world** (ต่างประเทศ / รอบโลก)

---

## ✅ ความต้องการของระบบ

- **Python**: 3.10 ขึ้นไป
- **Package Manager**: [uv](https://docs.astral.sh/uv/) (แนะนำ)
- **Browser**: Chromium (ติดตั้งผ่าน Playwright)

---

## 📦 การติดตั้ง (Installation)

```bash
# ติดตั้ง dependencies ผ่าน uv
uv sync

# ติดตั้ง Chromium สำหรับ Playwright
uv run playwright install chromium
```

---

## ⚙️ Environment Setup

คัดลอก `backend/.env.example` เป็น `backend/.env` แล้วกำหนดค่าตามต้องการ:

```env
# LLM (สำหรับสรุปข่าวใน /api/collect-md)
LLM_API=your_api_key_here
LLM_BASE_URL=https://gen.ai.kku.ac.th/api/v1
LLM_MODEL=gemini-3.1-flash-lite-preview
LLM_TEMPERATURE=0.3

# Scraper Settings
INTERVAL_MINUTES=15
MAX_ARTICLES_PER_SOURCE=10
SUMMARY_SENTENCES=3
PAGE_SIZE=20

# Server
HOST=0.0.0.0
PORT=5000
```

---

## 🚀 วิธีรันระบบ (Run Server)

```bash
# รัน backend server (FastAPI + Socket.IO)
uv run python backend/main.py
```

เปิดเบราว์เซอร์ที่: **`http://localhost:5000`**

---

## 🧪 การทดสอบ (Testing)

```bash
# รันชุดทดสอบทั้งหมด
uv run pytest -v

# รันเฉพาะทดสอบ URL Priority และ Classifier
uv run pytest backend/tests/test_classifier_service.py -v

# รันเฉพาะทดสอบการลงทะเบียนของสำนักข่าว
uv run pytest backend/tests/test_sources.py -v
```

---

## 🔍 ตรวจสอบ Code Style & Type Safety

```bash
# Linting ด้วย Ruff
uv run ruff check backend/

# Type Checking ด้วย MyPy
uv run mypy backend/ --ignore-missing-imports --explicit-package-bases
```

---

## 📝 หมายเหตุ

- โฟลเดอร์ `data/` จะถูกสร้างขึ้นอัตโนมัติเมื่อรันระบบ เพื่อเก็บข้อมูลข่าว (`news_data.json`) และไฟล์ Markdown ที่ดาวน์โหลดมา
- ระบบมีการบันทึก Seen URLs เพื่อป้องกันการดึงข่าวซ้ำซ้อนในแต่ละรอบ
- ศึกษารายละเอียดแนวทางการเขียนโค้ดและ SOLID / GRASP architecture ได้ใน `AGENTS.md`

