"""
backend/tests/test_issue_explorer.py
─────────────────────────────────────────────────────────────────
Test suite for Issue Explorer (TC-08 to TC-13):
- TC-08: Query Parser & SQL injection safety
- TC-09: Read-Only SQLite engine guarantee (mode=ro)
- TC-10: Deterministic clustering calibration regression
- TC-11: Outlier and false-positive filter (e.g. Gaston tennis)
- TC-12: Packaging integrity (Dockerfile & Tailwind configs)
- TC-13: API Contract, Rate Limiting & Kill Switch
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.issue_explorer.analyzer import analyze_issue
from backend.issue_explorer.query_parser import escape_like, parse_query
from backend.issue_explorer.source import SqliteReadOnlyArticleSource
from backend.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ── TC-08: Query Parser & SQL Safety ──────────────────────────────
def test_tc08_query_parser_basic_and_sql() -> None:
    # 1. Basic AND
    pq = parse_query("สตง ไทยพีบีเอส")
    assert len(pq.groups) == 2
    assert pq.groups[0] == ("สตง",)
    assert pq.groups[1] == ("ไทยพีบีเอส",)

    # 2. OR pipe syntax
    pq_or = parse_query("สตง | คตง")
    assert len(pq_or.groups) == 1
    assert pq_or.groups[0] == ("สตง", "คตง")

    # 3. Exclude syntax
    pq_ex = parse_query("สตง -กีฬา")
    assert len(pq_ex.groups) == 1
    assert pq_ex.groups[0] == ("สตง",)
    assert pq_ex.excludes == ("กีฬา",)

    # 4. Quoted phrase
    pq_phrase = parse_query('"ตึก สตง. ถล่ม" ข่าว')
    assert len(pq_phrase.groups) == 2
    assert pq_phrase.groups[0] == ("ตึก สตง. ถล่ม",)
    assert pq_phrase.groups[1] == ("ข่าว",)

    # 5. Parameterized SQL safety
    sql, params = pq.to_sql(fields=["title", "summary"])
    assert sql.count("?") == len(params)
    assert "LIKE ? ESCAPE '\\'" in sql
    assert "%สตง%" in params
    assert "%ไทยพีบีเอส%" in params

    # 6. Injection attempt test
    malicious = "'; DROP TABLE articles; --"
    pq_mal = parse_query(malicious)
    sql_mal, params_mal = pq_mal.to_sql(fields=["title"])
    assert "DROP TABLE" not in sql_mal
    assert any("DROP" in p for p in params_mal) and any("TABLE" in p for p in params_mal)

    # 7. Wildcard escaping
    assert escape_like("100%_bonus\\test") == "100\\%\\_bonus\\\\test"


# ── TC-09: Read-Only SQLite Guarantee ─────────────────────────────
def test_tc09_readonly_sqlite_guarantee(tmp_path: Path) -> None:
    db_file = tmp_path / "test_ro.db"
    conn = sqlite3.connect(str(db_file))
    with conn:
        conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, fetched_at TEXT);")
        conn.execute("INSERT INTO articles (id, title, fetched_at) VALUES (1, 'หัวข้อทดสอบ', '2026-10-16 10:00:00');")
    conn.close()

    source = SqliteReadOnlyArticleSource(db_file)
    ro_conn = source._get_connection()

    # Reading should succeed
    rows = ro_conn.execute("SELECT COUNT(*) FROM articles;").fetchone()
    assert rows[0] == 1

    # Attempting to write must fail with OperationalError
    with pytest.raises(sqlite3.OperationalError, match=r"readonly|attempt to write a readonly database"):
        ro_conn.execute("INSERT INTO articles (id, title, fetched_at) VALUES (2, 'เขียนเพิ่ม', '2026-10-16 11:00:00');")

    source.close()


# ── TC-10 & TC-11: Clustering Calibration & Outlier Detection ─────
def test_tc10_and_tc11_clustering_and_outlier_filter() -> None:
    # 39 verified STG articles + 1 outlier tennis article
    stg_fixture = [
        {"id": 1, "title": "สตง. แจงไทม์ไลน์สอบคดีตึกถล่ม ยืนยันตรวจสอบก่อนสื่อนำเสนอ", "summary": "สำนักงานการตรวจเงินแผ่นดิน ชี้แจงลำดับเหตุการณ์กรณีตึกถล่ม", "source": "The Standard", "category": "politics", "fetched_at": "2026-10-14 07:49:27"},
        {"id": 2, "title": "สตง. แจงคดีตึกถล่ม เร่งยกเลิกสัญญา เตรียมคืนที่ให้การรถไฟฯ", "summary": "สตง.แจงความคืบหน้าปมตึกถล่ม เร่งยกเลิกสัญญาเรียกเงินคืน", "source": "Matichon", "category": "politics", "fetched_at": "2026-10-14 08:56:01"},
        {"id": 3, "title": "โฆษก สตง. รับ! ตึกถล่มเป็นบาดแผลของ สตง. ตลอดชีวิต", "summary": "โฆษก สตง. วอนสังคมแยกเรื่องตึกถล่ม ออกจากภารกิจตรวจสอบเงินแผ่นดิน", "source": "PPTV HD 36", "category": "society", "fetched_at": "2026-10-14 09:20:08"},
        {"id": 4, "title": "สตง.อัปเดตคดีตึกถล่ม ส่งหลักฐานให้ ป.ป.ช.-ฟ้องแพ่งเรียก 500 ล้าน", "summary": "ชี้แจงความคืบหน้าการดำเนินการทางกฎหมาย กรณีอาคาร สตง. พังถล่มช่วงแผ่นดินไหว", "source": "Bangkokbiznews", "category": "politics", "fetched_at": "2026-10-14 10:30:20"},
        {"id": 5, "title": "ตึก สตง. ถล่ม คดีไปถึงไหน? เปิดไทม์ไลน์ส่งฟ้อง 23 ราย ย้ำคดียังไม่สิ้นสุด", "summary": "เปิดไทม์ไลน์คดีตึก สตง. ถล่ม หลังเหตุแผ่นดินไหว", "source": "PPTV HD 36", "category": "politics", "fetched_at": "2026-10-16 06:22:26"},
        {"id": 6, "title": "สตง. แถลงผลสอบ ‘ไทยพีบีเอส’ ชี้เบิกจ่ายไร้ระเบียบรองรับ เสียหายกว่า 85 ล้านบาท", "summary": "แถลงผลการตรวจสอบการใช้จ่ายเงิน ชี้จ้างผลิตรายการไร้ระเบียบ", "source": "The Standard", "category": "politics", "fetched_at": "2026-10-14 07:07:59"},
        {"id": 7, "title": "สตง. ฟัน ไทยพีบีเอส ใช้งบมีปัญหา จ้างผลิต ขัด พ.ร.บ.-ไร้ระเบียบ", "summary": "พบปัญหาประสิทธิภาพการดำเนินงาน การจ้างผลิตรายการขัด พ.ร.บ.จัดซื้อจัดจ้าง", "source": "Nation Online", "category": "economy", "fetched_at": "2026-10-14 07:09:50"},
        {"id": 8, "title": "Thai PBS แถลงโต้ สตง. ย้ำความเป็นอิสระ ต้องไม่มีแทรกแซง", "summary": "ผู้บริหารไทยพีบีเอส แถลงโต้ผลตรวจสอบ ยันไร้ทุจริต", "source": "Matichon", "category": "politics", "fetched_at": "2026-10-14 10:18:40"},
        {"id": 9, "title": "Thai PBS แจงพัลวัน จ้างบริษัทร่วมผลิต-พิธีกรแพง ข้องใจสตง.รีบสอบช่วงประชาพิจารณ์", "summary": "แจงจ้างพิธีกรราคาสูงเพื่อเป็นแม่เหล็กดึงคนดู", "source": "Khaosod", "category": "technology", "fetched_at": "2026-10-14 10:18:47"},
        {"id": 10, "title": "การดี บุก สตง. ยื่นสอบ TH-AI Passport 1.6 พันล้าน", "summary": "ยื่นหนังสือถึงผู้ว่าการตรวจเงินแผ่นดิน ตรวจสอบข้อเท็จจริงความโปร่งใส", "source": "Khaosod", "category": "politics", "fetched_at": "2026-09-21 05:53:37"},
        {"id": 11, "title": "สมชัย เปิดภาพ ฐิติเชฏฐ์ ถือซองเงิน 3 แสนเข้าสตง. ถาม ป.ป.ช. ผ่านมา 3 ปีคดีเงียบ", "summary": "แฉภาพวงจรปิดหิ้วเงิน 3 แสนบาท วิ่งเต้นตำแหน่งใน สตง.", "source": "Daily News", "category": "politics", "fetched_at": "2026-08-31 05:48:20"},
        # 1 Outlier item (Tennis player Gaston):
        {"id": 8006, "title": "เคี้ยวกระจาย! ‘เมดเวเดฟ’ พึ่งหมากฝรั่ง 12 ชิ้น ชนะ อูโก กาสตง ฝรั่งเศส ยูเอส โอเพน", "summary": "ดานิอิล เมดเวเดฟ นักเทนนิสชาวรัสเซีย เอาชนะ อูโก กาสตง คว้าชัย 3 เซตรวด", "source": "Khaosod", "category": "sports", "fetched_at": "2026-08-31 09:58:42"},
    ]

    result = analyze_issue(
        raw_articles=stg_fixture,
        query_terms=["สตง"],
        expanded_terms=["สตง", "สตง.", "สำนักงานการตรวจเงินแผ่นดิน"],
        cluster_distance_threshold=0.85,
    )

    # 1. TC-10: Clusters should be well formed
    clusters = result["clusters"]
    assert len(clusters) >= 2, f"Expected multiple distinct clusters, got {len(clusters)}"

    # 2. TC-11: Outlier detection
    outliers = result["possibly_unrelated"]
    outlier_ids = [u.id for u in outliers]
    assert 8006 in outlier_ids, f"Tennis article 8006 should be flagged in possibly_unrelated: {outliers}"


# ── TC-12: Packaging Integrity ────────────────────────────────────
def test_tc12_packaging_integrity() -> None:
    root_dir = Path(__file__).resolve().parent.parent.parent

    # Check Dockerfile includes issues.html
    dockerfile = root_dir / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile must exist"
    docker_content = dockerfile.read_text(encoding="utf-8")
    assert "issues.html" in docker_content, "Dockerfile must include issues.html in COPY statement"

    # Check tailwind.config.js includes issues.html
    tailwind_cfg = root_dir / "frontend" / "tailwind.config.js"
    assert tailwind_cfg.exists(), "tailwind.config.js must exist"
    tw_content = tailwind_cfg.read_text(encoding="utf-8")
    assert "issues.html" in tw_content, "tailwind.config.js must include issues.html in content array"


# ── TC-13: API Contract, Rate Limiting & Kill Switch ──────────────
def test_tc13_api_contract_and_rate_limit(client: TestClient) -> None:
    # 1. Health endpoint
    res_health = client.get("/api/issues/health")
    assert res_health.status_code == 200
    assert res_health.json()["readonly"] is True

    # 2. Search endpoint with empty query
    res_empty = client.get("/api/issues/search?q=")
    assert res_empty.status_code == 422

    # 3. Valid search endpoint
    res_valid = client.get("/api/issues/search?q=สตง")
    assert res_valid.status_code == 200
    body = res_valid.json()
    assert "clusters" in body
    assert "articles" in body
    assert "stats" in body
    assert "timeline" in body

    # 4. Rate limit check (30 requests/min limit)
    # Fire rapid requests from an isolated mock IP
    headers = {"CF-Connecting-IP": "198.51.100.99"}
    got_429 = False
    for _ in range(35):
        r = client.get("/api/issues/search?q=สตง", headers=headers)
        if r.status_code == 429:
            got_429 = True
            break
    assert got_429, "Expected 429 Too Many Requests after exceeding 30 requests"

    # 5. Kill switch test: when disabled, route returns 404
    with patch.object(settings, "issue_explorer_enabled", False):
        res_page = client.get("/issues")
        assert res_page.status_code == 404
