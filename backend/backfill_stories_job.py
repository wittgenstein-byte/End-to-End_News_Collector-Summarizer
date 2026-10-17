"""
backend/backfill_stories_job.py
─────────────────────────────────────────────────────────────────
SOLID  S — Migration and evaluation job for persistent story_id assignment.
SOLID  O — Supports audit, shadow evaluation, dry-run, and production backfill.
SOLID  D — Injects repositories and services for deterministic sandboxing.
GRASP  Information Expert — Computes file SHA-256 hashes, assignment diffs,
            and cluster migration statistics.
POLICY STRICT PRODUCTION DATA PROTECTION — Safe by default. Never mutates
            production files unless explicitly confirmed with --apply.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

# Reconfigure stdout and stderr for UTF-8 encoding support on Windows cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.repo.macro_event_repo import (
    InMemoryMacroEventRepository,
    MacroEventRepositoryPort,
    get_macro_event_repository,
)
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.repo.story_repo import (
    FileStoryRepository,
    StoryRepositoryPort,
    get_story_repository,
)
from backend.schemas.news_schema import ArticleRecord
from backend.services.macro_event_service import MacroEventService
from backend.services.story_service import StoryService, get_story_service

logger = logging.getLogger(__name__)

PRODUCTION_FILES = [
    BASE_DIR / "data" / "news_collector.db",
    BASE_DIR / "data" / "stories_data.json",
    BASE_DIR / "data" / "macro_events_data.json",
    BASE_DIR / "data" / "news_data.json",
]


def compute_file_hashes() -> dict[str, str]:
    """Computes SHA-256 digests of all production data files."""
    hashes: dict[str, str] = {}
    for p in PRODUCTION_FILES:
        if p.exists():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            hashes[str(p.name)] = h
        else:
            hashes[str(p.name)] = "FILE_NOT_FOUND"
    return hashes


def run_audit(
    news_repo: NewsRepositoryPort | None = None,
    story_repo: StoryRepositoryPort | None = None,
    macro_repo: MacroEventRepositoryPort | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Read-only audit: inspects current state of news, stories, and macro-events
    without modifying any persistent records or database files.
    """
    printer = log_fn or print
    printer("\n" + "=" * 78)
    printer(" 🔍 READ-ONLY PRODUCTION DATABASE AUDIT REPORT")
    printer("=" * 78)

    hashes = compute_file_hashes()
    printer("📁 Production File Integrity Hashes (SHA-256):")
    for fname, fhash in hashes.items():
        printer(f"   • {fname:<24}: {fhash}")
    printer("-" * 78)

    repo = news_repo or get_news_repository()
    s_repo = story_repo or get_story_repository()
    m_repo = macro_repo or get_macro_event_repository()

    articles = repo.load_news()
    total_articles = len(articles)

    assigned_count = 0
    unassigned_count = 0
    categories_counter: Counter[str] = Counter()
    sources_counter: Counter[str] = Counter()

    for a in articles:
        sid = a.get("story_id")
        if sid and str(sid).strip():
            assigned_count += 1
        else:
            unassigned_count += 1
        cat = str(a.get("category") or "unspecified").lower()
        src = str(a.get("source") or "unknown").strip()
        categories_counter[cat] += 1
        sources_counter[src] += 1

    pct_assigned = (assigned_count / total_articles * 100.0) if total_articles else 0.0

    printer("📰 Articles Overview:")
    printer(f"   • Total Articles          : {total_articles}")
    printer(f"   • Assigned to Stories     : {assigned_count} ({pct_assigned:.1f}%)")
    printer(f"   • Unassigned (Pending)    : {unassigned_count} ({100.0 - pct_assigned:.1f}%)")
    printer(f"   • Top Sources             : {dict(sources_counter.most_common(5))}")
    printer(f"   • Categories Breakdown    : {dict(categories_counter)}")
    printer("-" * 78)

    # Stories inspection
    all_stories = s_repo.list_stories(limit=10000)
    total_stories = len(all_stories)
    verified_stories = sum(1 for s in all_stories if getattr(s, "verification_status", "") == "verified")
    pending_stories = sum(1 for s in all_stories if getattr(s, "verification_status", "") == "pending_review")
    active_stories = sum(1 for s in all_stories if getattr(s, "status", "") == "active")
    dormant_stories = sum(1 for s in all_stories if getattr(s, "status", "") == "dormant")

    printer("📚 Story Identification Overview:")
    printer(f"   • Total Story Records     : {total_stories}")
    printer(f"   • Verified Stories        : {verified_stories}")
    printer(f"   • Pending Review Stories  : {pending_stories}")
    printer(f"   • Active / Dormant Ratio  : {active_stories} active / {dormant_stories} dormant")
    printer("-" * 78)

    # Macro Events inspection
    all_macros = m_repo.list_macro_events(limit=5000)
    total_macros = len(all_macros)
    printer("🌐 Macro-Events Overview:")
    printer(f"   • Total Macro-Events      : {total_macros}")
    printer("=" * 78 + "\n")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file_hashes": hashes,
        "articles": {
            "total": total_articles,
            "assigned": assigned_count,
            "unassigned": unassigned_count,
            "pct_assigned": pct_assigned,
            "sources": dict(sources_counter),
            "categories": dict(categories_counter),
        },
        "stories": {
            "total": total_stories,
            "verified": verified_stories,
            "pending_review": pending_stories,
            "active": active_stories,
            "dormant": dormant_stories,
        },
        "macro_events": {
            "total": total_macros,
        },
    }


