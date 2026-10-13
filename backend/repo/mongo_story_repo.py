"""
repo/mongo_story_repo.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ persistence และ query ข้อมูล Story ใน MongoDB NoSQL
SOLID  O — ขยายจาก StoryRepositoryPort โดยไม่ต้องแก้ core domain logic
SOLID  L — สามารถสลับใช้แทน FileStoryRepository ได้ 100%
SOLID  D — รองรับการ inject mongo_uri, db_name, และ collection_name ผ่าน constructor
GRASP  Information Expert — จัดการ collection, compound indexes, และ BSON query
GRASP  Creator — จัดการ StoryRecord records และ metadata ใน MongoDB
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

import pymongo
from pymongo import UpdateOne
from pymongo.errors import PyMongoError

from backend.schemas.story_schema import StoryRecord

logger = logging.getLogger(__name__)


class MongoStoryRepository:
    """
    High-performance NoSQL repository implementation for StoryRecord persistence using MongoDB.
    Uses compound indexes for fast sorting and candidate window filtering,
    multikey index on article_urls for reverse lookups, and bulk operations for upserts.
    """

    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017",
        db_name: str = "news_collector",
        collection_name: str = "stories",
        server_selection_timeout_ms: int = 3000,
    ) -> None:
        self._client: pymongo.MongoClient = pymongo.MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
        )
        # Verify connection immediately
        self._client.admin.command("ping")

        self._db = self._client[db_name]
        self._stories = self._db[collection_name]
        self._metadata = self._db["metadata"]

        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create necessary indexes for high-speed queries, pagination, and candidate filtering."""
        try:
            # 1. Unique index on story_id
            self._stories.create_index([("story_id", pymongo.ASCENDING)], unique=True, background=True)

            # 2. Timeline sort index (latest article update)
            self._stories.create_index([("updated_at", pymongo.DESCENDING)], background=True)

            # 3. Compound index for status filtering + timeline sort
            self._stories.create_index(
                [("status", pymongo.ASCENDING), ("updated_at", pymongo.DESCENDING)],
                background=True,
            )

            # 4. Multikey index on article_urls for fast reverse lookups
            self._stories.create_index([("article_urls", pymongo.ASCENDING)], background=True)

            # 5. Compound index for temporal candidate search
            self._stories.create_index(
                [("status", pymongo.ASCENDING), ("category", pymongo.ASCENDING), ("updated_at", pymongo.DESCENDING)],
                background=True,
            )
        except PyMongoError as exc:
            logger.warning("Failed to create some MongoDB story indexes: %s", exc)

    # ── Story Operations ──────────────────────────────────────────

    def get_story(self, story_id: str) -> StoryRecord | None:
        """Retrieve a single story by its story_id."""
        clean_id = story_id.strip() if story_id else ""
        if not clean_id:
            return None
        try:
            doc = self._stories.find_one({"story_id": clean_id}, {"_id": 0})
            if doc is None:
                return None
            return StoryRecord.model_validate(doc)
        except PyMongoError as exc:
            logger.error("MongoDB get_story error for story_id %s: %s", clean_id, exc)
            return None

    def save_story(self, story: StoryRecord) -> None:
        """Upsert a single story record."""
        try:
            doc = story.model_dump(mode="python")
            doc.pop("_id", None)
            self._stories.update_one(
                {"story_id": story.story_id},
                {"$set": doc},
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("MongoDB save_story error for story_id %s: %s", story.story_id, exc)

    def save_stories_batch(self, stories: list[StoryRecord]) -> None:
        """Atomic bulk upsert of multiple stories using story_id as unique key."""
        if not stories:
            return
        try:
            operations: list[UpdateOne] = []
            for s in stories:
                doc = s.model_dump(mode="python")
                doc.pop("_id", None)
                operations.append(UpdateOne({"story_id": s.story_id}, {"$set": doc}, upsert=True))

            if operations:
                self._stories.bulk_write(operations, ordered=False)

            self._metadata.update_one(
                {"_id": "stories_metadata"},
                {
                    "$set": {
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "total_stories": self._stories.count_documents({}),
                    }
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.error("MongoDB save_stories_batch error: %s", exc)

    def list_stories(
        self,
        status: Literal["active", "dormant"] | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoryRecord]:
        """List stories sorted by updated_at descending, optionally filtered by status."""
        try:
            filter_doc: dict[str, Any] = {}
            if status is not None and status.strip() and status.strip().lower() != "all":
                filter_doc["status"] = status.strip().lower()

            cursor = (
                self._stories.find(filter_doc, {"_id": 0})
                .sort("updated_at", pymongo.DESCENDING)
                .skip(max(0, offset))
                .limit(max(1, limit))
            )
            return [StoryRecord.model_validate(d) for d in cursor]
        except PyMongoError as exc:
            logger.error("MongoDB list_stories error: %s", exc)
            return []

    def find_candidate_stories(
        self,
        since_time: datetime,
        category: str | None = None,
    ) -> list[StoryRecord]:
        """
        Query stories updated within the candidate window (updated_at >= since_time).
        Supports soft category filtering without blocking cross-category candidates.
        Handles both BSON datetime objects and ISO-formatted strings.
        """
        try:
            since_iso = since_time.isoformat() if isinstance(since_time, datetime) else str(since_time)
            filter_doc: dict[str, Any] = {
                "$or": [
                    {"updated_at": {"$gte": since_time}},
                    {"updated_at": {"$gte": since_iso}},
                ]
            }
            if category and category.strip().lower() != "all":
                filter_doc["category"] = category.strip().lower()

            cursor = self._stories.find(filter_doc, {"_id": 0}).sort("updated_at", pymongo.DESCENDING)
            return [StoryRecord.model_validate(d) for d in cursor]
        except PyMongoError as exc:
            logger.error("MongoDB find_candidate_stories error: %s", exc)
            return []

    def get_stories_by_ids(self, story_ids: list[str]) -> list[StoryRecord]:
        """Batch fetch stories by their story_ids, preserving request order."""
        if not story_ids:
            return []
        try:
            clean_ids = [s.strip() for s in story_ids if s and s.strip()]
            if not clean_ids:
                return []
            cursor = self._stories.find({"story_id": {"$in": clean_ids}}, {"_id": 0})
            found: dict[str, StoryRecord] = {}
            for d in cursor:
                story = StoryRecord.model_validate(d)
                found[story.story_id] = story
            return [found[sid] for sid in clean_ids if sid in found]
        except PyMongoError as exc:
            logger.error("MongoDB get_stories_by_ids error: %s", exc)
            return []

    def get_story_by_article_url(self, url: str) -> StoryRecord | None:
        """Find the story containing the given article URL via multikey index on article_urls."""
        clean_url = url.strip() if url else ""
        if not clean_url:
            return None
        try:
            doc = self._stories.find_one({"article_urls": clean_url}, {"_id": 0})
            if doc is None:
                return None
            return StoryRecord.model_validate(doc)
        except PyMongoError as exc:
            logger.error("MongoDB get_story_by_article_url error for url %s: %s", clean_url, exc)
            return None

    def count_stories(self, status: str | None = None) -> int:
        """Count total stories, optionally filtered by status."""
        try:
            filter_doc: dict[str, Any] = {}
            if status is not None and status.strip() and status.strip().lower() != "all":
                filter_doc["status"] = status.strip().lower()
            return self._stories.count_documents(filter_doc)
        except PyMongoError as exc:
            logger.error("MongoDB count_stories error: %s", exc)
            return 0

    def close(self) -> None:
        """Close MongoDB client connection."""
        self._client.close()
