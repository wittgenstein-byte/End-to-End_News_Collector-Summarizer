# 📰 NEWSROOM — Thai News Aggregator & Intelligent Summarizer

ระบบรวบรวมข่าวสารภาษาไทยอัตโนมัติแบบเรียลไทม์จาก 14 สำนักข่าวชั้นนำ พร้อมระบบจัดหมวดหมู่อัจฉริยะ (3-Tier Classification Engine), ระบบติดตามประเด็นข่าวมหากาพย์และจัดอันดับเทรนด์ (Two-Layer Story Identification & Deterministic Trending), ระบบสรุปใจความสำคัญด้วย AI (LLM Executive Briefing) และเว็บแอปพลิเคชันแบบก้าวหน้า (Progressive Web App - PWA) ที่ปลอดภัยต่อลิขสิทธิ์และเคารพความเป็นส่วนตัว

---

## 🌟 จุดเด่นของระบบ (Key Highlights)

- 📡 **รวบรวมข่าวสารจาก 14 สำนักข่าวชั้นนำ:** ดึงข่าวต่อเนื่องทั้งผ่าน RSS Feed, HTTP Scraping และ Headless Browser (Playwright)
- 🧠 **ระบบจำแนกหมวดหมู่อัจฉริยะ 3 ระดับ (3-Tier Classification):** ตรวจจับรวดเร็วระดับเสี้ยววินาทีด้วย URL Priority (<0.1ms), กฎคำสำคัญทางภาษาศาสตร์ (NLP) และโมเดล Machine Learning (TF-IDF + SVM)
- 🧭 **ติดตามมหากาพย์ประเด็นข่าว (Two-Layer Story Identification):** จัดกลุ่มข่าวเรื่องเดียวกันข้ามวันและข้ามหมวดหมู่ด้วย Dense Vector Embeddings (WangchanBERTa 768-d) และ Named Entity Recognition (`thainer-v2`)
- 📊 **จัดอันดับเทรนด์ข่าวเชิงสถิติ (Deterministic Trending Engine):** คำนวณความร้อนแรงของประเด็นข่าวด้วย 6 มิติทางสถิติ (Volume, Burst Velocity, Outlet Diversity, Recency Decay, Novelty, Reader Telemetry) ปราศจาก LLM ในขั้นตอนคำนวณคะแนน โปร่งใสและตรวจสอบได้ (Explainable Scoring)
- ⚡ **สรุปเนื้อหาข่าวสารด้วย AI (Executive Briefing):** สังเคราะห์สาระสำคัญ (Key Takeaways), วิเคราะห์โทนข่าว (Sentiment) และจัดทำไทม์ไลน์เหตุการณ์ด้วย Gemini LLM พร้อมระบบ Fallback เมื่อ API ขัดข้อง
- 📱 **สถาปัตยกรรม PWA ปลอดภัยลิขสิทธิ์ (Copyright-Safe PWA):** ติดตั้งเป็นแอปบนมือถือและคอมพิวเตอร์ รองรับการอ่านออฟไลน์ และหลีกเลี่ยงการละเมิดลิขสิทธิ์รูปภาพด้วยภาพเวกเตอร์ Editorial Placeholder
- 🛡️ **สถาปัตยกรรมแคช 4 ระดับ (4-Layer Caching):** ประมวลผลรวดเร็วและประหยัดทรัพยากรด้วย Client Cache, Async TTLCache, Browser Snapshot Cache และ HTTP Conditional Request (ETag/304)
- 📋 **ระบบแบบประเมินโครงงาน (Project Evaluation System):** หน้า Landing Page สำหรับประเมินโครงงาน (`#/evaluation`), ปุ่มนำทางโดดเด่นสะดุดตาบน Header และระบบแจ้งเตือนชวนทำแบบประเมินผ่าน Google Forms หลังใช้งาน AI

---

## 🗂️ โครงสร้างโปรเจกต์ (Project Structure)