def run_shadow_eval(
    news_repo: NewsRepositoryPort | None = None,
    limit: int = 500,
    output_file: Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Shadow Evaluation: Runs online StoryService & MacroEventService assignment
    in a strictly isolated sandbox (temporary in-memory/isolated repository).
    Guarantees ZERO mutation to production files and reports detailed diffs.
    """
    printer = log_fn or print
    printer("\n" + "=" * 78)
    printer(" 🧪 RUNNING SHADOW EVALUATION (ISOLATED SANDBOX)")
    printer("=" * 78)

    pre_hashes = compute_file_hashes()
    repo = news_repo or get_news_repository()
    articles = repo.load_news()

    if not articles:
        printer("  No articles available for shadow evaluation.")
        return {"error": "no_articles"}

    # Sort articles chronologically
    def get_time_key(a: dict[str, Any]) -> str:
        return str(a.get("fetched_at") or a.get("created_at") or a.get("published_at") or "")

    sorted_articles = sorted(articles, key=get_time_key)
    if limit > 0:
        sorted_articles = sorted_articles[:limit]

    printer(f"  Sandbox Population: Evaluating {len(sorted_articles)} chronological articles...")

    with TemporaryDirectory() as tmp_dir:
        tmp_story_file = Path(tmp_dir) / "shadow_stories.json"
        shadow_story_repo = FileStoryRepository(data_file=tmp_story_file)
        shadow_macro_repo = InMemoryMacroEventRepository()
        shadow_macro_service = MacroEventService(
            macro_repo=shadow_macro_repo,
            story_repo=shadow_story_repo,
        )
        shadow_story_service = StoryService(
            story_repo=shadow_story_repo,
            macro_service=shadow_macro_service,
        )

        processed = 0
        new_stories_count = 0
        merged_count = 0
        follow_up_count = 0
        conflict_counter: Counter[str] = Counter()
        macro_status_counter: Counter[str] = Counter()

        diff_unchanged = 0
        diff_reassigned = 0
        diff_newly_assigned = 0

        diff_sample: list[dict[str, Any]] = []

        for idx, art_dict in enumerate(sorted_articles, start=1):
            try:
                record = ArticleRecord.model_validate(art_dict)
                orig_story_id = art_dict.get("story_id")

                story, is_new = shadow_story_service.assign_article(record)
                processed += 1

                if is_new:
                    new_stories_count += 1
                else:
                    merged_count += 1

                if story.metadata.get("antecedent_story_id"):
                    follow_up_count += 1

                if story.conflict_type:
                    conflict_counter[story.conflict_type] += 1

                macro_st = story.macro_association_status or "none"
                macro_status_counter[macro_st] += 1

                # Diff comparison
                if orig_story_id:
                    if orig_story_id == story.story_id:
                        diff_unchanged += 1
                    else:
                        diff_reassigned += 1
                else:
                    diff_newly_assigned += 1

                if len(diff_sample) < 15:
                    diff_sample.append({
                        "url": record.url,
                        "title": record.title[:60],
                        "source": record.source,
                        "original_story_id": orig_story_id,
                        "projected_story_id": story.story_id,
                        "is_new_story": is_new,
                        "verification_status": story.verification_status,
                        "macro_association_status": story.macro_association_status,
                    })

                if idx % 100 == 0 or idx == len(sorted_articles):
                    printer(f"  Processed {idx}/{len(sorted_articles)} sandbox articles...")

            except Exception as exc:
                logger.warning("Shadow eval error at index %d: %s", idx, exc)

        all_shadow_stories = shadow_story_repo.list_stories(limit=10000)
        verified_stories = sum(1 for s in all_shadow_stories if s.verification_status == "verified")
        pending_stories = sum(1 for s in all_shadow_stories if s.verification_status == "pending_review")

        all_shadow_macros = shadow_macro_repo.list_macro_events(limit=5000)

        # Immutability verification
        post_hashes = compute_file_hashes()
        hashes_match = (pre_hashes == post_hashes)

        printer("-" * 78)
        printer("📊 SHADOW EVALUATION RESULTS:")
        printer(f"   • Evaluated Articles      : {processed}")
        printer(f"   • Projected Stories       : {len(all_shadow_stories)}")
        printer(f"   • Articles Merged         : {merged_count} ({(merged_count / processed * 100.0) if processed else 0:.1f}%)")
        printer(f"   • Follow-Up Lineages      : {follow_up_count}")
        printer(f"   • Verified Stories        : {verified_stories}")
        printer(f"   • Pending Review Stories  : {pending_stories}")
        printer(f"   • Conflict Types Held     : {dict(conflict_counter)}")
        printer(f"   • Projected Macro-Events  : {len(all_shadow_macros)}")
        printer(f"   • Macro Status Breakdown  : {dict(macro_status_counter)}")
        printer("-" * 78)
        printer("🔄 Assignment Diff Breakdown (vs Current News DB):")
        printer(f"   • Newly Assigned          : {diff_newly_assigned}")
        printer(f"   • Reassigned to New Story : {diff_reassigned}")
        printer(f"   • Unchanged Existing Story: {diff_unchanged}")
        printer("-" * 78)
        printer("🔒 Production Immutability Verification:")
        printer(f"   • Pre/Post SHA-256 Match  : {'✅ PASSED (100% UNTOUCHED)' if hashes_match else '❌ FAILED'}")
        printer("=" * 78 + "\n")

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluated_articles": processed,
            "projected_stories_count": len(all_shadow_stories),
            "merged_count": merged_count,
            "follow_up_lineages": follow_up_count,
            "verified_stories": verified_stories,
            "pending_review_stories": pending_stories,
            "conflict_types": dict(conflict_counter),
            "projected_macros_count": len(all_shadow_macros),
            "macro_status_breakdown": dict(macro_status_counter),
            "diff_summary": {
                "newly_assigned": diff_newly_assigned,
                "reassigned": diff_reassigned,
                "unchanged": diff_unchanged,
            },
            "immutability_verified": hashes_match,
            "pre_file_hashes": pre_hashes,
            "post_file_hashes": post_hashes,
            "sample_diff": diff_sample,
        }

        target_out = output_file or (BASE_DIR / "data" / "shadow_eval_report.json")
        target_out.parent.mkdir(parents=True, exist_ok=True)
        target_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        printer(f"💾 Shadow evaluation report saved to {target_out}\n")

        return report


def run_backfill(
    news_repo: NewsRepositoryPort | None = None,
    story_service: StoryService | None = None,
    limit: int | None = None,
    dry_run: bool | None = None,
    apply: bool = False,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Back-fill runner with strict dry-run protection for production repositories.
    When both news_repo and story_service are explicitly injected (e.g. unit tests on tmp_path),
    executes against the injected test repositories unless dry_run=True is explicitly requested.
    """
    printer = log_fn or print

    is_injected_test = (news_repo is not None and story_service is not None)
    if dry_run is None:
        dry_run = not (apply or is_injected_test)

    if not apply and not dry_run and not is_injected_test:
        printer("⚠️ SAFETY GUARD: Neither --apply nor --dry-run was specified. Defaulting to --dry-run.")
        dry_run = True

    if dry_run:
        printer(f"[{datetime.now(timezone.utc):%H:%M:%S}] 🛡️ Running Back-fill in DRY-RUN mode (No DB writes)...")
        return run_shadow_eval(news_repo=news_repo, limit=limit or 500, log_fn=printer)

    if not apply and not is_injected_test:
        raise RuntimeError("Production backfill aborted: --apply flag must be explicitly passed.")

    printer(f"[{datetime.now(timezone.utc):%H:%M:%S}] 🚀 Starting Story Back-fill Migration Job...")
    repo = news_repo or get_news_repository()
    service = story_service or get_story_service()

    articles = repo.load_news()
    total_found = len(articles)
    printer(f"  Found {total_found} articles in news repository.")

    if not articles:
        printer("  No articles to back-fill. Exiting.")
        return {"total_articles": 0, "processed": 0, "new_stories": 0, "merged_articles": 0}

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

            if idx % 200 == 0 or idx == len(sorted_articles):
                printer(f"  Processed {idx}/{len(sorted_articles)} articles ({new_stories_count} new, {merged_count} merges)...")
        except Exception as exc:
            logger.warning("Error processing article at index %d (%s): %s", idx, art_dict.get("url"), exc)

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

    printer(f"[{datetime.now(timezone.utc):%H:%M:%S}] ✅ Production Back-fill complete!")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Story Back-fill, Audit, and Shadow Evaluation")
    parser.add_argument("--audit", action="store_true", help="Perform read-only audit of current production database")
    parser.add_argument("--dry-run", action="store_true", help="Simulate back-fill in read-only sandbox")
    parser.add_argument("--shadow-eval", action="store_true", help="Run shadow evaluation with diff reporting")
    parser.add_argument("--limit", type=int, default=500, help="Limit number of articles to process (default 500)")
    parser.add_argument("--output", type=Path, default=None, help="Path to save shadow report JSON")
    parser.add_argument("--apply", action="store_true", help="Explicitly allow production database writes")

    args = parser.parse_args()

    if args.audit and (args.dry_run or args.shadow_eval):
        # Run audit first, then dry-run / shadow-eval
        run_audit()
        run_shadow_eval(limit=args.limit, output_file=args.output)
        return 0

    if args.audit:
        run_audit()
        return 0

    if args.shadow_eval or args.dry_run:
        run_shadow_eval(limit=args.limit, output_file=args.output)
        return 0

    if args.apply:
        run_backfill(limit=args.limit, dry_run=False, apply=True)
        return 0

    # Default if no arguments passed
    print("ℹ️ No specific mode selected. Running safe read-only audit. Use --shadow-eval or --dry-run for simulation.")
    run_audit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
