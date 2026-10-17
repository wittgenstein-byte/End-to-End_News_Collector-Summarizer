"""
backend/tests/test_api_endpoints.py
─────────────────────────────────────────────────────────────────
Comprehensive test suite for Milestone 5: API Endpoints & Presentation:
1. GET /api/stories:
   - Pagination (limit, offset, page, total_pages, has_next, has_prev)
   - Status filtering ('active', 'dormant')
   - Category filtering (soft signal)
   - StorySummary projection fields & fallback headline/summary
2. GET /api/stories/{story_id}:
   - Story detail retrieval with 200 OK
   - Member articles assembled in chronological order (earliest to latest)
   - Timeline development events (timestamp, event, source, url)
   - Explainable TrendingScoreBreakdown (volume, velocity, diversity, recency, novelty, engagement)
   - Mandatory coverage limitation disclaimer
   - 404 Not Found on nonexistent story_id
3. GET /api/news/trending:
   - Backward-compatible response (total, updated, trending, articles, clusters, hero)
   - Enriched with ranked active stories and TrendingScoreBreakdown
   - Category and limit query filtering
   - Mandatory coverage limitation disclaimer
4. GET /api/stories/trending:
   - Dedicated story-based trending endpoint returning TrendingStoryListResponse
5. Graceful Heuristic Fallback (LLM Unavailable):
   - HTTP 200 guaranteed across all endpoints when LLM is down / missing API key
   - Fallback headline and summary generated and verified
6. Telemetry Endpoints:
   - POST /api/news/engage and /api/news/engagement recording events
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.repo.engagement_repo import (
    EngagementRepositoryPort,
    get_engagement_repository,
)
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.story_schema import StoryRecord, TimelineEvent
from backend.services.story_presentation_service import (
    StoryPresentationService,
    get_story_presentation_service,
)
from backend.services.trending_service import (
    TrendingService,
    get_trending_service,
)

# ── In-Memory Repository Test Doubles ──────────────────────────────

class InMemoryStoryRepository(StoryRepositoryPort):
    def __init__(self, stories: list[StoryRecord] | None = None) -> None:
        self.stories: dict[str, StoryRecord] = {}
        self.url_map: dict[str, str] = {}
        if stories:
            for s in stories:
                self.save_story(s)

    def get_story(self, story_id: str) -> StoryRecord | None:
        return self.stories.get(story_id)

    def save_story(self, story: StoryRecord) -> None:
        self.stories[story.story_id] = story
        for u in story.article_urls:
            if u:
                self.url_map[u] = story.story_id

    def save_stories_batch(self, stories: list[StoryRecord]) -> None:
        for s in stories:
            self.save_story(s)

    def list_stories(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoryRecord]:
        items = list(self.stories.values())
        items.sort(key=lambda s: s.updated_at, reverse=True)
        if status and status.strip().lower() != "all":
            target = status.strip().lower()
            items = [s for s in items if s.status.lower() == target]
        return items[offset : offset + limit]

    def find_candidate_stories(
        self,
        since_time: datetime,
        category: str | None = None,
    ) -> list[StoryRecord]:
        norm_since = since_time if since_time.tzinfo else since_time.replace(tzinfo=timezone.utc)
        items = [s for s in self.stories.values() if s.updated_at >= norm_since]
        if category and category.strip().lower() != "all":
            items = [s for s in items if s.category.lower() == category.strip().lower()]
        items.sort(key=lambda s: s.updated_at, reverse=True)
        return items

    def get_stories_by_ids(self, story_ids: list[str]) -> list[StoryRecord]:
        return [self.stories[sid] for sid in story_ids if sid in self.stories]

    def get_story_by_article_url(self, url: str) -> StoryRecord | None:
        sid = self.url_map.get(url)
        return self.stories.get(sid) if sid else None

    def count_stories(self, status: str | None = None) -> int:
        if not status or status.strip().lower() == "all":
            return len(self.stories)
        target = status.strip().lower()
        return sum(1 for s in self.stories.values() if s.status.lower() == target)


class InMemoryNewsRepository(NewsRepositoryPort):
    def __init__(self, news: list[dict[str, Any]] | None = None) -> None:
        self._news: list[dict[str, Any]] = list(news) if news else []

    def load_news(self) -> list[dict[str, Any]]:
        return list(self._news)

    def save_news(self, news: list[dict[str, Any]]) -> None:
        self._news = list(news)

    def get_article_by_url(self, url: str) -> dict[str, Any] | None:
        for a in self._news:
            if a.get("url") == url:
                return dict(a)
        return None

    def get_by_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        url_set = {u.strip() for u in urls if u}
        return [dict(a) for a in self._news if a.get("url") in url_set]

    def count_news(self) -> int:
        return len(self._news)

    def filter_news(
        self,
        source: str | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        results = list(self._news)
        if source:
            results = [a for a in results if a.get("source") == source]
        if category:
            results = [a for a in results if a.get("category") == category]
        return results


class InMemoryEngagementRepository(EngagementRepositoryPort):
    def __init__(self) -> None:
        self._data: dict[str, dict[str, int]] = {}

    def record_event(self, url: str, event_type: str) -> dict[str, int]:
        clean_url = url.strip()
        if clean_url not in self._data:
            self._data[clean_url] = {"clicks": 0, "summaries": 0, "bookmarks": 0}
        key = f"{event_type}s" if not event_type.endswith("s") else event_type
        if key in self._data[clean_url]:
            self._data[clean_url][key] += 1
        return dict(self._data[clean_url])

    def get_engagement(self, url: str) -> dict[str, int]:
        return dict(self._data.get(url.strip(), {"clicks": 0, "summaries": 0, "bookmarks": 0}))

    def get_all_engagements(self) -> dict[str, dict[str, int]]:
        return {u: dict(stats) for u, stats in self._data.items()}


# ── Fixtures & Setup ───────────────────────────────────────────────

@pytest.fixture
def test_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def sample_test_data(test_now: datetime) -> tuple[list[StoryRecord], list[dict[str, Any]]]:
    # Story 1: Active Nan Floods (Multi-outlet, Environment)
    url_nan1 = "https://thaipbs.or.th/news/nan-001"
    url_nan2 = "https://thestandard.co/news/nan-002"
    url_nan3 = "https://bangkokpost.com/news/nan-003"
    story_nan = StoryRecord(
        story_id="story_nan_floods",
        title="สถานการณ์น้ำท่วมและดินถล่มในพื้นที่จังหวัดน่าน",
        headline="เกาะติดวิกฤตน้ำท่วมน่าน หลายพื้นที่ถูกตัดขาด เร่งระดมความช่วยเหลือ",
        summary="สถานการณ์น้ำท่วมดินถล่มที่น่านขยายวงกว้าง นายกฯ สั่งการเร่งเยียวยาผู้ประสบภัย",
        category="environment",
        status="active",
        created_at=test_now - timedelta(hours=36),
        updated_at=test_now - timedelta(hours=2),
        article_urls=[url_nan1, url_nan2, url_nan3],
        article_count=3,
        outlet_count=3,
        outlets=["ThaiPBS", "The Standard", "Bangkok Post"],
        entities=["น่าน", "อนุทิน", "GISTDA"],
        timeline=[
            TimelineEvent(
                timestamp="2026-10-10 08:30:00",
                event="GISTDA รายงานพื้นที่เสี่ยงดินถล่ม 11 ชุมชนในอำเภอบ่อเกลือ",
                source="ThaiPBS",
                url=url_nan1,
            ),
            TimelineEvent(
                timestamp="2026-10-10 14:00:00",
                event="กรมบัญชีกลางอนุมัติขยายวงเงินทดรองราชการ 100 ล้านบาทช่วยน้ำท่วมน่าน",
                source="The Standard",
                url=url_nan2,
            ),
            TimelineEvent(
                timestamp="2026-10-11 10:00:00",
                event="นายกรัฐมนตรีลงพื้นที่ตรวจน้ำท่วมน่าน กำชับแผนฟื้นฟูเยียวยา",
                source="Bangkok Post",
                url=url_nan3,
            ),
        ],
    )

    # Story 2: Active Politics Story (Thai Parliament debate)
    url_pol1 = "https://thaipbs.or.th/news/pol-001"
    url_pol2 = "https://thairath.co.th/news/pol-002"
    story_pol = StoryRecord(
        story_id="story_parliament",
        title="การอภิปรายงบประมาณรายจ่ายประจำปีในรัฐสภา",
        headline="สภาผู้แทนราษฎรเปิดอภิปรายงบประมาณเข้มข้น ฝ่ายค้านซักฟอกจัดสรรงบ",
        summary="สภาฯ เดินหน้าพิจารณาร่าง พ.ร.บ. งบประมาณรายจ่าย ประธานสภาฯ คุมเข้มกรอบเวลา",
        category="politics",
        status="active",
        created_at=test_now - timedelta(hours=24),
        updated_at=test_now - timedelta(hours=4),
        article_urls=[url_pol1, url_pol2],
        article_count=2,
        outlet_count=2,
        outlets=["ThaiPBS", "Thairath"],
        entities=["สภาผู้แทนราษฎร", "งบประมาณ"],
    )

    # Story 3: Dormant Story (Older festival over 90h ago)
    url_dor1 = "https://thaipbs.or.th/news/festival-001"
    story_dormant = StoryRecord(
        story_id="story_festival_old",
        title="ประเพณีลอยกระทงและการจัดงานเทศกาล",
        headline="บรรยากาศการจัดงานลอยกระทงทั่วประเทศ",
        summary="ประชาชนร่วมสืบสานประเพณีลอยกระทงในบรรยากาศอบอุ่น",
        category="society",
        status="dormant",
        created_at=test_now - timedelta(hours=120),
        updated_at=test_now - timedelta(hours=95),
        article_urls=[url_dor1],
        article_count=1,
        outlet_count=1,
        outlets=["ThaiPBS"],
    )

    articles = [
        {
            "url": url_nan1,
            "title": "GISTDA เตือน 11 ชุมชนน่านเสี่ยงดินถล่ม",
            "summary": "ภาพถ่ายดาวเทียมระบุพื้นที่เสี่ยงดินถล่มในบ่อเกลือ",
            "source": "ThaiPBS",
            "category": "environment",
            "fetched_at": "2026-10-10 08:30:00",
        },
        {
            "url": url_nan2,
            "title": "อนุมัติ 100 ล้าน ช่วยน้ำท่วมน่าน",
            "summary": "เพิ่มงบฉุกเฉินช่วยเหลือประชาชนที่ประสบอุทกภัย",
            "source": "The Standard",
            "category": "environment",
            "fetched_at": "2026-10-10 14:00:00",
        },
        {
            "url": url_nan3,
            "title": "PM visits Nan flood crisis areas",
            "summary": "Prime minister inspects flood situation and relief measures.",
            "source": "Bangkok Post",
            "category": "environment",
            "fetched_at": "2026-10-11 10:00:00",
        },
        {
            "url": url_pol1,
            "title": "ประชุมสภาถกงบประมาณวาระแรก",
            "summary": "ฝ่ายค้านและรัฐบาลเปิดศึกอภิปรายร่างงบประมาณ",
            "source": "ThaiPBS",
            "category": "politics",
            "fetched_at": "2026-10-11 08:00:00",
        },
        {
            "url": url_pol2,
            "title": "เกาะติดศึกงบประมาณ 67 สภาเดือด",
            "summary": "บรรยากาศในสภาช่วงเปิดอภิปรายงบประมาณ",
            "source": "Thairath",
            "category": "politics",
            "fetched_at": "2026-10-11 09:30:00",
        },
        {
            "url": url_dor1,
            "title": "สีสันงานลอยกระทงสุโขทัย",
            "summary": "นักท่องเที่ยวร่วมงานลอยกระทงเผาเทียนเล่นไฟ",
            "source": "ThaiPBS",
            "category": "society",
            "fetched_at": "2026-10-07 13:00:00",
        },
    ]

    return [story_nan, story_pol, story_dormant], articles


@pytest.fixture
def client_with_data(sample_test_data: tuple[list[StoryRecord], list[dict[str, Any]]]):
    stories, articles = sample_test_data
    story_repo = InMemoryStoryRepository(stories)
    news_repo = InMemoryNewsRepository(articles)
    eng_repo = InMemoryEngagementRepository()

    # Telemetry data
    eng_repo.record_event("https://thaipbs.or.th/news/nan-001", "click")
    eng_repo.record_event("https://thaipbs.or.th/news/nan-001", "summary")
    eng_repo.record_event("https://thestandard.co/news/nan-002", "bookmark")

    trending_service = TrendingService(
        news_repo=news_repo,
        engagement_repo=eng_repo,
        story_repo=story_repo,
    )

    presentation_service = StoryPresentationService(
        client=None,  # Tests offline fallback guarantee
        models=["gpt-4o-mini"],
        news_repo=news_repo,
    )

    app.dependency_overrides[get_story_repository] = lambda: story_repo
    app.dependency_overrides[get_news_repository] = lambda: news_repo
    app.dependency_overrides[get_engagement_repository] = lambda: eng_repo
    app.dependency_overrides[get_trending_service] = lambda: trending_service
    app.dependency_overrides[get_story_presentation_service] = lambda: presentation_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ── Test Suite 1: GET /api/stories ─────────────────────────────────

class TestStoryListEndpoint:
    def test_list_stories_default_pagination(self, client_with_data: TestClient) -> None:
        """GET /api/stories returns HTTP 200 with StoryListResponse structure."""
        resp = client_with_data.get("/api/stories")
        assert resp.status_code == 200
        data = resp.json()

        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert "has_next" in data
        assert "has_prev" in data
        assert "updated" in data
        assert "stories" in data
        assert isinstance(data["stories"], list)
        assert data["total"] == 3
        assert len(data["stories"]) == 3

        # Validate StorySummary fields
        first = data["stories"][0]
        assert "story_id" in first
        assert "title" in first
        assert "headline" in first
        assert "summary" in first
        assert "category" in first
        assert "status" in first
        assert "article_count" in first
        assert "outlet_count" in first
        assert "outlets" in first
        assert "entities" in first

    def test_list_stories_filter_active_status(self, client_with_data: TestClient) -> None:
        """GET /api/stories?status=active filters for active stories only."""
        resp = client_with_data.get("/api/stories?status=active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for s in data["stories"]:
            assert s["status"] == "active"

    def test_list_stories_filter_dormant_status(self, client_with_data: TestClient) -> None:
        """GET /api/stories?status=dormant returns only dormant stories."""
        resp = client_with_data.get("/api/stories?status=dormant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["stories"][0]["story_id"] == "story_festival_old"
        assert data["stories"][0]["status"] == "dormant"

    def test_list_stories_filter_category(self, client_with_data: TestClient) -> None:
        """GET /api/stories?category=environment filters stories by category tag."""
        resp = client_with_data.get("/api/stories?category=environment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["stories"][0]["story_id"] == "story_nan_floods"
        assert data["stories"][0]["category"] == "environment"

    def test_list_stories_pagination_offset_limit(self, client_with_data: TestClient) -> None:
        """GET /api/stories?limit=1&offset=1 respects pagination slicing."""
        resp = client_with_data.get("/api/stories?limit=1&offset=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["page_size"] == 1
        assert data["page"] == 2
        assert len(data["stories"]) == 1
        assert data["has_prev"] is True

    def test_list_stories_empty_repository(self) -> None:
        """Empty story repository returns HTTP 200 with total=0 and empty stories list."""
        app.dependency_overrides[get_story_repository] = lambda: InMemoryStoryRepository([])
        with TestClient(app) as client:
            resp = client.get("/api/stories")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0
            assert data["stories"] == []
        app.dependency_overrides.clear()


# ── Test Suite 2: GET /api/stories/{story_id} ──────────────────────

class TestStoryDetailEndpoint:
    def test_get_story_detail_success(self, client_with_data: TestClient) -> None:
        """GET /api/stories/{story_id} returns HTTP 200 with full StoryDetailResponse."""
        resp = client_with_data.get("/api/stories/story_nan_floods")
        assert resp.status_code == 200
        data = resp.json()

        assert data["story_id"] == "story_nan_floods"
        assert "สถานการณ์น้ำท่วม" in data["title"]
        assert data["headline"] is not None
        assert data["summary"] is not None
        assert data["category"] == "environment"
        assert data["status"] == "active"
        assert data["article_count"] == 3
        assert data["outlet_count"] == 3
        assert sorted(data["outlets"]) == sorted(["ThaiPBS", "The Standard", "Bangkok Post"])

        # Timeline verification
        assert "timeline" in data
        assert isinstance(data["timeline"], list)
        assert len(data["timeline"]) >= 3
        first_event = data["timeline"][0]
        assert "timestamp" in first_event
        assert "event" in first_event
        assert "source" in first_event
        assert "url" in first_event

        # Score and breakdown verification
        assert data["trending_score"] is not None
        assert data["trending_score"] > 0.0
        assert "breakdown" in data
        bd = data["breakdown"]
        assert "volume_score" in bd
        assert "velocity_score" in bd
        assert "diversity_score" in bd
        assert "recency_score" in bd
        assert "novelty_score" in bd
        assert "engagement_score" in bd
        assert "final_score" in bd

        # Mandatory coverage limitation disclaimer
        assert "coverage_disclaimer" in data
        assert "Trending reflects how widely and frequently" in data["coverage_disclaimer"]

    def test_member_articles_chronological_order(self, client_with_data: TestClient) -> None:
        """Member articles in StoryDetailResponse are sorted chronologically (earliest to latest)."""
        resp = client_with_data.get("/api/stories/story_nan_floods")
        assert resp.status_code == 200
        articles = resp.json()["articles"]
        assert len(articles) == 3

        # Earliest: 2026-10-10 08:30:00 -> Middle: 2026-10-10 14:00:00 -> Latest: 2026-10-11 10:00:00
        timestamps = [a["fetched_at"] for a in articles]
        assert timestamps == sorted(timestamps)

    def test_get_story_detail_not_found(self, client_with_data: TestClient) -> None:
        """GET /api/stories/{nonexistent_id} returns HTTP 404 Not Found."""
        resp = client_with_data.get("/api/stories/story_nonexistent_999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ── Test Suite 3: GET /api/news/trending (Backward Compatible) ────

class TestTrendingNewsEndpoint:
    def test_trending_news_returns_backward_compatible_response(self, client_with_data: TestClient) -> None:
        """GET /api/news/trending returns HTTP 200 with all legacy fields plus enriched stories."""
        resp = client_with_data.get("/api/news/trending")
        assert resp.status_code == 200
        data = resp.json()

        # Legacy fields verified
        assert "total" in data
        assert "updated" in data
        assert "trending" in data
        assert "articles" in data
        assert "clusters" in data
        assert "trending_hashtags" in data
        assert "hero" in data

        # Enriched Milestone 5 fields verified
        assert "stories" in data
        assert isinstance(data["stories"], list)
        assert len(data["stories"]) >= 1

        # Disclaimer verified
        assert "coverage_disclaimer" in data
        assert "Trending reflects how widely and frequently" in data["coverage_disclaimer"]

    def test_trending_articles_contain_score_breakdown(self, client_with_data: TestClient) -> None:
        """Articles in trending response have explainable TrendingScoreBreakdown."""
        resp = client_with_data.get("/api/news/trending")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["trending"]) > 0

        first_art = data["trending"][0]
        assert "trending_score" in first_art
        assert "breakdown" in first_art
        bd = first_art["breakdown"]
        assert bd is not None
        assert "volume_score" in bd
        assert "velocity_score" in bd
        assert "diversity_score" in bd
        assert "recency_score" in bd
        assert "novelty_score" in bd
        assert "final_score" in bd

    def test_trending_stories_contain_enriched_presentation(self, client_with_data: TestClient) -> None:
        """Stories in trending response contain headline, summary, timeline, and breakdown."""
        resp = client_with_data.get("/api/news/trending")
        assert resp.status_code == 200
        stories = resp.json()["stories"]
        assert len(stories) >= 1

        top_story = stories[0]
        assert top_story["story_id"] in ("story_nan_floods", "story_parliament")
        assert top_story["headline"] is not None
        assert top_story["summary"] is not None
        assert "timeline" in top_story
        assert "breakdown" in top_story
        assert top_story["breakdown"]["final_score"] > 0.0

    def test_trending_category_filter(self, client_with_data: TestClient) -> None:
        """GET /api/news/trending?category=politics narrows trending stories."""
        resp = client_with_data.get("/api/news/trending?category=politics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["stories"]) == 1
        assert data["stories"][0]["story_id"] == "story_parliament"


# ── Test Suite 4: GET /api/stories/trending ────────────────────────

class TestStoriesTrendingEndpoint:
    def test_dedicated_stories_trending_endpoint(self, client_with_data: TestClient) -> None:
        """GET /api/stories/trending returns HTTP 200 with TrendingStoryListResponse."""
        resp = client_with_data.get("/api/stories/trending?limit=5")
        assert resp.status_code == 200
        data = resp.json()

        assert "total" in data
        assert "updated" in data
        assert "stories" in data
        assert len(data["stories"]) == 2  # Only 2 active stories (dormant excluded)

        # Ranked deterministically: Nan Floods (3 outlets) outranks Parliament (2 outlets)
        assert data["stories"][0]["story_id"] == "story_nan_floods"
        assert data["stories"][0]["rank"] == 1
        assert data["stories"][1]["story_id"] == "story_parliament"
        assert data["stories"][1]["rank"] == 2


# ── Test Suite 5: Robust Graceful Heuristic Fallback (LLM Down) ────

class TestOfflineLLMFallbackGuarantee:
    def test_fallback_when_llm_is_unavailable(self, sample_test_data: tuple[list[StoryRecord], list[dict[str, Any]]]) -> None:
        """
        When LLM client is None or offline, story list, detail, and trending endpoints
        ALL guarantee HTTP 200 responses with synthesized heuristic headline and summary.
        """
        stories, articles = sample_test_data
        story_repo = InMemoryStoryRepository(stories)
        news_repo = InMemoryNewsRepository(articles)
        eng_repo = InMemoryEngagementRepository()

        # Presentation service with NO client (completely offline)
        fallback_presentation = StoryPresentationService(
            client=None,
            news_repo=news_repo,
        )

        app.dependency_overrides[get_story_repository] = lambda: story_repo
        app.dependency_overrides[get_news_repository] = lambda: news_repo
        app.dependency_overrides[get_engagement_repository] = lambda: eng_repo
        app.dependency_overrides[get_trending_service] = lambda: TrendingService(
            news_repo=news_repo,
            engagement_repo=eng_repo,
            story_repo=story_repo,
        )
        app.dependency_overrides[get_story_presentation_service] = lambda: fallback_presentation

        with TestClient(app) as client:
            # 1. Story List
            res_list = client.get("/api/stories")
            assert res_list.status_code == 200
            for s in res_list.json()["stories"]:
                assert s["headline"] is not None and len(s["headline"].strip()) > 0
                assert s["summary"] is not None and len(s["summary"].strip()) > 0

            # 2. Story Detail
            res_detail = client.get("/api/stories/story_nan_floods")
            assert res_detail.status_code == 200
            detail_data = res_detail.json()
            assert detail_data["headline"] is not None
            assert len(detail_data["headline"].strip()) > 0
            assert detail_data["summary"] is not None
            assert len(detail_data["summary"].strip()) > 0
            assert len(detail_data["timeline"]) > 0

            # 3. Trending News
            res_trend = client.get("/api/news/trending")
            assert res_trend.status_code == 200
            trend_data = res_trend.json()
            assert len(trend_data["stories"]) > 0
            for st in trend_data["stories"]:
                assert st["headline"] is not None and len(st["headline"].strip()) > 0
                assert st["summary"] is not None and len(st["summary"].strip()) > 0

        app.dependency_overrides.clear()


# ── Test Suite 6: Reader Engagement Telemetry ──────────────────────

class TestEngagementTelemetryEndpoints:
    def test_record_engagement_endpoints(self, client_with_data: TestClient) -> None:
        """POST /api/news/engage and /api/news/engagement record reader telemetry."""
        target_url = "https://thaipbs.or.th/news/nan-001"

        res1 = client_with_data.post(
            "/api/news/engage",
            json={"url": target_url, "event_type": "click"},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["ok"] is True
        assert data1["stats"]["clicks"] >= 1

        res2 = client_with_data.post(
            "/api/news/engagement",
            json={"url": target_url, "event_type": "bookmark"},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["ok"] is True
        assert data2["stats"]["bookmarks"] >= 1