```
backend/
├── main.py                     — FastAPI application factory, middleware & Socket.IO mounting
├── config.py                   — ศูนย์กลางตั้งค่าคอนฟิก (Settings singleton via pydantic-settings)
├── .env / .env.example         — Environment variables (API keys, model checkpoints, parameters)
├── core/
│   ├── browser.py              — Playwright browser automation (Service + Local Fallback)
│   ├── constants.py            — ค่าคงที่ของระบบ และ HTTP Browser Headers
│   ├── fetcher_service.py      — HTML extraction & Markdown converter
│   └── socket_manager.py       — Socket.IO singleton manager สำหรับสตรีมมิ่งข่าวแบบเรียลไทม์
├── schemas/
│   ├── news_schema.py          — Pydantic models (ArticleRecord, NewsSummary, CollectRequest)
│   ├── story_schema.py         — Pydantic models (StoryRecord, TimelineEvent, StorySynthesis)
│   ├── trending_schema.py      — Pydantic models (TrendingStoryItem, TrendingScoreBreakdown)
│   ├── macro_event_schema.py   — Pydantic models (MacroEventRecord, TopicCluster)
│   └── event_evidence_schema.py — Pydantic models สำหรับตรวจสอบความสัมพันธ์ของหลักฐานข่าว
├── repo/
│   ├── news_repo.py            — ข้อมูลข่าวพื้นฐาน (FileNewsRepository / NewsRepositoryPort)
│   ├── story_repo.py           — ข้อมูลกลุ่มข่าวแบบต่อเนื่อง (FileStoryRepository / MongoDB)
│   ├── engagement_repo.py      — ข้อมูล Telemetry การมีส่วนร่วมของผู้ใช้ (คลิก, สรุป, บุ๊กมาร์ก)
│   ├── macro_event_repo.py     — การจัดเก็บกลุ่มเหตุการณ์ระดับมหภาค
│   └── sqlite_news_repo.py     — การจัดเก็บสำรองด้วย SQLite
├── routers/
│   ├── news_router.py          — API ข่าว: /api/news, /api/sources, /api/categories, /api/status
│   ├── story_router.py         — API ประเด็นข่าว: /api/stories, /api/stories/{id}, /api/storylines
│   ├── trending_router.py      — API เทรนด์: /api/trending/stories, /api/trending/score-breakdown
│   ├── collect_router.py       — API สรุปข่าว: /api/collect-md (LLM Summarization)
│   ├── monitoring_router.py    — API ตรวจสอบสถานะระบบ: /api/monitoring/health, /api/monitoring/metrics
│   └── macro_event_router.py   — API จัดการเหตุการณ์ระดับมหภาค
├── services/
│   ├── scraper_service.py      — Background loop ทำงานดึงข่าวรอบละ 15 นาที
│   ├── classifier_service.py   — เครื่องมือจัดหมวดหมู่อัจฉริยะ 3-Tier Multi-strategy Classifier
│   ├── story_service.py        — การจับคู่และรวมกลุ่มบทความข่าวแบบ Online Incremental
│   ├── trending_service.py     — การคำนวณคะแนนความร้อนแรงของประเด็นข่าวด้วย 6 มิติทางสถิติ
│   ├── story_presentation_service.py — สังเคราะห์หัวข้อข่าวและไทม์ไลน์ภาพรวมด้วย LLM
│   ├── summarizer_service.py   — บริการถอดใจความและสรุปบทความข่าวรายชิ้น
│   ├── entity_extractor.py     — สกัด Named Entities (PyThaiNLP thainer-v2)
│   └── browser_service.py      — จัดการ Playwright CDP sessions
├── scrapers/
│   ├── registry.py             — Decorator @register_source และแคตตาล็อกสำนักข่าว
│   ├── helpers.py              — HTML/RSS parser, ตัวดึงรูปภาพ และ Article Builder
│   └── sources.py              — สคริปต์สแครปข่าวสำหรับ 14 สำนักข่าว
├── model/
│   ├── tfidf_vectorizer.pkl    — TF-IDF Vectorizer สำหรับข้อความภาษาไทย
│   ├── svm_classifier.pkl      — Support Vector Machine Classifier
│   └── wangchanberta_classifier — Local Offline Embedding Checkpoint (WangchanBERTa)
└── tests/                      — ชุดทดสอบระบบครอบคลุมทั้ง Unit Tests และ Integration Tests

frontend/
├── index.html                  — หน้าเว็บหลักแบบ Single Page Application (SPA)
├── manifest.webmanifest        — Progressive Web App Manifest
├── sw.js                       — Service Worker สำหรับแคชและประมวลผลออฟไลน์
└── static/
    ├── app.css                 — สไตล์ชีต Editorial Theme และ Tailwind Utilities
    ├── config.js               — การตั้งค่าฝั่งผู้ใช้ (API Base, หมวดหมู่, สีสำนักข่าว, ลิงก์แบบประเมิน)
    ├── api.js                  — REST API Client และ Socket.IO Handlers
    ├── UI.js                   — จัดการ DOM, เรนเดอร์การ์ดข่าว, สรุป AI, ไทม์ไลน์ และแบบประเมิน
    └── main.js                 — State Manager, Hash Router (`#/`, `#/preview/`, `#/storyline/`, `#/evaluation`)

