"""
scripts/evaluate_stories.py
─────────────────────────────────────────────────────────────────
SOLID  S — Quantitative evaluation harness for story identification:
           Pairwise metrics, B-cubed metrics, false merge/split analysis.
SOLID  O — Supports pluggable clustering algorithms (SemanticClusterer baseline,
           StoryService online layer, future models).
SOLID  D — Injects StoryRepositoryPort, WangchanEmbedder, and EntityExtractor.
GRASP  Information Expert — Computes formal Bagga & Baldwin (1998) / Amigó et al. (2009)
           clustering precision, recall, and F1.
GRASP  Controller — Coordinates benchmark loading, baseline clustering, online assignment,
           and evaluation report serialization.
POLICY STRICTLY ZERO JACCARD — Zero token Jaccard or lexical overlap.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Reconfigure stdout and stderr for UTF-8 encoding support on Windows cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.repo.story_repo import StoryRepositoryPort
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import StoryRecord
from backend.services.entity_extractor import EntityExtractor, get_entity_extractor
from backend.services.story_service import StoryService
from backend.services.trending_service import (
    SemanticClusterer,
    WangchanEmbedder,
    parse_article_time,
)

logger = logging.getLogger("evaluate_stories")


# ── In-Memory Story Repository for Isolated Evaluation ─────────────

class InMemoryStoryRepository(StoryRepositoryPort):
    """Clean in-memory repository implementing StoryRepositoryPort."""

    def __init__(self, stories: list[StoryRecord] | None = None) -> None:
        self.stories: dict[str, StoryRecord] = {}
        self.url_to_story_id: dict[str, str] = {}
        if stories:
            for s in stories:
                self.save_story(s)

    def get_story(self, story_id: str) -> StoryRecord | None:
        clean_id = story_id.strip() if story_id else ""
        return self.stories.get(clean_id)

    def save_story(self, story: StoryRecord) -> None:
        self.stories[story.story_id] = story
        for url in story.article_urls:
            clean_url = url.strip() if url else ""
            if clean_url:
                self.url_to_story_id[clean_url] = story.story_id

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
        if status:
            target_status = status.strip().lower()
            items = [s for s in items if s.status.strip().lower() == target_status]
        items.sort(key=lambda s: s.updated_at, reverse=True)
        return items[offset : offset + limit]

    def find_candidate_stories(
        self,
        since_time: datetime,
        category: str | None = None,
    ) -> list[StoryRecord]:
        norm_since = since_time if since_time.tzinfo else since_time.replace(tzinfo=timezone.utc)
        cat_filter = category.strip().lower() if category and category.strip().lower() != "all" else None

        candidates: list[StoryRecord] = []
        for s in self.stories.values():
            s_dt = s.updated_at if s.updated_at.tzinfo else s.updated_at.replace(tzinfo=timezone.utc)
            if s_dt >= norm_since:
                if cat_filter is not None and s.category.strip().lower() != cat_filter:
                    continue
                candidates.append(s)

        candidates.sort(key=lambda s: s.updated_at, reverse=True)
        return candidates

    def get_stories_by_ids(self, story_ids: list[str]) -> list[StoryRecord]:
        res: list[StoryRecord] = []
        for sid in story_ids:
            clean_id = sid.strip() if sid else ""
            if clean_id in self.stories:
                res.append(self.stories[clean_id])
        return res

    def get_story_by_article_url(self, url: str) -> StoryRecord | None:
        clean_url = url.strip() if url else ""
        sid = self.url_to_story_id.get(clean_url)
        return self.stories.get(sid) if sid else None

    def count_stories(self, status: str | None = None) -> int:
        if status:
            target_status = status.strip().lower()
            return sum(1 for s in self.stories.values() if s.status.strip().lower() == target_status)
        return len(self.stories)


# ── Formal Evaluation Metrics ─────────────────────────────────────

def calculate_pairwise_metrics(
    ground_truth: list[str],
    predictions: list[str],
) -> dict[str, Any]:
    """
    Calculate Pairwise Precision, Recall, F1, False Merges (FP), and False Splits (FN).
    Examines all N*(N-1)/2 unique article pairs.
    """
    n = len(ground_truth)
    if n != len(predictions):
        raise ValueError(f"Length mismatch: {n} ground truth vs {len(predictions)} predictions")

    if n < 2:
        return {
            "total_pairs": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "tn": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "false_merges": 0,
            "false_splits": 0,
        }

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for i in range(n):
        gt_i = ground_truth[i]
        pred_i = predictions[i]
        for j in range(i + 1, n):
            same_gt = gt_i == ground_truth[j]
            same_pred = pred_i == predictions[j]

            if same_gt and same_pred:
                tp += 1
            elif not same_gt and same_pred:
                fp += 1  # False merge
            elif same_gt and not same_pred:
                fn += 1  # False split
            else:
                tn += 1

    total_pairs = tp + fp + fn + tn
    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 1.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float((2.0 * precision * recall) / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "total_pairs": total_pairs,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_merges": fp,
        "false_splits": fn,
    }


def calculate_bcubed_metrics(
    ground_truth: list[str],
    predictions: list[str],
) -> dict[str, Any]:
    """
    Calculate B-cubed Precision, Recall, and F1 (Bagga & Baldwin 1998, Amigó et al. 2009).
    Averages the precision and recall computed for each item's predicted cluster vs its ground truth cluster.
    """
    n = len(ground_truth)
    if n != len(predictions):
        raise ValueError(f"Length mismatch: {n} ground truth vs {len(predictions)} predictions")

    if n == 0:
        return {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
        }

    # Map each cluster ID to set of article indices
    gt_clusters: dict[str, set[int]] = defaultdict(set)
    pred_clusters: dict[str, set[int]] = defaultdict(set)

    for idx, (gt, pred) in enumerate(zip(ground_truth, predictions)):
        gt_clusters[gt].add(idx)
        pred_clusters[pred].add(idx)

    prec_sum = 0.0
    rec_sum = 0.0

    for idx, (gt, pred) in enumerate(zip(ground_truth, predictions)):
        s_pred = pred_clusters[pred]
        s_gt = gt_clusters[gt]
        intersection_size = len(s_pred.intersection(s_gt))

        prec_i = intersection_size / len(s_pred) if len(s_pred) > 0 else 1.0
        rec_i = intersection_size / len(s_gt) if len(s_gt) > 0 else 1.0

        prec_sum += prec_i
        rec_sum += rec_i

    bcubed_precision = float(prec_sum / n)
    bcubed_recall = float(rec_sum / n)
    bcubed_f1 = (
        float((2.0 * bcubed_precision * bcubed_recall) / (bcubed_precision + bcubed_recall))
        if (bcubed_precision + bcubed_recall) > 0
        else 0.0
    )

    return {
        "precision": round(bcubed_precision, 4),
        "recall": round(bcubed_recall, 4),
        "f1": round(bcubed_f1, 4),
    }


# ── Benchmark Dataset Builder & Loader ────────────────────────────

def build_or_load_eval_dataset(
    eval_file_path: Path,
    raw_news_path: Path,
    rebuild: bool = False,
) -> list[dict[str, Any]]:
    """
    Load labeled evaluation dataset from disk or construct it from data/news_data.json.
    Ensures >= 100 real articles covering multi-day events, cross-categories, routine news, and singletons.
    """
    if eval_file_path.exists() and not rebuild:
        try:
            content = eval_file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list) and len(data) >= 100:
                logger.info("Loaded %d articles from existing benchmark at %s", len(data), eval_file_path)
                return data
        except Exception as exc:
            logger.warning("Could not load existing benchmark file (%s), rebuilding...", exc)

    if not raw_news_path.exists():
        raise FileNotFoundError(f"Raw news dataset not found at {raw_news_path}")

    logger.info("Building labeled benchmark dataset from %s...", raw_news_path)
    raw_content = json.loads(raw_news_path.read_text(encoding="utf-8"))
    raw_articles: list[dict[str, Any]] = raw_content.get("articles", [])

    used_urls: set[str] = set()
    dataset: list[dict[str, Any]] = []

    def add_match(article: dict[str, Any], gt_story_id: str) -> bool:
        url = str(article.get("url") or "").strip()
        if not url or url in used_urls:
            return False
        used_urls.add(url)
        # Limit summary to first substantive paragraph / 300 chars to avoid NER sequence length boundary
        full_summary = str(article.get("summary") or "").strip()
        brief_summary = full_summary[:300] if len(full_summary) > 300 else full_summary
        dataset.append({
            "url": url,
            "title": str(article.get("title") or "").strip(),
            "summary": brief_summary,
            "source": str(article.get("source") or "").strip(),
            "category": str(article.get("category") or "society").strip().lower(),
            "fetched_at": str(article.get("fetched_at") or "").strip(),
            "ground_truth_story_id": gt_story_id,
        })
        return True

    # 1. story_nan_floods_crisis (Nan floods multi-day crisis across environment, society, politics, economy)
    # Real event spanning Aug 23 - Aug 31 (~8 days). Target: 28 articles across 10+ sources
    c_flood = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        s = str(a.get("summary") or "")
        if (
            "น่าน" in t
            and any(kw in (t + s) for kw in ("น้ำท่วม", "ดินโคลน", "ฝาย", "เยียวยา", "เพื่อนพึ่ง", "ข่าวปลอม", "ปัว", "ธงน้อย"))
        ):
            if add_match(a, "story_nan_floods_crisis"):
                c_flood += 1
                if c_flood >= 28:
                    break

    # 2. story_senate_collusion (Senate collusion investigation event across politics)
    # Real event spanning Aug 24 - Aug 28. Target: 15 articles
    c_senate = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        s = str(a.get("summary") or "")
        if (
            any(sw in t for sw in ("สว.", "ส.ว.", "วุฒิสภา", "ผู้สมัคร สว"))
            and any(kw in (t + s) for kw in ("ฮั้ว", "กกต.", "ไอลอว์", "iLaw", "1,767", "1767", "229", "ปิดสำนวน", "ป.ป.ช."))
        ):
            if add_match(a, "story_senate_collusion"):
                c_senate += 1
                if c_senate >= 15:
                    break

    # 3. story_pattani_pho_ming_bomb (Pattani Pho Ming municipal office arson and bomb attack)
    # Target: 4 articles
    c_bomb = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        s = str(a.get("summary") or "")
        if "พ่อมิ่ง" in t or "พ่อมิ่ง" in s or (
            "ปัตตานี" in t and ("ระเบิด" in t or "วางเพลิง" in t or "เผา" in t) and ("เทศบาล" in t or "อบต." in t)
        ):
            if add_match(a, "story_pattani_pho_ming_bomb"):
                c_bomb += 1
                if c_bomb >= 4:
                    break

    # 4. story_paralympics_paris_2024 (Paris 2024 Paralympics preparation)
    # Target: 3 articles
    c_para = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        if ("พาราลิมปิก" in t or "พาราลิมปิกเกมส์" in t) and "2024" in t:
            if add_match(a, "story_paralympics_paris_2024"):
                c_para += 1
                if c_para >= 3:
                    break

    # 5. story_gold_price_2026_08_24 (Routine daily gold price report on 2026-08-24)
    # Target: 3 articles
    c_g1 = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        f = str(a.get("fetched_at") or "")
        if ("ราคาทอง" in t or "ทองคำ" in t) and "2026-08-24" in f:
            if add_match(a, "story_gold_price_2026_08_24"):
                c_g1 += 1
                if c_g1 >= 3:
                    break

    # 6. story_gold_price_2026_08_28 (Routine daily gold price report on 2026-08-28)
    # Target: 3 articles
    c_g2 = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        f = str(a.get("fetched_at") or "")
        if ("ราคาทอง" in t or "ทองคำ" in t) and "2026-08-28" in f:
            if add_match(a, "story_gold_price_2026_08_28"):
                c_g2 += 1
                if c_g2 >= 3:
                    break

    # 7. story_gold_price_2026_09_02 (Routine daily gold price report on 2026-09-02)
    # Target: 3 articles
    c_g3 = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        f = str(a.get("fetched_at") or "")
        if ("ราคาทอง" in t or "ทองคำ" in t) and "2026-09-02" in f:
            if add_match(a, "story_gold_price_2026_09_02"):
                c_g3 += 1
                if c_g3 >= 3:
                    break

    # 8. story_fuel_price_2026_08_24 (Routine retail fuel price change on 2026-08-24)
    # Target: 3 articles
    c_f1 = 0
    for a in raw_articles:
        t = str(a.get("title") or "")
        f = str(a.get("fetched_at") or "")
        if ("ราคาน้ำมัน" in t or "น้ำมันขายปลีก" in t) and "2026-08-24" in f:
            if add_match(a, "story_fuel_price_2026_08_24"):
                c_f1 += 1
                if c_f1 >= 3:
                    break

    # 9. Singletons & Routine Distractors across categories
    # Target: 52 distinct singleton articles to reach exactly 114 total articles
    target_singletons = 52
    singleton_count = 0

    categories_cycle = [
        "sports", "technology", "world", "entertainment", "health", "economy", "society", "politics"
    ]
    cat_idx = 0

    for a in raw_articles:
        url = str(a.get("url") or "").strip()
        if url in used_urls:
            continue
        cat = str(a.get("category") or "").strip().lower()
        t = str(a.get("title") or "")

        # Skip articles from known big events to avoid false singleton labeling
        if any(kw in t for kw in ("น้ำท่วม", "น่าน", "สว.", "ส.ว.", "กกต.", "ทองคำ", "ราคาทอง", "ราคาน้ำมัน", "พาราลิมปิก")):
            continue

        desired_cat = categories_cycle[cat_idx % len(categories_cycle)]
        if cat == desired_cat or (cat not in ("", "society") and singleton_count > 30):
            singleton_id = f"singleton_{singleton_count + 1:02d}_{cat}"
            if add_match(a, singleton_id):
                singleton_count += 1
                cat_idx += 1
                if singleton_count >= target_singletons:
                    break

    logger.info(
        "Built benchmark dataset: %d total articles, %d multi-article topics, %d singletons",
        len(dataset),
        17,
        singleton_count,
    )

    # Save to disk
    eval_file_path.parent.mkdir(parents=True, exist_ok=True)
    eval_file_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved benchmark dataset to %s", eval_file_path)

    return dataset


# ── Model Evaluators ──────────────────────────────────────────────

def evaluate_semantic_clusterer(
    dataset: list[dict[str, Any]],
    embedder: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Evaluate the baseline SemanticClusterer on the benchmark set.
    """
    clusterer = SemanticClusterer(
        cosine_threshold=0.92,
        cohesion_threshold=0.88,
        time_window_hours=36.0,
    )

    # Encode all articles
    payload = [{"title": a["title"], "summary": a.get("summary", "")} for a in dataset]
    embeddings = embedder.encode_articles(payload)

    # Article times
    times = [parse_article_time(a.get("fetched_at")) for a in dataset]

    # Cluster articles
    clustered_results = clusterer.cluster_articles(dataset, embeddings, times)

    # Map each article index to assigned cluster_id
    n = len(dataset)
    pred_map: dict[int, str] = {}
    for item in clustered_results:
        idx = item["index"]
        cid = item["cluster_id"]
        pred_map[idx] = cid

    # Unclustered articles receive unique singleton IDs
    predictions: list[str] = [pred_map.get(i, f"unclustered_{i}") for i in range(n)]
    ground_truth = [a["ground_truth_story_id"] for a in dataset]

    pairwise = calculate_pairwise_metrics(ground_truth, predictions)
    bcubed = calculate_bcubed_metrics(ground_truth, predictions)

    unique_clusters = len(set(predictions))
    metadata = {
        "model": "SemanticClusterer (Baseline)",
        "cosine_threshold": 0.92,
        "cohesion_threshold": 0.88,
        "time_window_hours": 36.0,
        "predicted_clusters_count": unique_clusters,
    }

    results = {
        "metadata": metadata,
        "pairwise": pairwise,
        "bcubed": bcubed,
    }
    return results, {"predictions": predictions}


