"""
reconcile_stories_job.py
─────────────────────────────────────────────────────────────────
SOLID  S — Audit, reconcile lifecycle status, and backfill Macro-Events.
SOLID  O — Supports CLI flags (--dry-run, --inactivity-hours, --backup).
SOLID  D — Injects StoryRepositoryPort and MacroEventRepositoryPort.
GRASP  Controller — Coordinates story lifecycle audit and macro-event backfill.
SAFETY ZERO DATA LOSS — Automated timestamped backup before any disk write.
SAFETY DRY-RUN MODE — Inspect proposed mutations before committing.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root in sys.path
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from backend.config import settings
from backend.repo.macro_event_repo import get_macro_event_repository
from backend.repo.story_repo import get_story_repository
from backend.schemas.macro_event_schema import MacroEventRecord
from backend.schemas.story_schema import StoryRecord
from backend.services.macro_event_service import MacroEventService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reconcile_stories")


def reconcile_stories(
    dry_run: bool = False,
    inactivity_hours: float = 72.0,
    create_backup: bool = True,
) -> dict[str, Any]:
    """
    Audit and reconcile story lifecycle states and macro-event relationships.
    Returns audit statistics dictionary.
    """
    now = datetime.now(timezone.utc)
    story_repo = get_story_repository()
    macro_repo = get_macro_event_repository()
    macro_service = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

    stories_file = getattr(
        settings,
        "stories_file",
        getattr(settings, "DATA_DIR", Path("data")) / "stories_data.json",
    )
    macros_file = getattr(
        settings,
        "macro_events_file",
        getattr(settings, "DATA_DIR", Path("data")) / "macro_events_data.json",
    )

    all_stories = story_repo.list_stories(limit=10000)
    logger.info("Auditing %d story records...", len(all_stories))

    stats: dict[str, Any] = {
        "total_stories": len(all_stories),
        "status_stale_active_to_dormant": 0,
        "status_stale_dormant_to_active": 0,
        "stories_missing_macro_id": 0,
        "macro_events_created": 0,
        "macro_events_linked": 0,
        "dry_run": dry_run,
    }

    stories_to_save: list[StoryRecord] = []

    # 1. Lifecycle Reconciliation
    for s in all_stories:
        was_active = (s.status == "active")
        is_now_active = s.is_active_dynamic(now=now, inactivity_threshold_hours=inactivity_hours)

        if was_active and not is_now_active:
            stats["status_stale_active_to_dormant"] += 1
            if not dry_run:
                s.status = "dormant"
                stories_to_save.append(s)
        elif not was_active and is_now_active:
            stats["status_stale_dormant_to_active"] += 1
            if not dry_run:
                s.status = "active"
                stories_to_save.append(s)

        if not s.macro_event_id:
            stats["stories_missing_macro_id"] += 1

    # 2. Backup if writing
    if not dry_run and create_backup:
        ts_str = now.strftime("%Y%m%d_%H%M%S")
        if stories_file.exists():
            bak_path = stories_file.with_name(f"{stories_file.stem}_{ts_str}.json.bak")
            shutil.copy2(stories_file, bak_path)
            logger.info("Created backup at %s", bak_path)
        if macros_file.exists():
            m_bak_path = macros_file.with_name(f"{macros_file.stem}_{ts_str}.json.bak")
            shutil.copy2(macros_file, m_bak_path)
            logger.info("Created backup at %s", m_bak_path)

    # 3. Save reconciled lifecycle stories
    if not dry_run and stories_to_save:
        story_repo.save_stories_batch(stories_to_save)
        logger.info("Updated %d stories with reconciled lifecycle status", len(stories_to_save))

    # 4. Macro-Event Backfill & SST Synchronization
    # Process stories in chronological order (earliest first)
    sorted_stories = sorted(all_stories, key=lambda s: s.first_article_at or s.created_at)

    for s in sorted_stories:
        if not s.macro_event_id:
            if dry_run:
                stats["macro_events_created"] += 1
            else:
                _macro, is_new = macro_service.assign_event(s)
                if is_new:
                    stats["macro_events_created"] += 1
                else:
                    stats["macro_events_linked"] += 1

    # 5. Derived Index Synchronization
    # Ensure every MacroEventRecord's child_event_ids matches StoryRecord.macro_event_id (SST)
    if not dry_run:
        all_macros = macro_repo.list_macro_events(limit=10000)
        macros_to_update: list[MacroEventRecord] = []
        for m in all_macros:
            child_stories = story_repo.get_stories_by_macro_id(m.macro_event_id)
            actual_child_ids = sorted([cs.story_id for cs in child_stories])
            if sorted(m.child_event_ids) != actual_child_ids:
                m.child_event_ids = actual_child_ids
                macros_to_update.append(m)

        if macros_to_update:
            macro_repo.save_macro_events_batch(macros_to_update)
            logger.info("Synchronized derived index for %d macro-events", len(macros_to_update))

    logger.info("Reconciliation complete: %s", stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile Story lifecycle and backfill Macro-Events")
    parser.add_argument("--dry-run", action="store_true", help="Audit only without writing changes")
    parser.add_argument("--inactivity-hours", type=float, default=72.0, help="Inactivity threshold in hours")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating backup file")
    args = parser.parse_args()

    reconcile_stories(
        dry_run=args.dry_run,
        inactivity_hours=args.inactivity_hours,
        create_backup=not args.no_backup,
    )


if __name__ == "__main__":
    main()
