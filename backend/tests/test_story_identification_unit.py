"""
tests/test_story_identification_unit.py
─────────────────────────────────────────────────────────────────
Unit specifications verifying Phase 1 domain ontology and contracts:
  - Contract A: EventTimeEvidence interval gap, precision, ambiguity.
  - Contract B: URL canonicalization, cluster fingerprinting, synthesis cache key.
  - Domain records: StoryRecord, MacroEventRecord, and Trending response telemetry.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.core.url_utils import (
    canonicalize_url,
    compute_cluster_fingerprint,
    compute_synthesis_cache_key,
)
from backend.schemas.macro_event_schema import MacroEventRecord
from backend.schemas.story_schema import (
    EventTimeEvidence,
    StoryRecord,
    TypedEventAnchors,
)
from backend.schemas.trending_schema import (
    TrendingListResponse,
    TrendingStoryListResponse,
)


class TestContractAEventTimeEvidence:
    """Verify Contract A interval calculation and precision semantics."""

    def test_interval_gap_overlapping_intervals_return_zero(self) -> None:
        t1_start = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
        t1_end = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
        t2_start = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)
        t2_end = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)

        ev1 = EventTimeEvidence(start_utc=t1_start, end_utc=t1_end, precision="datetime", confidence="explicit")
        ev2 = EventTimeEvidence(start_utc=t2_start, end_utc=t2_end, precision="datetime", confidence="explicit")

        assert ev1.interval_gap_hours(ev2) == 0.0
        assert ev2.interval_gap_hours(ev1) == 0.0

    def test_interval_gap_disjoint_intervals(self) -> None:
        t1_start = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
        t1_end = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        # Gap is 3 hours: from 12:00 to 15:00
        t2_start = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
        t2_end = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)

        ev1 = EventTimeEvidence(start_utc=t1_start, end_utc=t1_end, precision="datetime", confidence="explicit")
        ev2 = EventTimeEvidence(start_utc=t2_start, end_utc=t2_end, precision="datetime", confidence="explicit")

        assert ev1.interval_gap_hours(ev2) == 3.0
        assert ev2.interval_gap_hours(ev1) == 3.0

    def test_interval_gap_missing_bounds_returns_none(self) -> None:
        ev1 = EventTimeEvidence(precision="none", confidence="none")
        ev2 = EventTimeEvidence(
            start_utc=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
            end_utc=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            precision="datetime",
            confidence="explicit",
        )

        assert ev1.interval_gap_hours(ev2) is None
        assert ev2.interval_gap_hours(ev1) is None

    def test_ambiguous_year_preservation(self) -> None:
        ev = EventTimeEvidence(
            start_utc=None,
            end_utc=None,
            precision="ambiguous",
            confidence="ambiguous",
            evidence_span="เมื่อวันที่ 20 ส.ค.",
        )
        assert ev.start_utc is None
        assert ev.end_utc is None
        assert ev.precision == "ambiguous"
        assert ev.confidence == "ambiguous"


class TestContractBUrlAndCacheKey:
    """Verify Contract B URL canonicalization, fingerprinting, and cache keys."""

    def test_canonicalize_url_tracking_removal_and_normalization(self) -> None:
        raw_url = "https://www.thaipbs.or.th/news/content/12345/?utm_source=facebook&utm_medium=cpc&fbclid=abc123xyz&topic=flood&ref=home#section"
        expected = "https://thaipbs.or.th/news/content/12345?topic=flood"
        assert canonicalize_url(raw_url) == expected

    def test_canonicalize_url_trailing_slash_and_port(self) -> None:
        raw_url = "http://www.example.com:80/article/sample-headline/"
        expected = "http://example.com/article/sample-headline"
        assert canonicalize_url(raw_url) == expected

    def test_canonicalize_url_empty_input(self) -> None:
        assert canonicalize_url("") == ""
        assert canonicalize_url("   ") == ""

    def test_compute_cluster_fingerprint_empty_guard(self) -> None:
        assert compute_cluster_fingerprint([]) == "fp_empty"
        assert compute_cluster_fingerprint(["", "  "]) == "fp_empty"

    def test_compute_cluster_fingerprint_deterministic_and_order_independent(self) -> None:
        urls1 = [
            "https://www.thaipbs.or.th/news/1",
            "https://www.thairath.co.th/news/2?utm_source=twitter",
        ]
        urls2 = [
            "https://thairath.co.th/news/2",
            "https://thaipbs.or.th/news/1/",
        ]
        fp1 = compute_cluster_fingerprint(urls1)
        fp2 = compute_cluster_fingerprint(urls2)

        assert fp1.startswith("fp_")
        assert len(fp1) == 19  # "fp_" + 16 hex chars
        assert fp1 == fp2

    def test_compute_synthesis_cache_key_invalidation(self) -> None:
        articles = [
            {"url": "https://thaipbs.or.th/1", "title": "Headline 1", "summary": "Summary 1"},
            {"url": "https://thairath.co.th/2", "title": "Headline 2", "summary": "Summary 2"},
        ]
        fp = compute_cluster_fingerprint([a["url"] for a in articles])

        key1 = compute_synthesis_cache_key("story_abc123", fp, articles, prompt_version="v4.0")
        assert key1.startswith("synth_")
        assert len(key1) == 30  # "synth_" + 24 hex chars

        # Key is stable on identical inputs
        key1_repeat = compute_synthesis_cache_key("story_abc123", fp, articles, prompt_version="v4.0")
        assert key1 == key1_repeat

        # Invalidation on summary edit
        modified_articles = [
            {"url": "https://thaipbs.or.th/1", "title": "Headline 1", "summary": "Updated Summary 1"},
            {"url": "https://thairath.co.th/2", "title": "Headline 2", "summary": "Summary 2"},
        ]
        key_modified = compute_synthesis_cache_key("story_abc123", fp, modified_articles, prompt_version="v4.0")
        assert key_modified != key1

        # Invalidation on prompt version upgrade
        key_v5 = compute_synthesis_cache_key("story_abc123", fp, articles, prompt_version="v5.0")
        assert key_v5 != key1


class TestDomainOntologyRecords:
    """Verify StoryRecord, MacroEventRecord, and Trending telemetry models."""

    def test_story_record_fingerprint_auto_sync(self) -> None:
        story = StoryRecord(
            title="เรือล่มภูเก็ต",
            article_urls=["https://www.thaipbs.or.th/news/101/"],
            category="disaster",
        )
        assert story.cluster_fingerprint != "fp_empty"
        assert story.cluster_fingerprint == compute_cluster_fingerprint(["https://thaipbs.or.th/news/101"])

        # Dynamic add article updates fingerprint
        story.add_article("https://www.thairath.co.th/news/202", "Thairath")
        assert story.cluster_fingerprint == compute_cluster_fingerprint([
            "https://thaipbs.or.th/news/101",
            "https://thairath.co.th/news/202",
        ])

    def test_story_record_v4_defaults(self) -> None:
        story = StoryRecord(title="ทดสอบ", category="society")
        assert story.verification_status == "verified"
        assert story.macro_association_status == "new_macro"
        assert story.conflict_type is None
        assert story.competing_candidate_ids == []
        assert isinstance(story.event_time, EventTimeEvidence)
        assert isinstance(story.typed_anchors, TypedEventAnchors)

    def test_macro_event_record_anchor_sync(self) -> None:
        macro = MacroEventRecord(title="น้ำท่วมน่าน 2569", storyline_anchor="น้ำท่วมน่าน")
        assert macro.named_crisis_anchor == "น้ำท่วมน่าน"
        assert macro.storyline_anchor == "น้ำท่วมน่าน"

    def test_trending_response_telemetry_defaults(self) -> None:
        resp = TrendingStoryListResponse(total=0, updated="2026-10-17 17:00:00")
        assert resp.unassigned_article_count == 0
        assert resp.pending_review_count == 0

        news_resp = TrendingListResponse(total=0, updated="2026-10-17 17:00:00")
        assert news_resp.unassigned_article_count == 0
        assert news_resp.pending_review_count == 0


class TestEntityExtractorAdditions:
    """Verify Contract A time parsing, typed anchors, and P0.1 syndication detection."""

    def test_extract_event_time_evidence_datetime(self) -> None:
        from backend.services.entity_extractor import extract_event_time_evidence

        text = "เกิดเหตุระเบิดเมื่อวันที่ 20 ส.ค. 2569 เวลา 14:30 น. ที่อำเภอเมือง"
        ev = extract_event_time_evidence(text)
        assert ev.precision == "datetime"
        assert ev.confidence == "explicit"
        assert ev.start_utc is not None
        assert ev.start_utc == ev.end_utc
        # 14:30 Bangkok (UTC+7) is 07:30 UTC
        assert ev.start_utc.year == 2026
        assert ev.start_utc.month == 8
        assert ev.start_utc.day == 20
        assert ev.start_utc.hour == 7
        assert ev.start_utc.minute == 30

    def test_extract_event_time_evidence_date_only(self) -> None:
        from backend.services.entity_extractor import extract_event_time_evidence

        text = "พบผู้รอดชีวิตเมื่อวันที่ 20 ส.ค. 2569 ที่ผ่านมา"
        ev = extract_event_time_evidence(text)
        assert ev.precision == "date"
        assert ev.confidence == "explicit"
        assert ev.start_utc is not None
        assert ev.end_utc is not None
        # 2026-08-20 00:00:00+07:00 -> 2026-08-19 17:00:00 UTC
        assert ev.start_utc.hour == 17
        assert ev.start_utc.day == 19
        # 2026-08-20 23:59:59+07:00 -> 2026-08-20 16:59:59 UTC
        assert ev.end_utc.hour == 16
        assert ev.end_utc.day == 20

    def test_extract_event_time_evidence_yearless_anchored_vs_ambiguous(self) -> None:
        from backend.services.entity_extractor import extract_event_time_evidence

        text = "เกิดเหตุเมื่อวันที่ 20 ส.ค. โดยมีรายงานด่วน"
        # Anchored against published_at in same month
        ev_anchored = extract_event_time_evidence(text, published_at="2026-08-21 05:00:00Z")
        assert ev_anchored.precision == "date"
        assert ev_anchored.start_utc is not None
        assert ev_anchored.start_utc.year == 2026

        # Missing published_at -> ambiguous
        ev_ambiguous = extract_event_time_evidence(text, published_at=None)
        assert ev_ambiguous.precision == "ambiguous"
        assert ev_ambiguous.confidence == "ambiguous"
        assert ev_ambiguous.start_utc is None

    def test_extract_typed_anchors_roles_vs_proper_names(self) -> None:
        from backend.services.entity_extractor import extract_typed_anchors

        text = "นายกรัฐมนตรี พร้อมด้วย ตำรวจ และ นายอนุทิน ลงพื้นที่ น้ำท่วมน่าน ตรวจสอบบ้านเรือน และ สั่งการ เยียวยา"
        anchors = extract_typed_anchors(text, entities=["นายกรัฐมนตรี", "ตำรวจ", "นายอนุทิน", "น้ำท่วมน่าน"])

        assert "นายกรัฐมนตรี" in anchors.actor_roles or "ตำรวจ" in anchors.actor_roles
        assert "นายอนุทิน" in anchors.actor_names
        assert "บ้านเรือน" in anchors.targets
        assert "สั่งการ" in anchors.actions or "เยียวยา" in anchors.actions
        assert anchors.storyline_anchor == "น้ำท่วมน่าน"

    def test_is_syndicated_duplicate_jaccard_and_wire_markers(self) -> None:
        from backend.services.entity_extractor import is_syndicated_duplicate

        art1 = {
            "title": "ด่วน เกิดอุบัติเหตุรถตู้พลิกคว่ำบนทางด่วน มีผู้บาดเจ็บ 5 ราย",
            "summary": "เกิดอุบัติเหตุรถตู้โดยสารพลิกคว่ำบนทางด่วนช่วงเช้าวันนี้ ส่งผลให้มีผู้บาดเจ็บ 5 ราย เจ้าหน้าที่กู้ภัยเร่งนำส่งโรงพยาบาล",
            "source": "ThaiPBS",
        }
        # Near verbatim republish from another outlet
        art2 = {
            "title": "ด่วน เกิดอุบัติเหตุรถตู้พลิกคว่ำบนทางด่วน บาดเจ็บ 5 ราย",
            "summary": "เกิดอุบัติเหตุรถตู้โดยสารพลิกคว่ำบนทางด่วนช่วงเช้าวันนี้ ส่งผลให้มีผู้บาดเจ็บ 5 ราย เจ้าหน้าที่กู้ภัยเร่งนำส่งโรงพยาบาล ที่มา: ThaiPBS",
            "source": "Thairath",
        }
        # Distinct independent article on different event
        art3 = {
            "title": "ราคาทองคำวันนี้พุ่งแรงต่อเนื่อง 200 บาท",
            "summary": "สมาคมค้าทองคำรายงานราคาทองวันนี้ปรับตัวสูงขึ้นทะลุแนวต้านสำคัญ นักลงทุนจับตาเศรษฐกิจสหรัฐ",
            "source": "BangkokPost",
        }

        assert is_syndicated_duplicate(art1, art2, cos_sim=0.995) is True
        assert is_syndicated_duplicate(art1, art3, cos_sim=0.25) is False

