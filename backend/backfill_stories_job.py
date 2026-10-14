"""
backend/backfill_stories_job.py
─────────────────────────────────────────────────────────────────
SOLID  S — Migration job to back-fill story_id into all news articles.
SOLID  D — Injects NewsRepositoryPort and StoryService for testability.
GRASP  Controller — Coordinates batch chronological processing and dual persistence.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.repo.story_repo import get_story_repository
from backend.schemas.news_schema import ArticleRecord
from backend.services.story_service import StoryService, get_story_service

logger = logging.getLogger(__name__)


def run_backfill(
    news_repo: NewsRepositoryPort | None = None,
    story_service: StoryService | None = None,
    limit: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run back-fill job:
    1. Loads all existing articles from NewsRepositoryPort.
    2. Sorts them chronologically (by fetched_at or created_at).
    3. Runs online assignment through StoryService.
    4. Updates each article's story_id.
    5. Saves updated articles back to NewsRepositoryPort and stories to StoryRepositoryPort.
    """
    printer = log_fn or print
    printer(f"[{datetime.now(timezone.utc):%H:%M:%S}] 🚀 Starting Story Back-fill Migration Job...")

    repo = news_repo or get_news_repository()
    service = story_service or get_story_service()

    articles = repo.load_news()
    total_found = len(articles)
    printer(f"  Found {total_found} articles in news repository.")

    if not articles:
        printer("  No articles to back-fill. Exiting.")
        return {
            "total_articles": 0,
            "processed": 0,
            "new_stories": 0,
            "merged_articles": 0,
        }

    # Sort articles chronologically
    def get_time_key(a: dict[str, Any]) -> str:
        return str(a.get("fetched_at") or a.get("created_at") or a.get("published_at") or "")

    sorted_articles = sorted(articles, key=get_time_key)

    if limit is not None and limit > 0:
        sorted_articles = sorted_articles[:limit]
        printer(f"  Processing limited subset: {len(sorted_articles)} articles.")

    processed = 0
    new_stories_count = 0
    merged_count = 0

    for idx, art_dict in enumerate(sorted_articles, start=1):
        try:
            record = ArticleRecord.model_validate(art_dict)
            story, is_new = service.assign_article(record)

            art_dict["story_id"] = story.story_id
            processed += 1

            if is_new:
                new_stories_count += 1
            else:
                merged_count += 1

            if idx % 500 == 0 or idx == len(sorted_articles):
                printer(
                    f"  Processed {idx}/{len(sorted_articles)} articles "
                    f"({new_stories_count} new stories, {merged_count} merges)..."
                )
        except Exception as exc:
            logger.warning("Error processing article at index %d (%s): %s", idx, art_dict.get("url"), exc)

    # Persist updated articles back to news repository
    printer("  💾 Saving updated articles with story_id to news repository...")
    repo.save_news(articles)

    story_repo = get_story_repository()
    total_stories = story_repo.count_stories()

    stats = {
        "total_articles": total_found,
        "processed": processed,
        "new_stories": new_stories_count,
        "merged_articles": merged_count,
        "total_stories_in_repo": total_stories,
    }

    printer(
        f"[{datetime.now(timezone.utc):%H:%M:%S}] ✅ Back-fill complete! "
        f"Processed: {processed}, New Stories: {new_stories_count}, Merges: {merged_count}, "
        f"Total Stories: {total_stories}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Back-fill story_id into existing news articles")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles to process")
    args = parser.parse_args()

    run_backfill(limit=args.limit)


if __name__ == "__main__":
    main()
