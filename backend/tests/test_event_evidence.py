"""
tests/test_event_evidence.py
─────────────────────────────────────────────────────────────────
Unit tests for deterministic evidence extraction, prompt payload,
and event progression intelligence synthesis.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from backend.schemas.event_evidence_schema import (
    EventProgressionSynthesis,
    EvidenceInputPayload,
)
from backend.services.evidence_extractor import EvidenceExtractor
from backend.services.story_presentation_service import (
    get_story_presentation_service,
)


def test_evidence_extractor_quotes_and_claims():
    text = (
        'นายสมชาย โฆษกกระทรวง เผยว่า "โครงการนี้มีความโปร่งใสและปฏิบัติตามระเบียบทุกประการ" '
        'ขณะที่ตัวแทนภาคประชาชนกล่าวหาว่า "มีการล็อกสเปกและเอื้อประโยชน์ให้เอกชนบางราย"'
    )
    claims = EvidenceExtractor.extract_claims(text, "art_01")
    assert len(claims) >= 2
    types = [c.claim_type for c in claims]
    assert any(t in ("official_statement", "fact_report", "accusation", "opinion") for t in types)
    assert any("สมชาย" in c.speaker or "โฆษก" in c.speaker or "ตัวแทน" in c.speaker for c in claims)


def test_evidence_extractor_build_payload():
    raw_articles = [
        {
            "title": "ก.คลัง แถลงปรับลดคาดการณ์จีดีพีปีนี้เหลือ 2.4%",
            "summary": 'นายพิชัย รมว.คลัง เผยว่า "เศรษฐกิจไทยเผชิญแรงกดดันจากภายนอก แต่ยังมีเสถียรภาพ"',
            "source": "ThaiPBS",
            "url": "https://thaipbs.or.th/news/1",
            "fetched_at": "2026-10-14 10:00:00",
        },
        {
            "title": "เอกชนชี้ GDP โตต่ำ แนะรัฐเร่งเบิกจ่ายงบประมาณ",
            "summary": 'ประธาน ส.อ.ท. มองว่า "การบริโภคในประเทศยังชะลอตัว หากรัฐบาลไม่กระตุ้นอาจโตไม่ถึง 2%"',
            "source": "Bangkok Post",
            "url": "https://bangkokpost.com/news/2",
            "fetched_at": "2026-10-14 12:00:00",
        },
        {
            "title": "ข่าวนอกเรื่อง: มหาวิทยาลัยเปิดตัวหลักสูตร AI ใหม่",
            "summary": "สถาบันการศึกษาชั้นนำเปิดรับสมัครนักศึกษาใหม่หลักสูตรปริญญาโทด้านปัญญาประดิษฐ์",
            "source": "Techhub",
            "url": "https://techhub.in.th/news/3",
            "fetched_at": "2026-10-14 14:00:00",
        },
    ]

    payload = EvidenceExtractor.build_payload(
        event_id="macro_evt_001",
        title="การปรับประมาณการเศรษฐกิจและจีดีพีไทย",
        articles=raw_articles,
    )

    assert isinstance(payload, EvidenceInputPayload)
    assert len(payload.articles) == 3
    assert payload.articles[0].article_id == "art_01"
    assert len(payload.articles[0].claims) > 0


def test_story_presentation_fallback_synthesis():
    svc = get_story_presentation_service()
    raw_articles = [
        {
            "title": "ก.คลัง แถลงปรับลดคาดการณ์จีดีพีปีนี้เหลือ 2.4%",
            "summary": 'นายพิชัย รมว.คลัง เผยว่า "เศรษฐกิจไทยเผชิญแรงกดดันจากภายนอก แต่ยังมีเสถียรภาพ"',
            "source": "ThaiPBS",
            "url": "https://thaipbs.or.th/news/1",
            "fetched_at": "2026-10-14 10:00:00",
        },
        {
            "title": "เอกชนชี้ GDP โตต่ำ แนะรัฐเร่งเบิกจ่ายงบประมาณ",
            "summary": 'ประธาน ส.อ.ท. มองว่า "การบริโภคในประเทศยังชะลอตัว หากรัฐบาลไม่กระตุ้นอาจโตไม่ถึง 2%"',
            "source": "Bangkok Post",
            "url": "https://bangkokpost.com/news/2",
            "fetched_at": "2026-10-14 12:00:00",
        },
        {
            "title": "ข่าวนอกเรื่อง: มหาวิทยาลัยเปิดตัวหลักสูตร AI ใหม่",
            "summary": "สถาบันการศึกษาชั้นนำเปิดรับสมัครนักศึกษาใหม่หลักสูตรปริญญาโทด้านปัญญาประดิษฐ์",
            "source": "Techhub",
            "url": "https://techhub.in.th/news/3",
            "fetched_at": "2026-10-14 14:00:00",
        },
    ]

    synthesis = svc.synthesize_event_progression(
        event_id="test_evt_01",
        title="การปรับประมาณการเศรษฐกิจและจีดีพีไทย",
        articles=raw_articles,
        allow_llm=False,
    )

    assert isinstance(synthesis, EventProgressionSynthesis)
    assert synthesis.is_fallback is True
    assert len(synthesis.progression_timeline) > 0
    assert len(synthesis.confirmed_facts) > 0
    assert len(synthesis.unknowns) > 0
    assert any(irr.article_id == "art_03" for irr in synthesis.irrelevant_articles)


def test_synthesis_cache_persistence_and_cluster_shift():
    svc = get_story_presentation_service()
    raw_articles_v1 = [
        {
            "title": "ข่าวการเมือง 1",
            "summary": "รายละเอียดการประชุมสภา",
            "source": "ThaiPBS",
            "url": "https://example.com/pol/1",
        },
        {
            "title": "ข่าวการเมือง 2",
            "summary": "การอภิปรายงบประมาณ",
            "source": "Bangkok Post",
            "url": "https://example.com/pol/2",
        },
    ]

    # Synthesize for initial dynamic cluster id "cluster_old_1"
    synth1 = svc.synthesize_event_progression(
        event_id="cluster_old_1",
        title="การประชุมสภาและงบประมาณ",
        articles=raw_articles_v1,
        allow_llm=False,
    )
    assert synth1 is not None

    # Simulate dynamic re-clustering: cluster_id changes to "cluster_new_99" with the exact same articles
    cached_match_exact = svc.find_cached_synthesis("cluster_new_99", raw_articles_v1, "การประชุมสภา")
    assert cached_match_exact is not None
    assert cached_match_exact.executive_summary == synth1.executive_summary

    # Simulate slight cluster evolution: an article is added (2 shared out of 3 = 66% overlap)
    raw_articles_v2 = raw_articles_v1 + [
        {
            "title": "ข่าวการเมือง 3 เพิ่มเติม",
            "summary": "ผลการลงมติ",
            "source": "Matichon",
            "url": "https://example.com/pol/3",
        }
    ]
    cached_match_overlap = svc.find_cached_synthesis("cluster_evolved_777", raw_articles_v2, "การประชุมสภา")
    assert cached_match_overlap is not None
    assert cached_match_overlap.executive_summary == synth1.executive_summary
