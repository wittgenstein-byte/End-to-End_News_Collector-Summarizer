"""
backend/tests/test_story_presentation.py
─────────────────────────────────────────────────────────────────
Comprehensive test suite for Milestone 4: Story Presentation via LLM & Fallback.

Covers:
1. LLM Presentation Generation:
   - Thai headline, synthesized summary, chronological developments timeline,
     and source citations.
   - Dual-compatible TimelineEvent access (event_description/event, source_name/source, etc.).
   - Model cascading fallback on model failure (e.g. 429 quota, timeout).
2. Robust Graceful Fallback:
   - Missing API key, network error, timeout, 401, 429, 500, or invalid JSON.
   - Fallback headline cleaning, synthesized excerpt, chronological timeline,
     and citations.
   - Zero crash guarantee: never raises unhandled exceptions.
3. Composite Caching:
   - Caching keyed by (story_id, updated_at).
   - Same updated_at hits cache (zero LLM calls).
   - New updated_at (new article added) invalidates cache and regenerates.
   - Cache eviction, clearing, and independence across stories.
4. Story & Top Story Enrichment:
   - Enriches StoryRecord, TrendingStoryCluster, and dict models.
   - enrich_top_stories limits enrichment to top N stories.
   - Async API support (present_story_async, enrich_story_async, enrich_top_stories_async).
5. Recorded Run Artifact Verification:
   - Verifies data/real_llm_presentation_output.json schema and content.
6. LLM Separation Principle:
   - Presentation never modifies trending scores, rank, or cluster membership.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import StoryRecord
from backend.schemas.trending_schema import TrendingScoreBreakdown, TrendingStoryCluster
from backend.services.story_presentation_service import (
    Citation,
    StoryPresentation,
    StoryPresentationService,
    TimelineEvent,
    get_story_presentation_service,
    reset_story_presentation_service,
)

# ── Sample Fixtures ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_presentation_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.config.settings.DATA_DIR", tmp_path)
    reset_story_presentation_service()

@pytest.fixture
def sample_nan_articles() -> list[dict[str, Any]]:
    return [
        {
            "title": "GISTDA ใช้ข้อมูลเชิงพื้นที่ เฝ้าระวัง 11 ชุมชนบ่อเกลือ เสี่ยงเส้นทางถูกตัดขาด",
            "summary": "GISTDA ใช้ข้อมูลดาวเทียมเฝ้าระวัง 11 ชุมชนในอำเภอบ่อเกลือ จังหวัดน่าน ที่เสี่ยงต่อการถูกตัดขาดจากเหตุดินถล่ม",
            "source": "ThaiPBS",
            "url": "https://www.thaipbs.or.th/news/content/509744",
            "fetched_at": "2026-08-22 14:35:12",
        },
        {
            "title": "กรมบัญชีกลางอนุมัติเพิ่ม 100 ล้าน เพิ่มเงินทดรองราชการช่วยน้ำท่วม “น่าน”",
            "summary": "กรมบัญชีกลางอนุมัติขยายวงเงินทดรองราชการเพื่อช่วยเหลือผู้ประสบภัยพิบัติกรณีฉุกเฉินน้ำท่วมน่านเป็น 100 ล้านบาท",
            "source": "ThaiPBS",
            "url": "https://www.thaipbs.or.th/news/content/509750",
            "fetched_at": "2026-08-22 14:35:11",
        },
        {
            "title": "นายกฯ ไปน่าน-อุบลฯ ตรวจน้ำท่วม-เยี่ยมทหารเหยียบทุ่นระเบิด",
            "summary": "นายกฯ อนุทิน บินด่วนตรวจสถานการณ์น้ำท่วมจังหวัดน่าน ประชุมติดตามแผนฟื้นฟูและเยียวยาประชาชนร่วมกับส่วนราชการ",
            "source": "ThaiPBS",
            "url": "https://www.thaipbs.or.th/news/content/509767",
            "fetched_at": "2026-08-23 14:35:11",
        },
        {
            "title": "Nan flood recovery under way, aid payments prepared",
            "summary": "Prime Minister ordered state agencies to speed up flood recovery, compensation payments and infrastructure repairs in Nan.",
            "source": "Bangkok Post",
            "url": "https://www.bangkokpost.com/thailand/general/3306558/nan-flood-recovery-under-way-aid-payments-prepared",
            "fetched_at": "2026-08-23 14:35:26",
        },
    ]


@pytest.fixture
def sample_nan_story(sample_nan_articles: list[dict[str, Any]]) -> StoryRecord:
    story = StoryRecord(
        story_id="story_nan_floods_001",
        title="สถานการณ์น้ำท่วมดินถล่มจังหวัดน่านและการเยียวยาฟื้นฟู",
        category="environment",
        status="active",
        created_at=datetime(2026, 8, 22, 14, 35, 11, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 23, 14, 35, 26, tzinfo=timezone.utc),
        article_urls=[a["url"] for a in sample_nan_articles],
        article_count=len(sample_nan_articles),
        outlet_count=2,
        outlets=["ThaiPBS", "Bangkok Post"],
    )
    return story


@pytest.fixture
def sample_trending_cluster(sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]) -> TrendingStoryCluster:
    return TrendingStoryCluster(
        story_id=sample_nan_story.story_id,
        title=sample_nan_story.title,
        category=sample_nan_story.category,
        status="active",
        created_at="2026-08-22 14:35:11",
        updated_at="2026-08-23 14:35:26",
        article_urls=sample_nan_story.article_urls,
        article_count=sample_nan_story.article_count,
        outlet_count=sample_nan_story.outlet_count,
        outlets=sample_nan_story.outlets,
        trending_score=8.75,
        rank=1,
        breakdown=TrendingScoreBreakdown(final_score=8.75),
        articles=sample_nan_articles,
    )


# ── 1. TimelineEvent & Citation Schemas Tests ─────────────────────

class TestPresentationSchemas:
    def test_timeline_event_dual_compatibility(self) -> None:
        event = TimelineEvent(
            timestamp="2026-08-23 14:35:26",
            event_description="นายกฯ สั่งเร่งเยียวยาน้ำท่วมน่าน",
            source_name="ThaiPBS",
            source_url="https://www.thaipbs.or.th/news/1",
            source_title="นายกฯ ลงพื้นที่น่าน",
            citation="สั่งการทุกหน่วยงานเร่งเยียวยา",
        )
        # Check primary fields
        assert event.event_description == "นายกฯ สั่งเร่งเยียวยาน้ำท่วมน่าน"
        assert event.source_name == "ThaiPBS"
        assert event.source_url == "https://www.thaipbs.or.th/news/1"
        assert event.source_title == "นายกฯ ลงพื้นที่น่าน"
        # Check backward-compatible base fields
        assert event.event == "นายกฯ สั่งเร่งเยียวยาน้ำท่วมน่าน"
        assert event.source == "ThaiPBS"
        assert event.url == "https://www.thaipbs.or.th/news/1"
        assert event.title == "นายกฯ ลงพื้นที่น่าน"
        assert event.citation == "สั่งการทุกหน่วยงานเร่งเยียวยา"

    def test_timeline_event_from_base_fields(self) -> None:
        event = TimelineEvent(
            timestamp="2026-08-23 14:35:26",
            event="น้ำป่าไหลหลากเส้นทางถูกตัดขาด",
            source="Bangkok Post",
            url="https://bangkokpost.com/news/2",
            title="Roads cut off by flood",
        )
        assert event.event_description == "น้ำป่าไหลหลากเส้นทางถูกตัดขาด"
        assert event.source_name == "Bangkok Post"
        assert event.source_url == "https://bangkokpost.com/news/2"
        assert event.source_title == "Roads cut off by flood"

    def test_citation_model_validation(self) -> None:
        c = Citation(
            source_name="ThaiPBS",
            source_url="https://www.thaipbs.or.th/news/content/509750",
            source_title="กรมบัญชีกลางอนุมัติเพิ่ม 100 ล้าน",
            quote="ขยายวงเงินทดรองราชการจาก 20 ล้านเป็น 100 ล้านบาท",
            timestamp="2026-08-22 14:35:11",
        )
        assert c.source_name == "ThaiPBS"
        assert c.quote is not None
        assert "100 ล้านบาท" in c.quote

    def test_story_presentation_property_aliases(self) -> None:
        p = StoryPresentation(
            story_id="s1",
            headline="หัวข้อข่าวสรุป",
            summary="เนื้อหาข่าวย่อ",
            timeline=[],
            citations=[{"source_name": "ThaiPBS", "source_url": "https://test.com"}],
        )
        assert p.generated_headline == "หัวข้อข่าวสรุป"
        assert p.synthesized_summary == "เนื้อหาข่าวย่อ"
        assert len(p.source_citations) == 1


# ── 2. LLM Presentation Generation & Cascading Tests ──────────────

class TestLLMPresentationGeneration:
    def test_successful_llm_presentation(self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "headline": "นายกฯ ตรวจน้ำท่วมน่าน ขยายงบ 100 ล้าน เฝ้าระวังบ่อเกลือ",
                        "summary": "นายกฯ อนุทิน ลงพื้นที่ตรวจสถานการณ์อุทกภัยใน จ.น่าน กำชับจ่ายเงินเยียวยาผู้ประสบภัย ขณะที่กรมบัญชีกลางอนุมัติงบฉุกเฉิน 100 ล้านบาท",
                        "timeline": [
                            {
                                "timestamp": "2026-08-22 14:35:11",
                                "event_description": "กรมบัญชีกลางอนุมัติงบ 100 ล้านบาท ช่วยน้ำท่วมน่าน",
                                "source_name": "ThaiPBS",
                                "source_url": "https://www.thaipbs.or.th/news/content/509750",
                                "source_title": "กรมบัญชีกลางอนุมัติเพิ่ม 100 ล้าน",
                            },
                            {
                                "timestamp": "2026-08-23 14:35:11",
                                "event_description": "นายกฯ ลงพื้นที่น่าน สั่งเร่งเยียวยาประชาชน",
                                "source_name": "ThaiPBS",
                                "source_url": "https://www.thaipbs.or.th/news/content/509767",
                                "source_title": "นายกฯ ไปน่าน ตรวจน้ำท่วม",
                            },
                        ],
                        "citations": [
                            {
                                "source_name": "ThaiPBS",
                                "source_url": "https://www.thaipbs.or.th/news/content/509750",
                                "source_title": "กรมบัญชีกลางอนุมัติเพิ่ม 100 ล้าน",
                                "quote": "ขยายวงเงินทดรองราชการเป็น 100 ล้านบาท",
                            }
                        ],
                    })
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("backend.config.settings.llm_api_key", "valid-test-key"):
            service = StoryPresentationService(
                client=mock_client,
                models=["gemini-3.5-flash-lite", "nova-2-lite-v1"],
            )
            presentation = service.present_story(sample_nan_story, sample_nan_articles)

        assert presentation.story_id == sample_nan_story.story_id
        assert presentation.headline == "นายกฯ ตรวจน้ำท่วมน่าน ขยายงบ 100 ล้าน เฝ้าระวังบ่อเกลือ"
        assert "อนุทิน" in presentation.summary
        assert presentation.is_fallback is False
        assert presentation.cached is False
        assert len(presentation.timeline) == 2
        assert presentation.timeline[0].source_name == "ThaiPBS"
        assert len(presentation.citations) == 1
        assert mock_client.chat.completions.create.call_count == 1
        assert mock_client.chat.completions.create.call_args.kwargs["model"] == "gemini-3.5-flash-lite"

    def test_llm_cascading_fallback_on_first_model_failure(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        mock_client = MagicMock()
        mock_response_2 = MagicMock()
        mock_response_2.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "headline": "พาดหัวข่าวจากโมเดลสำรอง",
                        "summary": "สรุปสถานการณ์จากโมเดลสำรอง",
                        "timeline": [
                            {
                                "timestamp": "2026-08-23 14:35:11",
                                "event_description": "ความคืบหน้าน้ำท่วม",
                                "source_name": "ThaiPBS",
                                "source_url": "https://thaipbs.or.th/1",
                                "source_title": "ข่าวน้ำท่วม",
                            }
                        ],
                        "citations": [],
                    })
                )
            )
        ]

        # First model fails with 429 quota error, second succeeds
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("Rate limit exceeded 429"),
            mock_response_2,
        ]

        with patch("backend.config.settings.llm_api_key", "valid-test-key"):
            service = StoryPresentationService(
                client=mock_client,
                models=["model-primary", "model-backup"],
            )
            presentation = service.present_story(sample_nan_story, sample_nan_articles)

        assert presentation.headline == "พาดหัวข่าวจากโมเดลสำรอง"
        assert presentation.is_fallback is False
        assert mock_client.chat.completions.create.call_count == 2
        assert mock_client.chat.completions.create.call_args_list[0].kwargs["model"] == "model-primary"
        assert mock_client.chat.completions.create.call_args_list[1].kwargs["model"] == "model-backup"


# ── 3. Robust Graceful Fallback Tests ─────────────────────────────

class TestRobustGracefulFallback:
    def test_fallback_when_api_key_is_missing(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        mock_client = MagicMock()
        with patch("backend.config.settings.llm_api_key", ""):
            service = StoryPresentationService(client=mock_client)
            presentation = service.present_story(sample_nan_story, sample_nan_articles)

        assert presentation.is_fallback is True
        assert presentation.headline != ""
        assert presentation.summary != ""
        assert len(presentation.timeline) == 4
        assert len(presentation.citations) == 4
        assert mock_client.chat.completions.create.call_count == 0

    def test_fallback_on_all_models_exception(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("APIConnectionError: Network unreachable"),
            RuntimeError("TimeoutError: Request timed out after 25s"),
        ]

        with patch("backend.config.settings.llm_api_key", "valid-key"):
            service = StoryPresentationService(
                client=mock_client,
                models=["model-1", "model-2"],
            )
            # Must NEVER raise exception
            presentation = service.present_story(sample_nan_story, sample_nan_articles)

        assert presentation.is_fallback is True
        assert presentation.headline != ""
        assert len(presentation.timeline) == 4
        assert len(presentation.citations) == 4
        assert mock_client.chat.completions.create.call_count == 2

    def test_fallback_on_malformed_llm_json(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="This is not valid JSON string at all."))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("backend.config.settings.llm_api_key", "valid-key"):
            service = StoryPresentationService(client=mock_client, models=["model-1"])
            presentation = service.present_story(sample_nan_story, sample_nan_articles)

        assert presentation.is_fallback is True
        assert presentation.headline != ""
        assert len(presentation.timeline) == 4

    def test_fallback_with_empty_articles_does_not_crash(self) -> None:
        story = StoryRecord(
            story_id="story_empty_001",
            title="ข่าวเหตุการณ์ที่ไม่มีบทความ",
            category="general",
        )
        service = StoryPresentationService(client=None)
        presentation = service.present_story(story, articles=[])

        assert presentation.is_fallback is True
        assert presentation.headline == "ข่าวเหตุการณ์ที่ไม่มีบทความ"
        assert presentation.timeline == []
        assert presentation.citations == []

    def test_fallback_timeline_is_chronological(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        service = StoryPresentationService(client=None)
        presentation = service.present_story(sample_nan_story, sample_nan_articles)

        timestamps = [t.timestamp for t in presentation.timeline]
        # Timestamps must be sorted in non-decreasing chronological order
        assert timestamps == sorted(timestamps)
        assert timestamps[0] == "2026-08-22 14:35:11"
        assert timestamps[-1] == "2026-08-23 14:35:26"

    def test_fallback_cleans_publisher_suffix_from_headline(self) -> None:
        articles = [
            {
                "title": "อนุทิน ลงพื้นที่เร่งเยียวยาน้ำท่วมน่าน | ThaiPBS",
                "summary": "ความคืบหน้าการลงพื้นที่ของนายกฯ อนุทิน ชาญวีรกูล",
                "source": "ThaiPBS",
                "url": "https://test.com/1",
                "fetched_at": "2026-08-23 10:00:00",
            }
        ]
        service = StoryPresentationService(client=None)
        presentation = service.present_story({"story_id": "s1", "title": "default"}, articles)
        assert presentation.headline == "อนุทิน ลงพื้นที่เร่งเยียวยาน้ำท่วมน่าน"
        assert "| ThaiPBS" not in presentation.headline


# ── 4. Caching Tests ──────────────────────────────────────────────

class TestStoryPresentationCaching:
    def test_cache_hit_on_identical_story_id_and_updated_at(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "headline": "หัวข้อข่าวครั้งแรก",
                        "summary": "สรุปครั้งแรก",
                        "timeline": [],
                        "citations": [],
                    })
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("backend.config.settings.llm_api_key", "valid-key"):
            service = StoryPresentationService(client=mock_client, models=["model-1"])

            # Call 1: Misses cache, calls LLM
            p1 = service.present_story(sample_nan_story, sample_nan_articles)
            assert p1.cached is False
            assert p1.headline == "หัวข้อข่าวครั้งแรก"
            assert mock_client.chat.completions.create.call_count == 1

            # Call 2: Hits cache, ZERO LLM calls
            p2 = service.present_story(sample_nan_story, sample_nan_articles)
            assert p2.cached is True
            assert p2.headline == "หัวข้อข่าวครั้งแรก"
            assert mock_client.chat.completions.create.call_count == 1  # Unchanged!

    def test_cache_miss_and_regeneration_when_updated_at_changes(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        mock_client = MagicMock()
        mock_resp_1 = MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
            "headline": "หัวข้อแรก", "summary": "สรุปแรก", "timeline": [], "citations": []
        })))])
        mock_resp_2 = MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
            "headline": "หัวข้อใหม่หลังอัปเดต", "summary": "สรุปใหม่", "timeline": [], "citations": []
        })))])
        mock_client.chat.completions.create.side_effect = [mock_resp_1, mock_resp_2]

        with patch("backend.config.settings.llm_api_key", "valid-key"):
            service = StoryPresentationService(client=mock_client, models=["model-1"])

            # Call 1 with original updated_at (2026-08-23 14:35:26)
            p1 = service.present_story(sample_nan_story, sample_nan_articles)
            assert p1.headline == "หัวข้อแรก"
            assert mock_client.chat.completions.create.call_count == 1

            # Story receives a new article! updated_at changes
            sample_nan_story.updated_at = datetime(2026, 8, 24, 9, 0, 0, tzinfo=timezone.utc)
            sample_nan_story.article_urls.append("https://new.article.url")

            # Call 2: Cache miss because updated_at changed -> regenerates
            p2 = service.present_story(sample_nan_story, sample_nan_articles)
            assert p2.cached is False
            assert p2.headline == "หัวข้อใหม่หลังอัปเดต"
            assert mock_client.chat.completions.create.call_count == 2

    def test_cache_eviction_and_clear(self) -> None:
        service = StoryPresentationService(client=None, cache_max_size=2)
        service.set_cached("s1", "2026-01-01 10:00:00", StoryPresentation(story_id="s1", headline="h1", summary="s1"))
        service.set_cached("s2", "2026-01-01 10:00:00", StoryPresentation(story_id="s2", headline="h2", summary="s2"))
        assert service.cache_size == 2

        # Add 3rd: should evict oldest (s1)
        service.set_cached("s3", "2026-01-01 10:00:00", StoryPresentation(story_id="s3", headline="h3", summary="s3"))
        assert service.cache_size == 2
        assert service.get_cached("s1", "2026-01-01 10:00:00") is None
        assert service.get_cached("s3", "2026-01-01 10:00:00") is not None

        service.clear_cache()
        assert service.cache_size == 0


# ── 5. Story Enrichment & Top Stories Tests ───────────────────────

class TestStoryEnrichment:
    def test_enrich_story_record(self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]) -> None:
        service = StoryPresentationService(client=None)
        enriched = service.enrich_story(sample_nan_story, sample_nan_articles)

        assert isinstance(enriched, StoryRecord)
        assert enriched.headline is not None
        assert enriched.summary is not None
        assert len(enriched.timeline) == 4
        assert enriched.enriched_at is not None
        assert "citations" in enriched.metadata
        assert enriched.metadata["is_fallback"] is True

    def test_present_story_with_article_record_instances(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        records = [ArticleRecord.model_validate(a) for a in sample_nan_articles]
        service = StoryPresentationService(client=None)
        pres = service.present_story(sample_nan_story, records)
        assert pres.headline != ""
        assert len(pres.timeline) == 4
        assert len(pres.citations) == 4

    def test_enrich_trending_cluster(
        self, sample_trending_cluster: TrendingStoryCluster, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        service = StoryPresentationService(client=None)
        enriched = service.enrich_story(sample_trending_cluster, sample_nan_articles)

        assert isinstance(enriched, TrendingStoryCluster)
        assert enriched.headline is not None
        assert enriched.summary is not None
        assert len(enriched.timeline) == 4
        assert "citations" in enriched.metadata

    def test_enrich_top_stories_limits_to_top_n(
        self, sample_trending_cluster: TrendingStoryCluster, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        cluster_1 = sample_trending_cluster.model_copy()
        cluster_2 = sample_trending_cluster.model_copy(update={"story_id": "c2", "headline": None, "summary": None})
        cluster_3 = sample_trending_cluster.model_copy(update={"story_id": "c3", "headline": None, "summary": None})

        clusters = [cluster_1, cluster_2, cluster_3]
        service = StoryPresentationService(client=None)

        # Enrich only top 2
        result = service.enrich_top_stories(clusters, top_n=2)
        assert len(result) == 3
        assert result[0].headline is not None
        assert result[1].headline is not None
        # 3rd should remain untouched
        assert result[2].headline is None

    @pytest.mark.anyio
    async def test_async_presentation_and_enrichment(
        self, sample_nan_story: StoryRecord, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        service = StoryPresentationService(client=None)
        pres = await service.present_story_async(sample_nan_story, sample_nan_articles)
        assert pres.headline != ""

        enriched = await service.enrich_story_async(sample_nan_story, sample_nan_articles)
        assert enriched.headline == pres.headline

        enriched_list = await service.enrich_top_stories_async([
            TrendingStoryCluster(
                story_id="s_async",
                title="async test",
                created_at="2026-08-23 10:00:00",
                updated_at="2026-08-23 10:00:00",
                articles=sample_nan_articles,
            )
        ], top_n=1)
        assert enriched_list[0].headline is not None


# ── 6. LLM Separation Principle Test ──────────────────────────────

class TestLLMSeparationPrinciple:
    def test_llm_presentation_does_not_alter_trending_rank_or_scores(
        self, sample_trending_cluster: TrendingStoryCluster, sample_nan_articles: list[dict[str, Any]]
    ) -> None:
        orig_score = sample_trending_cluster.trending_score
        orig_rank = sample_trending_cluster.rank
        orig_urls = list(sample_trending_cluster.article_urls)

        service = StoryPresentationService(client=None)
        service.enrich_story(sample_trending_cluster, sample_nan_articles)

        # Trending score, rank, and article membership must remain strictly identical
        assert sample_trending_cluster.trending_score == orig_score
        assert sample_trending_cluster.rank == orig_rank
        assert sample_trending_cluster.article_urls == orig_urls


# ── 7. Real Recorded Run Artifact Validation Test ─────────────────

class TestRealRecordedRunArtifact:
    def test_recorded_real_llm_presentation_output_exists_and_valid(self) -> None:
        artifact_path = Path(__file__).resolve().parent.parent.parent / "data" / "real_llm_presentation_output.json"
        assert artifact_path.exists(), f"Recorded run artifact {artifact_path} must exist"

        with artifact_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert "story_id" in data
        assert "headline" in data and len(data["headline"]) > 10
        assert "summary" in data and len(data["summary"]) > 20
        assert "timeline" in data and isinstance(data["timeline"], list) and len(data["timeline"]) >= 2
        assert "citations" in data and isinstance(data["citations"], list) and len(data["citations"]) >= 2

        # Check timeline event format
        for ev in data["timeline"]:
            assert "timestamp" in ev
            assert "event_description" in ev
            assert "source_name" in ev
            assert "source_url" in ev
            assert "source_title" in ev

        # Check citations format
        for cit in data["citations"]:
            assert "source_name" in cit
            assert "source_url" in cit
            assert "source_title" in cit
            assert "quote" in cit

        # Verify Thai content
        assert "น่าน" in data["headline"] or "น่าน" in data["summary"]

        # Verify dual outlet citations
        sources = {c["source_name"] for c in data["citations"]}
        assert "ThaiPBS" in sources
        assert "Bangkok Post" in sources


# ── 8. DI Factory Tests ───────────────────────────────────────────

class TestDIFactory:
    def test_get_story_presentation_service_singleton(self) -> None:
        reset_story_presentation_service()
        s1 = get_story_presentation_service()
        s2 = get_story_presentation_service()
        assert s1 is s2
        reset_story_presentation_service()
