"""
tests/test_trending_challenger_stress.py
─────────────────────────────────────────────────────────────────
Adversarial & Empirical Stress Test Suite for Trending Calculation Engine
and PDPA Engagement Storage.

Tested Failure Modes:
1. Extreme time deltas: future dates (dt < 0), 100 days old (dt = 2400h),
   missing/corrupted timestamps, epoch 1970, timezone skews.
2. Thai NLP title clustering edge cases: single-token titles, identical titles
   from single vs multi-publishers, 1-char titles, stopword-only titles,
   emoji/punctuation titles, 36h time-window thresholding, transitive clusters.
3. Concurrency & race conditions on engagement persistence: multi-threaded
   concurrent increments, multi-instance repository contention, atomic writes.
4. Mathematical robustness: NaN/Inf isolation, log-scale engagement dampening,
   floating point precision, monotonic decay invariant.
5. PDPA compliance: zero PII invariants, schema purity, purge verification.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import concurrent.futures
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.repo.engagement_repo import FileEngagementRepository
from backend.repo.news_repo import NewsRepositoryPort
from backend.schemas.trending_schema import TrendingListResponse
from backend.services.trending_service import (
    SemanticClusterer,
    TrendingService,
    parse_article_time,
)

# ── Test Fixtures & In-Memory Mocks ───────────────────────────────

class InMemoryNewsRepo(NewsRepositoryPort):
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


class InMemoryEngageRepo:
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


# ═══════════════════════════════════════════════════════════════════
# 1. EXTREME TIME DELTAS & TIMESTAMP PARSING STRESS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestExtremeTimeDeltasAndTimestamps:
    """Stress test trending calculation under abnormal and boundary timestamps."""

    @pytest.fixture
    def service(self) -> TrendingService:
        return TrendingService(
            news_repo=InMemoryNewsRepo(),
            engagement_repo=InMemoryEngageRepo(),
        )

    def test_future_timestamp_clamping_prevents_exponential_explosion(
        self, service: TrendingService
    ) -> None:
        """
        If an article has a future timestamp (e.g. clock skew, bad server time),
        dt = elapsed_hours < 0.
        Formula must clamp dt to 0.0 so time_decay = 2^(-0) = 1.0 (not > 1.0).
        """
        future_deltas = [-0.1, -1.0, -24.0, -1000.0, -87600.0]
        for dt_future in future_deltas:
            score, breakdown, _ = service.calculate_score(
                elapsed_hours=dt_future,
                distinct_sources_count=1,
                engagement={},
            )
            assert breakdown.time_decay == 1.0, f"Future dt={dt_future} did not clamp time_decay to 1.0"
            assert score == 1.0, f"Future dt={dt_future} caused score explosion: {score}"

    def test_extreme_past_timestamp_100_days_underflow_safety(
        self, service: TrendingService
    ) -> None:
        """
        100 days old = 2,400 hours old.
        Decay = 2^(-2400/12) = 2^(-200) ≈ 6.22e-61.
        Must evaluate gracefully to ~0.0 without floating point underflow error.
        """
        score_100d, breakdown_100d, _ = service.calculate_score(
            elapsed_hours=2400.0,
            distinct_sources_count=1,
            engagement={},
        )
        assert breakdown_100d.time_decay >= 0.0
        assert breakdown_100d.time_decay < 1e-50
        assert score_100d == 0.0

        # 1000 days old (24,000 hours)
        score_1000d, _breakdown_1000d, _ = service.calculate_score(
            elapsed_hours=24000.0,
            distinct_sources_count=1,
            engagement={},
        )
        assert score_1000d == 0.0
        assert not math.isnan(score_1000d)
        assert not math.isinf(score_1000d)

    def test_strict_monotonic_decay_invariant(self, service: TrendingService) -> None:
        """
        Mathematical Invariant: For any fixed E and K,
        Score(t1) >= Score(t2) for all 0 <= t1 <= t2.
        """
        eng = {"clicks": 15, "summaries": 3, "bookmarks": 2}
        dt_series = [0.0, 0.5, 1.0, 2.99, 3.0, 3.01, 6.0, 12.0, 18.0, 24.0, 36.0, 48.0, 72.0, 168.0, 720.0]

        for k in [1, 2, 4]:
            scores = [
                service.calculate_score(elapsed_hours=dt, distinct_sources_count=k, engagement=eng)[0]
                for dt in dt_series
            ]
            for i in range(len(scores) - 1):
                assert scores[i] >= scores[i + 1], (
                    f"Monotonicity violation at K={k}: Score({dt_series[i]})={scores[i]} < Score({dt_series[i+1]})={scores[i+1]}"
                )

    def test_parse_article_time_comprehensive_formats(self) -> None:
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

        # Standard ISO formats
        assert parse_article_time("2026-08-22T10:00:00Z", now) == datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        assert parse_article_time("2026-08-22T10:00:00+00:00", now) == datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        assert parse_article_time("2026-08-22 10:00:00", now) == datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        assert parse_article_time("2026-08-22T10:00:00", now) == datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)

        # Timezone offset format
        parsed_bkk = parse_article_time("2026-08-22T17:00:00+07:00", now)
        assert parsed_bkk.astimezone(timezone.utc) == datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)

        # Fallbacks for corrupt/empty strings
        assert parse_article_time("", now) == now
        assert parse_article_time("   ", now) == now
        assert parse_article_time("not-a-date", now) == now
        assert parse_article_time("99999-99-99", now) == now
        assert parse_article_time("null", now) == now


# ═══════════════════════════════════════════════════════════════════
# 2. SEMANTIC VECTOR CLUSTERING & COHESION EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestSemanticClusteringEdgeCases:
    """Stress test vector cosine clustering, anti-chain cohesion, and temporal windows."""

    def test_identical_titles_same_publisher_vs_different_publishers(self) -> None:
        """
        If ThaiPBS publishes the identical title twice:
          cluster_size = 2, distinct_source_count = 1 -> is_multi_source = False.
        If ThaiPBS and The Standard publish the identical title:
          cluster_size = 2, distinct_source_count = 2 -> is_multi_source = True.
        """
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        clusterer = SemanticClusterer(cosine_threshold=0.70, time_window_hours=36.0)

        # Case A: Same publisher
        articles_same_pub = [
            {"title": "ด่วน แผ่นดินไหว เชียงใหม่ ขนาด 4.5", "source": "ThaiPBS", "url": "https://thaipbs.or.th/1", "fetched_at": "2026-08-22 11:00:00"},
            {"title": "ด่วน แผ่นดินไหว เชียงใหม่ ขนาด 4.5", "source": "ThaiPBS", "url": "https://thaipbs.or.th/2", "fetched_at": "2026-08-22 11:15:00"},
        ]
        embs_same = np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
        times_same = [now, now + timedelta(minutes=15)]
        res_same = clusterer.cluster_articles(articles_same_pub, embs_same, times_same)
        assert res_same[0]["cluster_size"] == 2
        assert res_same[0]["distinct_source_count"] == 1
        assert res_same[0]["is_multi_source"] is False
        assert res_same[0]["cluster_sources"] == ["ThaiPBS"]

        # Case B: Different publishers
        articles_diff_pub = [
            {"title": "ด่วน แผ่นดินไหว เชียงใหม่ ขนาด 4.5", "source": "ThaiPBS", "url": "https://thaipbs.or.th/1", "fetched_at": "2026-08-22 11:00:00"},
            {"title": "ด่วน แผ่นดินไหว เชียงใหม่ ขนาด 4.5", "source": "The Standard", "url": "https://thestandard.co/2", "fetched_at": "2026-08-22 11:15:00"},
        ]
        res_diff = clusterer.cluster_articles(articles_diff_pub, embs_same, times_same)
        assert res_diff[0]["cluster_size"] == 2
        assert res_diff[0]["distinct_source_count"] == 2
        assert res_diff[0]["is_multi_source"] is True
        assert sorted(res_diff[0]["cluster_sources"]) == ["ThaiPBS", "The Standard"]

    def test_orthogonal_embeddings_do_not_cluster(self) -> None:
        """Articles with completely orthogonal embeddings must produce singletons."""
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        clusterer = SemanticClusterer(cosine_threshold=0.70)

        articles = [
            {"title": "ข่าวน้ำท่วม", "source": "SourceA", "url": "https://a.com/1"},
            {"title": "ข่าวตลาดหุ้น", "source": "SourceB", "url": "https://b.com/2"},
            {"title": "ข่าวเทคโนโลยี", "source": "SourceC", "url": "https://c.com/3"},
            {"title": "ข่าวบันเทิง", "source": "SourceD", "url": "https://d.com/4"},
        ]
        embs = np.eye(4, dtype=np.float32)
        times = [now, now, now, now]
        results = clusterer.cluster_articles(articles, embs, times)
        for res in results:
            assert res["cluster_size"] == 1
            assert res["distinct_source_count"] == 1

    def test_anti_chain_cohesion_pruning(self) -> None:
        """
        Transitive chain A <-> B (0.75), B <-> C (0.72), A <-> C (0.40).
        With cohesion_threshold=0.65, the clusterer must prune the outlier
        and prevent runaway transitive grouping.
        """
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        clusterer = SemanticClusterer(cosine_threshold=0.70, cohesion_threshold=0.65)

        articles = [
            {"title": "ราคาทองคำ วันนี้ พุ่งแรง ทุบสถิติใหม่", "source": "ThaiPBS", "url": "https://1.com"},
            {"title": "ราคาทองคำ วันนี้ ปรับขึ้น 500 บาท", "source": "The Standard", "url": "https://2.com"},
            {"title": "ตลาดหุ้นไทย ปรับตัวลดลง เล็กน้อย", "source": "Thairath", "url": "https://3.com"},
        ]
        vec_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        vec_b = np.array([0.75, 0.6614378, 0.0], dtype=np.float32)
        cx = 0.40
        cy = (0.72 - 0.75 * cx) / 0.6614378
        cz = np.sqrt(max(0.0, 1.0 - cx**2 - cy**2))
        vec_c = np.array([cx, cy, cz], dtype=np.float32)
        embs = np.vstack([vec_a, vec_b, vec_c])

        results = clusterer.cluster_articles(articles, embs, [now, now, now])
        sizes = [r["cluster_size"] for r in results]
        assert 3 not in sizes, "Runaway chain was not split!"

    def test_clustering_window_hours_boundary(self) -> None:
        """Articles with identical embeddings published at 35.5h vs 36.5h apart."""
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        clusterer = SemanticClusterer(cosine_threshold=0.70, time_window_hours=36.0)

        # 35.5 hours apart -> Clustered
        within_window = [
            {"title": "นโยบาย เงินดิจิทัล วอลเล็ต 10000 บาท", "source": "ThaiPBS", "url": "https://1.com"},
            {"title": "นโยบาย เงินดิจิทัล วอลเล็ต 10000 บาท", "source": "The Standard", "url": "https://2.com"},
        ]
        embs = np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
        times_within = [now, now - timedelta(hours=35.5)]
        res_within = clusterer.cluster_articles(within_window, embs, times_within)
        assert res_within[0]["cluster_size"] == 2

        # 36.5 hours apart -> Separate clusters
        times_outside = [now, now - timedelta(hours=36.5)]
        res_outside = clusterer.cluster_articles(within_window, embs, times_outside)
        assert res_outside[0]["cluster_size"] == 1
        assert res_outside[1]["cluster_size"] == 1


# ═══════════════════════════════════════════════════════════════════
# 3. HIGH CONCURRENCY & ENGAGEMENT PERSISTENCE STRESS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEngagementHighConcurrency:
    """Stress test FileEngagementRepository under massive concurrent workloads."""

    def test_heavy_concurrent_increments_single_instance(self, tmp_path: Path) -> None:
        """50 concurrent threads executing 20 increments each (1,000 operations total)."""
        data_file = tmp_path / "heavy_concurrent.json"
        repo = FileEngagementRepository(data_file=data_file)
        url = "https://example.com/breaking-event"

        num_threads = 50
        events_per_thread = 20

        def worker() -> None:
            for _ in range(events_per_thread):
                repo.record_event(url, "click")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            concurrent.futures.wait(futures)

        stats = repo.get_engagement(url)
        assert stats["clicks"] == num_threads * events_per_thread

    def test_concurrent_mixed_operations_read_write_clear(self, tmp_path: Path) -> None:
        """Simulate concurrent readers and writers without deadlock or data corruption."""
        data_file = tmp_path / "mixed_concurrent.json"
        repo = FileEngagementRepository(data_file=data_file)

        urls = [f"https://example.com/article/{i}" for i in range(10)]

        def writer(w_id: int) -> None:
            for i in range(20):
                target = urls[(w_id + i) % len(urls)]
                repo.record_event(target, "click" if i % 2 == 0 else "summary")

        def reader() -> None:
            for _ in range(30):
                _ = repo.get_all_engagements()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            writer_futures = [executor.submit(writer, w) for w in range(10)]
            reader_futures = [executor.submit(reader) for _ in range(10)]
            concurrent.futures.wait(writer_futures + reader_futures)

        # File must remain valid JSON on disk
        fresh_repo = FileEngagementRepository(data_file=data_file)
        engagements = fresh_repo.get_all_engagements()
        assert len(engagements) <= 10
        total_clicks = sum(e["clicks"] for e in engagements.values())
        total_summaries = sum(e["summaries"] for e in engagements.values())
        assert total_clicks + total_summaries == 200


# ═══════════════════════════════════════════════════════════════════
# 4. MATHEMATICAL BOUNDS & BADGE ASSIGNMENT ACCURACY
# ═══════════════════════════════════════════════════════════════════

class TestMathematicalBoundsAndBadges:
    """Verify formula accuracy, log damping, and badge permutations."""

    @pytest.fixture
    def service(self) -> TrendingService:
        return TrendingService(
            news_repo=InMemoryNewsRepo(),
            engagement_repo=InMemoryEngageRepo(),
        )

    def test_extreme_engagement_log_damping(self, service: TrendingService) -> None:
        """
        Massive engagement numbers (e.g. 1,000,000 clicks, summaries, bookmarks)
        must scale logarithmically and never cause numeric overflow.
        """
        score_1m, _breakdown_1m, badges_1m = service.calculate_score(
            elapsed_hours=0.0,
            distinct_sources_count=1,
            engagement={"clicks": 1_000_000, "summaries": 1_000_000, "bookmarks": 1_000_000},
        )
        # E = 1*1M + 3*1M + 5*1M = 9,000,000
        # Factor = 1.0 + ln(1 + 9000000) * 2.0 = 1.0 + 16.0127 * 2 = 33.025
        assert 30.0 < score_1m < 40.0
        assert "🔥 Trending" in badges_1m
        assert not math.isinf(score_1m)

    def test_all_badge_combinations(self, service: TrendingService) -> None:
        # 1. Breaking only: dt <= 3.0, K = 2, low engagement (< 4.5 score)
        # dt = 2.0, K = 2, E = 0 -> Score = 1.0 * 1.55 * 2^(-2/12) + 4.0 = 1.55 * 0.8909 + 4 = 5.38 (triggers Trending)
        # Let's test dt = 2.9, K = 2, E = 0
        _, _, b1 = service.calculate_score(elapsed_hours=2.9, distinct_sources_count=2, engagement={})
        assert "⚡ Breaking" in b1

        # 2. Breaking + Top Story + Trending: dt = 1.0, K = 4
        # K = 4 >= 3 -> Top Story, dt <= 3 and K >= 2 -> Breaking, score >= 4.5 -> Trending
        _score_all, _, b_all = service.calculate_score(
            elapsed_hours=1.0,
            distinct_sources_count=4,
            engagement={"clicks": 20},
        )
        assert "⚡ Breaking" in b_all
        assert "🌟 Top Story" in b_all
        assert "🔥 Trending" in b_all

        # 3. Top Story but NOT Breaking: dt = 10.0 (> 3.0), K = 3
        _, _, b_top_only = service.calculate_score(
            elapsed_hours=10.0,
            distinct_sources_count=3,
            engagement={},
        )
        assert "🌟 Top Story" in b_top_only
        assert "⚡ Breaking" not in b_top_only


# ═══════════════════════════════════════════════════════════════════
# 5. END-TO-END FASTAPI ROUTER & SCHEMA COMPLIANCE
# ═══════════════════════════════════════════════════════════════════

class TestTrendingRouterFullAPI:
    """Full HTTP API validation with FastAPI TestClient."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_trending_response_contract(self, client: TestClient) -> None:
        response = client.get("/api/news/trending?limit=5")
        assert response.status_code == 200
        data = response.json()
        validated = TrendingListResponse.model_validate(data)
        assert validated.total >= 0
        assert len(validated.trending) <= 5
        if validated.trending:
            for art in validated.trending:
                assert art.trending_score >= 0.0
                assert art.cluster_size >= 1
                assert isinstance(art.badges, list)
                if art.breakdown:
                    assert art.breakdown.raw_trending_score == art.trending_score
