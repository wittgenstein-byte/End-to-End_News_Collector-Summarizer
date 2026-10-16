"""
tests/test_sports_presentation.py
─────────────────────────────────────────────────────────────────
Unit tests verifying the Dedicated Sports Intelligence & Multi-Sport
Aggregation behavior:
1. Sports collection detection (_check_is_sports_collection).
2. Sports Relevance Gate preservation (zero false exclusions for multi-sport clusters).
3. Sports synthesis fallback produces a multi-sport executive overview with complete metrics.
4. Non-sports stories remain unaffected (relevance gate isolation intact).
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from backend.services.story_presentation_service import (
    StoryPresentationService,
    _check_is_sports_collection,
)


def _build_cluster_52_sports_fixture() -> list[dict[str, str]]:
    """
    Construct realistic 29-article sports dataset modeling cluster_52:
    - European Football / UCL (UCL, Premier League, PSG, Man City, Liverpool, Arsenal, Atletico vs Man Utd)
    - Thai Domestic Football & Asian Clubs (Thai League 3, ACL Elite, King's Cup, Asian Cup)
    - Volleyball & Beach Volleyball (PMYC Roi Et, Qatar beach volleyball)
    - Asian Para Games & Other Sports (Shooting, Cycling, Ajinomoto, Tennis)
    Total: 29 articles across 4 publishers (PPTV HD 36, Daily News, Khaosod, Matichon).
    """
    return [
        {
            "article_id": "art_01",
            "title": "โปรแกรมบอล 14 ต.ค. 2569 แมนฯ ซิตี้เปิดบ้านบู๊เปแอสเชแมตช์รอบลีกศึก ชปล.",
            "summary": "โปรแกรมการแข่งขันฟุตบอลยูฟ่า แชมเปียนส์ ลีก นัดสำคัญ",
            "source": "Khaosod",
            "url": "https://www.khaosod.co.th/sports/news_10437491",
            "category": "sports",
        },
        {
            "article_id": "art_02",
            "title": "ยิงปืน-จักรยานพาราไทย ส่ง 20 นักกีฬาลุยเอเชี่ยนพาราเกมส์ วางเป้า 3 ทอง",
            "summary": "ทัพนักกีฬาพาราไทยเดินทางสู้ศึกเอเชี่ยนพาราเกมส์ 2026",
            "source": "Matichon",
            "url": "https://www.matichon.co.th/sport/news_5934198",
            "category": "sports",
        },
        {
            "article_id": "art_03",
            "title": "‘ท่าเรือ’ บุกแพ้ ‘คาชิวะ’ ยับ – 3 สโมสรไทยเตะ 3 นัด ยังไม่ชนะเลย",
            "summary": "การแข่งขันฟุตบอลเอเอฟซี แชมเปียนส์ ลีก อีลิท การท่าเรือ พ่าย คาชิว่า",
            "source": "Daily News",
            "url": "https://www.dailynews.co.th/news/6274614/",
            "category": "sports",
        },
        {
            "article_id": "art_04",
            "title": "บีจี ปทุม นำก่อนแต่โดน แอดิเลด ยูไนเต็ด ยิงคืนแซงเก็บชัย ศึกเอเอฟซี แชมเปียนส์ ลีก ทู",
            "summary": "บีจี ปทุม ยูไนเต็ด พ่าย แอดิเลด ยูไนเต็ด ในศึกฟุตบอลเอเชีย",
            "source": "Khaosod",
            "url": "https://www.khaosod.co.th/sports/news_10438916",
            "category": "sports",
        },
        {
            "article_id": "art_05",
            "title": "ผลบอล แอต.มาดริด เปิดบ้านชนะ แมนยู 10 คน คว้า 3 แต้ม ศึก UCL",
            "summary": "แอตเลติโก มาดริด เปิดบ้านเอาชนะ แมนเชสเตอร์ ยูไนเต็ด 2-0 ในศึกแชมเปียนส์ลีก",
            "source": "PPTV HD 36",
            "url": "https://www.pptvhd36.com/sport/news/285227",
            "category": "sports",
        },
        {
            "article_id": "art_06",
            "title": "ผลบอลเปแอสเช บุกชนะ แมนฯ ซิตี้ 4-2 เกม UCL ลีก เฟส นัดที่ 2",
            "summary": "ปารีส แซงต์ แชร์กแมง บุกคว้าชัยเหนือ แมนเชสเตอร์ ซิตี้ 4-2",
            "source": "PPTV HD 36",
            "url": "https://www.pptvhd36.com/sport/news/285225",
            "category": "sports",
        },
        {
            "article_id": "art_07",
            "title": "โรงเรียนกีฬาเทศบาลเมืองร้อยเอ็ด ขอคว้าแชมป์ภาคอีสาน 2 ศึกลูกยาง PMYC",
            "summary": "ทีมนักกีฬาวอลเลย์บอลเยาวชนร้อยเอ็ดพร้อมสู้ศึกชิงแชมป์ลูกยาง",
            "source": "Khaosod",
            "url": "https://www.khaosod.co.th/sports/news_10438800",
            "category": "sports",
        },
        {
            "article_id": "art_08",
            "title": "AIS ผนึกกำลัง จุฬาลงกรณ์ฯ หนุน “จามจุรี ยูไนเต็ด” ลุยศึกไทยลีก 3 เต็มพิกัด",
            "summary": "การสนับสนุนสโมสรฟุตบอลจามจุรี ยูไนเต็ด สู้ศึกไทยลีก 3",
            "source": "Daily News",
            "url": "https://www.dailynews.co.th/news/6274699/",
            "category": "sports",
        },
        {
            "article_id": "art_09",
            "title": "'ไบรท์-เบส' ล้มมือวางอันดับ 1 ญี่ปุ่น คว้าแชมป์วอลเลย์ชายหาดที่กาตาร์",
            "summary": "นักกีฬาวอลเลย์บอลชายหาดทีมชาติไทยสร้างชื่อคว้าแชมป์ระดับนานาชาติ",
            "source": "PPTV HD 36",
            "url": "https://www.pptvhd36.com/sport/news/285226",
            "category": "sports",
        },
    ]


def test_sports_collection_detection() -> None:
    """Test 1: _check_is_sports_collection detects sports vs political datasets."""
    sports_articles = _build_cluster_52_sports_fixture()
    assert _check_is_sports_collection("รวมข่าวกีฬาประจำวัน", sports_articles) is True

    # Political dataset
    politics_articles = [
        {"title": "ป.ป.ช. ไต่สวนเงินบริจาคพรรคภูมิใจไทย", "category": "politics", "url": "https://news.com/1"},
        {"title": "อนุทินแจงเงินบริจาคถูกต้อง", "category": "politics", "url": "https://news.com/2"},
        {"title": "ฝ่ายค้านยื่นอภิปรายไม่ไว้วางใจ", "category": "politics", "url": "https://news.com/3"},
    ]
    assert _check_is_sports_collection("เงินบริจาคพรรคภูมิใจไทย", politics_articles) is False


def test_sports_relevance_gate_preserves_all_articles() -> None:
    """
    Test 2: In a sports collection, evaluate_event_relevance preserves all sports
    articles without excluding distinct matches as 'irrelevant outliers'.
    """
    svc = StoryPresentationService(client=None)
    sports_articles = _build_cluster_52_sports_fixture()

    gate_result = svc.evaluate_event_relevance(
        event_id="cluster_52",
        title='ฝ่ายจัดยัน “เอเชียน คัพ” ไม่เลื่อนเตะแม้ซาอุดีอาระเบียเพิ่งโดนโจมตีสนามบิน',
        articles=sports_articles,
        allow_llm=False,
    )

    # All 9 articles must be retained as relevant evidence
    assert len(gate_result.relevant_article_ids) == 9
    assert gate_result.excluded_article_ids == []
    assert gate_result.context_article_ids == []
    assert "art_05" in gate_result.relevant_article_ids  # Atletico vs Man Utd
    assert "art_08" in gate_result.relevant_article_ids  # Chamchuri Thai League 3
    assert "art_07" in gate_result.relevant_article_ids  # Roi Et volleyball


def test_sports_synthesis_heuristic_overview() -> None:
    """
    Test 3: Sports synthesis heuristic produces a multi-sport executive overview
    with 0 excluded count and all sports publishers represented.
    """
    svc = StoryPresentationService(client=None)
    sports_articles = _build_cluster_52_sports_fixture()

    synthesis = svc.synthesize_event_progression(
        event_id="cluster_52_test",
        title="รวมข่าวกีฬาเด่น ผลบอล และความเคลื่อนไหวล่าสุด",
        articles=sports_articles,
        allow_llm=False,
        force_refresh=True,
    )

    assert synthesis.event_id == "cluster_52_test"
    assert "ศูนย์รวมข่าวกีฬาเด่น" in synthesis.executive_summary
    assert synthesis.metrics is not None
    assert synthesis.metrics.candidate_count == 9
    assert synthesis.metrics.excluded_count == 0
    assert synthesis.metrics.synthesized_evidence_count == 9
    assert synthesis.metrics.candidate_publishers_count == 4
    assert synthesis.metrics.synthesized_publishers_count == 4
    assert len(synthesis.progression_timeline) > 0


def test_non_sports_relevance_gate_still_enforced() -> None:
    """
    Test 4: Non-sports stories (politics) continue to enforce outlier and context triage.
    """
    svc = StoryPresentationService(client=None)
    politics_articles = [
        {"article_id": "art_01", "title": "ป.ป.ช. ไต่สวนเงินบริจาคพรรคภูมิใจไทย", "category": "politics", "url": "https://news.com/1"},
        {"article_id": "art_02", "title": "อนุทินแจงเงินบริจาคถูกต้องตามกฎหมาย", "category": "politics", "url": "https://news.com/2"},
        {"article_id": "art_03", "title": "เปิดตัวสมาร์ทโฟนรุ่นใหม่ล่าสุดประจำปี", "category": "technology", "url": "https://news.com/3"},
    ]

    gate_result = svc.evaluate_event_relevance(
        event_id="cluster_politics_test",
        title="ตรวจสอบเงินบริจาคพรรคภูมิใจไทย",
        articles=politics_articles,
        allow_llm=False,
    )

    # Tech article should be excluded in politics event
    assert "art_01" in gate_result.relevant_article_ids
    assert "art_02" in gate_result.relevant_article_ids
    assert "art_03" in gate_result.excluded_article_ids
