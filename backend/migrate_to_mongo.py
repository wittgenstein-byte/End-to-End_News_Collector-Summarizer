"""
backend/migrate_to_mongo.py
─────────────────────────────────────────────────────────────────
Migration utility: Import existing JSON news archive into MongoDB NoSQL.
Usage:
    python backend/migrate_to_mongo.py
    python backend/migrate_to_mongo.py --mongo-uri mongodb://localhost:27017 --db-name news_collector
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import settings
from backend.repo.mongo_news_repo import MongoNewsRepository


def migrate(data_file: Path, mongo_uri: str, db_name: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] 🚀 Starting migration to MongoDB...")
    print(f"  Source file: {data_file}")
    print(f"  Target DB:   {mongo_uri} / {db_name}")

    if not data_file.exists():
        print(f"❌ Source file {data_file} does not exist. Nothing to migrate.")
        return

    try:
        with data_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"❌ Failed to parse {data_file}: {exc}")
        return

    articles = data.get("articles", [])
    seen_urls = set(data.get("seen_urls", []))

    print(f"  Found {len(articles)} articles and {len(seen_urls)} seen URLs.")

    try:
        repo = MongoNewsRepository(mongo_uri=mongo_uri, db_name=db_name)
    except Exception as exc:
        print(f"❌ Could not connect to MongoDB: {exc}")
        return

    if articles:
        print("  ⏳ Bulk upserting articles...")
        repo.save_news(articles)
        print(f"  ✅ Articles migrated successfully: {len(articles)}")

    if seen_urls:
        print("  ⏳ Bulk upserting seen URLs...")
        repo.save_seen(seen_urls)
        print(f"  ✅ Seen URLs migrated successfully: {len(seen_urls)}")

    repo.close()
    print("🎉 Migration completed successfully!\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate news data from JSON to MongoDB")
    parser.add_argument("--data-file", type=Path, default=settings.data_file, help="Path to news_data.json")
    parser.add_argument("--mongo-uri", type=str, default=settings.mongo_uri, help="MongoDB connection URI")
    parser.add_argument("--db-name", type=str, default=settings.mongo_db_name, help="Database name")

    args = parser.parse_args()
    migrate(data_file=args.data_file, mongo_uri=args.mongo_uri, db_name=args.db_name)


if __name__ == "__main__":
    main()