data/                           — ไดเรกทอรีจัดเก็บข้อมูลในเครื่อง (สร้างขึ้นอัตโนมัติ)
├── news_data.json              — ฐานข้อมูลบทความข่าว
├── stories_data.json           — ฐานข้อมูลกลุ่มเรื่องราวเหตุการณ์ (StoryRecords)
├── engagement_data.json        — ข้อมูล Telemetry การใช้งาน
└── collected_md/               — ไฟล์สรุปข่าวในรูปแบบ Markdown
```

---

## 🧠 ระบบจำแนกหมวดหมู่ข่าว (3-Tier Classification Engine)

1. **Tier 1: Fast-Path URL Priority (< 0.1ms)**
   - สกัดหมวดหมู่จาก URL path หรือ slug อัตโนมัติ (เช่น `/politics`, `/business`, `/sport`, `/tech`, `/foreign`, `/local` รวมถึง URL ภาษาไทยแบบ Percent-encoded)
   - หากเงื่อนไขตรงกับพจนานุกรมความมั่นใจสูง จะจัดหมวดหมู่ทันทีโดยไม่ต้องผ่าน NLP หรือ Machine Learning ประหยัดพลังงานประมวลผลสูงสุด
2. **Tier 2: Rule-based Domain Expert Scoring**
   - ตัดคำภาษาไทยด้วย PyThaiNLP และคำนวณคะแนนตามคีย์เวิร์ดบริบทเฉพาะด้านพร้อม Compound Rules แบบถ่วงน้ำหนัก ในกรณีที่ URL ไม่ระบุหมวด
3. **Tier 3: Machine Learning Model (TF-IDF + SVM)**
   - ใช้โมเดล Machine Learning ในการวิเคราะห์บริบทเนื้อหาอย่างละเอียดสำหรับหมวดหมู่ที่มีความคาบเกี่ยวกันสูง (เช่น การเมือง, เศรษฐกิจ, สังคม)

---

## 🧭 ระบบติดตามเรื่องราวและจัดอันดับเทรนด์ (Two-Layer Architecture)

### Layer 1: Persistent Online Story Identification
- **Online Incremental Clustering:** ข่าวแต่ละบทความที่ดึงเข้ามาใหม่จะถูกนำมาประเมินทันที (`StoryService.assign_article`) โดยไม่จำเป็นต้อง re-cluster ข่าวทั้งหมดใหม่
- **Semantic Vector Similarity:** สกัดเวกเตอร์ขนาด 768 มิติด้วย WangchanBERTa ทำ Cosine Similarity เทียบกับ Centroid ของประเด็นข่าว
- **Secondary Entity Confirmation Gate:** สกัด Named Entities (บุคคล, องค์กร, สถานที่) ด้วย PyThaiNLP `thainer-v2` เพื่อยืนยันความถูกต้องในกรณีค่าความคล้ายคลึงก้ำกึ่ง ($0.74 \le \text{sim} < 0.85$)
- **Non-Capping 72-Hour Candidate Window:** ค้นหาประเด็นข่าวที่มีความเคลื่อนไหวภายใน 72 ชั่วโมง ทำให้ประเด็นข่าวที่เกิดขึ้นต่อเนื่องเป็นสัปดาห์ (เช่น อุทกภัย, คดีความ) ถูกร้อยเรียงอยู่ภายใต้ `story_id` เดียวกันได้อย่างแม่นยำ
- **Centroid Exponential Moving Average (EMA, $\alpha=0.85$):** ปรับค่าเวกเตอร์แกนกลางของประเด็นข่าวอย่างราบรื่นตามความคืบหน้าของสถานการณ์

### Layer 2: Deterministic Trending Engine
จัดอันดับความร้อนแรงของประเด็นข่าวด้วย 6 มิติทางสถิติที่โปร่งใส ตรวจสอบได้ และปราศจาก LLM ในการคำนวณคะแนน:
- **Volume Score (25%):** จำนวนบทความข่าวที่รายงานในรอบ 24 ชั่วโมง ($\ln(1 + N_{\text{recent}})$)
- **Burst Velocity Score (30%):** อัตราการเพิ่มขึ้นอย่างรวดเร็วของข่าวเปรียบเทียบกับช่วงก่อนหน้า
- **Diversity Score (25%):** ความหลากหลายของสำนักข่าวที่รายงาน ($\sqrt{N_{\text{outlets}}}$) พร้อมระบบลดทอนคะแนนสำหรับข่าวคัดลอก (Syndication Discount)
- **Recency Decay (10%):** ลดทอนคะแนนตามกาลเวลาด้วย Exponential Half-Life Decay ($\tau = 12$ ชั่วโมง)
- **Novelty Score (5%):** ความแปลกใหม่ของประเด็นเมื่อเทียบกับประเด็นข่าวอื่น
- **Engagement Telemetry (5%):** สถิติการมีส่วนร่วมของผู้อ่านแบบไม่ระบุตัวตน (คลิก, สรุปเนื้อหา, บุ๊กมาร์ก)
- **Routine News Penalty ($0.25\times$):** ลดทอนคะแนนข่าวที่เป็นกิจวัตรประจำวัน (ผลสลากกินแบ่ง, รายงานสภาพอากาศ, ราคาน้ำมัน/ทองคำประจำวัน) ไม่ให้แย่งพื้นที่เทรนด์ข่าวสำคัญ

---

## 📡 สำนักข่าวที่รองรับ (14 สำนักข่าว)

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
| **PPTV HD 36** | `https://www.pptvhd36.com` | HTTP Scraping | ทั่วไป, ต่างประเทศ, กีฬา |
| **Techhub** | `https://www.techhub.in.th` | HTTP Scraping | เทคโนโลยี, ไอที, คอมพิวเตอร์ |

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

