"""
backend/tests/test_sqlite_news_repo.py
─────────────────────────────────────────────────────────────────
Tests for SqliteNewsRepository:
- WAL Mode initialization and PRAGMA settings
- Decoupled storage (articles metadata vs article_contents)
- High-speed indexed queries, sorting, pagination, and filters
- Category and source aggregations
- Concurrent multi-threaded reads/writes in WAL mode
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest

from backend.repo.sqlite_news_repo import SqliteNewsRepository


@pytest.fixture
def sample_articles() -> list[dict]:
    return [
        {
            "title": "ข่าวการเมืองร้อนแรง สภาเปิดอภิปรายงบประมาณ",
            "summary": "สรุปการเมืองวันนี้ มีการประชุมสภาผู้แทนราษฎร",
            "url": "https://example.com/politics/1",
            "source": "ThaiPBS",
            "category": "politics",
            "fetched_at": "2026-10-14T10:00:00Z",
            "story_id": "story_pol_01",
        },
        {
            "title": "ตลาดหุ้นไทยพุ่ง เศรษฐกิจเริ่มฟื้นตัว",
            "summary": "ดัชนี SET ปิดบวก 15 จุด รับข่าวดีเศรษฐกิจ",
            "url": "https://example.com/economy/1",
            "source": "Bangkok Post",
            "category": "economy",
            "fetched_at": "2026-10-14T11:00:00Z",
            "story_id": "story_eco_01",
        },
        {
            "title": "เทคโนโลยี AI ตัวใหม่ฉลาดขึ้น",
            "summary": "การพัฒนาโมเดล AI ช่วยงานผู้ใช้ได้เร็วขึ้น",
            "url": "https://example.com/tech/1",
            "source": "ThaiPBS",
            "category": "technology",
            "fetched_at": "2026-10-14T12:00:00Z",
            "story_id": "story_tech_01",
        },
    ]


class TestSqliteNewsRepository:
    def test_wal_mode_and_init(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test_wal.db"
        repo = SqliteNewsRepository(db_path=db_path, wal_mode=True)

        conn = repo._get_connection()
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"
        repo.close()

    def test_save_and_load_news(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        db_path = tmp_path / "test_news.db"
        repo = SqliteNewsRepository(db_path=db_path)

        assert repo.load_news() == []
        repo.save_news(sample_articles)

        loaded = repo.load_news()
        assert len(loaded) == 3
        # Should be ordered by fetched_at DESC
        assert loaded[0]["category"] == "technology"
        assert loaded[1]["category"] == "economy"
        assert loaded[2]["category"] == "politics"
        repo.close()

    def test_query_news_sorting_and_pagination(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        db_path = tmp_path / "test_news.db"
        repo = SqliteNewsRepository(db_path=db_path)
        repo.save_news(sample_articles)

        # Page 1 (limit 2)
        items, total = repo.query_news(page=1, page_size=2)
        assert total == 3
        assert len(items) == 2
        assert items[0]["category"] == "technology"
        assert items[1]["category"] == "economy"

        # Page 2 (limit 2)
        items2, total2 = repo.query_news(page=2, page_size=2)
        assert total2 == 3
        assert len(items2) == 1
        assert items2[0]["category"] == "politics"
        repo.close()

    def test_query_news_filters(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        db_path = tmp_path / "test_news.db"
        repo = SqliteNewsRepository(db_path=db_path)
        repo.save_news(sample_articles)

        # Filter by source (case-insensitive)
        items, total = repo.query_news(source="thaipbs")
        assert total == 2
        assert all(n["source"] == "ThaiPBS" for n in items)

        # Filter by category
        items, total = repo.query_news(category="economy")
        assert total == 1
        assert items[0]["category"] == "economy"

        # Substring search in Thai title
        items, total = repo.query_news(query="สภา")
        assert total == 1
        assert items[0]["category"] == "politics"
        repo.close()

    def test_category_and_source_counts(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        db_path = tmp_path / "test_news.db"
        repo = SqliteNewsRepository(db_path=db_path)
        repo.save_news(sample_articles)

        cat_counts = repo.get_category_counts()
        assert cat_counts["all"] == 3
        assert cat_counts["politics"] == 1
        assert cat_counts["economy"] == 1
        assert cat_counts["technology"] == 1

        src_counts = repo.get_source_counts()
        assert src_counts["ThaiPBS"] == 2
        assert src_counts["Bangkok Post"] == 1
        repo.close()

    def test_decoupled_heavy_content(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        db_path = tmp_path / "test_news.db"
        repo = SqliteNewsRepository(db_path=db_path)
        repo.save_news(sample_articles)

        # Initially no content linked
        target_url = sample_articles[0]["url"]
        assert repo.get_article_content(target_url) is None

        # Save heavy content
        repo.save_article_content(
            url=target_url,
            content="# Full article markdown body\n\nDetailed political coverage.",
            raw_html="<html><body><p>Detailed political coverage.</p></body></html>",
            bullets=["Point 1", "Point 2"],
            keywords=["การเมือง", "สภา"],
        )

        content_res = repo.get_article_content(target_url)
        assert content_res is not None
        assert "Full article markdown body" in content_res["content"]
        assert content_res["bullets"] == ["Point 1", "Point 2"]
        assert content_res["keywords"] == ["การเมือง", "สภา"]
        repo.close()

    def test_seen_urls(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test_news.db"
        repo = SqliteNewsRepository(db_path=db_path)

        assert repo.load_seen() == set()
        seen = {"https://example.com/1", "https://example.com/2"}
        repo.save_seen(seen)
        assert repo.load_seen() == seen
        repo.close()

    def test_concurrent_multithreaded_wal_access(self, tmp_path: Path, sample_articles: list[dict]) -> None:
        """Verify concurrent multi-threaded reads and writes do not lock under WAL mode."""
        db_path = tmp_path / "test_concurrency.db"
        repo = SqliteNewsRepository(db_path=db_path, wal_mode=True)
        repo.save_news(sample_articles)

        def reader_task():
            local_repo = SqliteNewsRepository(db_path=db_path, wal_mode=True)
            for _ in range(15):
                _items, total = local_repo.query_news(page=1, page_size=10)
                assert total >= 3
            local_repo.close()
            return True

        def writer_task(idx: int):
            local_repo = SqliteNewsRepository(db_path=db_path, wal_mode=True)
            for j in range(5):
                article = {
                    "title": f"Concurrent Article {idx}_{j}",
                    "summary": "Concurrent test body",
                    "url": f"https://example.com/concurrent/{idx}/{j}",
                    "source": "Test",
                    "category": "society",
                    "fetched_at": "2026-10-14T15:00:00Z",
                }
                local_repo.save_news([article])
            local_repo.close()
            return True

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [
                executor.submit(reader_task),
                executor.submit(writer_task, 1),
                executor.submit(reader_task),
                executor.submit(writer_task, 2),
                executor.submit(reader_task),
                executor.submit(writer_task, 3),
            ]
            results = [f.result() for f in futures]
            assert all(results)

        repo.close()
