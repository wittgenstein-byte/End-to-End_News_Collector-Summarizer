"""
backend/tests/test_evaluation_harness.py
─────────────────────────────────────────────────────────────────
SOLID  S — Unit tests verifying B-cubed and Pairwise metric calculations,
           ground truth benchmark schema, evaluation acceptance criteria,
           and trending sanity report logic.
SOLID  D — Tests depend on public metric formulas and report contracts.
GRASP  Information Expert — Verifies mathematical accuracy of Amigó et al. (2009)
           and Bagga & Baldwin (1998) metric implementations.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.repo.engagement_repo import EngagementRepositoryPort
from backend.repo.news_repo import NewsRepositoryPort
from backend.schemas.story_schema import StoryRecord
from scripts.evaluate_stories import (
    InMemoryStoryRepository,
    build_or_load_eval_dataset,
    calculate_bcubed_metrics,
    calculate_pairwise_metrics,
    evaluate_semantic_clusterer,
    evaluate_story_service,
)
from scripts.trending_sanity_report import generate_trending_sanity_report

# ── Test Doubles ──────────────────────────────────────────────────

class MockNewsRepo(NewsRepositoryPort):
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


class MockEngagementRepo(EngagementRepositoryPort):
    def __init__(self) -> None:
        self.engagements: dict[str, dict[str, int]] = {}

    def record_event(self, url: str, event_type: str) -> dict[str, int]:
        return {"clicks": 0, "summaries": 0, "bookmarks": 0}

    def get_engagement(self, url: str) -> dict[str, int]:
        return {"clicks": 0, "summaries": 0, "bookmarks": 0}

    def get_all_engagements(self) -> dict[str, dict[str, int]]:
        return dict(self.engagements)

    def clear_all(self) -> None:
        self.engagements.clear()


# ── 1. Pairwise Metric Unit Tests ─────────────────────────────────

class TestPairwiseMetrics:
    """Verifies pairwise precision, recall, F1, false merges, and false splits."""

    def test_pairwise_perfect_clustering(self) -> None:
        gt = ["story_A", "story_A", "story_B", "story_B"]
        pred = ["c1", "c1", "c2", "c2"]
        res = calculate_pairwise_metrics(gt, pred)

        assert res["total_pairs"] == 6
        assert res["tp"] == 2
        assert res["fp"] == 0  # 0 false merges
        assert res["fn"] == 0  # 0 false splits
        assert res["tn"] == 4
        assert res["precision"] == 1.0
        assert res["recall"] == 1.0
        assert res["f1"] == 1.0
        assert res["false_merges"] == 0
        assert res["false_splits"] == 0

    def test_pairwise_all_singletons_severe_splits(self) -> None:
        gt = ["story_A", "story_A", "story_A"]
        pred = ["c1", "c2", "c3"]  # All split
        res = calculate_pairwise_metrics(gt, pred)

        assert res["tp"] == 0
        assert res["fp"] == 0
        assert res["fn"] == 3  # 3 pairs split
        assert res["recall"] == 0.0
        assert res["precision"] == 1.0  # Vacuum truth
        assert res["f1"] == 0.0
        assert res["false_splits"] == 3

    def test_pairwise_all_merged_severe_merges(self) -> None:
        gt = ["story_A", "story_B", "story_C"]
        pred = ["c1", "c1", "c1"]  # Everything falsely merged
        res = calculate_pairwise_metrics(gt, pred)

        assert res["tp"] == 0
        assert res["fp"] == 3  # 3 false merge pairs
        assert res["fn"] == 0
        assert res["precision"] == 0.0
        assert res["recall"] == 0.0
        assert res["f1"] == 0.0
        assert res["false_merges"] == 3

    def test_pairwise_known_hand_calculated_example(self) -> None:
        # Items: 0, 1, 2, 3
        # GT: [A, A, B, B] -> GT pairs: (0,1) same, (2,3) same. Different: (0,2), (0,3), (1,2), (1,3)
        # Pred: [X, X, X, Y] -> Pred pairs: (0,1) same, (0,2) same, (1,2) same. Different: (0,3), (1,3), (2,3)
        # Pairs:
        # (0, 1): same GT, same Pred -> TP (1)
        # (0, 2): diff GT, same Pred -> FP (1) [false merge]
        # (0, 3): diff GT, diff Pred -> TN (1)
        # (1, 2): diff GT, same Pred -> FP (2) [false merge]
        # (1, 3): diff GT, diff Pred -> TN (2)
        # (2, 3): same GT, diff Pred -> FN (1) [false split]
        gt = ["A", "A", "B", "B"]
        pred = ["X", "X", "X", "Y"]
        res = calculate_pairwise_metrics(gt, pred)

        assert res["tp"] == 1
        assert res["fp"] == 2
        assert res["fn"] == 1
        assert res["tn"] == 2
        assert res["precision"] == round(1 / 3, 4)  # 0.3333
        assert res["recall"] == round(1 / 2, 4)     # 0.5000
        # F1 = 2 * (1/3) * (1/2) / (1/3 + 1/2) = (1/3) / (5/6) = 2/5 = 0.4000
        assert res["f1"] == 0.4000

    def test_pairwise_empty_and_single_item(self) -> None:
        res_empty = calculate_pairwise_metrics([], [])
        assert res_empty["precision"] == 1.0
        assert res_empty["f1"] == 1.0

        res_single = calculate_pairwise_metrics(["A"], ["X"])
        assert res_single["total_pairs"] == 0
        assert res_single["precision"] == 1.0


# ── 2. B-cubed Metric Unit Tests ──────────────────────────────────

class TestBcubedMetrics:
    """Verifies Bagga & Baldwin (1998) / Amigó et al. (2009) B-cubed calculations."""

    def test_bcubed_perfect_clustering(self) -> None:
        gt = ["story_A", "story_A", "story_B", "story_B", "singleton_1"]
        pred = ["c1", "c1", "c2", "c2", "c3"]
        res = calculate_bcubed_metrics(gt, pred)

        assert res["precision"] == 1.0
        assert res["recall"] == 1.0
        assert res["f1"] == 1.0

    def test_bcubed_all_singletons_calculation(self) -> None:
        # Two 2-article stories split into 4 singletons
        gt = ["A", "A", "B", "B"]
        pred = ["1", "2", "3", "4"]
        res = calculate_bcubed_metrics(gt, pred)

        # For each article i:
        # S_pred(i) has size 1. Intersection with S_gt(i) has size 1.
        # prec_i = 1 / 1 = 1.0 -> Avg precision = 1.0
        # S_gt(i) has size 2. Intersection has size 1.
        # rec_i = 1 / 2 = 0.5 -> Avg recall = 0.5
        # F1 = 2 * 1.0 * 0.5 / (1.0 + 0.5) = 1.0 / 1.5 = 2/3 ≈ 0.6667
        assert res["precision"] == 1.0
        assert res["recall"] == 0.5
        assert res["f1"] == round(2 / 3, 4)

    def test_bcubed_known_amigo_literature_case(self) -> None:
        # Ground truth: {1, 2, 3}, {4, 5}
        # Prediction: {1, 2}, {3, 4}, {5}
        gt = ["A", "A", "A", "B", "B"]
        pred = ["C1", "C1", "C2", "C2", "C3"]

        # Item 0 (GT A, Pred C1={0,1}):
        # S_pred = {0, 1}, S_gt = {0, 1, 2}, Inter = {0, 1}
        # prec = 2/2 = 1.0, rec = 2/3

        # Item 1 (GT A, Pred C1={0,1}):
        # prec = 2/2 = 1.0, rec = 2/3

        # Item 2 (GT A, Pred C2={2,3}):
        # S_pred = {2, 3}, S_gt = {0, 1, 2}, Inter = {2}
        # prec = 1/2 = 0.5, rec = 1/3

        # Item 3 (GT B, Pred C2={2,3}):
        # S_pred = {2, 3}, S_gt = {3, 4}, Inter = {3}
        # prec = 1/2 = 0.5, rec = 1/2

        # Item 4 (GT B, Pred C3={4}):
        # S_pred = {4}, S_gt = {3, 4}, Inter = {4}
        # prec = 1/1 = 1.0, rec = 1/2

        # Mean precision: (1.0 + 1.0 + 0.5 + 0.5 + 1.0) / 5 = 4.0 / 5 = 0.8000
        # Mean recall: (2/3 + 2/3 + 1/3 + 1/2 + 1/2) / 5 = (5/3 + 1) / 5 = (8/3) / 5 = 8/15 ≈ 0.5333
        # F1 = 2 * 0.8 * (8/15) / (0.8 + 8/15) = 2 * (4/5) * (8/15) / (20/15) = (64/75) / (4/3) = 16/25 = 0.6400
        res = calculate_bcubed_metrics(gt, pred)

        assert res["precision"] == 0.8000
        assert res["recall"] == round(8 / 15, 4)
        assert res["f1"] == 0.6400

    def test_bcubed_empty_dataset(self) -> None:
        res = calculate_bcubed_metrics([], [])
        assert res["precision"] == 1.0
        assert res["recall"] == 1.0
        assert res["f1"] == 1.0


# ── 3. Trending Sanity Report Unit Tests ───────────────────────────

class TestTrendingSanityReport:
    """Verifies distinct source counting, single-origin flags, and report structure."""

    def test_single_origin_flag_detection(self) -> None:
        now = datetime.now(timezone.utc)
        story_single = StoryRecord(
            story_id="story_single",
            title="Single Origin News",
            category="sports",
            status="active",
            created_at=now,
            updated_at=now,
            article_urls=["https://outlet1.com/1", "https://outlet1.com/2"],
            article_count=2,
            outlets=["Khaosod"],
            outlet_count=1,
            centroid=[0.1] * 768,
        )

        story_multi = StoryRecord(
            story_id="story_multi",
            title="Multi Source News",
            category="politics",
            status="active",
            created_at=now,
            updated_at=now,
            article_urls=["https://outlet1.com/1", "https://outlet2.com/1", "https://outlet3.com/1"],
            article_count=3,
            outlets=["Thai Post", "Matichon", "Daily News"],
            outlet_count=3,
            centroid=[0.1] * 768,
        )

        story_repo = InMemoryStoryRepository([story_single, story_multi])
        news_repo = MockNewsRepo()
        eng_repo = MockEngagementRepo()

        report = generate_trending_sanity_report(
            news_repo=news_repo,
            story_repo=story_repo,
            engagement_repo=eng_repo,
            limit=5,
            now=now,
        )

        assert report["sanity_check_passed"] is True
        top_stories = report["top_stories"]
        assert len(top_stories) == 2

        story_map = {s["story_id"]: s for s in top_stories}

        # Verify single origin is flagged
        assert story_map["story_single"]["distinct_source_count"] == 1
        assert story_map["story_single"]["is_single_origin"] is True
        assert story_map["story_single"]["origin_type"] == "SINGLE_ORIGIN"

        # Verify multi-source is not flagged as single origin
        assert story_map["story_multi"]["distinct_source_count"] == 3
        assert story_map["story_multi"]["is_single_origin"] is False
        assert story_map["story_multi"]["origin_type"] == "MULTI_SOURCE"

    def test_top5_distinct_sources_completeness(self) -> None:
        now = datetime.now(timezone.utc)
        stories: list[StoryRecord] = []
        for i in range(7):
            stories.append(
                StoryRecord(
                    story_id=f"story_{i}",
                    title=f"Event {i}",
                    category="society",
                    status="active",
                    created_at=now,
                    updated_at=now,
                    article_urls=[f"https://source{i}.com/a"],
                    article_count=1,
                    outlets=[f"Source_{i}"],
                    outlet_count=1,
                    centroid=[0.2] * 768,
                )
            )

        story_repo = InMemoryStoryRepository(stories)
        report = generate_trending_sanity_report(
            news_repo=MockNewsRepo(),
            story_repo=story_repo,
            engagement_repo=MockEngagementRepo(),
            limit=5,
            now=now,
        )

        top_5 = report["top_stories"][:5]
        assert len(top_5) == 5
        for s in top_5:
            assert "distinct_source_count" in s
            assert "is_single_origin" in s
            assert "score_breakdown" in s
            assert "rank" in s
            assert 1 <= s["rank"] <= 5


# ── 4. Benchmark Dataset Integrity & Schema ───────────────────────

class TestBenchmarkDatasetIntegrity:
    """Verifies labeled evaluation set schema, size, and real-world event composition."""

    def test_benchmark_schema_and_size(self) -> None:
        eval_path = Path("data/labeled_story_eval_set.json")
        raw_news_path = Path("data/news_data.json")

        dataset = build_or_load_eval_dataset(eval_path, raw_news_path, rebuild=True)

        # Requirement 1: >= 100 real articles
        assert len(dataset) >= 100, f"Expected >= 100 articles, got {len(dataset)}"

        # Ground truth schema verification
        required_keys = {"url", "title", "source", "category", "fetched_at", "ground_truth_story_id"}
        for art in dataset:
            missing = required_keys - set(art.keys())
            assert not missing, f"Article {art.get('url')} missing keys: {missing}"
            assert isinstance(art["url"], str) and art["url"].startswith("http")
            assert isinstance(art["title"], str) and len(art["title"].strip()) > 0
            assert isinstance(art["ground_truth_story_id"], str) and len(art["ground_truth_story_id"]) > 0

    def test_benchmark_multi_day_and_cross_category_composition(self) -> None:
        eval_path = Path("data/labeled_story_eval_set.json")
        raw_news_path = Path("data/news_data.json")

        dataset = build_or_load_eval_dataset(eval_path, raw_news_path)

        # Group by ground_truth_story_id
        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for art in dataset:
            clusters[art["ground_truth_story_id"]].append(art)

        # Check multi-article stories exist
        multi_article_stories = [cid for cid, members in clusters.items() if len(members) > 1]
        assert len(multi_article_stories) >= 6, f"Expected >= 6 multi-article stories, got {len(multi_article_stories)}"

        # Check Nan floods events exist
        nan_stories = [cid for cid in clusters if "flood" in cid or "nan" in cid]
        assert len(nan_stories) >= 1, f"Expected Nan flood crisis story, got {nan_stories}"

        # Check Senate collusion events exist
        senate_stories = [cid for cid in clusters if "senate" in cid]
        assert len(senate_stories) >= 1, f"Expected Senate collusion story, got {senate_stories}"

        # Check bombing incident exists
        bomb_stories = [cid for cid in clusters if "bomb" in cid or "pattani" in cid]
        assert len(bomb_stories) >= 1, f"Expected bombing story, got {bomb_stories}"

        # Check routine news hard negative test (gold prices on distinct dates)
        gold_stories = [cid for cid in clusters if "gold_price" in cid]
        assert len(gold_stories) >= 3, f"Expected 3 separate gold price stories on distinct dates, got {gold_stories}"

        # Check singletons exist
        singletons = [cid for cid in clusters if "singleton" in cid]
        assert len(singletons) >= 20, f"Expected >= 20 singletons, got {len(singletons)}"

        # Check cross-category coverage exists within multi-article stories
        cross_cat_found = False
        for members in clusters.values():
            distinct_cats = {m["category"] for m in members}
            if len(distinct_cats) >= 2:
                cross_cat_found = True
                break
        assert cross_cat_found, "Expected at least one cross-category story in benchmark"


# ── 5. End-to-End Evaluation Acceptance Criteria Verification ─────

class TestStoryEvaluationAcceptanceCriteria:
    """Verifies that StoryService achieves required B-cubed targets vs baseline."""

    def test_acceptance_criteria_targets_satisfied(self) -> None:
        eval_path = Path("data/labeled_story_eval_set.json")
        raw_news_path = Path("data/news_data.json")
        results_output_path = Path("data/evaluation_results.json")

        dataset = build_or_load_eval_dataset(eval_path, raw_news_path, rebuild=True)

        from backend.services.entity_extractor import get_entity_extractor
        from backend.services.trending_service import WangchanEmbedder

        embedder = WangchanEmbedder.get_instance()
        entity_extractor = get_entity_extractor()

        # Run Baseline
        base_res, _ = evaluate_semantic_clusterer(dataset, embedder)
        base_b3 = base_res["bcubed"]

        # Run StoryService
        story_res, _ = evaluate_story_service(dataset, embedder, entity_extractor)
        story_b3 = story_res["bcubed"]

        # Save evaluation results to data/evaluation_results.json
        eval_results_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "benchmark": {
                "dataset_file": str(eval_path),
                "total_articles": len(dataset),
                "total_ground_truth_stories": len({a["ground_truth_story_id"] for a in dataset}),
            },
            "baseline": base_res,
            "story_service": story_res,
            "acceptance_criteria": {
                "target_bcubed_precision": 0.85,
                "target_bcubed_f1": 0.75,
                "actual_bcubed_precision": story_b3["precision"],
                "actual_bcubed_f1": story_b3["f1"],
                "baseline_bcubed_f1": base_b3["f1"],
                "passed_bcubed_precision": bool(story_b3["precision"] >= 0.85),
                "passed_bcubed_f1": bool(story_b3["f1"] >= 0.75),
                "passed_strictly_higher_than_baseline": bool(story_b3["f1"] > base_b3["f1"]),
                "all_passed": bool(
                    story_b3["precision"] >= 0.85
                    and story_b3["f1"] >= 0.75
                    and story_b3["f1"] > base_b3["f1"]
                ),
            },
        }
        results_output_path.parent.mkdir(parents=True, exist_ok=True)
        results_output_path.write_text(
            json.dumps(eval_results_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Target Acceptance Criteria:
        # 1. B-cubed Precision >= 0.85
        # 2. B-cubed F1 >= 0.75
        # 3. B-cubed F1 strictly > baseline SemanticClusterer
        assert (
            story_b3["precision"] >= 0.85
        ), f"Expected B-cubed Precision >= 0.85, got {story_b3['precision']}"
        assert (
            story_b3["f1"] >= 0.75
        ), f"Expected B-cubed F1 >= 0.75, got {story_b3['f1']}"
        assert (
            story_b3["f1"] > base_b3["f1"]
        ), f"Expected StoryService F1 ({story_b3['f1']}) > Baseline F1 ({base_b3['f1']})"

    def test_trending_sanity_report_generation_and_serialization(self) -> None:
        sanity_report_output_path = Path("data/trending_sanity_report.json")
        report = generate_trending_sanity_report(limit=10)

        assert report["sanity_check_passed"] is True
        assert report["total_ranked_stories"] > 0
        top_5 = report["top_stories"][:5]
        assert len(top_5) >= 1
        for s in top_5:
            assert "distinct_source_count" in s
            assert "is_single_origin" in s

        sanity_report_output_path.parent.mkdir(parents=True, exist_ok=True)
        sanity_report_output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