## 📱 สถาปัตยกรรม PWA, ความปลอดภัยลิขสิทธิ์ & แบบประเมินโครงงาน

### 1. Progressive Web App (PWA) Standalone
- **Web App Manifest (`manifest.webmanifest`)**: รองรับการติดตั้งเป็นแอปพลิเคชันแบบ Standalone ทั้งบน iOS และ Android
- **Service Worker (`sw.js`)**: ประมวลผลแบบออฟไลน์ด้วยกลยุทธ์ Cache-First สำหรับ App Shell และ Network-First พร้อม Cache Fallback สำหรับฟีดข่าว

### 2. นโยบายรูปภาพปลอดภัยลิขสิทธิ์ (Copyright-Safe Image Policy)
- หลีกเลี่ยงการทำสำเนา บันทึก หรือแคชไฟล์ภาพข่าวของสำนักข่าวภายนอกลงบนเซิร์ฟเวอร์
- แสดงผลด้วยภาพ Editorial SVG Placeholders ประจำหมวดหมู่เมื่อขาดการเชื่อมต่ออินเทอร์เน็ต

### 3. Excerpt Snippet Preview & Clean URL Launching
- อ่านบทคัดย่อข่าว 2-3 บรรทัดผ่าน SPA Hash Routing (`#/preview/{id}`) โดยไม่ต้องโหลดหน้าเว็บใหม่
- ปุ่มเปิดอ่านข่าวต้นฉบับจะทำการตัดพารามิเตอร์การตลาดและเครื่องมือติดตามทั้งหมด (`utm_*`, `fbclid`, `gclid`) เพื่อปกป้องความเป็นส่วนตัวของผู้ใช้