def evaluate_story_service(
    dataset: list[dict[str, Any]],
    embedder: Any,
    entity_extractor: EntityExtractor,
    high_threshold: float = 0.85,
    low_threshold: float = 0.74,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Evaluate the new online incremental StoryService on the benchmark set in chronological arrival order.
    """
    # Sort dataset chronologically to reflect real-world online arrival order
    indexed_dataset = list(enumerate(dataset))
    indexed_dataset.sort(key=lambda item: parse_article_time(item[1].get("fetched_at")))

    # Fresh in-memory repository for clean evaluation
    in_memory_repo = InMemoryStoryRepository()

    story_service = StoryService(
        story_repo=in_memory_repo,
        embedder=embedder,
        entity_extractor=entity_extractor,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
        candidate_window_hours=72.0,
        ema_alpha=0.85,
    )

    # Assign articles one by one
    predicted_story_by_url: dict[str, str] = {}
    for orig_idx, art in indexed_dataset:
        rec = ArticleRecord.model_validate(art)
        story, _ = story_service.assign_article(rec)
        predicted_story_by_url[rec.url] = story.story_id

    # Restore original dataset order for identical item-by-item comparison
    n = len(dataset)
    predictions = [predicted_story_by_url[dataset[i]["url"]] for i in range(n)]
    ground_truth = [a["ground_truth_story_id"] for a in dataset]

    pairwise = calculate_pairwise_metrics(ground_truth, predictions)
    bcubed = calculate_bcubed_metrics(ground_truth, predictions)

    unique_stories = len(set(predictions))
    metadata = {
        "model": "StoryService (Online Incremental)",
        "high_threshold": high_threshold,
        "low_threshold": low_threshold,
        "candidate_window_hours": 72.0,
        "ema_alpha": 0.85,
        "predicted_stories_count": unique_stories,
    }

    results = {
        "metadata": metadata,
        "pairwise": pairwise,
        "bcubed": bcubed,
    }
    return results, {"predictions": predictions}


# ── CLI & Report Generator ────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Story Identification vs Baseline")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "data" / "labeled_story_eval_set.json",
        help="Path to labeled evaluation dataset JSON",
    )
    parser.add_argument(
        "--raw-news",
        type=Path,
        default=PROJECT_ROOT / "data" / "news_data.json",
        help="Path to raw collected news data JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation_results.json",
        help="Path to save evaluation output results JSON",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild benchmark dataset from raw news even if file exists",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n" + "=" * 78)
    print(" 🚀 STORY IDENTIFICATION EVALUATION HARNESS")
    print("=" * 78)

    # 1. Load or build benchmark dataset
    dataset = build_or_load_eval_dataset(
        eval_file_path=args.dataset,
        raw_news_path=args.raw_news,
        rebuild=args.rebuild,
    )
    n = len(dataset)
    gt_story_ids = [a["ground_truth_story_id"] for a in dataset]
    distinct_gt_stories = len(set(gt_story_ids))

    print(f"Dataset Size:           {n} real articles")
    print(f"Ground Truth Stories:   {distinct_gt_stories} distinct events")
    print(f"Dataset Path:           {args.dataset}")
    print("-" * 78)

    # 2. Initialize Embedder and NER
    print("⏳ Initializing WangchanBERTa Embedder & PyThaiNLP Entity Extractor...")
    embedder = WangchanEmbedder.get_instance()
    entity_extractor = get_entity_extractor()

    # 3. Evaluate Baseline SemanticClusterer
    print("\n📊 [1/2] Evaluating Baseline SemanticClusterer...")
    baseline_results, _ = evaluate_semantic_clusterer(dataset, embedder)

    # 4. Evaluate New StoryService
    print("📊 [2/2] Evaluating New StoryService Online Incremental Layer...")
    story_results, _ = evaluate_story_service(dataset, embedder, entity_extractor)

    # 5. Extract Key Metrics
    base_pair = baseline_results["pairwise"]
    base_b3 = baseline_results["bcubed"]
    story_pair = story_results["pairwise"]
    story_b3 = story_results["bcubed"]

    # 6. Format Comparison Table
    print("\n" + "=" * 78)
    print(f"{'METRIC':<26} | {'BASELINE (SemanticClusterer)':<24} | {'NEW (StoryService)':<22}")
    print("-" * 78)
    print(f"{'B-cubed Precision':<26} | {base_b3['precision']:<24.4f} | {story_b3['precision']:<22.4f}")
    print(f"{'B-cubed Recall':<26} | {base_b3['recall']:<24.4f} | {story_b3['recall']:<22.4f}")
    print(f"{'B-cubed F1':<26} | {base_b3['f1']:<24.4f} | {story_b3['f1']:<22.4f}")
    print("-" * 78)
    print(f"{'Pairwise Precision':<26} | {base_pair['precision']:<24.4f} | {story_pair['precision']:<22.4f}")
    print(f"{'Pairwise Recall':<26} | {base_pair['recall']:<24.4f} | {story_pair['recall']:<22.4f}")
    print(f"{'Pairwise F1':<26} | {base_pair['f1']:<24.4f} | {story_pair['f1']:<22.4f}")
    print("-" * 78)
    print(f"{'False Merges (FP pairs)':<26} | {base_pair['false_merges']:<24} | {story_pair['false_merges']:<22}")
    print(f"{'False Splits (FN pairs)':<26} | {base_pair['false_splits']:<24} | {story_pair['false_splits']:<22}")
    print(f"{'Predicted Clusters Count':<26} | {baseline_results['metadata']['predicted_clusters_count']:<24} | {story_results['metadata']['predicted_stories_count']:<22}")
    print("=" * 78)

    # 7. Check Acceptance Criteria
    # Target: B-cubed Precision >= 0.85, B-cubed F1 >= 0.75, B-cubed F1 > baseline
    target_prec = 0.85
    target_f1 = 0.75

    passed_prec = story_b3["precision"] >= target_prec
    passed_f1 = story_b3["f1"] >= target_f1
    passed_strictly_higher = story_b3["f1"] > base_b3["f1"]
    all_passed = bool(passed_prec and passed_f1 and passed_strictly_higher)

    print("\n🎯 ACCEPTANCE CRITERIA VERIFICATION:")
    print(f"  [1] B-cubed Precision >= {target_prec}:  {'✅ PASS' if passed_prec else '❌ FAIL'} ({story_b3['precision']:.4f})")
    print(f"  [2] B-cubed F1 >= {target_f1}:         {'✅ PASS' if passed_f1 else '❌ FAIL'} ({story_b3['f1']:.4f})")
    print(f"  [3] B-cubed F1 > Baseline:      {'✅ PASS' if passed_strictly_higher else '❌ FAIL'} ({story_b3['f1']:.4f} > {base_b3['f1']:.4f})")

    if all_passed:
        print("\n🎉 ALL ACCEPTANCE CRITERIA SATISFIED!\n")
    else:
        print("\n⚠️ WARNING: Some acceptance criteria were not satisfied.\n")

    # 8. Serialize Results
    results_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmark": {
            "dataset_file": str(args.dataset),
            "total_articles": n,
            "total_ground_truth_stories": distinct_gt_stories,
        },
        "baseline": baseline_results,
        "story_service": story_results,
        "acceptance_criteria": {
            "target_bcubed_precision": target_prec,
            "target_bcubed_f1": target_f1,
            "actual_bcubed_precision": story_b3["precision"],
            "actual_bcubed_f1": story_b3["f1"],
            "baseline_bcubed_f1": base_b3["f1"],
            "passed_bcubed_precision": passed_prec,
            "passed_bcubed_f1": passed_f1,
            "passed_strictly_higher_than_baseline": passed_strictly_higher,
            "all_passed": all_passed,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 Results saved to {args.output}\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
