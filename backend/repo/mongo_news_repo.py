"""
repo/mongo_news_repo.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ persistence และ query ข้อมูลข่าวใน MongoDB NoSQL
SOLID  O — ขยายจาก NewsRepositoryPort โดยไม่ต้องแก้ core domain logic
SOLID  L — สามารถสลับใช้แทน FileNewsRepository ได้ 100%
SOLID  D — รองรับการ inject mongo_uri และ db_name ผ่าน constructor
GRASP  Information Expert — จัดการ collection, indexes, และ BSON query
GRASP  Creator — จัดการ article และ seen_url records ใน MongoDB
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import pymongo
from pymongo import UpdateOne
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)


class MongoNewsRepository:
    """
    High-performance NoSQL repository implementation using MongoDB.
    Uses compound indexes for fast sorting and filtering, and bulk operations for upserts.
    """

    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017",
        db_name: str = "news_collector",
        server_selection_timeout_ms: int = 3000,
    ) -> None:
        self._client: pymongo.MongoClient = pymongo.MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
        )
        # Test connection immediately
        self._client.admin.command("ping")

        self._db = self._client[db_name]
        self._articles = self._db["articles"]
        self._seen = self._db["seen_urls"]
        self._metadata = self._db["metadata"]

        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create necessary indexes for high-speed queries, pagination, and deduplication."""
        try:
            # 1. Timeline sort index
            self._articles.create_index([("fetched_at", pymongo.DESCENDING)], background=True)

            # 2. Compound indexes for category & source filtered timeline
            self._articles.create_index(
                [("category", pymongo.ASCENDING), ("fetched_at", pymongo.DESCENDING)],
                background=True,
            )
            self._articles.create_index(
                [("source", pymongo.ASCENDING), ("fetched_at", pymongo.DESCENDING)],
                background=True,
            )

            # 3. Unique index on URL to prevent duplicates and enable fast upserts
            self._articles.create_index([("url", pymongo.ASCENDING)], unique=True, background=True)

            # 4. Seen URLs index
            self._seen.create_index([("url", pymongo.ASCENDING)], unique=True, background=True)

            # 5. Text search index (fallback for text searches)
            self._articles.create_index(
                [("title", pymongo.TEXT), ("summary", pymongo.TEXT)],
                background=True,
            )
        except PyMongoError as exc:
            logger.warning("Failed to create some MongoDB indexes: %s", exc)

    # ── News Operations ──────────────────────────────────────────

    def load_news(self) -> list[dict]:
        """Load all articles sorted by fetched_at descending (projects out Mongo _id)."""
        try:
            cursor = self._articles.find({}, {"_id": 0}).sort("fetched_at", pymongo.DESCENDING)
            return list(cursor)
        except PyMongoError as exc:
            logger.error("MongoDB load_news error: %s", exc)
            return []

    def save_news(self, articles: list[dict]) -> None:
        """Atomic bulk upsert of articles using URL as unique key."""
        if not articles:
            return
        try:
            operations: list[UpdateOne] = []
            for art in articles:
                url = art.get("url")
                if not url:
                    continue
                # Clean _id if present in incoming dict
                doc = {k: v for k, v in art.items() if k != "_id"}
                operations.append(UpdateOne({"url": url}, {"$set": doc}, upsert=True))

            if operations:
                self._articles.bulk_write(operations, ordered=False)

            self._metadata.update_one(
                {"_id": "global_metadata"},
                {
                    "$set": {
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "total_articles": self._articles.count_documents({}),
                    }
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("MongoDB save_news error: %s", exc)

    def query_news(
        self,
        page: int = 1,
        page_size: int = 20,
        source: str = "",
        category: str | None = None,
        query: str = "",
    ) -> tuple[list[dict], int]:
        """
        High-performance indexed query with database-level filtering and pagination.
        Does not load full article corpus into memory.
        """
        try:
            filter_doc: dict[str, Any] = {}

            if source:
                filter_doc["source"] = {"$regex": f"^{re.escape(source.strip())}$", "$options": "i"}

            if category and category != "all":
                filter_doc["category"] = category

            if query:
                q_clean = query.strip()
                # Substring regex matching works best for Thai language queries
                pattern = re.escape(q_clean)
                filter_doc["$or"] = [
                    {"title": {"$regex": pattern, "$options": "i"}},
                    {"summary": {"$regex": pattern, "$options": "i"}},
                ]

            total = self._articles.count_documents(filter_doc)

            page = max(1, page)
            skip = (page - 1) * page_size

            cursor = (
                self._articles.find(filter_doc, {"_id": 0})
                .sort("fetched_at", pymongo.DESCENDING)
                .skip(skip)
                .limit(page_size)
            )
            items = list(cursor)
            return items, total
        except PyMongoError as exc:
            logger.error("MongoDB query_news error: %s", exc)
            return [], 0

    def get_category_counts(self) -> dict[str, int]:
        """Aggregate article counts grouped by category using MongoDB aggregation pipeline."""
        try:
            pipeline: list[dict[str, Any]] = [
                {"$match": {"category": {"$exists": True, "$ne": None}}},
                {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            ]
            results = self._articles.aggregate(pipeline)
            counts: dict[str, int] = {doc["_id"]: doc["count"] for doc in results}
            counts["all"] = self._articles.count_documents({})
            return counts
        except PyMongoError as exc:
            logger.error("MongoDB get_category_counts error: %s", exc)
            return {"all": 0}

    def get_source_counts(self) -> dict[str, int]:
        """Aggregate article counts grouped by source using MongoDB aggregation pipeline."""
        try:
            pipeline: list[dict[str, Any]] = [
                {"$match": {"source": {"$exists": True, "$ne": None}}},
                {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            ]
            results = self._articles.aggregate(pipeline)
            return {doc["_id"]: doc["count"] for doc in results}
        except PyMongoError as exc:
            logger.error("MongoDB get_source_counts error: %s", exc)
            return {}

    # ── Seen URLs ────────────────────────────────────────────────

    def load_seen(self) -> set[str]:
        """Load set of seen URLs from both seen collection and articles collection."""
        try:
            seen: set[str] = set()
            for doc in self._seen.find({}, {"_id": 0, "url": 1}):
                if "url" in doc:
                    seen.add(doc["url"])

            # Also ensure all existing articles' URLs are counted as seen
            article_urls = self._articles.distinct("url")
            seen.update(u for u in article_urls if u)
            return seen
        except PyMongoError as exc:
            logger.error("MongoDB load_seen error: %s", exc)
            return set()

    def save_seen(self, seen: set[str]) -> None:
        """Save seen URLs into seen collection."""
        if not seen:
            return
        try:
            operations = [
                UpdateOne({"url": url}, {"$set": {"url": url}}, upsert=True)
                for url in seen
                if url
            ]
            if operations:
                self._seen.bulk_write(operations, ordered=False)
        except PyMongoError as exc:
            logger.error("MongoDB save_seen error: %s", exc)

    def close(self) -> None:
        """Close client connection."""
        self._client.close()
