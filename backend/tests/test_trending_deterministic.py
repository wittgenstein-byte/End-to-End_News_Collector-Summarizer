"""
backend/tests/test_trending_deterministic.py
─────────────────────────────────────────────────────────────────
Comprehensive tests for Milestone 3: Deterministic Trending Layer:
- Deterministic scoring: Zero LLM in scoring path, 100% reproducible ranking & scores
- Distinct outlet diversity with syndication discount (3 distinct outranks 3 from 1)
- Velocity / burst detection (recent burst outranks flat older volume)
- Story lifecycle gating (active eligible, dormant excluded, reactivated eligible under same story_id)
- Routine report suppression (lottery & weather dampening penalty)
- Reader engagement telemetry integration
- Recency exponential half-life decay
- Novelty signal relative to other active stories
- Explainable TrendingScoreBreakdown schema validation
- Configurable scoring weights via Settings
- 100% backward compatibility with legacy trending consumers
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.repo.engagement_repo import EngagementRepositoryPort
from backend.repo.news_repo import NewsRepositoryPort
from backend.repo.story_repo import StoryRepositoryPort
from backend.schemas.story_schema import StoryRecord
from backend.schemas.trending_schema import (
    TrendingScoreBreakdown,
)
from backend.services.trending_service import TrendingService

# ── In-Memory Repository Test Doubles ──────────────────────────────

class InMemoryStoryRepository(StoryRepositoryPort):
    def __init__(self, stories: list[StoryRecord] | None = None) -> None:
        self.stories: dict[str, StoryRecord] = {}
        self.url_map: dict[str, str] = {}
        if stories:
            for s in stories:
                self.save_story(s)

    def get_story(self, story_id: str) -> StoryRecord | None:
        return self.stories.get(story_id)

    def save_story(self, story: StoryRecord) -> None:
        self.stories[story.story_id] = story
        for u in story.article_urls:
            if u:
                self.url_map[u] = story.story_id

    def save_stories_batch(self, stories: list[StoryRecord]) -> None:
        for s in stories:
            self.save_story(s)

    def list_stories(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoryRecord]:
        items = list(self.stories.values())
        items.sort(key=lambda s: s.updated_at, reverse=True)
        if status and status.strip().lower() != "all":
            target = status.strip().lower()
            items = [s for s in items if s.status.lower() == target]
        return items[offset : offset + limit]

    def find_candidate_stories(
        self,
        since_time: datetime,
        category: str | None = None,
    ) -> list[StoryRecord]:
        norm_since = since_time if since_time.tzinfo else since_time.replace(tzinfo=timezone.utc)
        items = [s for s in self.stories.values() if s.updated_at >= norm_since]
        if category and category.strip().lower() != "all":
            items = [s for s in items if s.category.lower() == category.strip().lower()]
        items.sort(key=lambda s: s.updated_at, reverse=True)
        return items

    def get_stories_by_ids(self, story_ids: list[str]) -> list[StoryRecord]:
        return [self.stories[sid] for sid in story_ids if sid in self.stories]

    def get_story_by_article_url(self, url: str) -> StoryRecord | None:
        sid = self.url_map.get(url)
        return self.stories.get(sid) if sid else None

    def count_stories(self, status: str | None = None) -> int:
        if not status or status.strip().lower() == "all":
            return len(self.stories)
        target = status.strip().lower()
        return sum(1 for s in self.stories.values() if s.status.lower() == target)


class InMemoryNewsRepository(NewsRepositoryPort):
    def __init__(self, articles: list[dict[str, Any]] | None = None) -> None:
        self.articles = articles or []
        self.seen: set[str] = set()

    def load_news(self) -> list[dict[str, Any]]:
        return list(self.articles)

    def save_news(self, data: list[dict[str, Any]]) -> None:
        self.articles = list(data)

    def load_seen(self) -> set[str]:
        return set(self.seen)

    def save_seen(self, seen: set[str]) -> None:
        self.seen = set(seen)

    def query_news(
        self,
        page: int = 1,
        page_size: int = 20,
        source: str = "",
        category: str | None = None,
        query: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        items = list(self.articles)
        if source:
            items = [a for a in items if a.get("source") == source]
        if category and category != "all":
            items = [a for a in items if a.get("category") == category]
        if query:
            items = [a for a in items if query.lower() in str(a.get("title", "")).lower()]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    def get_category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self.articles:
            cat = str(a.get("category") or "other")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def get_source_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self.articles:
            src = str(a.get("source") or "unknown")
            counts[src] = counts.get(src, 0) + 1
        return counts


class InMemoryEngagementRepository(EngagementRepositoryPort):
    def __init__(self) -> None:
        self.engagements: dict[str, dict[str, int]] = {}

    def record_event(self, url: str, event_type: str) -> dict[str, int]:
        norm_url = url.strip()
        field_map = {"click": "clicks", "summary": "summaries", "bookmark": "bookmarks"}
        field = field_map.get(event_type.strip().lower())
        stats = self.engagements.setdefault(norm_url, {"clicks": 0, "summaries": 0, "bookmarks": 0})
        if field:
            stats[field] += 1
        return dict(stats)

    def get_engagement(self, url: str) -> dict[str, int]:
        return dict(self.engagements.get(url.strip(), {"clicks": 0, "summaries": 0, "bookmarks": 0}))

    def get_all_engagements(self) -> dict[str, dict[str, int]]:
        return {k: dict(v) for k, v in self.engagements.items()}

    def clear_all(self) -> None:
        self.engagements.clear()


# ── Test Suite ─────────────────────────────────────────────────────

class TestDeterministicTrendingEngine:
    """Verifies all R2 Trending Acceptance Criteria."""

    @pytest.fixture
    def fixed_now(self) -> datetime:
        return datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)

    def test_scoring_is_strictly_deterministic_across_repeated_runs(self, fixed_now: datetime) -> None:
        """
        Acceptance Criteria: scoring is deterministic — identical input produces
        identical ranking and scores across runs, with no LLM call in the scoring path.
        """
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        # Create two active stories
        story_a = StoryRecord(
            story_id="story_a",
            title="นายกฯ ลงพื้นที่ช่วยเหลือน้ำท่วมภาคเหนือ",
            category="politics",
            status="active",
            created_at=fixed_now - timedelta(hours=8),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=["https://thaipbs.or.th/1", "https://thestandard.co/2", "https://thairath.co.th/3"],
            article_count=3,
            outlet_count=3,
            outlets=["ThaiPBS", "The Standard", "Thairath"],
        )
        story_b = StoryRecord(
            story_id="story_b",
            title="ราคาทองคำปรับขึ้นต่อเนื่องทำสถิติสูงสุดใหม่",
            category="economy",
            status="active",
            created_at=fixed_now - timedelta(hours=12),
            updated_at=fixed_now - timedelta(hours=2),
            article_urls=["https://thairath.co.th/gold1", "https://matichon.co.th/gold2"],
            article_count=2,
            outlet_count=2,
            outlets=["Thairath", "Matichon"],
        )
        story_repo.save_story(story_a)
        story_repo.save_story(story_b)

        articles_data = [
            {"url": "https://thaipbs.or.th/1", "title": "นายกฯ ตรวจน้ำท่วม", "source": "ThaiPBS", "fetched_at": "2026-10-11 11:00:00"},
            {"url": "https://thestandard.co/2", "title": "น้ำท่วมภาคเหนือวิกฤต", "source": "The Standard", "fetched_at": "2026-10-11 10:30:00"},
            {"url": "https://thairath.co.th/3", "title": "รัฐบาลระดมกำลังช่วยน้ำท่วม", "source": "Thairath", "fetched_at": "2026-10-11 10:00:00"},
            {"url": "https://thairath.co.th/gold1", "title": "ราคาทองพุ่งแรง", "source": "Thairath", "fetched_at": "2026-10-11 09:30:00"},
            {"url": "https://matichon.co.th/gold2", "title": "ทองคำทำนิวไฮ", "source": "Matichon", "fetched_at": "2026-10-11 09:00:00"},
        ]
        news_repo.save_news(articles_data)

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )

        # Execute 50 consecutive scoring runs
        baseline_results = service.get_trending_stories(limit=10, now=fixed_now)
        assert len(baseline_results) == 2

        for _ in range(50):
            run_results = service.get_trending_stories(limit=10, now=fixed_now)
            assert len(run_results) == len(baseline_results)
            for b, r in zip(baseline_results, run_results):
                assert b.story_id == r.story_id
                assert b.trending_score == r.trending_score
                assert b.rank == r.rank
                assert b.breakdown.volume_score == r.breakdown.volume_score
                assert b.breakdown.velocity_score == r.breakdown.velocity_score
                assert b.breakdown.diversity_score == r.breakdown.diversity_score
                assert b.breakdown.recency_score == r.breakdown.recency_score
                assert b.breakdown.final_score == r.breakdown.final_score

    def test_zero_llm_calls_in_scoring_path(self, fixed_now: datetime) -> None:
        """Verify that strictly ZERO LLM calls are invoked during deterministic scoring."""
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        story = StoryRecord(
            story_id="story_1",
            title="ข่าวทดสอบ",
            category="politics",
            status="active",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=["https://example.com/1"],
            article_count=1,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )
        story_repo.save_story(story)
        news_repo.save_news([{"url": "https://example.com/1", "title": "ข่าวทดสอบ", "source": "ThaiPBS", "fetched_at": "2026-10-11 11:00:00"}])

        mock_llm_enricher = MagicMock()

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
            llm_enricher=mock_llm_enricher,
        )

        results = service.get_trending_stories(limit=5, now=fixed_now)
        assert len(results) == 1

        # Assert zero LLM enricher calls in scoring path
        assert mock_llm_enricher.enrich_clusters.call_count == 0
        assert mock_llm_enricher.call_count == 0

    def test_distinct_outlets_outranks_single_outlet_volume(self, fixed_now: datetime) -> None:
        """
        Acceptance Criteria: a story covered by 3 distinct outlets outranks
        an otherwise-equivalent story with 3 articles from one outlet.
        """
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        same_created = fixed_now - timedelta(hours=4)
        same_updated = fixed_now - timedelta(hours=1)

        # Story Multi: 3 articles from 3 distinct outlets
        story_multi = StoryRecord(
            story_id="story_multi",
            title="วิกฤตน้ำท่วมฉับพลันภาคเหนือ",
            category="society",
            status="active",
            created_at=same_created,
            updated_at=same_updated,
            article_urls=["https://thaipbs.or.th/m1", "https://thestandard.co/m2", "https://thairath.co.th/m3"],
            article_count=3,
            outlet_count=3,
            outlets=["ThaiPBS", "The Standard", "Thairath"],
        )

        # Story Single: 3 articles all from a single outlet (syndicated / repeated)
        story_single = StoryRecord(
            story_id="story_single",
            title="ความคืบหน้าอุบัติเหตุสะพานข้ามแยก",
            category="society",
            status="active",
            created_at=same_created,
            updated_at=same_updated,
            article_urls=["https://thaipbs.or.th/s1", "https://thaipbs.or.th/s2", "https://thaipbs.or.th/s3"],
            article_count=3,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )

        story_repo.save_story(story_multi)
        story_repo.save_story(story_single)

        t_str = same_updated.strftime("%Y-%m-%d %H:%M:%S")
        articles = [
            {"url": "https://thaipbs.or.th/m1", "title": "น้ำท่วมฉับพลัน", "source": "ThaiPBS", "fetched_at": t_str},
            {"url": "https://thestandard.co/m2", "title": "น้ำท่วมฉับพลัน", "source": "The Standard", "fetched_at": t_str},
            {"url": "https://thairath.co.th/m3", "title": "น้ำท่วมฉับพลัน", "source": "Thairath", "fetched_at": t_str},
            {"url": "https://thaipbs.or.th/s1", "title": "อุบัติเหตุสะพาน", "source": "ThaiPBS", "fetched_at": t_str},
            {"url": "https://thaipbs.or.th/s2", "title": "อุบัติเหตุสะพาน", "source": "ThaiPBS", "fetched_at": t_str},
            {"url": "https://thaipbs.or.th/s3", "title": "อุบัติเหตุสะพาน", "source": "ThaiPBS", "fetched_at": t_str},
        ]
        news_repo.save_news(articles)

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )

        results = service.get_trending_stories(limit=10, now=fixed_now)
        assert len(results) == 2

        # 3 distinct outlets MUST rank #1, outranking 3 articles from 1 outlet
        assert results[0].story_id == "story_multi"
        assert results[1].story_id == "story_single"
        assert results[0].trending_score > results[1].trending_score

        # Check breakdown diversity score
        assert results[0].breakdown.diversity_score > results[1].breakdown.diversity_score

    def test_recent_burst_outranks_flat_older_volume(self, fixed_now: datetime) -> None:
        """
        Acceptance Criteria: a story with a recent burst outranks an otherwise-equivalent
        story with the same total volume spread evenly over older time.
        """
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        # Both stories have exactly 6 articles from the same 2 outlets
        outlets = ["ThaiPBS", "The Standard"]

        # Story Burst: all 6 articles arrived recently in a sudden burst (1-4 hours ago)
        burst_urls = [f"https://burst.com/{i}" for i in range(6)]
        story_burst = StoryRecord(
            story_id="story_burst",
            title="เหตุการณ์กราดยิงกลางห้างดัง",
            category="crime",
            status="active",
            created_at=fixed_now - timedelta(hours=4),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=burst_urls,
            article_count=6,
            outlet_count=2,
            outlets=outlets,
        )

        # Story Flat: 6 articles spread evenly over older days (1 recent, 5 between 30h-65h ago)
        flat_urls = [f"https://flat.com/{i}" for i in range(6)]
        story_flat = StoryRecord(
            story_id="story_flat",
            title="การพิจารณาคดีการเมืองยืดเยื้อ",
            category="crime",
            status="active",
            created_at=fixed_now - timedelta(hours=70),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=flat_urls,
            article_count=6,
            outlet_count=2,
            outlets=outlets,
        )

        story_repo.save_story(story_burst)
        story_repo.save_story(story_flat)

        burst_articles = [
            {
                "url": burst_urls[i],
                "title": "เหตุกราดยิง",
                "source": outlets[i % 2],
                "fetched_at": (fixed_now - timedelta(hours=1 + i * 0.5)).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for i in range(6)
        ]

        flat_articles = [
            # 1 recent article
            {
                "url": flat_urls[0],
                "title": "พิจารณาคดี",
                "source": outlets[0],
                "fetched_at": (fixed_now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            # 5 older distributed articles
            {
                "url": flat_urls[1],
                "title": "พิจารณาคดี",
                "source": outlets[1],
                "fetched_at": (fixed_now - timedelta(hours=32)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "url": flat_urls[2],
                "title": "พิจารณาคดี",
                "source": outlets[0],
                "fetched_at": (fixed_now - timedelta(hours=42)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "url": flat_urls[3],
                "title": "พิจารณาคดี",
                "source": outlets[1],
                "fetched_at": (fixed_now - timedelta(hours=50)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "url": flat_urls[4],
                "title": "พิจารณาคดี",
                "source": outlets[0],
                "fetched_at": (fixed_now - timedelta(hours=58)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "url": flat_urls[5],
                "title": "พิจารณาคดี",
                "source": outlets[1],
                "fetched_at": (fixed_now - timedelta(hours=65)).strftime("%Y-%m-%d %H:%M:%S"),
            },
        ]

        news_repo.save_news(burst_articles + flat_articles)

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )

        results = service.get_trending_stories(limit=10, now=fixed_now)
        assert len(results) == 2

        # Story Burst MUST strictly outrank Story Flat
        assert results[0].story_id == "story_burst"
        assert results[1].story_id == "story_flat"
        assert results[0].trending_score > results[1].trending_score

        # Check velocity score in breakdown
        assert results[0].breakdown.velocity_score > results[1].breakdown.velocity_score

    def test_dormant_stories_excluded_and_reactivated_eligible_under_same_id(self, fixed_now: datetime) -> None:
        """
        Acceptance Criteria: dormant stories are not ranked; a dormant story that receives
        new articles becomes eligible again under the same story id.
        """
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        # Story Active
        story_active = StoryRecord(
            story_id="story_active",
            title="ข่าวประจำวันทั่วไป",
            category="society",
            status="active",
            created_at=fixed_now - timedelta(hours=5),
            updated_at=fixed_now - timedelta(hours=2),
            article_urls=["https://active.com/1"],
            article_count=1,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )

        # Story Dormant (received no articles for 5 days)
        story_dormant = StoryRecord(
            story_id="story_dormant_123",
            title="ข่าวเรื่องเก่าที่เงียบไปแล้ว",
            category="society",
            status="dormant",
            created_at=fixed_now - timedelta(days=10),
            updated_at=fixed_now - timedelta(days=5),
            article_urls=["https://dormant.com/1"],
            article_count=1,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )

        story_repo.save_story(story_active)
        story_repo.save_story(story_dormant)

        news_repo.save_news([
            {"url": "https://active.com/1", "title": "ข่าวประจำวันทั่วไป", "source": "ThaiPBS", "fetched_at": "2026-10-11 10:00:00"},
            {"url": "https://dormant.com/1", "title": "ข่าวเรื่องเก่า", "source": "ThaiPBS", "fetched_at": "2026-10-06 10:00:00"},
        ])

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )

        # Step 1: Dormant story must NOT be ranked
        initial_trending = service.get_trending_stories(limit=10, now=fixed_now)
        ranked_ids = [s.story_id for s in initial_trending]
        assert "story_active" in ranked_ids
        assert "story_dormant_123" not in ranked_ids

        # Step 2: Story receives a breaking update article, reactivating it
        new_url = "https://dormant.com/new_update"
        new_time = fixed_now - timedelta(minutes=30)
        story_dormant.add_article(
            url=new_url,
            source="The Standard",
            article_time=new_time,
        )
        assert story_dormant.status == "active"
        story_repo.save_story(story_dormant)

        news_repo.save_news([
            {"url": "https://active.com/1", "title": "ข่าวประจำวันทั่วไป", "source": "ThaiPBS", "fetched_at": "2026-10-11 10:00:00"},
            {"url": "https://dormant.com/1", "title": "ข่าวเรื่องเก่า", "source": "ThaiPBS", "fetched_at": "2026-10-06 10:00:00"},
            {"url": new_url, "title": "ความคืบหน้าครั้งสำคัญของข่าวเก่า", "source": "The Standard", "fetched_at": new_time.strftime("%Y-%m-%d %H:%M:%S")},
        ])

        # Step 3: Now the reactivated story must be eligible under the same story_id
        reactivated_trending = service.get_trending_stories(limit=10, now=fixed_now)
        reactivated_ids = [s.story_id for s in reactivated_trending]
        assert "story_dormant_123" in reactivated_ids
        reactivated_cluster = next(s for s in reactivated_trending if s.story_id == "story_dormant_123")
        assert reactivated_cluster.status == "active"
        assert new_url in reactivated_cluster.article_urls

    def test_routine_report_suppression_dampens_lottery_and_weather(self, fixed_now: datetime) -> None:
        """
        Acceptance Criteria / R2: Routine/recurring reports (lottery results, weather forecasts)
        must not be inflated into top trending stories.
        """
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        # Story 1: Breaking national news with moderate volume (3 articles)
        story_breaking = StoryRecord(
            story_id="story_breaking",
            title="เกิดเหตุด่วน รถไฟตกรางที่สถานีชุมทางบ้านภาชี มีผู้บาดเจ็บ",
            category="society",
            status="active",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(minutes=30),
            article_urls=["https://news.com/b1", "https://news.com/b2", "https://news.com/b3"],
            article_count=3,
            outlet_count=3,
            outlets=["ThaiPBS", "The Standard", "Thairath"],
        )

        # Story 2: Routine Lottery result with high volume (8 articles)
        lottery_urls = [f"https://lotto.com/{i}" for i in range(8)]
        story_lottery = StoryRecord(
            story_id="story_lottery",
            title="ตรวจหวย ผลสลากกินแบ่งรัฐบาล งวดประจำวันที่ 16 ตุลาคม 2569 ผลรางวัลที่ 1",
            category="lottery",
            status="active",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(minutes=30),
            article_urls=lottery_urls,
            article_count=8,
            outlet_count=4,
            outlets=["Thairath", "Sanook", "Khaosod", "DailyNews"],
        )

        # Story 3: Routine Weather forecast
        weather_urls = [f"https://weather.com/{i}" for i in range(5)]
        story_weather = StoryRecord(
            story_id="story_weather",
            title="กรมอุตุนิยมวิทยา พยากรณ์อากาศ 24 ชั่วโมงข้างหน้า ฝนตกทั่วไทย",
            category="weather",
            status="active",
            created_at=fixed_now - timedelta(hours=3),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=weather_urls,
            article_count=5,
            outlet_count=3,
            outlets=["ThaiPBS", "Thairath", "Matichon"],
        )

        story_repo.save_story(story_breaking)
        story_repo.save_story(story_lottery)
        story_repo.save_story(story_weather)

        all_articles = [
            {"url": u, "title": "รถไฟตกราง", "source": "ThaiPBS", "fetched_at": (fixed_now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")}
            for u in story_breaking.article_urls
        ] + [
            {"url": u, "title": "ตรวจหวย ผลสลาก", "source": "Thairath", "fetched_at": (fixed_now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")}
            for u in lottery_urls
        ] + [
            {"url": u, "title": "พยากรณ์อากาศประจำวัน", "source": "ThaiPBS", "fetched_at": (fixed_now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")}
            for u in weather_urls
        ]
        news_repo.save_news(all_articles)

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
            routine_penalty_factor=0.25,
        )

        # Verify routine detection
        assert service.is_routine_story(story_lottery) is True
        assert service.is_routine_story(story_weather) is True
        assert service.is_routine_story(story_breaking) is False

        results = service.get_trending_stories(limit=10, now=fixed_now)
        assert len(results) == 3

        # Breaking news MUST be #1 despite lottery having more articles
        assert results[0].story_id == "story_breaking"

        # Check breakdown routine suppression penalty
        lottery_res = next(r for r in results if r.story_id == "story_lottery")
        assert lottery_res.is_routine is True
        assert lottery_res.breakdown.is_routine is True
        assert lottery_res.breakdown.routine_penalty == 0.25
        assert "⚠️ Routine" in lottery_res.badges

    def test_reader_engagement_boosts_trending_score(self, fixed_now: datetime) -> None:
        """Verify that reader engagement telemetry (clicks, summaries, bookmarks) boosts score."""
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        # Story High Engagement
        story_eng = StoryRecord(
            story_id="story_eng",
            title="การค้นพบทางวิทยาศาสตร์ครั้งสำคัญ",
            category="science",
            status="active",
            created_at=fixed_now - timedelta(hours=3),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=["https://science.com/eng1"],
            article_count=1,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )

        # Story Zero Engagement (identical in volume, outlets, recency)
        story_no_eng = StoryRecord(
            story_id="story_no_eng",
            title="ข่าวประชาสัมพันธ์ทั่วไป",
            category="science",
            status="active",
            created_at=fixed_now - timedelta(hours=3),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=["https://science.com/no_eng1"],
            article_count=1,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )

        story_repo.save_story(story_eng)
        story_repo.save_story(story_no_eng)

        news_repo.save_news([
            {"url": "https://science.com/eng1", "title": "วิทยาศาสตร์", "source": "ThaiPBS", "fetched_at": "2026-10-11 11:00:00"},
            {"url": "https://science.com/no_eng1", "title": "ประชาสัมพันธ์", "source": "ThaiPBS", "fetched_at": "2026-10-11 11:00:00"},
        ])

        # Record reader engagement for story_eng
        for _ in range(30):
            eng_repo.record_event("https://science.com/eng1", "click")
        for _ in range(10):
            eng_repo.record_event("https://science.com/eng1", "summary")
        for _ in range(5):
            eng_repo.record_event("https://science.com/eng1", "bookmark")

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )

        results = service.get_trending_stories(limit=10, now=fixed_now)
        assert len(results) == 2

        assert results[0].story_id == "story_eng"
        assert results[1].story_id == "story_no_eng"
        assert results[0].trending_score > results[1].trending_score
        assert results[0].breakdown.engagement_score > results[1].breakdown.engagement_score

    def test_recency_half_life_exponential_decay(self, fixed_now: datetime) -> None:
        """Verify mathematical adherence to recency half-life decay (12h half-life)."""
        service = TrendingService(
            news_repo=InMemoryNewsRepository(),
            engagement_repo=InMemoryEngagementRepository(),
            story_repo=InMemoryStoryRepository(),
            recency_half_life_hours=12.0,
        )

        # Fresh right now: dt = 0 -> decay = 1.0
        story_0h = StoryRecord(
            title="ข่าว 0h",
            category="society",
            updated_at=fixed_now,
        )
        decay_0 = service.compute_recency_decay(story_0h, fixed_now)
        assert pytest.approx(decay_0, abs=1e-3) == 1.0

        # 12 hours ago: dt = 12h -> decay = 0.5
        story_12h = StoryRecord(
            title="ข่าว 12h",
            category="society",
            updated_at=fixed_now - timedelta(hours=12),
        )
        decay_12 = service.compute_recency_decay(story_12h, fixed_now)
        assert pytest.approx(decay_12, abs=1e-3) == 0.5

        # 24 hours ago: dt = 24h -> decay = 0.25
        story_24h = StoryRecord(
            title="ข่าว 24h",
            category="society",
            updated_at=fixed_now - timedelta(hours=24),
        )
        decay_24 = service.compute_recency_decay(story_24h, fixed_now)
        assert pytest.approx(decay_24, abs=1e-3) == 0.25

    def test_novelty_signal_rewards_unique_topics(self, fixed_now: datetime) -> None:
        """Verify that a story covering a unique topic receives higher novelty credit."""
        service = TrendingService(
            news_repo=InMemoryNewsRepository(),
            engagement_repo=InMemoryEngagementRepository(),
            story_repo=InMemoryStoryRepository(),
        )

        dim = 768
        # Story A and Story B are nearly identical topics (cosine ~ 0.95)
        vec_base = [1.0] + [0.0] * (dim - 1)
        vec_near = [0.95, 0.3122] + [0.0] * (dim - 2)

        # Story C is unique / orthogonal (cosine = 0.0)
        vec_unique = [0.0, 0.0, 1.0] + [0.0] * (dim - 3)

        story_a = StoryRecord(story_id="sa", title="A", category="a", centroid=vec_base)
        story_b = StoryRecord(story_id="sb", title="B", category="b", centroid=vec_near)
        story_c = StoryRecord(story_id="sc", title="C", category="c", centroid=vec_unique)

        active_peers = [story_a, story_b, story_c]

        novelty_near = service.compute_novelty(story_b, active_peers)
        novelty_unique = service.compute_novelty(story_c, active_peers)

        # Unique story must have significantly higher novelty than near-duplicate
        assert novelty_unique > novelty_near
        assert novelty_unique >= 0.8
        assert novelty_near <= 0.15

    def test_explainable_breakdown_schema_completeness(self, fixed_now: datetime) -> None:
        """Verify that TrendingScoreBreakdown exposes all per-signal components and details."""
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        story = StoryRecord(
            story_id="story_comp",
            title="ข่าวทดสอบโครงสร้าง Breakdown",
            category="society",
            status="active",
            created_at=fixed_now - timedelta(hours=5),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=["https://test.com/1", "https://test.com/2"],
            article_count=2,
            outlet_count=2,
            outlets=["ThaiPBS", "Thairath"],
        )
        story_repo.save_story(story)
        news_repo.save_news([
            {"url": "https://test.com/1", "title": "ข่าว 1", "source": "ThaiPBS", "fetched_at": "2026-10-11 11:00:00"},
            {"url": "https://test.com/2", "title": "ข่าว 2", "source": "Thairath", "fetched_at": "2026-10-11 10:30:00"},
        ])

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )

        results = service.get_trending_stories(limit=5, now=fixed_now)
        assert len(results) == 1
        cluster = results[0]

        bd: TrendingScoreBreakdown = cluster.breakdown
        assert isinstance(bd.volume_score, float)
        assert isinstance(bd.velocity_score, float)
        assert isinstance(bd.diversity_score, float)
        assert isinstance(bd.recency_score, float)
        assert isinstance(bd.novelty_score, float)
        assert isinstance(bd.engagement_score, float)
        assert isinstance(bd.routine_penalty, float)
        assert isinstance(bd.final_score, float)
        assert isinstance(bd.is_routine, bool)

        # Details map should contain exact telemetry counts
        assert "recent_articles" in bd.details
        assert "distinct_outlets" in bd.details
        assert "clicks" in bd.details
        assert bd.details["distinct_outlets"] == 2

    def test_configurable_weights_alter_ranking(self, fixed_now: datetime) -> None:
        """Verify that configurable weights in Settings/constructor change ranking priorities."""
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        # Story High Volume, Low Diversity (10 articles from 1 outlet)
        story_vol = StoryRecord(
            story_id="story_vol",
            title="ข่าวเจาะลึกพิเศษสำนักพิมพ์เดียว",
            category="society",
            status="active",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=[f"https://vol.com/{i}" for i in range(10)],
            article_count=10,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )

        # Story High Diversity, Lower Volume (3 articles from 3 outlets)
        story_div = StoryRecord(
            story_id="story_div",
            title="ข่าวหลากหลายสำนักพิมพ์",
            category="society",
            status="active",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=[f"https://div.com/{i}" for i in range(3)],
            article_count=3,
            outlet_count=3,
            outlets=["ThaiPBS", "The Standard", "Thairath"],
        )

        story_repo.save_story(story_vol)
        story_repo.save_story(story_div)

        t_str = (fixed_now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        articles = [
            {"url": u, "title": "เจาะลึก", "source": "ThaiPBS", "fetched_at": t_str}
            for u in story_vol.article_urls
        ] + [
            {"url": story_div.article_urls[0], "title": "หลากหลาย 1", "source": "ThaiPBS", "fetched_at": t_str},
            {"url": story_div.article_urls[1], "title": "หลากหลาย 2", "source": "The Standard", "fetched_at": t_str},
            {"url": story_div.article_urls[2], "title": "หลากหลาย 3", "source": "Thairath", "fetched_at": t_str},
        ]
        news_repo.save_news(articles)

        # Service 1: Heavy Diversity Weight
        service_div_heavy = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
            volume_weight=0.1,
            velocity_weight=0.1,
            diversity_weight=10.0,
        )
        res_div = service_div_heavy.get_trending_stories(limit=2, now=fixed_now)
        assert res_div[0].story_id == "story_div"

        # Service 2: Heavy Volume Weight
        service_vol_heavy = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
            volume_weight=5.0,
            diversity_weight=0.1,
        )
        res_vol = service_vol_heavy.get_trending_stories(limit=2, now=fixed_now)
        assert res_vol[0].story_id == "story_vol"

    def test_empty_story_repository_handled_gracefully(self, fixed_now: datetime) -> None:
        """Verify boundary condition: empty repository returns empty list without error."""
        service = TrendingService(
            news_repo=InMemoryNewsRepository(),
            engagement_repo=InMemoryEngagementRepository(),
            story_repo=InMemoryStoryRepository(),
        )
        results = service.get_trending_stories(limit=10, now=fixed_now)
        assert results == []

    def test_category_filtering_in_trending_stories(self, fixed_now: datetime) -> None:
        """Verify category filtering narrows ranked active stories."""
        news_repo = InMemoryNewsRepository()
        story_repo = InMemoryStoryRepository()
        eng_repo = InMemoryEngagementRepository()

        story_pol = StoryRecord(
            story_id="story_pol",
            title="การประชุมสภาผู้แทนราษฎร",
            category="politics",
            status="active",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=["https://pol.com/1"],
            article_count=1,
            outlet_count=1,
            outlets=["ThaiPBS"],
        )
        story_eco = StoryRecord(
            story_id="story_eco",
            title="ตลาดหุ้นไทยปิดบวก 15 จุด",
            category="economy",
            status="active",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(hours=1),
            article_urls=["https://eco.com/1"],
            article_count=1,
            outlet_count=1,
            outlets=["Thairath"],
        )
        story_repo.save_story(story_pol)
        story_repo.save_story(story_eco)

        news_repo.save_news([
            {"url": "https://pol.com/1", "title": "ประชุมสภา", "source": "ThaiPBS", "fetched_at": "2026-10-11 11:00:00"},
            {"url": "https://eco.com/1", "title": "ตลาดหุ้น", "source": "Thairath", "fetched_at": "2026-10-11 11:00:00"},
        ])

        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )

        pol_results = service.get_trending_stories(category="politics", limit=10, now=fixed_now)
        assert len(pol_results) == 1
        assert pol_results[0].story_id == "story_pol"

        eco_results = service.get_trending_stories(category="economy", limit=10, now=fixed_now)
        assert len(eco_results) == 1
        assert eco_results[0].story_id == "story_eco"
