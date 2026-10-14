"""
backend/tests/test_news_repo.py
─────────────────────────────────────────────────────────────────
Tests for NewsRepository implementations:
- FileNewsRepository (JSON storage)
- MongoNewsRepository (MongoDB NoSQL storage)
- Factory get_news_repository fallback handling
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.repo.mongo_news_repo import MongoNewsRepository
from backend.repo.news_repo import FileNewsRepository


@pytest.fixture
def sample_articles() -> list[dict]:
    return [
        {
            "title": "ข่าวการเมืองร้อนแรง สภาเปิดอภิปราย",
            "summary": "สรุปการเมืองวันนี้ มีการประชุมสภาผู้แทนราษฎร",
            "url": "https://example.com/politics/1",
            "source": "ThaiPBS",
            "category": "politics",
            "fetched_at": "2026-09-18T10:00:00Z",
        },
        {
            "title": "ตลาดหุ้นไทยพุ่ง เศรษฐกิจเริ่มฟื้นตัว",
            "summary": "ดัชนี SET ปิดบวก 15 จุด รับข่าวดีเศรษฐกิจ",
            "url": "https://example.com/economy/1",
            "source": "Bangkok Post",
            "category": "economy",
            "fetched_at": "2026-09-18T11:00:00Z",
        },
        {
            "title": "เทคโนโลยี AI ตัวใหม่ฉลาดขึ้น",
            "summary": "การพัฒนาโมเดล AI ช่วยงานผู้ใช้ได้เร็วขึ้น",
            "url": "https://example.com/tech/1",
            "source": "ThaiPBS",
            "category": "technology",
            "fetched_at": "2026-09-18T12:00:00Z",
        },
    ]


class TestFileNewsRepository:
    def test_save_and_load_news(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        data_file = tmp_path / "news.json"
        repo = FileNewsRepository(data_file=data_file)

        assert repo.load_news() == []
        repo.save_news(sample_articles)

        loaded = repo.load_news()
        assert len(loaded) == 3
        assert loaded[0]["title"] == sample_articles[0]["title"]

    def test_query_news_sorting_and_pagination(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        data_file = tmp_path / "news.json"
        repo = FileNewsRepository(data_file=data_file)
        repo.save_news(sample_articles)

        # Query all (sorted by fetched_at desc -> tech at 12:00 should be first)
        items, total = repo.query_news(page=1, page_size=2)
        assert total == 3
        assert len(items) == 2
        assert items[0]["category"] == "technology"
        assert items[1]["category"] == "economy"

        # Page 2
        items2, total2 = repo.query_news(page=2, page_size=2)
        assert total2 == 3
        assert len(items2) == 1
        assert items2[0]["category"] == "politics"

    def test_query_news_filters(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        data_file = tmp_path / "news.json"
        repo = FileNewsRepository(data_file=data_file)
        repo.save_news(sample_articles)

        # Filter by source
        items, total = repo.query_news(source="thaipbs")
        assert total == 2
        assert all(n["source"] == "ThaiPBS" for n in items)

        # Filter by category
        items, total = repo.query_news(category="economy")
        assert total == 1
        assert items[0]["category"] == "economy"

        # Search query in Thai
        items, total = repo.query_news(query="สภา")
        assert total == 1
        assert items[0]["category"] == "politics"

    def test_category_and_source_counts(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        data_file = tmp_path / "news.json"
        repo = FileNewsRepository(data_file=data_file)
        repo.save_news(sample_articles)

        cat_counts = repo.get_category_counts()
        assert cat_counts["all"] == 3
        assert cat_counts["politics"] == 1
        assert cat_counts["economy"] == 1
        assert cat_counts["technology"] == 1

        src_counts = repo.get_source_counts()
        assert src_counts["ThaiPBS"] == 2
        assert src_counts["Bangkok Post"] == 1

    def test_seen_urls(self, tmp_path: Path) -> None:
        data_file = tmp_path / "news.json"
        repo = FileNewsRepository(data_file=data_file)

        assert repo.load_seen() == set()
        seen = {"https://example.com/1", "https://example.com/2"}
        repo.save_seen(seen)
        assert repo.load_seen() == seen


class TestMongoNewsRepositoryMock:
    @patch("pymongo.MongoClient")
    def test_mongo_repo_init_and_indexes(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        MongoNewsRepository(mongo_uri="mongodb://fake:27017", db_name="test_db")
        mock_client.admin.command.assert_called_once_with("ping")

        articles_coll = mock_db.__getitem__.return_value
        assert articles_coll.create_index.called

    @patch("pymongo.MongoClient")
    def test_mongo_query_news(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_articles = MagicMock()
        mock_seen = MagicMock()
        mock_metadata = MagicMock()

        def get_coll(name: str):
            if name == "articles":
                return mock_articles
            if name == "seen_urls":
                return mock_seen
            return mock_metadata

        mock_db.__getitem__.side_effect = get_coll

        mock_articles.count_documents.return_value = 1
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = [{"title": "Test AI", "category": "technology"}]
        mock_articles.find.return_value = mock_cursor

        repo = MongoNewsRepository(mongo_uri="mongodb://fake:27017")
        items, total = repo.query_news(page=1, page_size=10, category="technology")

        assert total == 1
        assert len(items) == 1
        assert items[0]["title"] == "Test AI"
