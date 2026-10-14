"""
tests/test_trending_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Comprehensive test suite for trending & hot news detection,
          text clustering, half-life time decay, reader engagement telemetry,
          and FastAPI trending router endpoints.
GRASP  Information Expert — Validates algorithmic formulas, ranking accuracy,
          badges, concurrency safety, and zero PII storage.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import concurrent.futures
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.repo.engagement_repo import FileEngagementRepository, get_engagement_repository
from backend.repo.news_repo import NewsRepositoryPort
from backend.schemas.trending_schema import TrendingArticle, TrendingListResponse
from backend.services.trending_service import (
    SemanticClusterer,
    TrendingService,
    _proxy_image_url,
    parse_article_time,
)

# ── Mock Repositories for Isolated Testing ────────────────────────

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


class InMemoryEngagementRepository:
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


# ── 1. SemanticClusterer Tests (Strictly Zero Jaccard) ─────────────

class TestSemanticClusterer:
    """Test vector cosine clustering, temporal windows, and multi-source consensus."""

    def test_cluster_articles_grouping_by_similarity_and_time(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        clusterer = SemanticClusterer(cosine_threshold=0.70, time_window_hours=36.0)

        articles = [
            {
                "title": "นายกฯ แถลง นโยบาย ดิจิทัลวอลเล็ต ต่อ รัฐสภา",
                "source": "ThaiPBS",
                "url": "https://thaipbs.or.th/news/1",
                "fetched_at": "2026-08-22 11:00:00",
            },
            {
                "title": "นายกฯ แถลง นโยบาย ดิจิทัลวอลเล็ต เข้า สภาผู้แทนราษฎร",
                "source": "The Standard",
                "url": "https://thestandard.co/news/2",
                "fetched_at": "2026-08-22 10:30:00",
            },
            {
                "title": "ราคาทองคำ วันนี้ ปรับขึ้น 200 บาท",
                "source": "Thairath",
                "url": "https://thairath.co.th/news/3",
                "fetched_at": "2026-08-22 09:00:00",
            },
        ]

        # Art 1 & Art 2 are identical vector direction [1, 0]; Art 3 is orthogonal [0, 1]
        embeddings = np.array([
            [1.0, 0.0],
            [0.95, 0.3122],  # dot with Art 1 = 0.95 >= 0.70
            [0.0, 1.0],      # dot with Art 1 = 0.0, dot with Art 2 = 0.31
        ], dtype=np.float32)

        times = [now, now, now]
        results = clusterer.cluster_articles(articles, embeddings, times)
        assert len(results) == 3

        # First two articles should be in a cluster of size 2 with 2 distinct sources
        assert results[0]["cluster_size"] == 2
        assert results[0]["distinct_source_count"] == 2
        assert "ThaiPBS" in results[0]["cluster_sources"]
        assert "The Standard" in results[0]["cluster_sources"]
        assert results[0]["is_multi_source"] is True

        assert results[1]["cluster_size"] == 2
        assert results[1]["distinct_source_count"] == 2

        # Third article is isolated
        assert results[2]["cluster_size"] == 1
        assert results[2]["distinct_source_count"] == 1
        assert results[2]["cluster_sources"] == ["Thairath"]
        assert results[2]["is_multi_source"] is False

    def test_cluster_articles_same_publisher_dedup(self) -> None:
        """Multiple articles covering same topic by same publisher yield distinct_source_count = 1."""
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        clusterer = SemanticClusterer(cosine_threshold=0.70, time_window_hours=36.0)

        articles = [
            {
                "title": "นายกฯ สั่งการ น้ำท่วม ภาคเหนือ เร่งช่วยเหลือ",
                "source": "ThaiPBS",
                "url": "https://thaipbs.or.th/news/101",
                "fetched_at": "2026-08-22 11:00:00",
            },
            {
                "title": "นายกฯ ติดตาม น้ำท่วม ภาคเหนือ สั่งระดมพล",
                "source": "ThaiPBS",
                "url": "https://thaipbs.or.th/news/102",
                "fetched_at": "2026-08-22 11:30:00",
            },
        ]

        embeddings = np.array([
            [1.0, 0.0],
            [0.99, 0.141],
        ], dtype=np.float32)

        times = [now, now]
        results = clusterer.cluster_articles(articles, embeddings, times)
        assert len(results) == 2
        assert results[0]["cluster_size"] == 2
        assert results[0]["distinct_source_count"] == 1
        assert results[0]["cluster_sources"] == ["ThaiPBS"]
        assert results[0]["is_multi_source"] is False

    def test_cluster_articles_time_window_exceeded(self) -> None:
        """Articles with identical topics but published > 36h apart should not cluster."""
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        earlier = datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)
        clusterer = SemanticClusterer(cosine_threshold=0.50, time_window_hours=36.0)

        articles = [
            {
                "title": "ประชุม ครม. สัญจร จังหวัด เชียงใหม่",
                "source": "ThaiPBS",
                "url": "https://thaipbs.or.th/news/1",
                "fetched_at": "2026-08-22 11:00:00",
            },
            {
                "title": "ประชุม ครม. สัญจร จังหวัด เชียงใหม่",
                "source": "Matichon",
                "url": "https://matichon.co.th/news/2",
                "fetched_at": "2026-08-19 10:00:00",  # ~73 hours earlier
            },
        ]

        embeddings = np.array([
            [1.0, 0.0],
            [1.0, 0.0],
        ], dtype=np.float32)

        times = [now, earlier]
        results = clusterer.cluster_articles(articles, embeddings, times)
        assert results[0]["cluster_size"] == 1
        assert results[1]["cluster_size"] == 1

    def test_cluster_articles_empty_list(self) -> None:
        clusterer = SemanticClusterer()
        assert clusterer.cluster_articles([], np.empty((0, 2)), []) == []


# ── 2. Trending Scoring & Mathematical Model Tests ────────────────

class TestTrendingServiceCalculations:
    """Test individual components of the trending scoring formula."""

    @pytest.fixture
    def service(self) -> TrendingService:
        return TrendingService(
            news_repo=InMemoryNewsRepository(),
            engagement_repo=InMemoryEngagementRepository(),
        )

    def test_single_source_scoring_without_engagement_fresh(self, service: TrendingService) -> None:
        # dt = 0, K = 1, E = 0
        # M = 1.0, D = 1.0, B = 0.0, EngagementFactor = 1.0
        # Score = 1.0 * 1.0 * 1.0 + 0 = 1.0
        score, breakdown, _badges = service.calculate_score(
            elapsed_hours=0.0,
            distinct_sources_count=1,
            engagement={},
        )
        assert score == 1.0
        assert breakdown.base_score == 1.0
        assert breakdown.engagement_score == 0.0
        assert breakdown.cluster_multiplier == 1.0
        assert breakdown.time_decay == 1.0
        assert breakdown.breaking_boost == 0.0

    def test_multisource_consensus_multipliers_k_range(self, service: TrendingService) -> None:
        """
        Verify multi-source consensus multiplier:
        M(K) = 1.0 + 0.55 * (K - 1)
        K=1 -> 1.0
        K=2 -> 1.55
        K=3 -> 2.10
        K=4 -> 2.65
        K=5 -> 3.20
        """
        expected_multipliers = {
            1: 1.0,
            2: 1.55,
            3: 2.10,
            4: 2.65,
            5: 3.20,
            6: 3.75,
        }
        for k, expected_m in expected_multipliers.items():
            _, breakdown, _ = service.calculate_score(
                elapsed_hours=10.0,
                distinct_sources_count=k,
                engagement={},
            )
            assert breakdown.cluster_multiplier == pytest.approx(expected_m, 0.01)

    def test_monotonic_time_decay_across_time_deltas(self, service: TrendingService) -> None:
        """
        Verify strict monotonic decrease of time_decay as elapsed_hours increases.
        D(dt) = 2^(-dt / 12.0)
        """
        time_deltas = [0.0, 1.0, 3.0, 6.0, 12.0, 18.0, 24.0, 36.0, 48.0, 72.0]
        decay_values: list[float] = []

        for dt in time_deltas:
            _, breakdown, _ = service.calculate_score(
                elapsed_hours=dt,
                distinct_sources_count=1,
                engagement={},
            )
            decay_values.append(breakdown.time_decay)

        # 1. Check specific mathematical reference points
        assert pytest.approx(decay_values[0], 0.001) == 1.0      # dt = 0
        assert pytest.approx(decay_values[4], 0.001) == 0.5      # dt = 12 (half-life)
        assert pytest.approx(decay_values[6], 0.001) == 0.25     # dt = 24 (two half-lives)
        assert pytest.approx(decay_values[8], 0.001) == 0.0625   # dt = 48 (four half-lives)

        # 2. Check strictly decreasing monotonicity: D(t_i) > D(t_{i+1})
        for i in range(len(decay_values) - 1):
            assert decay_values[i] > decay_values[i + 1], (
                f"Time decay not strictly monotonic at dt={time_deltas[i]} vs dt={time_deltas[i+1]}"
            )

    def test_negative_elapsed_hours_clamped(self, service: TrendingService) -> None:
        """Future timestamp with dt < 0 must clamp to dt = 0 (decay = 1.0, no score explosion)."""
        _, breakdown, _ = service.calculate_score(
            elapsed_hours=-5.0,
            distinct_sources_count=1,
            engagement={},
        )
        assert breakdown.time_decay == 1.0

    def test_engagement_score_weights_and_damping(self, service: TrendingService) -> None:
        # Clicks = 10 (10*1 = 10), Summaries = 2 (2*3 = 6), Bookmarks = 1 (1*5 = 5)
        # E = 10 + 6 + 5 = 21.0
        # EngagementFactor = 1.0 + ln(1 + 21) * 2.0 = 1.0 + ln(22)*2.0 = 1 + 3.0910*2 = 7.182
        eng = {"clicks": 10, "summaries": 2, "bookmarks": 1}
        score, breakdown, _ = service.calculate_score(
            elapsed_hours=0.0,
            distinct_sources_count=1,
            engagement=eng,
        )
        assert breakdown.engagement_score == 21.0
        expected_factor = 1.0 + (math.log(1.0 + 21.0) * 2.0)
        assert pytest.approx(score, 0.05) == expected_factor

    def test_breaking_news_velocity_boost_and_boundaries(self, service: TrendingService) -> None:
        """
        Verify breaking boost:
        B = 4.0 if dt <= 3.0 and K >= 2 else 0.0
        """
        # Inside window: dt = 1.5, K = 2 -> B = 4.0, '⚡ Breaking' badge
        _, b_in, badges_in = service.calculate_score(
            elapsed_hours=1.5, distinct_sources_count=2, engagement={}
        )
        assert b_in.breaking_boost == 4.0
        assert "⚡ Breaking" in badges_in

        # Exact boundary: dt = 3.0, K = 2 -> B = 4.0
        _, b_bound, badges_bound = service.calculate_score(
            elapsed_hours=3.0, distinct_sources_count=2, engagement={}
        )
        assert b_bound.breaking_boost == 4.0
        assert "⚡ Breaking" in badges_bound

        # Outside window: dt = 3.1, K = 2 -> B = 0.0
        _, b_out, badges_out = service.calculate_score(
            elapsed_hours=3.1, distinct_sources_count=2, engagement={}
        )
        assert b_out.breaking_boost == 0.0
        assert "⚡ Breaking" not in badges_out

        # Fresh but single source: dt = 1.0, K = 1 -> B = 0.0
        _, b_single, badges_single = service.calculate_score(
            elapsed_hours=1.0, distinct_sources_count=1, engagement={}
        )
        assert b_single.breaking_boost == 0.0
        assert "⚡ Breaking" not in badges_single

    def test_top_story_badge_assignment(self, service: TrendingService) -> None:
        # K >= 3 publishers gets "🌟 Top Story"
        _, _, badges_k3 = service.calculate_score(
            elapsed_hours=6.0,
            distinct_sources_count=3,
            engagement={},
        )
        assert "🌟 Top Story" in badges_k3

        _, _, badges_k2 = service.calculate_score(
            elapsed_hours=6.0,
            distinct_sources_count=2,
            engagement={},
        )
        assert "🌟 Top Story" not in badges_k2

    def test_trending_badge_score_threshold(self, service: TrendingService) -> None:
        """Score >= 4.5 gets '🔥 Trending' badge automatically."""
        # High engagement to trigger score >= 4.5
        _, _, badges_high = service.calculate_score(
            elapsed_hours=0.0,
            distinct_sources_count=1,
            engagement={"clicks": 50, "summaries": 10, "bookmarks": 5},
        )
        assert "🔥 Trending" in badges_high

        # Low score does not get trending badge from calculate_score
        _, _, badges_low = service.calculate_score(
            elapsed_hours=12.0,
            distinct_sources_count=1,
            engagement={},
        )
        assert "🔥 Trending" not in badges_low


# ── 3. TrendingService End-to-End Ranking & Filtering ─────────────

class TestTrendingServiceEndToEnd:
    """Test full ranking, hero selection, category filtering, and limit handling."""

    def test_ranking_and_hero_selection(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        news_repo = InMemoryNewsRepository([
            {
                "title": "ข่าวสำคัญระดับประเทศ ครม. อนุมัติโครงการใหญ่",
                "summary": "สรุปข่าว 1",
                "source": "ThaiPBS",
                "url": "https://thaipbs.or.th/news/1",
                "category": "politics",
                "fetched_at": "2026-08-22 11:30:00",  # 0.5h ago
            },
            {
                "title": "ข่าวสำคัญระดับประเทศ ครม. อนุมัติโครงการใหญ่",
                "summary": "สรุปข่าว 2",
                "source": "The Standard",
                "url": "https://thestandard.co/news/2",
                "category": "politics",
                "fetched_at": "2026-08-22 11:20:00",  # ~0.6h ago
            },
            {
                "title": "ข่าวธรรมดาจากแหล่งเดียว เมื่อ 20 ชั่วโมงก่อน",
                "summary": "สรุปข่าว 3",
                "source": "DailyNews",
                "url": "https://dailynews.co.th/news/3",
                "category": "society",
                "fetched_at": "2026-08-21 16:00:00",  # 20h ago
            },
        ])
        eng_repo = InMemoryEngagementRepository()
        eng_repo.record_event("https://thaipbs.or.th/news/1", "click")
        eng_repo.record_event("https://thaipbs.or.th/news/1", "summary")

        service = TrendingService(news_repo=news_repo, engagement_repo=eng_repo)
        response: TrendingListResponse = service.get_trending_articles(limit=5, now=now)

        assert response.total == 3
        assert len(response.trending) == 3
        assert response.hero is not None

        # Hero must be the top-scoring article (the multi-source breaking news)
        assert response.hero.url == "https://thaipbs.or.th/news/1"
        assert response.hero.trending_score > response.trending[-1].trending_score
        assert "⚡ Breaking" in response.hero.badges
        assert "🔥 Trending" in response.hero.badges
        assert response.hero.cluster_size == 2
        assert response.hero.cluster_sources == ["ThaiPBS", "The Standard"]

        # Ensure strict descending order of trending_score in results
        scores = [a.trending_score for a in response.trending]
        assert scores == sorted(scores, reverse=True)

    def test_category_filtering_all_variants(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        news_repo = InMemoryNewsRepository([
            {
                "title": "การเมืองร้อนแรง สภาเปิดอภิปรายไม่ไว้วางใจ",
                "summary": "การเมือง",
                "source": "ThaiPBS",
                "url": "https://thaipbs.or.th/pol/1",
                "category": "politics",
                "fetched_at": "2026-08-22 11:00:00",
            },
            {
                "title": "ฟุตบอลทีมชาติไทย ซ้อมเข้มก่อนลุยคัดบอลโลก",
                "summary": "กีฬา",
                "source": "Thairath",
                "url": "https://thairath.co.th/sport/1",
                "category": "sports",
                "fetched_at": "2026-08-22 10:00:00",
            },
            {
                "title": "ธนาคารกลางประกาศลดอัตราดอกเบี้ยนโยบาย",
                "summary": "เศรษฐกิจ",
                "source": "The Standard",
                "url": "https://thestandard.co/econ/1",
                "category": "economy",
                "fetched_at": "2026-08-22 09:00:00",
            },
        ])
        eng_repo = InMemoryEngagementRepository()
        service = TrendingService(news_repo=news_repo, engagement_repo=eng_repo)

        # 1. Filter for politics
        pol_res = service.get_trending_articles(category="politics", now=now)
        assert pol_res.total == 1
        assert pol_res.trending[0].category == "politics"

        # 2. Filter for sports (case-insensitive)
        sport_res = service.get_trending_articles(category="SPORTS", now=now)
        assert sport_res.total == 1
        assert sport_res.trending[0].category == "sports"

        # 3. Filter with "all" or None returns all
        all_res = service.get_trending_articles(category="all", now=now)
        assert all_res.total == 3

        none_res = service.get_trending_articles(category=None, now=now)
        assert none_res.total == 3

        # 4. Filter for non-existent category returns empty
        empty_res = service.get_trending_articles(category="entertainment", now=now)
        assert empty_res.total == 0
        assert empty_res.trending == []
        assert empty_res.hero is None

    def test_limit_parameter_support(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        articles = [
            {
                "title": f"หัวข้อข่าวทดสอบที่ {i}",
                "summary": f"สรุปเนื้อหา {i}",
                "source": "SourceA",
                "url": f"https://example.com/news/{i}",
                "category": "technology",
                "fetched_at": "2026-08-22 11:00:00",
            }
            for i in range(15)
        ]
        service = TrendingService(
            news_repo=InMemoryNewsRepository(articles),
            engagement_repo=InMemoryEngagementRepository(),
        )

        res_default = service.get_trending_articles(limit=5, now=now)
        assert len(res_default.trending) == 5
        assert res_default.total == 15

        res_custom = service.get_trending_articles(limit=10, now=now)
        assert len(res_custom.trending) == 10

    def test_empty_news_repository_graceful_handling(self) -> None:
        service = TrendingService(
            news_repo=InMemoryNewsRepository([]),
            engagement_repo=InMemoryEngagementRepository(),
        )
        res = service.get_trending_articles()
        assert res.total == 0
        assert res.trending == []
        assert res.hero is None

    def test_malformed_timestamp_fallback(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        parsed = parse_article_time("invalid-date-string", now)
        assert parsed == now

        empty_parsed = parse_article_time("", now)
        assert empty_parsed == now

    def test_the_standard_image_proxying(self) -> None:
        """Verify image proxying for thestandard.co images."""
        url = "https://thestandard.co/wp-content/uploads/2026/08/news.jpg"
        proxied = _proxy_image_url(url, "The Standard")
        assert proxied.startswith("/api/image?url=")

        other_url = "https://thaipbs.or.th/assets/img.jpg"
        not_proxied = _proxy_image_url(other_url, "ThaiPBS")
        assert not_proxied == other_url


# ── 4. FileEngagementRepository Persistence & Concurrency Tests ───

class TestFileEngagementRepository:
    """Test disk persistence, counter increment, and thread safety."""

    def test_record_events_and_persistence(self, tmp_path: Path) -> None:
        file_path = tmp_path / "engagement_test.json"
        repo = FileEngagementRepository(data_file=file_path)

        url = "https://example.com/article/1"
        stats1 = repo.record_event(url, "click")
        assert stats1 == {"clicks": 1, "summaries": 0, "bookmarks": 0}

        stats2 = repo.record_event(url, "summary")
        assert stats2 == {"clicks": 1, "summaries": 1, "bookmarks": 0}

        stats3 = repo.record_event(url, "bookmark")
        assert stats3 == {"clicks": 1, "summaries": 1, "bookmarks": 1}

        # Verify disk persistence by re-instantiating repository
        repo2 = FileEngagementRepository(data_file=file_path)
        persisted_stats = repo2.get_engagement(url)
        assert persisted_stats == {"clicks": 1, "summaries": 1, "bookmarks": 1}

    def test_clear_all(self, tmp_path: Path) -> None:
        file_path = tmp_path / "engagement_test.json"
        repo = FileEngagementRepository(data_file=file_path)
        repo.record_event("https://example.com/1", "click")
        assert len(repo.get_all_engagements()) == 1

        repo.clear_all()
        assert len(repo.get_all_engagements()) == 0
        assert repo.get_engagement("https://example.com/1") == {"clicks": 0, "summaries": 0, "bookmarks": 0}

    def test_concurrent_event_recording(self, tmp_path: Path) -> None:
        """Verify thread-safety when recording hundreds of concurrent events."""
        file_path = tmp_path / "engagement_concurrent.json"
        repo = FileEngagementRepository(data_file=file_path)
        url = "https://example.com/concurrent-article"

        num_threads = 20
        clicks_per_thread = 10

        def worker() -> None:
            for _ in range(clicks_per_thread):
                repo.record_event(url, "click")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            concurrent.futures.wait(futures)

        final_stats = repo.get_engagement(url)
        assert final_stats["clicks"] == num_threads * clicks_per_thread


# ── 5. FastAPI Router Integration Tests & Schema Conformance ──────

class TestTrendingRouterAPI:
    """Test HTTP API endpoints with FastAPI TestClient and Pydantic validation."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_get_trending_endpoint_schema_conformance(self, client: TestClient) -> None:
        """Validate GET /api/news/trending response conforms to TrendingListResponse."""
        response = client.get("/api/news/trending?limit=5")
        assert response.status_code == 200
        data = response.json()

        # Pydantic schema validation
        validated = TrendingListResponse.model_validate(data)
        assert isinstance(validated.total, int)
        assert isinstance(validated.updated, str)
        assert isinstance(validated.trending, list)
        assert len(validated.trending) <= 5

        if validated.trending:
            first = validated.trending[0]
            assert isinstance(first.title, str)
            assert isinstance(first.trending_score, float)
            assert isinstance(first.cluster_size, int)
            assert isinstance(first.cluster_sources, list)
            assert isinstance(first.badges, list)
            if validated.hero is not None:
                assert validated.hero.url == first.url

    def test_get_trending_category_filter_api(self, client: TestClient) -> None:
        response = client.get("/api/news/trending?category=politics&limit=3")
        assert response.status_code == 200
        data = response.json()
        validated = TrendingListResponse.model_validate(data)
        for art in validated.trending:
            if art.category:
                assert art.category.lower() == "politics"

    def test_get_trending_limit_bounds_validation(self, client: TestClient) -> None:
        # Limit < 1 -> 422
        res_low = client.get("/api/news/trending?limit=0")
        assert res_low.status_code == 422

        # Limit > 50 -> 422
        res_high = client.get("/api/news/trending?limit=51")
        assert res_high.status_code == 422

    def test_post_engage_endpoint(self, client: TestClient) -> None:
        payload = {
            "url": "https://example.com/test-article-for-api",
            "event_type": "click",
        }
        response = client.post("/api/news/engage", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["url"] == payload["url"]
        assert data["event_type"] == "click"
        assert "stats" in data
        assert data["stats"]["clicks"] >= 1

    def test_post_engagement_alias_endpoint(self, client: TestClient) -> None:
        payload = {
            "url": "https://example.com/test-article-for-api-alias",
            "event_type": "bookmark",
        }
        response = client.post("/api/news/engagement", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["event_type"] == "bookmark"
        assert data["stats"]["bookmarks"] >= 1

    def test_post_engage_invalid_event_type(self, client: TestClient) -> None:
        payload = {
            "url": "https://example.com/test-article",
            "event_type": "invalid_type",
        }
        response = client.post("/api/news/engage", json=payload)
        assert response.status_code == 422  # Unprocessable Entity from Pydantic validation


# ── 6. Remediation Fixes Specific Verification Tests ──────────────

class TestTrendingRemediation:
    """Verifies all remediation quality fixes."""

    def test_engagement_repository_singleton(self) -> None:
        repo1 = get_engagement_repository()
        repo2 = get_engagement_repository()
        assert repo1 is repo2
        assert repo1._lock is repo2._lock

    def test_atomic_write_creates_valid_json(self, tmp_path: Path) -> None:
        file_path = tmp_path / "engagement_atomic.json"
        repo = FileEngagementRepository(data_file=file_path)
        repo.record_event("https://example.com/item1", "click")
        assert file_path.exists()

        # Temporary files should be cleaned up and only final file exists
        parent_files = list(tmp_path.iterdir())
        assert len(parent_files) == 1
        assert parent_files[0].name == "engagement_atomic.json"

    def test_trending_service_is_strictly_read_only(self) -> None:
        """Verify get_trending_articles never calls save_news on news repository."""
        class ReadOnlyAssertingNewsRepo(NewsRepositoryPort):
            def __init__(self, articles: list[dict[str, Any]]) -> None:
                self.articles = articles

            def load_news(self) -> list[dict[str, Any]]:
                return list(self.articles)

            def save_news(self, data: list[dict[str, Any]]) -> None:
                raise AssertionError("save_news() must not be called during read-only trending query!")

            def load_seen(self) -> set[str]:
                return set()

            def save_seen(self, seen: set[str]) -> None:
                pass

        # Articles without category or classification_method
        articles = [
            {
                "title": "ข่าวการเมือง ด่วน สภาผู้แทนราษฎร",
                "summary": "สรุปข่าว",
                "source": "ThaiPBS",
                "url": "https://thaipbs.or.th/news/pol1",
                "fetched_at": "2026-08-22 10:00:00",
            },
            {
                "title": "ราคาทองคำ ตลาดหุ้น วันนี้",
                "summary": "สรุปเศรษฐกิจ",
                "source": "The Standard",
                "url": "https://thestandard.co/news/econ1",
                "fetched_at": "2026-08-22 10:00:00",
            },
        ]
        news_repo = ReadOnlyAssertingNewsRepo(articles)
        eng_repo = InMemoryEngagementRepository()
        service = TrendingService(news_repo=news_repo, engagement_repo=eng_repo)

        # Calling get_trending_articles should resolve categories in memory and NOT fail assertion
        res = service.get_trending_articles(category=None, limit=5)
        assert res.total == 2
        assert len(res.trending) == 2
        # Categories should be computed in response
        assert res.trending[0].category in {"politics", "economy", "society"}

    def test_trending_list_response_dual_compatibility(self) -> None:
        """Verify both trending and articles fields are populated and synchronized."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Constructed with trending only
        art1 = TrendingArticle(
            title="ข่าวทดสอบ",
            summary="สรุป",
            source="ThaiPBS",
            url="https://example.com/1",
            fetched_at=now_str,
            trending_score=5.0,
        )
        resp1 = TrendingListResponse(
            total=1,
            updated=now_str,
            trending=[art1],
        )
        assert len(resp1.trending) == 1
        assert len(resp1.articles) == 1
        assert resp1.trending[0].title == resp1.articles[0].title

        # Constructed with articles only
        art2 = TrendingArticle(
            title="ข่าวทดสอบ 2",
            summary="สรุป 2",
            source="ThaiPBS",
            url="https://example.com/2",
            fetched_at=now_str,
            trending_score=6.0,
        )
        resp2 = TrendingListResponse(
            total=1,
            updated=now_str,
            articles=[art2],
        )
        assert len(resp2.trending) == 1
        assert len(resp2.articles) == 1
        assert resp2.trending[0].title == resp2.articles[0].title

    def test_parse_article_time_type_guard(self) -> None:
        """Verify type guard for non-string timestamps."""
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        assert parse_article_time(None, now) == now
        assert parse_article_time(12345, now) == now
        assert parse_article_time({"time": "now"}, now) == now
        assert parse_article_time([], now) == now
        assert isinstance(parse_article_time(None), datetime)

    def test_pre_filter_trending_window_48h(self) -> None:
        """Verify that historical articles older than 48h are pre-filtered out before clustering."""
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        articles = [
            # 5 recent articles within 48h (between 1h and 40h ago)
            {
                "title": f"ข่าวด่วนล่าสุด {i}",
                "summary": f"สรุปข่าว {i}",
                "source": "ThaiPBS",
                "url": f"https://thaipbs.or.th/recent/{i}",
                "category": "politics",
                "fetched_at": f"2026-08-22 10:0{i}:00",  # ~2 hours ago
            }
            for i in range(5)
        ]
        # 1,000 old historical articles (from 10 days to 60 days ago)
        for i in range(1000):
            articles.append({
                "title": f"ข่าวประวัติศาสตร์เก่า {i}",
                "summary": "สรุปข่าวเก่า",
                "source": "OldSource",
                "url": f"https://example.com/old/{i}",
                "category": "politics",
                "fetched_at": "2026-07-01 12:00:00",  # ~50 days ago
            })

        news_repo = InMemoryNewsRepository(articles)
        eng_repo = InMemoryEngagementRepository()
        service = TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            trending_window_hours=48.0,
        )

        res = service.get_trending_articles(category=None, limit=10, now=now)
        # Total clustered should only be the 5 recent articles, NOT 1005
        assert res.total == 5
        assert len(res.trending) == 5
        for art in res.trending:
            assert "ข่าวด่วนล่าสุด" in art.title

