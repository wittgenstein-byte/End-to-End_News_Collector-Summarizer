"""
scripts/preflight_test.py
─────────────────────────────────────────────────────────────────
สคริปต์ตรวจสอบความพร้อมก่อนขึ้น Production (Production Pre-flight Test)
ตรวจสอบ Backend Readyz, Trending Clustering, Browser Console Errors,
WebSocket Live Badge และ Cache-Control Headers

การใช้งาน:
    uv run python scripts/preflight_test.py
    uv run python scripts/preflight_test.py https://e2enews.wittensky.com
─────────────────────────────────────────────────────────────────
"""

import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import httpx
from playwright.sync_api import sync_playwright

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://e2enews.wittensky.com"


def test_backend_readyz():
    print(f"[1/4] ตรวจสอบสถานะความพร้อมของ Backend ({BASE_URL}/readyz)...")
    res = httpx.get(f"{BASE_URL}/readyz", timeout=10.0)
    assert res.status_code == 200, f"Readyz failed with status {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("status") == "ready", f"System not ready: {data}"
    print("  ✅ Backend Ready: Storage และ Playwright พร้อมใช้งาน")


def test_trending_api():
    print(f"[2/4] ตรวจสอบระบบประมวลผล AI & Trending ({BASE_URL}/api/news/trending)...")
    start = time.time()
    res = httpx.get(f"{BASE_URL}/api/news/trending?limit=3", timeout=15.0)
    duration = time.time() - start
    assert res.status_code == 200, f"Trending failed with status {res.status_code}"
    data = res.json()
    clusters = data.get("clusters") or data.get("trending") or []
    assert len(clusters) > 0, "No clusters in trending response"
    print(f"  ✅ Trending API พร้อม: พบ {len(clusters)} คลัสเตอร์ (ใช้เวลา {duration:.2f}s)")
    multi_article = [c for c in clusters if c.get("article_count", len(c.get("articles", []))) > 1]
    print(f"     📊 คลัสเตอร์ที่รวมกลุ่มข่าวหลายบทความ: {len(multi_article)} / {len(clusters)}")


def test_browser_e2e_and_socket():
    print(f"[3/4] ตรวจสอบหน้าบ้านด้วย Headless Browser & WebSocket ({BASE_URL})...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3500)

        assert len(page_errors) == 0, f"พบข้อผิดพลาดบน Console: {page_errors}"

        badge_text = page.locator("#ws-label").inner_text()
        assert badge_text == "LIVE", f"WebSocket ไม่เชื่อมต่อ! สถานะค้างที่: '{badge_text}' (คาดหวัง 'LIVE')"
        print(f"  ✅ หน้าบ้านสมบูรณ์: ไม่มี Console Error และสถานะ Real-time เป็น '{badge_text}'")
        browser.close()


def test_static_cache_headers():
    print(f"[4/4] ตรวจสอบ Headers ป้องกันแคชเก่า ({BASE_URL}/frontend/static/main.js)...")
    res = httpx.get(f"{BASE_URL}/frontend/static/main.js", timeout=5.0)
    cc = res.headers.get("cache-control", "")
    assert "no-cache" in cc or "must-revalidate" in cc, f"Cache-Control header ไม่ถูกต้อง: {cc}"
    print("  ✅ Static Cache Control ถูกต้อง ป้องกันการเกิด Stale Cache")


if __name__ == "__main__":
    print("=" * 60)
    print(f"🚀 เริ่มการรัน Pre-flight Production Test: {BASE_URL}")
    print("=" * 60)
    try:
        test_backend_readyz()
        test_trending_api()
        test_browser_e2e_and_socket()
        test_static_cache_headers()
        print("=" * 60)
        print("🎉 ผลการทดสอบ: ผ่านทุกข้อกำหนด (READY FOR PRODUCTION)")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ ข้อกำหนดไม่ผ่าน: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 เกิดข้อผิดพลาดร้ายแรงระหว่างทดสอบ: {e}")
        sys.exit(1)
