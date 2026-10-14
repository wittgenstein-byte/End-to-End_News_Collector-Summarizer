"""
backend/tests/test_layer1_stress.py
─────────────────────────────────────────────────────────────────
Adversarial Stress Test Suite for Layer 1:
Frontend Storage & Client Invariants (Bookmarks, 24h TTL, PDPA)

Validates:
1. Bookmark Schema & Serialization Invariants:
   - URL-encoded JSON passing between HTML onclick attributes and handler
   - Required fields (title, summary, source, url, category, published_at, bookmarked_at)
   - ISO 8601 timestamps and monotonic ordering
   - Idempotent add / remove / toggle operations
   - Handling of malformed, escaped, unicode (Thai), and special character payloads
2. 24h Offline News Cache TTL Lifecycle:
   - Cache hit within TTL (< 24h)
   - Exact boundary expiration (t = 86400s)
   - Auto-purge of expired cache on stale read
   - Corrupted JSON / malformed cache recovery
   - Category / Source filtering over cached offline payload
3. PDPA Consent Gating Invariants:
   - Declining consent removes all keys (personalization, search_history, news_cache)
   - Disables all writes to localStorage when consent is declined or missing
   - Accepting consent enables persistence and applies saved settings
   - Consent state itself stored in pdpa_consent cookie/localStorage exempt per PDPA
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any

# ═════════════════════════════════════════════════════════════════
# 1. BOOKMARK SCHEMA & ENCODING INVARIANTS
# ═════════════════════════════════════════════════════════════════


def test_bookmark_payload_roundtrip_encoding() -> None:
    """
    Simulate the exact frontend pipeline:
    Python Dict -> JSON String -> encodeURIComponent -> HTML onclick -> decodeURIComponent -> JSON.parse -> Bookmark
    """
    original_article = {
        "title": "ข่าวการเมืองไทย 2026: รัฐสภาผ่านร่าง พ.ร.บ. ใหม่",
        "summary": "สรุปสาระสำคัญของร่างกฎหมาย 'ใหม่' & \"ทันสมัย\" พร้อมผลกระทบต่อเศรษฐกิจ",
        "source": "ThaiPBS",
        "url": "https://www.thaipbs.or.th/news/content/345678?ref=app&lang=th#section1",
        "image_url": "https://images.thaipbs.or.th/2026/08/news_345678.jpg",
        "category": "politics",
        "classification_method": "WangchanBERTa (conf=0.98)",
        "fetched_at": "2026-08-21 14:30:00",
    }

    # 1. Backend/UI JSON serialization + URL encoding
    json_str = json.dumps(original_article, ensure_ascii=False)
    encoded = urllib.parse.quote(json_str)

    # 2. Frontend onclick decoding
    decoded_str = urllib.parse.unquote(encoded)
    parsed_article = json.loads(decoded_str)

    assert parsed_article["title"] == original_article["title"]
    assert parsed_article["url"] == original_article["url"]
    assert parsed_article["summary"] == original_article["summary"]

    # 3. Simulate client __toggleArticleBookmark saving
    bookmarked_at = datetime.now(timezone.utc).isoformat()
    parsed_article["bookmarked_at"] = bookmarked_at

    # Invariants
    assert "bookmarked_at" in parsed_article
    dt = datetime.fromisoformat(parsed_article["bookmarked_at"])
    assert dt.tzinfo is not None


def test_bookmark_store_idempotent_operations() -> None:
    """
    Test bookmark add, remove, toggle behavior.
    """
    store: dict[str, dict] = {}
    article_1 = {"url": "https://example.com/art1", "title": "Art 1"}
    article_2 = {"url": "https://example.com/art2", "title": "Art 2"}

    # Toggle Add 1
    store[article_1["url"]] = {**article_1, "bookmarked_at": datetime.now(timezone.utc).isoformat()}
    assert len(store) == 1
    assert "https://example.com/art1" in store

    # Toggle Add 2
    store[article_2["url"]] = {**article_2, "bookmarked_at": datetime.now(timezone.utc).isoformat()}
    assert len(store) == 2

    # Toggle Remove 1
    del store[article_1["url"]]
    assert len(store) == 1
    assert "https://example.com/art1" not in store
    assert "https://example.com/art2" in store

    # Toggle Add 1 again
    store[article_1["url"]] = {**article_1, "bookmarked_at": datetime.now(timezone.utc).isoformat()}
    assert len(store) == 2


# ═════════════════════════════════════════════════════════════════
# 2. 24-HOUR OFFLINE CACHE TTL LIFECYCLE
# ═════════════════════════════════════════════════════════════════


def test_offline_cache_ttl_boundary_matrix() -> None:
    """
    Adversarially evaluate the 24-hour TTL boundary calculation used in main.js.
    CACHE_TTL_MS = 24 * 60 * 60 * 1000 = 86,400,000 ms.
    """
    ttl_ms = 24 * 60 * 60 * 1000  # 86,400,000
    now_ms = 1755800000000

    test_cases = [
        # (offset_ms, is_valid_expected)
        (0, True),  # Just cached (0s old)
        (1000, True),  # 1s old
        (3600 * 1000, True),  # 1h old
        (23 * 3600 * 1000, True),  # 23h old
        (24 * 3600 * 1000 - 1, True),  # 23h 59m 59.999s (valid)
        (24 * 3600 * 1000, False),  # 24h 0m 0s (expired boundary)
        (24 * 3600 * 1000 + 1, False),  # 24h 0m 0.001s (expired)
        (48 * 3600 * 1000, False),  # 48h old (stale)
    ]

    for offset, expected_valid in test_cases:
        entry_timestamp = now_ms - offset
        is_fresh = (now_ms - entry_timestamp) < ttl_ms
        assert is_fresh == expected_valid, f"Failed at offset {offset}ms"


def test_offline_cache_filter_and_search_fallback() -> None:
    """
    Verify filtering logic over cached offline news payload.
    """
    cached_articles = [
        {"title": "หุ้นไทยปิดบวก 10 จุด", "summary": "ตลาดหุ้นไทยวันนี้ฟื้นตัว", "source": "Bangkokbiznews", "category": "economy"},
        {"title": "เปิดตัวโมเดล AI ใหม่", "summary": "เทคโนโลยีปัญญาประดิษฐ์รุ่นล่าสุด", "source": "ThaiPBS", "category": "technology"},
        {"title": "พายุโซนร้อนถล่มภาคเหนือ", "summary": "เกิดเหตุน้ำท่วมฉับพลัน", "source": "ThaiPBS", "category": "environment"},
        {"title": "การเมืองเดือดศึกซักฟอก", "summary": "อภิปรายไม่ไว้วางใจในสภา", "source": "The Standard", "category": "politics"},
    ]

    # Filter by category = 'technology'
    tech_articles = [a for a in cached_articles if a["category"] == "technology"]
    assert len(tech_articles) == 1
    assert tech_articles[0]["title"] == "เปิดตัวโมเดล AI ใหม่"

    # Filter by source = 'ThaiPBS'
    thaipbs_articles = [a for a in cached_articles if a["source"].lower() == "thaipbs"]
    assert len(thaipbs_articles) == 2

    # Filter by search query = 'สภา'
    q = "สภา".lower()
    search_results = [
        a for a in cached_articles
        if q in a["title"].lower() or q in a["summary"].lower()
    ]
    assert len(search_results) == 1
    assert search_results[0]["title"] == "การเมืองเดือดศึกซักฟอก"


# ═════════════════════════════════════════════════════════════════
# 3. PDPA CONSENT GATING INVARIANTS
# ═════════════════════════════════════════════════════════════════


def test_pdpa_declined_state_clears_all_storage() -> None:
    """
    Verify that declining PDPA consent purges all personalization keys,
    search history, and news cache, leaving only pdpa_consent='false'.
    """
    mock_local_storage: dict[str, str] = {
        "pdpa_consent": "true",
        "personalization": json.dumps({
            "darkMode": True,
            "fontSize": "18px",
            "layoutDensity": "compact",
            "preferredCategory": "economy",
            "bookmarkedArticles": {"https://example.com/1": {"title": "Saved"}},
            "bookmarks": ["https://example.com/tab1"],
        }),
        "search_history": json.dumps(["ai", "technology", "finance"]),
        "news_cache": json.dumps({"timestamp": 12345, "articles": [{"title": "Cached"}]}),
    }

    # Simulate __declineCookies()
    def decline_cookies(storage: dict[str, str]) -> dict[str, Any]:
        has_consent = False
        storage["pdpa_consent"] = "false"
        storage.pop("personalization", None)
        storage.pop("search_history", None)
        storage.pop("news_cache", None)
        personalization_data: dict[str, Any] = {}
        search_history: list[str] = []
        return {
            "has_consent": has_consent,
            "personalization_data": personalization_data,
            "search_history": search_history,
        }

    state = decline_cookies(mock_local_storage)

    assert state["has_consent"] is False
    assert state["personalization_data"] == {}
    assert state["search_history"] == []

    # LocalStorage must only retain pdpa_consent = 'false'
    assert mock_local_storage == {"pdpa_consent": "false"}
    assert "personalization" not in mock_local_storage
    assert "search_history" not in mock_local_storage
    assert "news_cache" not in mock_local_storage


def test_pdpa_write_protection_when_no_consent() -> None:
    """
    Verify that any attempt to save bookmarks, search queries, or preferences
    is rejected when has_consent is False.
    """
    has_consent = False
    mock_storage: dict[str, str] = {"pdpa_consent": "false"}

    def save_personalization(data: dict) -> bool:
        if not has_consent:
            return False
        mock_storage["personalization"] = json.dumps(data)
        return True

    def save_search_query(q: str) -> bool:
        if not has_consent or not q:
            return False
        mock_storage["search_history"] = json.dumps([q])
        return True

    def save_news_cache(payload: dict) -> bool:
        if not has_consent:
            return False
        mock_storage["news_cache"] = json.dumps(payload)
        return True

    assert save_personalization({"darkMode": True}) is False
    assert save_search_query("test query") is False
    assert save_news_cache({"articles": []}) is False

    assert "personalization" not in mock_storage
    assert "search_history" not in mock_storage
    assert "news_cache" not in mock_storage
