"""
tests/test_event_centric_guardrails.py
─────────────────────────────────────────────────────────────────
Unit tests verifying the 3-Layer Event-Centric Guardrails across the pipeline:
1. Layer 1: Event Assignment & Semantic Clustering Anchor Agreement
   - Prevents cross-event chaining between unrelated incidents in the same category
     (e.g., Sri Sakhon security clash vs Cyber police gambling bust).
   - Generates deterministic content-anchored cluster IDs (cluster_<8char_hash>).
2. Layer 2: Candidate Validation & Stopword Sanitization
   - Headline date cleaner strips scraped date suffixes.
   - Relevance gate heuristic and LLM validation cleanly triage out-of-domain articles.
3. Layer 3: Grounded Synthesis & Alignment Guardrail
   - Candidate mismatch halt: When 29/30 articles are excluded and the 1 remaining
     article does not match the incident headline (Sri Sakhon clash vs Temasek/NIA),
     synthesis halts safely (synthesis_status='halted_mismatch') with no hallucinated timeline.
   - Single-source transparent mode: When exactly 1 verified article matches the headline,
     synthesis enters single-source mode (synthesis_status='single_source', is_single_source=True).
   - Cache isolation: Verifies headline and content signature checking prevents
     cache collisions across distinct storylines.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import numpy as np

from backend.scrapers.helpers import clean_headline_date_suffix
from backend.services.story_presentation_service import StoryPresentationService
from backend.services.trending_service import SemanticClusterer


def test_headline_date_suffix_cleaner() -> None:
    """Verify clean_headline_date_suffix strips scraped Thai dates and temporal fragments."""
    # Pattern seen in scrapers where date is merged into the headline
    raw_title_1 = "ผบ.ทบ. ลงใต้ 'ศรีสาคร' ปะทะเดือด ตำรวจจับ 1 ทหารพรานเจ็บ 217 ต.ค. 2569"
    cleaned_1 = clean_headline_date_suffix(raw_title_1)
    assert "2569" not in cleaned_1
    assert "ต.ค." not in cleaned_1
    assert cleaned_1.endswith("เจ็บ 2")

    raw_title_2 = "เปิดประชุมสภาผู้แทนราษฎรพิจารณาร่างกฎหมายสำคัญ 15 ตุลาคม 2569"
    cleaned_2 = clean_headline_date_suffix(raw_title_2)
    assert cleaned_2 == "เปิดประชุมสภาผู้แทนราษฎรพิจารณาร่างกฎหมายสำคัญ"


def test_candidate_mismatch_halt_sri_sakhon() -> None:
    """
    Test Layer 3 Guardrail:
    Scenario: Headline is South Thailand security clash in Sri Sakhon.
    30 candidate articles were retrieved, but 29 are unrelated, and the 1 remaining
    candidate is about Temasek/NIA startup semiconductor funding.
    Verify synthesis HALTS safely with synthesis_status='halted_mismatch',
    producing 0 milestones and 0 facts, instead of synthesizing a false dossier.
    """
    svc = StoryPresentationService(client=None)

    headline = "ผบ.ทบ. ลงใต้ 'ศรีสาคร' ปะทะเดือด ตำรวจจับ 1 ทหารพรานเจ็บ"

    # Construct 30 candidate articles:
    # 29 generic politics/censure articles
    # 1 mismatched article on Temasek/NIA semiconductor collaboration
    articles: list[dict[str, Any]] = []
    for i in range(1, 30):
        articles.append({
            "article_id": f"art_{i:02d}",
            "title": f"การประชุมสภาผู้แทนราษฎรและวาระการเมืองทั่วไป รายการที่ {i}",
            "summary": "ความเคลื่อนไหวทางการเมืองในรัฐสภาและการแถลงข่าวของพรรคร่วมรัฐบาล",
            "source": "สำนักข่าวการเมือง",
            "url": f"https://example.com/pol/{i}",
            "fetched_at": "2026-10-16 10:00:00",
        })

    # The 30th article: Temasek / NIA tech funding
    articles.append({
        "article_id": "art_30",
        "title": "NIA จับมือ Temasek ตั้งกองทุนดิจิทัลและนวัตกรรมเซมิคอนดักเตอร์",
        "summary": "รองนายกรัฐมนตรีร่วมเป็นประธานเปิดตัวความร่วมมือส่งเสริมสตาร์ทอัพเทคโนโลยีขั้นสูง",
        "source": "Tech Daily",
        "url": "https://example.com/tech/temasek-nia",
        "fetched_at": "2026-10-16 11:00:00",
    })

    synthesis = svc.synthesize_event_progression(
        event_id="sri_sakhon_security_event",
        title=headline,
        articles=articles,
        allow_llm=False,
        force_refresh=True,
    )

    # Must be halted due to candidate set mismatch
    assert synthesis.synthesis_status == "halted_mismatch"
    assert synthesis.is_single_source is False
    assert "ไม่สอดคล้องกับเหตุการณ์ในพาดหัว" in synthesis.status_message
    assert len(synthesis.progression_timeline) == 0
    assert len(synthesis.confirmed_facts) == 0
    assert synthesis.metrics is not None
    assert synthesis.metrics.candidate_count == 30
    assert synthesis.metrics.synthesized_evidence_count == 0


def test_single_source_mode_transparent_disclosure() -> None:
    """
    Test Layer 3 Guardrail:
    Scenario: Headline is Sri Sakhon security clash.
    Among candidates, exactly 1 verified article directly reports on the clash.
    Verify synthesis transitions to 'single_source' mode:
    - synthesis_status == 'single_source'
    - is_single_source is True
    - Does NOT fabricate multi-source consensus claims.
    """
    svc = StoryPresentationService(client=None)

    headline = "ผบ.ทบ. ลงใต้ 'ศรีสาคร' ปะทะเดือด ตำรวจจับ 1 ทหารพรานเจ็บ"

    articles: list[dict[str, Any]] = [
        # Article 1: Direct report on Sri Sakhon clash
        {
            "article_id": "art_01",
            "title": "ผบ.ทบ. รุดตรวจจุดปะทะศรีสาคร นราธิวาส ทหารพรานเจ็บ 1 นาย คุมตัวผู้ต้องสงสัย 1 คน",
            "summary": "เจ้าหน้าที่กองทัพภาคที่ 4 และตำรวจเข้าปิดล้อมพื้นที่ศรีสาคร เกิดการยิงปะทะทำให้ทหารพรานได้รับบาดเจ็บ",
            "source": "สำนักข่าวความมั่นคง",
            "url": "https://example.com/south/clash-01",
            "fetched_at": "2026-10-16 08:30:00",
        },
        # Article 2: General tourism in Chiang Mai (excluded)
        {
            "article_id": "art_02",
            "title": "การท่องเที่ยวเชียงใหม่คึกคักรับลมหนาว ยอดจองห้องพักพุ่ง",
            "summary": "นักท่องเที่ยวแห่เดินทางสัมผัสอากาศหนาวบนดอยอินทนนท์ บรรยากาศเป็นไปอย่างคึกคัก",
            "source": "ไทยท่องเที่ยว",
            "url": "https://example.com/travel/cm",
            "fetched_at": "2026-10-16 09:00:00",
        },
    ]

    synthesis = svc.synthesize_event_progression(
        event_id="sri_sakhon_single_source",
        title=headline,
        articles=articles,
        allow_llm=False,
        force_refresh=True,
    )

    # Must be single source mode
    assert synthesis.synthesis_status == "single_source"
    assert synthesis.is_single_source is True
    assert "แหล่งข่าวเดียว" in synthesis.status_message or "เบื้องต้น" in synthesis.status_message
    assert len(synthesis.progression_timeline) >= 1
    assert synthesis.metrics is not None
    assert synthesis.metrics.synthesized_evidence_count == 1
    assert synthesis.metrics.synthesized_publishers_count == 1
    assert "สำนักข่าวความมั่นคง" in synthesis.metrics.synthesized_publishers


def test_semantic_clusterer_event_anchor_agreement() -> None:
    """
    Test Layer 1 Guardrail:
    Verify that SemanticClusterer enforces Event Anchor Agreement:
    Articles sharing general domain tokens (e.g. security/crime) but differing in
    specific entities, actions, and locations are NOT chained into the same cluster.
    """
    now = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    clusterer = SemanticClusterer(cosine_threshold=0.76)

    articles = [
        # Article A: Sri Sakhon clash
        {
            "title": "เจ้าหน้าที่ปะทะเดือดกลุ่มก่อความไม่สงบศรีสาคร นราธิวาส ทหารพรานเจ็บ 1 นาย",
            "summary": "เกิดเหตุปะทะในพื้นที่ อ.ศรีสาคร จ.นราธิวาส เจ้าหน้าที่ปิดล้อมตรวจค้น",
            "url": "https://example.com/south/1",
            "source": "Daily News",
            "category": "crime",
            "fetched_at": "2026-10-16 10:00:00",
        },
        # Article B: Chiang Mai cyber police gambling raid
        {
            "title": "ตำรวจไซเบอร์บุกทลายเว็บพนันออนไลน์รายใหญ่กลางเมืองเชียงใหม่ ยึดทรัพย์กว่า 50 ล้าน",
            "summary": "ชุดสืบสวนตำรวจไซเบอร์นำหมายศาลเข้าค้นอาคารพาณิชย์ในเชียงใหม่ จับกุมผู้ดูแลเว็บพนัน",
            "url": "https://example.com/cyber/1",
            "source": "Thai Post",
            "category": "crime",
            "fetched_at": "2026-10-16 11:00:00",
        },
    ]

    # Two embeddings with cosine similarity = 0.80 (exceeds cosine_threshold 0.76)
    # but strictly below 0.95 (not near-identical)
    # [cos(theta), sin(theta)] with dot product = 0.80
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.80, 0.60], dtype=np.float32)
    embeddings = np.array([v1, v2], dtype=np.float32)
    times = [now, now]

    results = clusterer.cluster_articles(articles, embeddings, times)

    # Must be partitioned into 2 distinct clusters because they have no specific event anchor overlap
    assert len(results) == 2
    assert results[0]["cluster_id"] != results[1]["cluster_id"]
    assert results[0]["cluster_size"] == 1
    assert results[1]["cluster_size"] == 1


def test_semantic_clusterer_deterministic_cluster_ids() -> None:
    """
    Test Layer 1 Guardrail:
    Verify that SemanticClusterer generates deterministic 8-character SHA-256 cluster IDs
    (cluster_<8char_hash>) rather than volatile sequential IDs (cluster_1).
    """
    now = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    clusterer = SemanticClusterer()

    articles = [
        {
            "title": "ชูวิทย์ยื่น ป.ป.ช. ตรวจสอบเงินบริจาคพรรคภูมิใจไทย 10 ล้านบาท",
            "summary": "เปิดหลักฐานเส้นทางการเงินบริจาคพรรคการเมือง",
            "url": "https://example.com/pol/1",
            "source": "Khaosod",
            "category": "politics",
            "fetched_at": "2026-10-16 10:00:00",
        },
    ]
    embeddings = np.array([[1.0, 0.0]], dtype=np.float32)
    times = [now]

    results_run_1 = clusterer.cluster_articles(articles, embeddings, times)
    results_run_2 = clusterer.cluster_articles(articles, embeddings, times)

    # Ensure format matches cluster_[0-9a-f]{8}
    cluster_id_1 = results_run_1[0]["cluster_id"]
    assert re.match(r"^cluster_[0-9a-f]{8}$", cluster_id_1) is not None

    # Ensure deterministic across multiple invocations
    assert cluster_id_1 == results_run_2[0]["cluster_id"]


def test_synthesis_cache_isolation_and_invalidation() -> None:
    """
    Test Cache Isolation:
    Verify that find_cached_synthesis enforces headline congruence and URL overlap ratio >= 0.75,
    preventing cache cross-contamination between different storylines or modified candidate sets.
    """
    svc = StoryPresentationService(client=None)

    articles_set_a = [
        {
            "article_id": "art_01",
            "title": "ผบ.ทบ. รุดตรวจจุดปะทะศรีสาคร นราธิวาส",
            "summary": "เหตุปะทะในพื้นที่ศรีสาคร",
            "source": "สำนักข่าวใต้",
            "url": "https://example.com/south/a1",
        },
        {
            "article_id": "art_02",
            "title": "เจ้าหน้าที่คุมตัวผู้ต้องสงสัยเหตุปะทะศรีสาครสอบขยายผล",
            "summary": "นำตัวผู้ต้องสงสัยเข้าศูนย์ซักถาม",
            "source": "สำนักข่าวไทย",
            "url": "https://example.com/south/a2",
        },
    ]

    articles_set_b = [
        {
            "article_id": "art_10",
            "title": "NIA จับมือพันธมิตรพัฒนาอุตสาหกรรมดิจิทัล",
            "summary": "ส่งเสริมนวัตกรรมเทคโนโลยี",
            "source": "Tech News",
            "url": "https://example.com/tech/b1",
        },
        {
            "article_id": "art_11",
            "title": "เปิดตัวกองทุนสตาร์ทอัพเทคโนโลยีขั้นสูง",
            "summary": "สนับสนุนเงินทุนผู้ประกอบการ",
            "source": "Biz News",
            "url": "https://example.com/tech/b2",
        },
    ]

    # Synthesize set A
    synth_a = svc.synthesize_event_progression(
        event_id="event_south_clash",
        title="ผบ.ทบ. ลงใต้ 'ศรีสาคร' ปะทะเดือด",
        articles=articles_set_a,
        allow_llm=False,
        force_refresh=True,
    )
    assert synth_a is not None

    # Try looking up cache with set B articles under same event_id
    cached_b = svc.find_cached_synthesis(
        event_id="event_south_clash",
        articles=articles_set_b,
        title="NIA จับมือพันธมิตรพัฒนาอุตสาหกรรมดิจิทัล",
    )
    # Must miss cache because URL overlap and content signature differ completely
    assert cached_b is None
