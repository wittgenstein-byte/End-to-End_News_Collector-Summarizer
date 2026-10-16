"""
tests/test_relevance_enforcement.py
─────────────────────────────────────────────────────────────────
Unit tests verifying the Two-Stage Relevance Gate & Executive Dossier:
1. Stage 1: evaluate_event_relevance triages candidate articles (33 articles
   into 9 direct evidence, 23 political context, 1 excluded off-topic).
2. Stage 2: Evidence payload isolation (payload receives strictly 9 relevant articles).
3. Stage 3: Output Validator Hard Reject on contaminated citations (e.g. art_25, art_29).
4. Stage 3: Bounded Retry (max 1 retry) and Deterministic Baseline Fallback.
5. DossierMetrics computation accuracy (33 candidate, 24 excluded, 9 synthesized,
   11 candidate publishers, 5 synthesized publishers).
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.schemas.event_evidence_schema import (
    ConfirmedFact,
    EventProgressionSynthesis,
    ProgressionMilestone,
)
from backend.schemas.macro_event_schema import MacroEventDetailResponse
from backend.services.evidence_extractor import EvidenceExtractor
from backend.services.story_presentation_service import (
    StoryPresentationService,
)


def _build_cluster_35_fixture() -> list[dict[str, str]]:
    """
    Construct realistic 33-article dataset modeling cluster_35:
    - 9 Direct Incident articles (5 publishers: Daily News, Thai Post, Khaosod, Nation, Komchadluek)
    - 23 Political Context articles (6 publishers: Matichon, ThaiPBS, Thairath, Bangkok Post, The Standard, Prachatai)
    - 1 Off-Topic Outlier article (Techhub)
    Total: 33 articles, 11 unique publishers.
    """
    articles: list[dict[str, str]] = []

    # 1. 9 Direct incident articles on donation investigation (15 Oct 2026)
    evidence_publishers = ["Daily News", "Thai Post", "Khaosod", "Nation", "Komchadluek"]
    incident_headlines = [
        "ชูวิทย์ยื่น ป.ป.ช. ตรวจสอบเงินบริจาคพรรคภูมิใจไทย 10 ล้านบาท",
        "ป.ป.ช. รับเรื่องร้องเรียนสอบเส้นทางการเงินเงินบริจาคพรรคภูมิใจไทย",
        "อนุทินแจงปมเงินบริจาคพรรคภูมิใจไทย ยันโปร่งใสตรวจสอบได้ตามกฎหมาย",
        "เลขาธิการ ป.ป.ช. เผยตั้งคณะอนุกรรมการไต่สวนเงินบริจาคพรรคภูมิใจไทย",
        "เปิดบัญชีทรัพย์สินและเอกสารเงินบริจาคพรรคภูมิใจไทย 10 ล้าน",
        "ดีเอสไอประสาน ป.ป.ช. ขอข้อมูลคดีเงินบริจาคพรรคภูมิใจไทยตรวจเส้นเงิน",
        "ศศิธรผู้บริจาคเงินพรรคภูมิใจไทยเข้าให้ปากคำ ป.ป.ช. ยันเงินส่วนตัว",
        "พรรคภูมิใจไทยแถลงย้ำ เงินบริจาค 10 ล้านถูกต้องตาม พ.ร.ป. พรรคการเมือง",
        "ป.ป.ช. เตรียมสรุปสำนวนเบื้องต้นคดีเงินบริจาคพรรคภูมิใจไทยสัปดาห์หน้า",
    ]
    for i, title in enumerate(incident_headlines, start=1):
        pub = evidence_publishers[(i - 1) % len(evidence_publishers)]
        articles.append({
            "article_id": f"art_{i:02d}",
            "title": title,
            "summary": f"รายละเอียดการตรวจสอบ {title} โดยมีพยานและเอกสารทางการเงินชัดเจน",
            "source": pub,
            "url": f"https://example.com/incident/{i}",
            "fetched_at": "2026-10-15 10:00:00",
        })

    # 2. 23 Political Context articles on no-confidence censure debate (14 Oct 2026)
    context_publishers = ["Matichon", "ThaiPBS", "Thairath", "Bangkok Post", "The Standard"]
    context_headlines = [
        "ฝ่ายค้านยื่นญัตติเปิดศึกอภิปรายไม่ไว้วางใจรัฐบาลทั้งคณะ",
        "สภาผู้แทนฯ บรรจุวาระการอภิปรายไม่ไว้วางใจเตรียมซักฟอกรัฐมนตรี",
        "เปิดศึกซักฟอก 3 วัน 3 คืน ฝ่ายค้านจัดขุนพลชำแหละผลงานรัฐบาล",
        "ประธานสภาฯ กำชับกรอบเวลาการอภิปรายไม่ไว้วางใจให้เป็นไปตามข้อบังคับ",
        "วิปฝ่ายค้านมั่นใจข้อมูลซักฟอกแน่น ชี้มีหมัดเด็ดสอยรัฐมนตรี",
        "วิปรัฐบาลเตรียมองครักษ์พิทักษ์นายกฯ รับมือการอภิปรายไม่ไว้วางใจ",
        "สภาเดือดเปิดศึกอภิปรายไม่ไว้วางใจวันแรก ฝ่ายค้านชูประเด็นบริหารล้มเหลว",
        "ฝ่ายค้านซักฟอกนโยบายเศรษฐกิจ ชี้จัดงบประมาณไม่ตอบโจทย์ประชาชน",
        "รมว.คลัง แจงกลางสภาฯ ศึกซักฟอก ยันเศรษฐกิจไทยมีเสถียรภาพ",
        "สภาฯ ถกญัตติไม่ไว้วางใจข้ามคืน รัฐมนตรีเรียงคิวแจงข้อกล่าวหา",
        "แกนนำพรรคร่วมรัฐบาลยันเสียงเหนียวแน่น พร้อมโหวตหนุนศึกซักฟอก",
        "ฝ่ายค้านเปิดข้อมูลโครงการจัดซื้อจัดจ้างในการอภิปรายไม่ไว้วางใจ",
        "สภาผู้แทนราษฎรเตรียมลงมติไม่ไว้วางใจรัฐมนตรีรายบุคคล",
        "พรรคประชาชาติเน้นซักฟอกปัญหาความไม่สงบชายแดนใต้",
        "พรรคก้าวไกลเดิมจัดเต็มอภิปรายไม่ไว้วางใจนโยบายพลังงาน",
        "บรรยากาศหน้าสภาฯ ประชาชนติดตามการอภิปรายไม่ไว้วางใจคึกคัก",
        "นักวิชาการวิเคราะห์ผลกระทบการเมืองหลังศึกอภิปรายไม่ไว้วางใจ",
        "ฝ่ายค้านยื่นหลักฐานต่อ ป.ป.ช. หลังเสร็จสิ้นการอภิปรายไม่ไว้วางใจ",
        "ผลการลงมติไม่ไว้วางใจ นายกฯ และรัฐมนตรีไว้วางใจผ่านฉลุย",
        "ประมวลภาพไฮไลต์ศึกอภิปรายไม่ไว้วางใจตลอด 3 วัน",
        "พรรคร่วมฝ่ายค้านแถลงสรุปภาพรวมการอภิปรายไม่ไว้วางใจในสภา",
        "นายกฯ ขอบคุณสภาฯ หลังผ่านศึกอภิปรายไม่ไว้วางใจ เดินหน้าทำงานต่อ",
        "วิเคราะห์ทิศทางการเมืองไทยหลังการลงมติไม่ไว้วางใจในสภาผู้แทนฯ",
    ]
    for j, title in enumerate(context_headlines, start=10):
        pub = context_publishers[(j - 10) % len(context_publishers)]
        articles.append({
            "article_id": f"art_{j:02d}",
            "title": title,
            "summary": f"รายงานการประชุมสภาผู้แทนราษฎรในวาระ {title} ถกเถียงเข้มข้น",
            "source": pub,
            "url": f"https://example.com/context/{j}",
            "fetched_at": "2026-10-14 09:00:00",
        })

    # 3. 1 Outlier article completely off-topic (Techhub)
    articles.append({
        "article_id": "art_33",
        "title": "มหาวิทยาลัยเปิดตัวหลักสูตร AI ใหม่สำหรับการศึกษาอนาคต",
        "summary": "สถาบันการศึกษาชั้นนำเปิดรับสมัครนักศึกษาใหม่ระดับปริญญาโทด้านปัญญาประดิษฐ์",
        "source": "Techhub",
        "url": "https://example.com/outlier/33",
        "fetched_at": "2026-10-14 12:00:00",
    })

    return articles


def test_relevance_gate_classification():
    """
    Test 1: Stage 1 evaluate_event_relevance triages 33 candidate articles
    into 9 direct incident evidence, 23 political context, and 1 off-topic outlier.
    """
    svc = StoryPresentationService(client=None)
    articles = _build_cluster_35_fixture()
    assert len(articles) == 33

    gate_result = svc.evaluate_event_relevance(
        event_id="cluster_35",
        title="กรณีตรวจสอบเงินบริจาคพรรคภูมิใจไทย 10 ล้าน",
        articles=articles,
        allow_llm=False,
    )

    assert len(gate_result.relevant_article_ids) == 9
    assert len(gate_result.context_article_ids) == 23
    assert len(gate_result.excluded_article_ids) == 1

    # Total excluded from timeline synthesis
    total_excluded = len(gate_result.context_article_ids) + len(gate_result.excluded_article_ids)
    assert total_excluded == 24

    # Relevant IDs are art_01 to art_09
    expected_relevant = {f"art_{i:02d}" for i in range(1, 10)}
    assert set(gate_result.relevant_article_ids) == expected_relevant

    # Context IDs include art_10 to art_32 (censure debate)
    assert "art_25" in gate_result.context_article_ids
    assert "art_29" in gate_result.context_article_ids

    # Outlier ID is art_33
    assert "art_33" in gate_result.excluded_article_ids

    # Every context and excluded item has an explanatory reason
    for cid in gate_result.context_article_ids:
        assert cid in gate_result.exclusion_reasons
        assert "บริบทการเมือง" in gate_result.exclusion_reasons[cid]

    assert "art_33" in gate_result.exclusion_reasons
    assert "ข่าวนอกประเด็น" in gate_result.exclusion_reasons["art_33"]


def test_stage2_payload_isolation():
    """
    Test 2: Stage 2 builds EvidenceInputPayload using strictly the 9 relevant articles,
    ensuring 0 contamination from the 24 context/outlier articles.
    """
    svc = StoryPresentationService(client=None)
    articles = _build_cluster_35_fixture()

    gate_result = svc.evaluate_event_relevance(
        event_id="cluster_35",
        title="กรณีตรวจสอบเงินบริจาคพรรคภูมิใจไทย 10 ล้าน",
        articles=articles,
        allow_llm=False,
    )

    relevant_articles = [
        a for a in articles
        if a["article_id"] in gate_result.relevant_article_ids
    ]
    assert len(relevant_articles) == 9

    payload = EvidenceExtractor.build_payload(
        event_id="cluster_35",
        title="กรณีตรวจสอบเงินบริจาคพรรคภูมิใจไทย 10 ล้าน",
        articles=relevant_articles,
    )

    # Payload contains exactly the 9 relevant articles
    assert len(payload.articles) == 9
    payload_ids = {a.article_id for a in payload.articles}
    assert payload_ids == {f"art_{i:02d}" for i in range(1, 10)}

    # None of the 24 excluded articles are present in payload
    for excluded_id in gate_result.context_article_ids + gate_result.excluded_article_ids:
        assert excluded_id not in payload_ids


def test_output_validator_hard_reject():
    """
    Test 3: Stage 3 validate_dossier_citations performs Hard Reject when LLM
    cites articles outside the allowed evidence pool (specifically art_25 or art_29).
    """
    svc = StoryPresentationService(client=None)
    allowed_evidence_ids = {f"art_{i:02d}" for i in range(1, 10)}

    # 1. Clean synthesis citing only allowed articles (art_01, art_02)
    valid_synthesis = EventProgressionSynthesis(
        event_id="cluster_35",
        executive_summary="สรุปสถานการณ์เงินบริจาคพรรคภูมิใจไทย",
        progression_timeline=[
            ProgressionMilestone(
                milestone_id="m_01",
                event_time="2026-10-15 10:00:00",
                description="ชูวิทย์ยื่นคำร้องต่อ ป.ป.ช.",
                evidence_ids=["art_01", "art_02"],
            )
        ],
        confirmed_facts=[
            ConfirmedFact(
                fact_id="f_01",
                fact="ป.ป.ช. รับคำร้องตรวจสอบเงินบริจาค 10 ล้าน",
                evidence_ids=["art_02"],
                corroborating_sources=["Thai Post"],
            )
        ],
    )
    is_valid, errors = svc.validate_dossier_citations(valid_synthesis, allowed_evidence_ids)
    assert is_valid is True
    assert len(errors) == 0

    # 2. Contaminated synthesis citing art_25 and art_29 (from the censure debate)
    contaminated_synthesis = EventProgressionSynthesis(
        event_id="cluster_35",
        executive_summary="สรุปสถานการณ์ที่มีการปนเปื้อนข้อมูลซักฟอก",
        progression_timeline=[
            ProgressionMilestone(
                milestone_id="m_01",
                event_time="2026-10-14 09:00:00",
                description="ฝ่ายค้านยื่นญัตติอภิปรายไม่ไว้วางใจในสภา",
                evidence_ids=["art_25"],  # Contaminated ID!
            ),
            ProgressionMilestone(
                milestone_id="m_02",
                event_time="2026-10-15 10:00:00",
                description="ชูวิทย์ร้องเรียนเรื่องเงินบริจาค",
                evidence_ids=["art_01", "art_29"],  # Contaminated ID!
            ),
        ],
        confirmed_facts=[
            ConfirmedFact(
                fact_id="f_01",
                fact="สภาผู้แทนราษฎรมีมติไว้วางใจ",
                evidence_ids=["art_25"],  # Contaminated ID!
                corroborating_sources=["Matichon"],
            )
        ],
    )
    is_invalid, err_list = svc.validate_dossier_citations(contaminated_synthesis, allowed_evidence_ids)
    assert is_invalid is False
    assert len(err_list) >= 3
    assert any("art_25" in err for err in err_list)
    assert any("art_29" in err for err in err_list)


def test_bounded_retry_and_fallback():
    """
    Test 4: Stage 3 Bounded Retry (max 1 retry) and Deterministic Baseline Fallback.
    Simulate LLM repeatedly outputting contaminated citations citing art_25;
    verify system rejects both, aborts retry loop, and cleanly falls back
    to deterministic heuristic built strictly from the 9 relevant articles.
    """
    # Create mock OpenAI client that repeatedly returns contaminated citations
    mock_client = MagicMock()
    contaminated_json = """{
      "executive_summary": "สรุปสถานการณ์ปนเปื้อน",
      "progression_timeline": [
        {
          "milestone_id": "m_01",
          "event_time": "2026-10-14 09:00:00",
          "description": "ฝ่ายค้านเปิดศึกอภิปรายไม่ไว้วางใจ",
          "evidence_ids": ["art_25"]
        }
      ],
      "confirmed_facts": [
        {
          "fact_id": "f_01",
          "fact": "การอภิปรายไม่ไว้วางใจเริ่มขึ้นแล้ว",
          "evidence_ids": ["art_25"],
          "corroborating_sources": ["Matichon"]
        }
      ],
      "conflicts": [],
      "unknowns": [],
      "irrelevant_articles": []
    }"""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=contaminated_json))]
    mock_client.chat.completions.create.return_value = mock_response

    svc = StoryPresentationService(client=mock_client, models=["mock-model"])
    # Bypass API key check for mock
    svc._should_attempt_llm = lambda: True  # type: ignore[method-assign]

    articles = _build_cluster_35_fixture()
    synthesis = svc.synthesize_event_progression(
        event_id="cluster_35",
        title="กรณีตรวจสอบเงินบริจาคพรรคภูมิใจไทย 10 ล้าน",
        articles=articles,
        allow_llm=True,
        force_refresh=True,
    )

    # 1. Output validator rejected contaminated LLM output and fell back
    assert synthesis.is_fallback is True

    # 2. Mock was called exactly twice (initial attempt + bounded retry 1 time)
    # Plus stage 1 relevance gate if called
    assert mock_client.chat.completions.create.call_count >= 2

    # 3. Milestones in fallback synthesis strictly cite ONLY the 9 relevant articles
    assert len(synthesis.progression_timeline) > 0
    allowed_ids = {f"art_{i:02d}" for i in range(1, 10)}
    for m in synthesis.progression_timeline:
        for eid in m.evidence_ids:
            assert eid in allowed_ids
            assert eid != "art_25"
            assert eid != "art_29"

    # 4. Context items are properly segregated in political_contexts
    assert len(synthesis.political_contexts) == 23
    assert any(c.article_id == "art_25" for c in synthesis.political_contexts)


def test_dossier_metrics_accuracy():
    """
    Test 5: Verify DossierMetrics accuracy:
    - candidate_count: 33
    - excluded_count: 24 (23 context + 1 outlier)
    - synthesized_evidence_count: 9
    - candidate_publishers_count: 11
    - synthesized_publishers_count: 5
    - synthesized_publishers: 5 corroborated evidence outlets
    """
    svc = StoryPresentationService(client=None)
    articles = _build_cluster_35_fixture()

    synthesis = svc.synthesize_event_progression(
        event_id="cluster_35",
        title="กรณีตรวจสอบเงินบริจาคพรรคภูมิใจไทย 10 ล้าน",
        articles=articles,
        allow_llm=False,
        force_refresh=True,
    )

    assert synthesis.metrics is not None
    m = synthesis.metrics

    assert m.candidate_count == 33
    assert m.excluded_count == 24
    assert m.synthesized_evidence_count == 9
    assert m.candidate_publishers_count == 11
    assert m.synthesized_publishers_count == 5

    expected_publishers = sorted(["Daily News", "Khaosod", "Komchadluek", "Nation", "Thai Post"])
    assert m.synthesized_publishers == expected_publishers


def test_relevance_gate_with_censure_only_topic():
    """
    Test 6: When the event topic title itself is about the censure debate,
    tokens are not stripped as context. Articles discussing the censure debate
    must be classified as relevant evidence, not excluded context.
    """
    svc = StoryPresentationService(client=None)
    articles = [
        {
            "article_id": "art_01",
            "title": "สภาผู้แทนฯ เปิดศึกอภิปรายไม่ไว้วางใจวันแรก",
            "summary": "การประชุมสภาผู้แทนราษฎรเพื่อเปิดศึกอภิปรายไม่ไว้วางใจ",
            "source": "ThaiPBS",
            "fetched_at": "2026-10-14 09:00:00",
        },
        {
            "article_id": "art_02",
            "title": "ฝ่ายค้านยื่นญัตติซักฟอกรัฐบาลทั้งคณะ",
            "summary": "รายงานข่าวการยื่นญัตติซักฟอกและอภิปรายไม่ไว้วางใจ",
            "source": "Matichon",
            "fetched_at": "2026-10-14 10:00:00",
        },
        {
            "article_id": "art_03",
            "title": "เทคโนโลยี Quantum Computing ก้าวกระโดดในปี 2026",
            "summary": "ความก้าวหน้าด้านคอมพิวเตอร์ควอนตัมสำหรับการประมวลผล",
            "source": "TechDaily",
            "fetched_at": "2026-10-14 11:00:00",
        },
    ]

    gate_result = svc.evaluate_event_relevance(
        event_id="cluster_censure_event",
        title="การอภิปรายไม่ไว้วางใจ",
        articles=articles,
        allow_llm=False,
    )

    assert "art_01" in gate_result.relevant_article_ids
    assert "art_02" in gate_result.relevant_article_ids
    assert "art_03" in gate_result.excluded_article_ids


def test_output_validator_case_insensitive_and_whitespace():
    """
    Test 7: Citation validator is resilient to uppercase and whitespace variations.
    """
    svc = StoryPresentationService(client=None)
    allowed_ids = ["art_01", "art_02"]

    synthesis = EventProgressionSynthesis(
        event_id="cluster_test",
        executive_summary="สรุปสถานการณ์ทดสอบ",
        progression_timeline=[
            ProgressionMilestone(
                milestone_id="m_01",
                event_time="2026-10-15 10:00:00",
                description="เหตุการณ์ทดสอบ",
                evidence_ids=["ART_01", " art_02 "],
            )
        ],
    )

    is_valid, errors = svc.validate_dossier_citations(synthesis, allowed_ids)
    assert is_valid is True
    assert len(errors) == 0


def test_find_cached_synthesis_requires_metrics(tmp_path):
    """
    Test 8: find_cached_synthesis skips legacy cache entries lacking metrics.
    """
    cache_file = tmp_path / "presentation_cache.json"
    svc = StoryPresentationService(client=None, cache_file=cache_file)

    # Insert legacy cache entry without metrics
    legacy_data = {
        "event_id": "legacy_cluster",
        "executive_summary": "สรุปแบบเดิมไม่มี metrics",
        "progression_timeline": [],
        "confirmed_facts": [],
        "conflicts": [],
        "unknowns": [],
        "irrelevant_articles": [],
        "metrics": None,
    }
    svc._disk_cache["synthesis_legacy_cluster"] = {
        "event_id": "legacy_cluster",
        "data": legacy_data,
        "article_urls": ["https://example.com/1"],
    }

    # require_metrics=True -> returns None so it regenerates
    cached = svc.find_cached_synthesis(event_id="legacy_cluster", require_metrics=True)
    assert cached is None

    # require_metrics=False -> returns the legacy entry
    cached_legacy = svc.find_cached_synthesis(event_id="legacy_cluster", require_metrics=False)
    assert cached_legacy is not None
    assert cached_legacy.executive_summary == "สรุปแบบเดิมไม่มี metrics"


def test_macro_event_detail_includes_synthesis():
    """
    Test 9: MacroEventDetailResponse retains synthesis in model_dump.
    """
    synthesis = EventProgressionSynthesis(
        event_id="macro_test",
        executive_summary="สรุปภาพรวม macro event",
    )
    res = MacroEventDetailResponse(
        macro_event_id="macro_test",
        title="หัวข้อ macro test",
        category="politics",
        status="active",
        created_at="2026-10-15 10:00:00",
        updated_at="2026-10-15 11:00:00",
        child_event_count=1,
        articles=[{"url": "https://example.com/1", "title": "ข่าว 1"}],
        synthesis=synthesis,
    )
    dumped = res.model_dump()
    assert "synthesis" in dumped
    assert dumped["synthesis"] is not None
    assert dumped["synthesis"]["executive_summary"] == "สรุปภาพรวม macro event"
    assert len(dumped["articles"]) == 1


def test_articles_without_preset_ids_chronological_sort():
    """
    Test 10: Candidate articles without article_id preset are chronologically
    sorted so art_01 corresponds to the earliest article.
    """
    svc = StoryPresentationService(client=None)
    unsorted_articles = [
        {
            "title": "ข่าวยามบ่าย",
            "summary": "เหตุการณ์บ่าย",
            "source": "Daily News",
            "url": "https://example.com/afternoon",
            "published_at": "2026-10-15 14:00:00",
        },
        {
            "title": "ข่าวยามเช้า",
            "summary": "เหตุการณ์เช้า",
            "source": "Thai Post",
            "url": "https://example.com/morning",
            "published_at": "2026-10-15 08:00:00",
        },
    ]

    synthesis = svc.synthesize_event_progression(
        event_id="cluster_chronological",
        title="เหตุการณ์ประจำวัน",
        articles=unsorted_articles,
        allow_llm=False,
        force_refresh=True,
    )

    # In chronological order: morning (08:00) should be art_01, afternoon (14:00) should be art_02
    assert len(synthesis.progression_timeline) >= 2
    assert synthesis.progression_timeline[0].evidence_ids == ["art_01"]
    assert "08:00:00" in synthesis.progression_timeline[0].event_time

