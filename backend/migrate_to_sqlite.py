"""
backend/migrate_to_sqlite.py
─────────────────────────────────────────────────────────────────
Migration utility: Import existing JSON news archive into SQLite WAL database.
Usage:
    python backend/migrate_to_sqlite.py
    python backend/migrate_to_sqlite.py --json-path data/news_data.json --db-path data/news_collector.db
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.config import settings
from backend.repo.sqlite_news_repo import SqliteNewsRepository


def migrate_json_to_sqlite(
    json_path: Path,
    sqlite_repo: SqliteNewsRepository,
    batch_size: int = 1000,
) -> dict[str, int]:
    """Import articles and seen URLs from JSON into SQLite WAL repository."""
    t0 = time.perf_counter()
    if not json_path.exists():
        print(f"⚠️ Source file {json_path} does not exist. Nothing to migrate.")
        return {"articles": 0, "seen_urls": 0}

    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] 🚀 Migrating from {json_path.name} to SQLite WAL...")
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    articles = data.get("articles", [])
    seen_urls = set(data.get("seen_urls", []))

    # 1. Batch upsert articles
    total_articles = len(articles)
    if total_articles > 0:
        for i in range(0, total_articles, batch_size):
            chunk = articles[i : i + batch_size]
            sqlite_repo.save_news(chunk)
            print(f"  💾 Upserted {min(i + batch_size, total_articles)}/{total_articles} articles...")

    # 2. Batch upsert seen URLs
    total_seen = len(seen_urls)
    if total_seen > 0:
        sqlite_repo.save_seen(seen_urls)
        print(f"  👀 Upserted {total_seen} seen URLs.")

    # 3. Decouple heavy markdown files if collected_md directory exists
    md_dir = settings.collected_md_dir
    linked_contents = 0
    if md_dir.exists():
        for md_file in md_dir.glob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                # Look for '# Source URL: <url>'
                match = re.search(r"^# Source URL:\s*(\S+)", text, re.MULTILINE)
                if match:
                    source_url = match.group(1).strip()
                    # Strip the source URL header line from content
                    body = text[match.end() :].strip()
                    sqlite_repo.save_article_content(url=source_url, content=body)
            except OSError as err:
                print(f"  [!] Skipped reading {md_file.name}: {err}")

    if linked_contents > 0:
        print(f"  📄 Linked {linked_contents} decoupled markdown files into article_contents table.")

    elapsed = time.perf_counter() - t0
    print(f"🎉 Migration completed in {elapsed:.2f}s! ({total_articles} articles, {total_seen} seen URLs)\n")
    return {"articles": total_articles, "seen_urls": total_seen, "contents": linked_contents}


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate news data from JSON to SQLite WAL")
    parser.add_argument("--json-path", type=Path, default=settings.data_file, help="Path to news_data.json")
    parser.add_argument("--db-path", type=Path, default=settings.sqlite_file, help="Path to news_collector.db")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")

    args = parser.parse_args()
    repo = SqliteNewsRepository(
        db_path=args.db_path,
        wal_mode=settings.sqlite_wal_mode,
        cache_size_kb=settings.sqlite_cache_size_kb,
        mmap_size_bytes=settings.sqlite_mmap_size_bytes,
    )
    migrate_json_to_sqlite(json_path=args.json_path, sqlite_repo=repo, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
