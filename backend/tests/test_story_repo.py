"""
backend/tests/test_story_repo.py
─────────────────────────────────────────────────────────────────
Comprehensive tests for Story domain model, schemas & dual persistence:
- TestFileStoryRepository: JSON storage, CRUD, candidate queries, restart persistence
- TestMongoStoryRepositoryMock: MongoDB NoSQL storage, indexes, bulk writes, boundary error swallowing
- TestArticleRecordBackwardCompatibility: 100% backward compatibility with legacy news
- TestStoryDomainMethods: StoryRecord domain methods (add_article, EMA, merge_entities, lifecycle)
- TestStoryRepositoryFactory: Factory selection and fallback handling
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pymongo.errors import PyMongoError

from backend.repo.mongo_story_repo import MongoStoryRepository
from backend.repo.news_repo import FileNewsRepository
from backend.repo.story_repo import (
    FileStoryRepository,
    StoryRepositoryPort,
    get_story_repository,
    reset_story_repository,
)
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import (
    StoryDetailResponse,
    StoryListResponse,
    StoryRecord,
    StorySummary,
    TimelineEvent,
)


@pytest.fixture
def sample_stories() -> list[StoryRecord]:
    """Sample stories across active/dormant states and multiple categories."""
    now = datetime.now(timezone.utc)
    return [
        StoryRecord(
            story_id="story_001",
            title="น้ำท่วมน่านวิกฤต น้ำยมเอ่อล้นเข้าท่วมชุมชน",
            category="environment",
            status="active",
            created_at=now - timedelta(hours=10),
            updated_at=now - timedelta(hours=2),
            article_urls=["https://thaipbs.or.th/news/1", "https://thairath.co.th/news/2"],
            article_count=2,
            outlet_count=2,
            outlets=["ThaiPBS", "Thairath"],
            centroid=[0.12] * 768,
            entities=["จ.น่าน", "แม่น้ำยม"],
        ),
        StoryRecord(
            story_id="story_002",
            title="สภาถกงบประมาณปี 70 วันที่สอง ฝ่ายค้านอภิปรายดุเดือด",
            category="politics",
            status="active",
            created_at=now - timedelta(hours=30),
            updated_at=now - timedelta(hours=20),
            article_urls=["https://dailynews.co.th/news/3"],
            article_count=1,
            outlet_count=1,
            outlets=["Daily News"],
            centroid=[0.25] * 768,
            entities=["รัฐสภา", "งบประมาณ"],
        ),
        StoryRecord(
            story_id="story_003",
            title="ราคาทองคำเปิดตลาดปรับลดลง 150 บาทต่อบาททองคำ",
            category="economy",
            status="dormant",
            created_at=now - timedelta(hours=100),
            updated_at=now - timedelta(hours=80),
            article_urls=["https://bangkokbiznews.com/news/4"],
            article_count=1,
            outlet_count=1,
            outlets=["Bangkokbiznews"],
            centroid=[-0.05] * 768,
            entities=["สมาคมค้าทองคำ"],
        ),
    ]


# ── 1. FileStoryRepository Unit Tests ──────────────────────────────

class TestFileStoryRepository:
    def test_save_and_get_story(self, tmp_path: Path, sample_stories: list[StoryRecord]) -> None:
        data_file = tmp_path / "stories.json"
        repo = FileStoryRepository(data_file=data_file)
        assert isinstance(repo, StoryRepositoryPort)

        assert repo.get_story("non_existent") is None
        story1 = sample_stories[0]
        repo.save_story(story1)

        retrieved = repo.get_story("story_001")
        assert retrieved is not None
        assert retrieved.story_id == "story_001"
        assert retrieved.title == story1.title
        assert retrieved.category == "environment"
        assert retrieved.article_count == 2
        assert retrieved.outlet_count == 2
        assert set(retrieved.outlets) == {"ThaiPBS", "Thairath"}
        assert retrieved.centroid is not None
        assert len(retrieved.centroid) == 768
        assert pytest.approx(retrieved.centroid[0]) == 0.12

    def test_save_stories_batch_and_get_by_ids(
        self, tmp_path: Path, sample_stories: list[StoryRecord]
    ) -> None:
        data_file = tmp_path / "stories.json"
        repo = FileStoryRepository(data_file=data_file)

        # Batch save empty list should succeed without error
        repo.save_stories_batch([])

        # Batch save 3 stories
        repo.save_stories_batch(sample_stories)
        assert repo.count_stories() == 3

        # Query by IDs preserving order
        ordered = repo.get_stories_by_ids(["story_002", "story_001", "non_existent"])
        assert len(ordered) == 2
        assert ordered[0].story_id == "story_002"
        assert ordered[1].story_id == "story_001"

    def test_list_stories_with_status_filter_and_pagination(
        self, tmp_path: Path, sample_stories: list[StoryRecord]
    ) -> None:
        data_file = tmp_path / "stories.json"
        repo = FileStoryRepository(data_file=data_file)
        repo.save_stories_batch(sample_stories)

        # List all: sorted by updated_at descending (story_001 updated 2h ago, story_002 updated 20h ago)
        all_stories = repo.list_stories()
        assert len(all_stories) == 3
        assert all_stories[0].story_id == "story_001"
        assert all_stories[1].story_id == "story_002"
        assert all_stories[2].story_id == "story_003"

        # List active only
        active_stories = repo.list_stories(status="active")
        assert len(active_stories) == 2
        assert all(s.status == "active" for s in active_stories)

        # List dormant only
        dormant_stories = repo.list_stories(status="dormant")
        assert len(dormant_stories) == 1
        assert dormant_stories[0].story_id == "story_003"

        # Pagination
        page1 = repo.list_stories(limit=2, offset=0)
        assert len(page1) == 2
        assert page1[0].story_id == "story_001"
        assert page1[1].story_id == "story_002"

        page2 = repo.list_stories(limit=2, offset=2)
        assert len(page2) == 1
        assert page2[0].story_id == "story_003"

    def test_find_candidate_stories_temporal_and_category(
        self, tmp_path: Path, sample_stories: list[StoryRecord]
    ) -> None:
        data_file = tmp_path / "stories.json"
        repo = FileStoryRepository(data_file=data_file)
        repo.save_stories_batch(sample_stories)

        now = datetime.now(timezone.utc)
        since_72h = now - timedelta(hours=72)

        # Candidates within 72h window: story_001 (2h ago) and story_002 (20h ago)
        candidates = repo.find_candidate_stories(since_time=since_72h)
        assert len(candidates) == 2
        assert {c.story_id for c in candidates} == {"story_001", "story_002"}

        # Candidates with category filter (soft signal)
        env_candidates = repo.find_candidate_stories(since_time=since_72h, category="environment")
        assert len(env_candidates) == 1
        assert env_candidates[0].story_id == "story_001"

        sports_candidates = repo.find_candidate_stories(since_time=since_72h, category="sports")
        assert len(sports_candidates) == 0

    def test_restart_persistence_and_fresh_instance_reload(
        self, tmp_path: Path, sample_stories: list[StoryRecord]
    ) -> None:
        data_file = tmp_path / "stories.json"

        # 1. Instance 1 writes data
        repo1 = FileStoryRepository(data_file=data_file)
        repo1.save_stories_batch(sample_stories)
        assert data_file.exists()

        # 2. Inspect raw file structure on disk
        with data_file.open("r", encoding="utf-8") as f:
            raw_json = json.load(f)
        assert "metadata" in raw_json
        assert raw_json["metadata"]["total_stories"] == 3
        assert raw_json["metadata"]["active_stories"] == 2
        assert raw_json["metadata"]["dormant_stories"] == 1
        assert len(raw_json["stories"]) == 3

        # 3. Instance 2 simulates server restart
        del repo1
        repo2 = FileStoryRepository(data_file=data_file)
        assert repo2.count_stories() == 3
        reloaded_story = repo2.get_story("story_001")
        assert reloaded_story is not None
        assert reloaded_story.title == sample_stories[0].title
        assert reloaded_story.centroid is not None
        assert len(reloaded_story.centroid) == 768

    def test_get_story_by_article_url(
        self, tmp_path: Path, sample_stories: list[StoryRecord]
    ) -> None:
        data_file = tmp_path / "stories.json"
        repo = FileStoryRepository(data_file=data_file)
        repo.save_stories_batch(sample_stories)

        # Reverse lookup for URL in story_001
        found = repo.get_story_by_article_url("https://thairath.co.th/news/2")
        assert found is not None
        assert found.story_id == "story_001"

        # Reverse lookup for URL in story_002
        found2 = repo.get_story_by_article_url("https://dailynews.co.th/news/3")
        assert found2 is not None
        assert found2.story_id == "story_002"

        # Unknown URL returns None
        assert repo.get_story_by_article_url("https://unknown.com/404") is None
        assert repo.get_story_by_article_url("") is None

    def test_count_stories_and_clear_all(
        self, tmp_path: Path, sample_stories: list[StoryRecord]
    ) -> None:
        data_file = tmp_path / "stories.json"
        repo = FileStoryRepository(data_file=data_file)
        repo.save_stories_batch(sample_stories)

        assert repo.count_stories() == 3
        assert repo.count_stories(status="active") == 2
        assert repo.count_stories(status="dormant") == 1

        repo.clear_all()
        assert repo.count_stories() == 0
        assert repo.list_stories() == []
        assert repo.get_story_by_article_url("https://thairath.co.th/news/2") is None

    def test_fault_tolerance_missing_empty_corrupted_file(self, tmp_path: Path) -> None:
        # Non-existent file
        data_file = tmp_path / "missing.json"
        repo = FileStoryRepository(data_file=data_file)
        assert repo.list_stories() == []
        assert repo.count_stories() == 0

        # Empty file
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("", encoding="utf-8")
        repo_empty = FileStoryRepository(data_file=empty_file)
        assert repo_empty.list_stories() == []

        # Corrupted JSON
        corrupt_file = tmp_path / "corrupt.json"
        corrupt_file.write_text("NOT_VALID_JSON{", encoding="utf-8")
        repo_corrupt = FileStoryRepository(data_file=corrupt_file)
        assert repo_corrupt.list_stories() == []


# ── 2. MongoStoryRepository Mock Tests ─────────────────────────────

class TestMongoStoryRepositoryMock:
    @patch("pymongo.MongoClient")
    def test_mongo_repo_init_and_indexes(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_stories = MagicMock()
        mock_db.__getitem__.return_value = mock_stories

        repo = MongoStoryRepository(mongo_uri="mongodb://fake:27017", db_name="test_db")
        assert isinstance(repo, StoryRepositoryPort)
        mock_client.admin.command.assert_called_once_with("ping")

        # Verify index creation calls
        assert mock_stories.create_index.call_count >= 5
        repo.close()
        mock_client.close.assert_called_once()

    @patch("pymongo.MongoClient")
    def test_mongo_save_and_get_story(
        self, mock_client_cls: MagicMock, sample_stories: list[StoryRecord]
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_stories = MagicMock()
        mock_metadata = MagicMock()

        def get_coll(name: str):
            if name == "stories":
                return mock_stories
            return mock_metadata

        mock_db.__getitem__.side_effect = get_coll

        story = sample_stories[0]
        mock_stories.find_one.return_value = story.model_dump(mode="python")

        repo = MongoStoryRepository(mongo_uri="mongodb://fake:27017")
        fetched = repo.get_story("story_001")
        assert fetched is not None
        assert fetched.story_id == "story_001"
        assert fetched.title == story.title

        # Test save_story
        repo.save_story(story)
        mock_stories.update_one.assert_called_once()
        args, kwargs = mock_stories.update_one.call_args
        assert args[0] == {"story_id": "story_001"}
        assert kwargs.get("upsert") is True

    @patch("pymongo.MongoClient")
    def test_mongo_save_stories_batch(
        self, mock_client_cls: MagicMock, sample_stories: list[StoryRecord]
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_stories = MagicMock()
        mock_metadata = MagicMock()

        def get_coll(name: str):
            if name == "stories":
                return mock_stories
            return mock_metadata

        mock_db.__getitem__.side_effect = get_coll

        repo = MongoStoryRepository(mongo_uri="mongodb://fake:27017")
        repo.save_stories_batch(sample_stories)
        mock_stories.bulk_write.assert_called_once()
        mock_metadata.update_one.assert_called_once()

    @patch("pymongo.MongoClient")
    def test_mongo_list_stories_and_candidate_window(
        self, mock_client_cls: MagicMock, sample_stories: list[StoryRecord]
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_stories = MagicMock()
        mock_db.__getitem__.return_value = mock_stories

        cursor_mock = MagicMock()
        cursor_mock.sort.return_value = cursor_mock
        cursor_mock.skip.return_value = cursor_mock
        cursor_mock.limit.return_value = cursor_mock
        cursor_mock.__iter__.side_effect = lambda: iter([s.model_dump(mode="python") for s in sample_stories])
        mock_stories.find.return_value = cursor_mock

        repo = MongoStoryRepository(mongo_uri="mongodb://fake:27017")

        # List stories
        result = repo.list_stories(status="active", limit=10, offset=0)
        assert len(result) == 3

        # Find candidate stories
        now = datetime.now(timezone.utc)
        candidates = repo.find_candidate_stories(since_time=now - timedelta(hours=72), category="politics")
        assert len(candidates) == 3

    @patch("pymongo.MongoClient")
    def test_mongo_get_stories_by_ids(
        self, mock_client_cls: MagicMock, sample_stories: list[StoryRecord]
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_stories = MagicMock()
        mock_db.__getitem__.return_value = mock_stories

        docs = [s.model_dump(mode="python") for s in sample_stories]
        mock_stories.find.return_value = docs

        repo = MongoStoryRepository(mongo_uri="mongodb://fake:27017")
        items = repo.get_stories_by_ids(["story_002", "story_001"])
        assert len(items) == 2
        assert items[0].story_id == "story_002"
        assert items[1].story_id == "story_001"

    @patch("pymongo.MongoClient")
    def test_mongo_get_story_by_article_url(
        self, mock_client_cls: MagicMock, sample_stories: list[StoryRecord]
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_stories = MagicMock()
        mock_db.__getitem__.return_value = mock_stories

        story = sample_stories[0]
        mock_stories.find_one.return_value = story.model_dump(mode="python")

        repo = MongoStoryRepository(mongo_uri="mongodb://fake:27017")
        found = repo.get_story_by_article_url("https://thaipbs.or.th/news/1")
        assert found is not None
        assert found.story_id == "story_001"

    @patch("pymongo.MongoClient")
    def test_mongo_error_handling_swallow_at_boundary(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_stories = MagicMock()
        mock_db.__getitem__.return_value = mock_stories

        # Configure methods to raise PyMongoError
        mock_stories.find_one.side_effect = PyMongoError("Connection failure")
        mock_stories.find.side_effect = PyMongoError("Connection failure")
        mock_stories.count_documents.side_effect = PyMongoError("Connection failure")
        mock_stories.update_one.side_effect = PyMongoError("Write failure")
        mock_stories.bulk_write.side_effect = PyMongoError("Bulk failure")

        repo = MongoStoryRepository(mongo_uri="mongodb://fake:27017")

        assert repo.get_story("story_001") is None
        assert repo.get_story_by_article_url("https://any.com") is None
        assert repo.list_stories() == []
        assert repo.find_candidate_stories(since_time=datetime.now(timezone.utc)) == []
        assert repo.get_stories_by_ids(["story_001"]) == []
        assert repo.count_stories() == 0

        # Should not raise exception
        repo.save_story(StoryRecord(title="test", category="politics"))
        repo.save_stories_batch([StoryRecord(title="test", category="politics")])


# ── 3. ArticleRecord Backward Compatibility Tests ──────────────────

class TestArticleRecordBackwardCompatibility:
    def test_article_record_load_legacy_dict_without_story_id(self) -> None:
        legacy_doc = {
            "title": "ราชกิจจาฯ ประกาศคงอัตราเก็บภาษีมูลค่าเพิ่ม 6.3% ถึง 30 ก.ย.70",
            "summary": "วันนี้ (23 ส.ค.2569) ราชกิจจานุเบกษา เผยแพร่พระราชกฤษฎีกา...",
            "source": "ThaiPBS",
            "url": "https://www.thaipbs.or.th/news/content/509779",
            "category": "politics",
            "fetched_at": "2026-08-23 14:35:08",
        }
        article = ArticleRecord.model_validate(legacy_doc)
        assert article.story_id is None
        assert article.title == legacy_doc["title"]
        assert article.url == legacy_doc["url"]
        assert article.source == legacy_doc["source"]
        assert article.category == "politics"

    def test_article_record_load_from_actual_news_data_json(self) -> None:
        data_file = Path("data/news_data.json")
        if not data_file.exists():
            pytest.skip("data/news_data.json not found in workspace")

        with data_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        articles = data.get("articles", [])
        assert len(articles) > 0, "news_data.json should contain articles"

        # Spot check first 100 articles
        for raw in articles[:100]:
            rec = ArticleRecord.model_validate(raw)
            assert rec.story_id is None
            assert isinstance(rec.title, str)
            assert len(rec.url) > 0

    def test_article_record_with_story_id_serialization(self) -> None:
        article = ArticleRecord(
            title="ข่าวสภา",
            source="ThaiPBS",
            url="https://thaipbs.or.th/123",
            story_id="story_pol_12345",
        )
        assert article.story_id == "story_pol_12345"

        dumped = article.model_dump()
        assert dumped["story_id"] == "story_pol_12345"

        reloaded = ArticleRecord.model_validate(dumped)
        assert reloaded.story_id == "story_pol_12345"

    def test_news_repository_compatibility_with_story_id(self, tmp_path: Path) -> None:
        data_file = tmp_path / "news.json"
        repo = FileNewsRepository(data_file=data_file)

        articles = [
            {
                "title": "ข่าวเดิมไม่มี story_id",
                "summary": "สรุป...",
                "source": "ThaiPBS",
                "url": "https://example.com/legacy",
                "category": "politics",
                "fetched_at": "2026-09-01T10:00:00Z",
            },
            {
                "title": "ข่าวใหม่มี story_id",
                "summary": "สรุป...",
                "source": "ThaiPBS",
                "url": "https://example.com/new",
                "category": "politics",
                "story_id": "story_assigned_999",
                "fetched_at": "2026-09-01T11:00:00Z",
            },
        ]

        repo.save_news(articles)
        loaded = repo.load_news()
        assert len(loaded) == 2
        by_url = {a.get("url"): a.get("story_id") for a in loaded}
        assert by_url["https://example.com/legacy"] is None
        assert by_url["https://example.com/new"] == "story_assigned_999"


# ── 4. StoryRecord Domain Methods & Responses Tests ────────────────

class TestStoryDomainMethods:
    def test_add_article_and_lifecycle(self) -> None:
        story = StoryRecord(
            story_id="story_test",
            title="ข่าวดั้งเดิม",
            category="society",
            status="dormant",
        )
        assert story.article_count == 0
        assert story.outlet_count == 0
        assert story.status == "dormant"

        # Add article
        story.add_article(
            url="https://thaipbs.or.th/art1",
            source="ThaiPBS",
            article_time="2026-08-23 15:00:00",
            article_entities=["กรุงเทพฯ", "กระทรวงมหาดไทย"],
        )

        assert story.status == "active"
        assert story.article_count == 1
        assert story.outlet_count == 1
        assert "ThaiPBS" in story.outlets
        assert "https://thaipbs.or.th/art1" in story.article_urls
        assert "กรุงเทพฯ" in story.entities
        assert story.first_article_at is not None
        assert story.last_article_at is not None

        # Add duplicate URL from same outlet
        story.add_article(url="https://thaipbs.or.th/art1", source="ThaiPBS")
        assert story.article_count == 1
        assert story.outlet_count == 1

        # Add second article from different outlet
        story.add_article(
            url="https://thairath.co.th/art2",
            source="Thairath",
            article_time="2026-08-23 16:00:00",
            article_entities=["กรุงเทพฯ", "ผู้ว่าฯ กทม."],
        )
        assert story.article_count == 2
        assert story.outlet_count == 2
        assert len(story.entities) == 3

    def test_update_centroid_ema(self) -> None:
        story = StoryRecord(story_id="story_test", title="ข่าวดั้งเดิม")
        assert story.centroid is None

        # First embedding initializes centroid
        initial_vec = [1.0, 2.0, 3.0]
        story.update_centroid_ema(initial_vec, alpha=0.85)
        assert story.centroid == [1.0, 2.0, 3.0]

        # Second embedding updates via EMA: 0.85 * old + 0.15 * new
        new_vec = [2.0, 4.0, 6.0]
        story.update_centroid_ema(new_vec, alpha=0.85)
        expected_0 = 0.85 * 1.0 + 0.15 * 2.0  # 0.85 + 0.30 = 1.15
        assert pytest.approx(story.centroid[0]) == expected_0

    def test_refresh_status_inactivity(self) -> None:
        now = datetime.now(timezone.utc)
        story = StoryRecord(
            story_id="story_test",
            title="ข่าวเก่า",
            updated_at=now - timedelta(hours=73),
            status="active",
        )
        # 73 hours old > 72 hours threshold -> dormant
        assert story.refresh_status(current_time=now, inactivity_threshold_hours=72.0) == "dormant"
        assert story.status == "dormant"

        # Fresh story within 72h -> active
        story.updated_at = now - timedelta(hours=10)
        assert story.refresh_status(current_time=now, inactivity_threshold_hours=72.0) == "active"
        assert story.status == "active"

    def test_story_summary_and_detail_response(self) -> None:
        now = datetime.now(timezone.utc)
        event = TimelineEvent(
            timestamp="2026-08-23 14:00:00",
            event="เริ่มการประชุมสภา",
            title="เปิดสภา",
            source="ThaiPBS",
            url="https://thaipbs.or.th/event1",
            citation="นายกรัฐมนตรีแถลงนโยบาย",
        )
        story = StoryRecord(
            story_id="story_summary_test",
            title="การประชุมสภา",
            category="politics",
            status="active",
            created_at=now,
            updated_at=now,
            article_urls=["https://thaipbs.or.th/1"],
            article_count=1,
            outlet_count=1,
            outlets=["ThaiPBS"],
            timeline=[event],
        )

        summary = StorySummary.from_story(story)
        assert summary.story_id == story.story_id
        assert summary.title == story.title
        assert summary.article_count == 1

        list_resp = StoryListResponse(
            total=1,
            page=1,
            page_size=20,
            total_pages=1,
            has_next=False,
            has_prev=False,
            updated="2026-08-23 14:00:00",
            stories=[summary],
        )
        assert list_resp.total == 1
        assert len(list_resp.stories) == 1
        assert list_resp.stories[0].story_id == story.story_id

        article = ArticleRecord(
            title="การประชุมสภา",
            source="ThaiPBS",
            url="https://thaipbs.or.th/1",
            fetched_at="2026-08-23 14:00:00",
        )
        detail = StoryDetailResponse.from_story_and_articles(
            story=story,
            articles=[article],
            trending_score=85.5,
            breakdown={"volume": 10.0, "burst": 5.0},
        )
        assert detail.story_id == story.story_id
        assert len(detail.articles) == 1
        assert len(detail.timeline) == 1
        assert detail.trending_score == 85.5
        assert "Trending reflects" in detail.coverage_disclaimer


# ── 5. StoryRepository Factory Tests ───────────────────────────────

class TestStoryRepositoryFactory:
    @patch("backend.config.settings")
    def test_get_story_repository_default(self, mock_settings: MagicMock) -> None:
        reset_story_repository()
        mock_settings.db_type = "json"
        mock_settings.stories_file = Path("data/stories_data.json")
        repo = get_story_repository()
        assert isinstance(repo, FileStoryRepository)
        reset_story_repository()

    @patch("backend.config.settings")
    def test_get_story_repository_mongo_fallback(self, mock_settings: MagicMock) -> None:
        reset_story_repository()
        mock_settings.db_type = "mongodb"
        mock_settings.mongo_uri = "mongodb://invalid.host:27017"
        mock_settings.mongo_db_name = "test_db"
        mock_settings.stories_file = Path("data/stories_data.json")

        with patch("backend.repo.mongo_story_repo.MongoStoryRepository", side_effect=Exception("Connection failed")):
            repo = get_story_repository()
            # Must fall back gracefully to FileStoryRepository
            assert isinstance(repo, FileStoryRepository)
        reset_story_repository()