### 4. หน้า Landing Page & ระบบแบบประเมินโครงงาน (Project Evaluation)
- **Landing Page (`#/evaluation`):** หน้าเพจเฉพาะสำหรับสรุปภาพรวมความสามารถของโครงงาน และเชื่อมต่อไปยังแบบสอบถามออนไลน์
- **Header Action Button:** ปุ่มกดสีอำพันโดดเด่นพร้อมสัญญาณไฟกระพริบ (Live Beacon Ping) บริเวณซ้ายสุดของแถบเครื่องมือ
- **Smart Post-Summarization Prompt:** เมื่อผู้ใช้ทดลองกดฟังก์ชันสรุปข่าวด้วย AI ระบบจะเปิดกล่องข้อความเชิญชวนทำแบบประเมิน Google Forms โดยหากผู้ใช้กดเปิดลิงก์แล้ว ระบบจะจดจำค่าไว้ใน `localStorage` และไม่แสดงกล่องแจ้งเตือนซ้ำอีกอย่างถาวร

---

## ✅ ความต้องการของระบบ (Prerequisites)

- **Python**: 3.10 ขึ้นไป
- **Package Manager**: [uv](https://docs.astral.sh/uv/) (แนะนำเป็นอย่างยิ่ง)
- **Browser**: Chromium (ติดตั้งผ่าน Playwright)

---

## 📦 การติดตั้ง (Installation)

```bash
# 1. ติดตั้ง dependencies ทั้งหมดผ่าน uv
uv sync

# 2. ติดตั้ง Chromium สำหรับระบบสแครปข่าวของ Playwright
uv run playwright install chromium
```

---

## ⚙️ การตั้งค่าสภาพแวดล้อม (Environment Setup)

คัดลอกไฟล์ `backend/.env.example` เป็น `backend/.env` แล้วกำหนดค่าตามต้องการ:

```env
# LLM API (สำหรับสรุปใจความสำคัญและประมวลผลไทม์ไลน์)
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
# รันเซิร์ฟเวอร์หลัก (FastAPI + Socket.IO)
uv run python backend/main.py
```

เปิดเว็บเบราว์เซอร์ที่: **`http://localhost:5000`**

---

## 🧪 การทดสอบระบบ (Testing & Verification)

```bash
# รันชุดทดสอบทั้งหมด
uv run pytest -v

# ทดสอบระบบจัดหมวดหมู่อัจฉริยะ (URL Priority & ML Classifier)
uv run pytest backend/tests/test_classifier_service.py -v

# ทดสอบสำนักข่าวและการดึงข้อมูล (14 Outlets)
uv run pytest backend/tests/test_sources.py -v

# ทดสอบสถาปัตยกรรมแคช 4 ระดับ (4-Layer Caching Suite)
uv run pytest backend/tests/test_caching.py -v

# ทดสอบระบบจัดกลุ่มเรื่องราวและเทรนด์ (Story Identification & Trending Engine)
uv run pytest backend/tests/test_story_service.py backend/tests/test_trending_deterministic.py -v

# รัน Benchmark วัดความแม่นยำ Pairwise & B-cubed F1 ของ Story Identification
uv run python scripts/evaluate_stories.py

# รันรายงานตรวจสอบคุณภาพเทรนด์ข่าว (Trending Sanity Report)
uv run python scripts/trending_sanity_report.py
```

---

## 🔍 ตรวจสอบ Code Style & Type Safety

```bash
# ตรวจสอบ Code Style ด้วย Ruff
uv run ruff check backend/

# ตรวจสอบ Type Safety ด้วย MyPy
uv run mypy backend/ --ignore-missing-imports --explicit-package-bases
```

---

## 📄 ใบอนุญาตและการอ้างอิง

โปรเจกต์นี้พัฒนาขึ้นเพื่อการวิจัยและศึกษาทางวิชาการ (Educational & Academic Research) รวบรวมข่าวสารจากสำนักข่าวเพื่อการวิเคราะห์และสรุปผลเชิงสังเคราะห์ ไม่มีการละเมิดหรือทำซ้ำภาพถ่ายที่มีลิขสิทธิ์ และเคารพมาตรฐานการคุ้มครองข้อมูลส่วนบุคคล (PDPA)
