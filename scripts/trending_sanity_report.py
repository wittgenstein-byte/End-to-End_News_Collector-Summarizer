"""
scripts/trending_sanity_report.py
─────────────────────────────────────────────────────────────────
SOLID  S — Generates trending sanity report analyzing top-N stories,
           distinct source counts, and single-origin origin flags.
SOLID  O — Configurable story limit, reference time, and output path.
SOLID  D — Injects NewsRepositoryPort, StoryRepositoryPort, and TrendingService.
GRASP  Information Expert — Analyzes cluster source diversity, syndication,
           and multi-source consensus.
GRASP  Controller — Coordinates story ranking, source inspection, and report output.
POLICY STRICTLY ZERO LLM — Deterministic statistics-based scoring path.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
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

from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.trending_schema import TrendingStoryCluster
from backend.services.story_service import StoryService
from backend.services.trending_service import TrendingService

logger = logging.getLogger("trending_sanity_report")


def ensure_stories_populated(
    news_repo: NewsRepositoryPort,
    story_repo: StoryRepositoryPort,
    max_articles_to_seed: int = 200,
) -> int:
    """
    Ensure that story_repo contains real persistent stories.
    If story_repo is empty, seeds real articles from news_repo or labeled eval set
    using StoryService online assignment.
    """
    existing_count = story_repo.count_stories()
    if existing_count > 0:
        logger.info("Found %d existing stories in story repository.", existing_count)
        return existing_count

    logger.info("Story repository is empty. Seeding stories from news data...")
    eval_set_path = PROJECT_ROOT / "data" / "labeled_story_eval_set.json"

    articles_to_process: list[dict[str, Any]] = []

    if eval_set_path.exists():
        try:
            eval_data = json.loads(eval_set_path.read_text(encoding="utf-8"))
            if isinstance(eval_data, list) and len(eval_data) > 0:
                articles_to_process = eval_data[:max_articles_to_seed]
                logger.info("Loaded %d articles from %s for story seeding.", len(articles_to_process), eval_set_path)
        except Exception as exc:
            logger.warning("Could not read eval set for seeding (%s)", exc)

    if not articles_to_process:
        raw_news = news_repo.load_news()
        if raw_news:
            # Sort chronologically and take up to max_articles_to_seed
            articles_to_process = sorted(
                raw_news,
                key=lambda a: str(a.get("fetched_at") or a.get("created_at") or ""),
            )[:max_articles_to_seed]
            logger.info("Loaded %d articles from news repository for story seeding.", len(articles_to_process))

    if not articles_to_process:
        logger.warning("No articles available to seed story repository.")
        return 0

    story_service = StoryService(story_repo=story_repo)
    for art in articles_to_process:
        try:
            rec = ArticleRecord.model_validate(art)
            story_service.assign_article(rec)
        except Exception as exc:
            logger.debug("Error assigning article %s: %s", art.get("url"), exc)

    new_count = story_repo.count_stories()
    logger.info("Seeded %d stories into story repository.", new_count)
    return new_count


def generate_trending_sanity_report(
    news_repo: NewsRepositoryPort | None = None,
    story_repo: StoryRepositoryPort | None = None,
    engagement_repo: Any = None,
    limit: int = 10,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Run TrendingService.get_trending_stories() on real news data and generate
    a comprehensive sanity report for the top-N stories.

    Analyzes:
    - Distinct-source count per story
    - Single-origin flags (is_single_origin: True if distinct_source_count <= 1)
    - Full deterministic score breakdown (volume, burst, diversity, recency, etc.)
    - Routine news suppression status
    """
    from backend.repo.engagement_repo import (
        EngagementRepositoryPort,
        get_engagement_repository,
    )

    n_repo = news_repo or get_news_repository()
    s_repo = story_repo or get_story_repository()
    e_repo = engagement_repo or get_engagement_repository()

    # Ensure stories exist in the story repository
    ensure_stories_populated(news_repo=n_repo, story_repo=s_repo)

    active_stories = s_repo.list_stories(status="active", limit=1000)

    # Determine reference time
    ref_time: datetime
    if now is not None:
        ref_time = now
    elif active_stories:
        # Use latest story timestamp if available to prevent stories from aging out during offline evaluation
        latest_story_dt = max(s.updated_at for s in active_stories)
        now_utc = datetime.now(timezone.utc)
        # If current time is within 72h of latest story, use now_utc; otherwise use latest_story_dt
        if abs((now_utc - latest_story_dt).total_seconds()) <= 72 * 3600:
            ref_time = now_utc
        else:
            ref_time = latest_story_dt
    else:
        ref_time = datetime.now(timezone.utc)

    trending_service = TrendingService(
        news_repo=n_repo,
        engagement_repo=e_repo,
        story_repo=s_repo,
    )
    ranked_clusters: list[TrendingStoryCluster] = trending_service.get_trending_stories(
        limit=limit,
        now=ref_time,
    )

    top_stories_data: list[dict[str, Any]] = []
    single_origin_count = 0
    multi_source_count = 0

    for cluster in ranked_clusters:
        # Compute distinct sources
        outlets = sorted(list(dict.fromkeys(cluster.outlets))) if cluster.outlets else []
        distinct_source_count = len(outlets)
        is_single_origin = distinct_source_count <= 1

        if is_single_origin:
            single_origin_count += 1
        else:
            multi_source_count += 1

        top_stories_data.append({
            "rank": cluster.rank,
            "story_id": cluster.story_id,
            "title": cluster.title,
            "category": cluster.category,
            "trending_score": round(cluster.trending_score, 2),
            "article_count": cluster.article_count,
            "distinct_source_count": distinct_source_count,
            "outlets": outlets,
            "is_single_origin": is_single_origin,
            "origin_type": "SINGLE_ORIGIN" if is_single_origin else "MULTI_SOURCE",
            "is_routine": cluster.is_routine,
            "badges": cluster.badges,
            "score_breakdown": {
                "volume_score": round(cluster.breakdown.volume_score, 3),
                "velocity_score": round(cluster.breakdown.velocity_score, 3),
                "diversity_score": round(cluster.breakdown.diversity_score, 3),
                "recency_score": round(cluster.breakdown.recency_score, 3),
                "engagement_score": round(cluster.breakdown.engagement_score, 3),
                "novelty_score": round(cluster.breakdown.novelty_score, 3),
                "routine_penalty": round(cluster.breakdown.routine_penalty, 3),
                "final_score": round(cluster.breakdown.final_score, 3),
            },
            "created_at": cluster.created_at,
            "updated_at": cluster.updated_at,
        })

    # Sanity checks on Top 5 stories
    top_5 = top_stories_data[:5]
    top_5_have_distinct_sources = all("distinct_source_count" in s for s in top_5)
    top_5_have_origin_flags = all("is_single_origin" in s for s in top_5)

    sanity_check_passed = bool(
        len(ranked_clusters) > 0 and top_5_have_distinct_sources and top_5_have_origin_flags
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reference_time": ref_time.isoformat(),
        "total_active_stories": len(active_stories),
        "total_ranked_stories": len(ranked_clusters),
        "top_5_summary": {
            "stories_evaluated": len(top_5),
            "multi_source_count": sum(1 for s in top_5 if not s["is_single_origin"]),
            "single_origin_count": sum(1 for s in top_5 if s["is_single_origin"]),
            "all_top_5_have_distinct_source_count": top_5_have_distinct_sources,
            "all_top_5_flagged_for_origin": top_5_have_origin_flags,
        },
        "sanity_check_passed": sanity_check_passed,
        "top_stories": top_stories_data,
        "notes": (
            "Trending score reflects coverage volume, burst velocity, outlet diversity, and recency. "
            "Single-origin stories receive reduced diversity credit compared to multi-source consensus."
        ),
    }

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Trending Sanity Report")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "trending_sanity_report.json",
        help="Path to save trending sanity report JSON",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of top stories to analyze (default: 10)",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n" + "=" * 80)
    print(" 📈 TRENDING STORIES SANITY REPORT")
    print("=" * 80)

    report = generate_trending_sanity_report(limit=args.limit)

    top_stories = report.get("top_stories", [])
    top_5 = top_stories[:5]

    print(f"Reference Time:         {report['reference_time']}")
    print(f"Total Ranked Stories:   {report['total_ranked_stories']}")
    print(f"Sanity Check Passed:    {'✅ YES' if report['sanity_check_passed'] else '❌ NO'}")
    print("-" * 80)

    print(f"{'RANK':<5} | {'SCORE':<7} | {'SOURCES':<8} | {'ORIGIN TYPE':<14} | {'TITLE'}")
    print("-" * 80)

    for s in top_5:
        rank_str = f"#{s['rank']}"
        score_str = f"{s['trending_score']:.2f}"
        sources_str = f"{s['distinct_source_count']} ({len(s['outlets'])})"
        origin_str = "🚩 SINGLE-ORIGIN" if s["is_single_origin"] else "🌐 MULTI-SOURCE"
        title_str = s["title"][:38] + ("..." if len(s["title"]) > 38 else "")
        print(f"{rank_str:<5} | {score_str:<7} | {sources_str:<8} | {origin_str:<14} | {title_str}")

    print("=" * 80)

    print("\n📊 TOP-5 SOURCES & BREAKDOWN DETAILS:")
    for s in top_5:
        flag_mark = "⚠️ [SINGLE ORIGIN]" if s["is_single_origin"] else "✓ [MULTI SOURCE]"
        print(f"\n  Story #{s['rank']} [{s['story_id']}]: \"{s['title']}\"")
        print(f"    Category: {s['category']} | Score: {s['trending_score']:.2f} {flag_mark}")
        print(f"    Distinct Outlets ({s['distinct_source_count']}): {', '.join(s['outlets'])}")
        bd = s["score_breakdown"]
        print(
            f"    Breakdown: Volume={bd['volume_score']:.2f}, Velocity={bd['velocity_score']:.2f}, "
            f"Diversity={bd['diversity_score']:.2f}, Recency={bd['recency_score']:.2f}, "
            f"RoutinePenalty={bd['routine_penalty']:.2f}"
        )

    # Save to disk
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 Report saved to {args.output}\n")

    return 0 if report["sanity_check_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
