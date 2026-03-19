"""
core/constants.py
─────────────────────────────────────────────────────────────────
SOLID  S — เก็บ constants ที่ใช้ร่วมกันระหว่าง modules
GRASP  Information Expert — รู้ว่า browser header ควรเป็นอะไร

เหตุผลที่แยกออกมา:
  - fetcher_service.py ใช้ BROWSER_HEADERS ดึง article content
  - scrapers/helpers.py ใช้ BROWSER_HEADERS ดึง article image/summary
  - ถ้าไม่แยก → ต้องแก้ 2 ที่เมื่อ User-Agent เปลี่ยน (DRY violation)
─────────────────────────────────────────────────────────────────
"""

BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
}

# คำที่บ่งบอกว่า Cloudflare บล็อกอยู่ (ใช้ร่วมกันทุก fetcher)
CLOUDFLARE_TELLS: frozenset[str] = frozenset({"Just a moment", "Enable JavaScript"})