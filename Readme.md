# 📰 NEWSROOM — Thai News Aggregator

ระบบดึงข่าวอัตโนมัติ และสรุปจากหลายสำนักข่าวไทย แสดงผลบนเว็บแบบ Real-time

---

## 🗂️ โครงสร้างไฟล์

```
project/
├── backend
|    └── server.py
|    └── news_scraper.py
|    └── jina.py
├── frontend
|    └── index.html
|    └── app.js
├── README.md
└── .gitignore
```

---

## ✅ ความต้องการของระบบ

- Python **3.10** ขึ้นไป
- Google Chrome หรือ Chromium (สำหรับ Playwright)

---

## 📦 ติดตั้ง Dependencies

```bash
pip install requests beautifulsoup4 playwright fastapi trafilatura uvicorn socketio httpx openai
```

จากนั้นติดตั้ง browser สำหรับ Playwright:

```bash
playwright install chromium
```

---

## 🚀 วิธีรัน

```bash
python server.py
```

จากนั้นเปิดเบราว์เซอร์ไปที่:

```
http://localhost:5000
```

.env exxample
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
