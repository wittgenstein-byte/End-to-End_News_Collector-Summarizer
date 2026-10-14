"""
backend/tests/test_story_service.py
─────────────────────────────────────────────────────────────────
Comprehensive tests for Milestone 2: Online Story Identification Engine:
- TestEntityExtractor: PyThaiNLP thainer-v2 BIO parsing, caching, fallbacks
- TestTwoBandSimilarityAndEntityConfirmation: 2-band matching, NER confirmation, zero Jaccard
- TestMultiDayCandidateWindowPersistence: >= 5 days single story persistence, window behavior
- TestCrossCategoryAndSoftCategory: Cross-category merges, soft category ranking
- TestCentroidEMAMathematics: Exact EMA numerical update (0.85 old + 0.15 new)
- TestStoryLifecycleAndDormantReactivation: 72h inactivity, dormant reactivation
- TestBackfillStoriesJob: One-off migration job assigning story_id to all articles
- TestStoryServiceIdempotencyAndEdgeCases: URL idempotency, graceful error handling
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.backfill_stories_job import run_backfill
from backend.repo.news_repo import FileNewsRepository
from backend.repo.story_repo import FileStoryRepository
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import StoryRecord
from backend.services.entity_extractor import EntityExtractor, get_entity_extractor
from backend.services.story_service import StoryService, _cosine_similarity


def make_vector_with_target_cosine(base_vec: list[float], target_cos: float) -> list[float]:
    """
    Given a unit base vector with nonzero components only in first dim,
    generate a unit vector whose cosine similarity with base_vec is exactly target_cos.
    """
    dim = len(base_vec)
    vec = [0.0] * dim
    clamped_cos = max(-1.0, min(1.0, target_cos))
    sin_val = math.sqrt(max(0.0, 1.0 - clamped_cos * clamped_cos))
    vec[0] = float(clamped_cos)
    vec[1] = float(sin_val)
    return vec


class MockEmbedder:
    """Mock embedder providing deterministic vectors for testing thresholds."""

    def __init__(self, vector_map: dict[str, list[float]] | None = None) -> None:
        self.vector_map = vector_map or {}
        self.hidden_size = 768
        self._default_vec = [1.0] + [0.0] * 767

    def encode_articles(self, articles: list[dict[str, Any]]) -> np.ndarray:
        results: list[list[float]] = []
        for a in articles:
            title = str(a.get("title") or "")
            vec = self.vector_map.get(title, self._default_vec)
            results.append(vec)
        return np.array(results, dtype=np.float32)

    def encode_text(self, text: str) -> list[float]:
        return self.vector_map.get(text, self._default_vec)


# ── 1. Entity Extractor Tests ─────────────────────────────────────

class TestEntityExtractor:
    """Tests for PyThaiNLP thainer-v2 NER entity extractor and caching."""

    def test_extract_entities_bio_person_org_loc_fac(self) -> None:
        """Verify BIO tag parsing into person, org, loc, and fac entity spans."""
        mock_ner = MagicMock()
        # Mock BIO output from thainer-v2
        mock_ner.tag.return_value = [
            ("นายกฯ", "O"),
            ("แพทองธาร", "B-PERSON"),
            (" ", "I-PERSON"),
            ("ชินวัตร", "I-PERSON"),
            ("เป็น", "O"),
            ("ประธาน", "O"),
            ("ประชุม", "O"),
            ("ครม.", "B-ORGANIZATION"),
            ("ที่", "O"),
            ("ทำเนียบรัฐบาล", "B-FACILITY"),
            ("ใน", "O"),
            ("กรุงเทพมหานคร", "B-LOCATION"),
        ]

        extractor = EntityExtractor(ner=mock_ner)
        entities = extractor.extract_entities("ข้อความทดสอบข่าวการเมือง")

        assert "แพทองธาร ชินวัตร" in entities
        assert "ครม." in entities
        assert "ทำเนียบรัฐบาล" in entities
        assert "กรุงเทพมหานคร" in entities
        assert len(entities) == 4

    def test_extract_entities_caching(self) -> None:
        """Verify in-memory caching prevents redundant NER execution on identical text."""
        mock_ner = MagicMock()
        mock_ner.tag.return_value = [
            ("ชัชชาติ", "B-PERSON"),
            (" ", "I-PERSON"),
            ("สิทธิพันธุ์", "I-PERSON"),
        ]

        extractor = EntityExtractor(ner=mock_ner, max_cache_size=100)
        text = "ชัชชาติ สิทธิพันธุ์ ตรวจสถานการณ์น้ำท่วม"

        # First call hits mock NER
        res1 = extractor.extract_entities(text)
        assert res1 == ["ชัชชาติ สิทธิพันธุ์"]
        assert mock_ner.tag.call_count == 1

        # Second call hits in-memory cache
        res2 = extractor.extract_entities(text)
        assert res2 == ["ชัชชาติ สิทธิพันธุ์"]
        assert mock_ner.tag.call_count == 1  # No additional call

        # Clear cache and call again
        extractor.clear_cache()
        res3 = extractor.extract_entities(text)
        assert res3 == ["ชัชชาติ สิทธิพันธุ์"]
        assert mock_ner.tag.call_count == 2

    def test_extract_entities_fallback_empty_and_short(self) -> None:
        """Verify empty strings, None, or short text return empty list without calling NER."""
        mock_ner = MagicMock()
        extractor = EntityExtractor(ner=mock_ner)

        assert extractor.extract_entities("") == []
        assert extractor.extract_entities("  ") == []
        assert extractor.extract_entities("ab") == []
        assert mock_ner.tag.call_count == 0

    def test_extract_entities_graceful_exception_handling(self) -> None:
        """Verify that engine exceptions are swallowed gracefully returning empty list."""
        mock_ner = MagicMock()
        mock_ner.tag.side_effect = RuntimeError("CUDA or Torch inference failure")

        extractor = EntityExtractor(ner=mock_ner)
        # Must not raise an exception
        entities = extractor.extract_entities("ข้อความทดสอบข้อผิดพลาดของโมเดล")
        assert entities == []

    def test_extract_entities_deduplication(self) -> None:
        """Verify entities appearing multiple times are deduplicated preserving order."""
        mock_ner = MagicMock()
        mock_ner.tag.return_value = [
            ("เชียงใหม่", "B-LOCATION"),
            ("และ", "O"),
            ("เชียงราย", "B-LOCATION"),
            ("ร่วมกับ", "O"),
            ("เชียงใหม่", "B-LOCATION"),
        ]
        extractor = EntityExtractor(ner=mock_ner)
        res = extractor.extract_entities("เชียงใหม่ และ เชียงราย ร่วมกับ เชียงใหม่")
        assert res == ["เชียงใหม่", "เชียงราย"]

    def test_real_pythainlp_ner_integration(self) -> None:
        """Real PyThaiNLP thainer-v2 integration smoke test on real Thai sentence."""
        extractor = get_entity_extractor()
        text = "นายกรัฐมนตรี ประชุม ครม. ที่ กรุงเทพมหานคร"
        entities = extractor.extract_entities(text)
        # Should execute without throwing and return a list of strings
        assert isinstance(entities, list)


# ── 2. Two-Band Similarity & Entity Confirmation Tests ────────────

class TestTwoBandSimilarityAndEntityConfirmation:
    """Tests for two-band matching: high similarity direct merge, borderline NER confirmation."""

    @pytest.fixture
    def setup_services(self, tmp_path: Path):
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        return repo, mock_extractor

    def test_direct_merge_above_high_threshold(self, setup_services) -> None:
        """Direct merge: cosine similarity >= 0.84 merges without shared entities."""
        repo, mock_extractor = setup_services
        # No entities returned
        mock_extractor.extract_entities.return_value = []

        # Vector 1 (seed) and Vector 2 with cosine similarity = 0.90
        base_v = [1.0] + [0.0] * 767
        merge_v = make_vector_with_target_cosine(base_v, 0.90)

        embedder = MockEmbedder({"ข่าว A": base_v, "ข่าว B": merge_v})
        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
        )

        art1 = ArticleRecord(url="https://news/1", title="ข่าว A", source="Thairath", summary="สรุป A")
        art2 = ArticleRecord(url="https://news/2", title="ข่าว B", source="ThaiPBS", summary="สรุป B")

        story1, is_new1 = service.assign_article(art1)
        assert is_new1 is True

        story2, is_new2 = service.assign_article(art2)
        assert is_new2 is False
        assert story2.story_id == story1.story_id
        assert story2.article_count == 2
        assert set(story2.outlets) == {"Thairath", "ThaiPBS"}

    def test_borderline_merge_with_shared_entities(self, setup_services) -> None:
        """Borderline merge: 0.70 <= sim < 0.84 merges when shared entities confirmed."""
        repo, mock_extractor = setup_services
        # Both articles share entity "เชียงราย"
        mock_extractor.extract_entities.side_effect = lambda t: ["เชียงราย"] if "ข่าว" in t else []

        base_v = [1.0] + [0.0] * 767
        # Borderline similarity = 0.75
        borderline_v = make_vector_with_target_cosine(base_v, 0.75)

        embedder = MockEmbedder({"ข่าว ก": base_v, "ข่าว ข": borderline_v})
        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
        )

        art1 = ArticleRecord(url="https://news/1", title="ข่าว ก", source="Thairath", summary="สรุป ก")
        art2 = ArticleRecord(url="https://news/2", title="ข่าว ข", source="ThaiPBS", summary="สรุป ข")

        story1, is_new1 = service.assign_article(art1)
        assert is_new1 is True

        story2, is_new2 = service.assign_article(art2)
        # Should merge because similarity (0.75) is in [0.70, 0.84) AND entities match
        assert is_new2 is False
        assert story2.story_id == story1.story_id
        assert story2.article_count == 2

    def test_borderline_reject_without_shared_entities(self, setup_services) -> None:
        """Borderline reject: 0.70 <= sim < 0.84 DOES NOT merge without shared entities."""
        repo, mock_extractor = setup_services
        # Art 1 has "เชียงใหม่", Art 2 has "ภูเก็ต" (no overlap)
        def get_entities(text: str) -> list[str]:
            if "ข่าว ก" in text:
                return ["เชียงใหม่"]
            return ["ภูเก็ต"]

        mock_extractor.extract_entities.side_effect = get_entities

        base_v = [1.0] + [0.0] * 767
        borderline_v = make_vector_with_target_cosine(base_v, 0.75)

        embedder = MockEmbedder({"ข่าว ก": base_v, "ข่าว ข": borderline_v})
        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
        )

        art1 = ArticleRecord(url="https://news/1", title="ข่าว ก", source="Thairath", summary="สรุป ก")
        art2 = ArticleRecord(url="https://news/2", title="ข่าว ข", source="ThaiPBS", summary="สรุป ข")

        story1, is_new1 = service.assign_article(art1)
        assert is_new1 is True

        story2, is_new2 = service.assign_article(art2)
        # Should NOT merge because entities do not match
        assert is_new2 is True
        assert story2.story_id != story1.story_id
        assert repo.count_stories() == 2

    def test_low_similarity_creates_new_story_even_with_entities(self, setup_services) -> None:
        """Below low threshold: sim < 0.70 creates new story (no forced merge) even with entities."""
        repo, mock_extractor = setup_services
        # Both have "ประเทศไทย"
        mock_extractor.extract_entities.return_value = ["ประเทศไทย"]

        base_v = [1.0] + [0.0] * 767
        low_sim_v = make_vector_with_target_cosine(base_v, 0.60)

        embedder = MockEmbedder({"ข่าว 1": base_v, "ข่าว 2": low_sim_v})
        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
        )

        art1 = ArticleRecord(url="https://news/1", title="ข่าว 1", source="Thairath")
        art2 = ArticleRecord(url="https://news/2", title="ข่าว 2", source="ThaiPBS")

        story1, _is_new1 = service.assign_article(art1)
        story2, is_new2 = service.assign_article(art2)

        assert is_new2 is True
        assert story2.story_id != story1.story_id

    def test_strictly_zero_token_jaccard(self, setup_services) -> None:
        """Verify that high lexical token overlap does NOT cause merge when vector sim < 0.70."""
        repo, mock_extractor = setup_services
        mock_extractor.extract_entities.return_value = []

        # Same words, but vectors generated with low semantic similarity
        base_v = [1.0] + [0.0] * 767
        low_v = make_vector_with_target_cosine(base_v, 0.50)

        embedder = MockEmbedder({
            "ราคาน้ำมัน วันนี้ ปรับตัว ลดลง": base_v,
            "ราคาน้ำมัน วันนี้ ไม่ปรับตัว ขึ้นลง": low_v,
        })
        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
        )

        art1 = ArticleRecord(
            url="https://news/1",
            title="ราคาน้ำมัน วันนี้ ปรับตัว ลดลง",
            source="Thairath",
        )
        art2 = ArticleRecord(
            url="https://news/2",
            title="ราคาน้ำมัน วันนี้ ไม่ปรับตัว ขึ้นลง",
            source="ThaiPBS",
        )

        story1, _is_new1 = service.assign_article(art1)
        story2, is_new2 = service.assign_article(art2)

        assert is_new2 is True
        assert story2.story_id != story1.story_id


# ── 3. Multi-Day Candidate Window & Persistence Tests ─────────────

class TestMultiDayCandidateWindowPersistence:
    """Tests for multi-day non-capping story persistence and candidate window."""

    def test_articles_spread_over_5_days_merge_into_single_story(self, tmp_path: Path) -> None:
        """
        R1 Acceptance Criteria:
        Articles about one event spread over >= 5 days (each within candidate window
        of previous) end up in a single story.
        """
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = ["น้ำท่วมน่าน", "แม่น้ำยม"]

        base_v = [1.0] + [0.0] * 767
        # High similarity for all updates of this evolving flood crisis
        v_map = {f"ข่าวน้ำท่วมน่าน วันที่ {d}": base_v for d in range(1, 7)}
        embedder = MockEmbedder(v_map)

        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
            candidate_window_hours=72.0,
        )

        base_time = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        stories_assigned: list[StoryRecord] = []

        # 6 articles spread over 5 days (one article every 24 hours)
        for day in range(6):
            art_time = base_time + timedelta(days=day)
            art = ArticleRecord(
                url=f"https://news/flood/day{day + 1}",
                title=f"ข่าวน้ำท่วมน่าน วันที่ {day + 1}",
                source=f"Source_{day}",
                fetched_at=art_time.isoformat(),
                category="environment",
            )
            story, is_new = service.assign_article(art)
            if day == 0:
                assert is_new is True
            else:
                assert is_new is False
            stories_assigned.append(story)

        # All 6 articles MUST belong to the exact same story cluster
        first_story_id = stories_assigned[0].story_id
        for s in stories_assigned:
            assert s.story_id == first_story_id

        # Final story in repo verification
        final_story = repo.get_story(first_story_id)
        assert final_story is not None
        assert final_story.article_count == 6
        assert len(final_story.article_urls) == 6
        assert final_story.first_article_at == base_time
        assert final_story.last_article_at == base_time + timedelta(days=5)
        # Span across days is >= 5 days
        delta = final_story.last_article_at - final_story.first_article_at
        assert delta.total_seconds() >= 5 * 86400

    def test_article_beyond_candidate_window_creates_new_story(self, tmp_path: Path) -> None:
        """An article arriving > 72h after story's last update starts a new story."""
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = ["กระทรวงการคลัง"]

        base_v = [1.0] + [0.0] * 767
        embedder = MockEmbedder({"ข่าว 1": base_v, "ข่าว 2": base_v})

        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            candidate_window_hours=72.0,
        )

        t1 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        # t2 is 96 hours later (> 72h candidate window)
        t2 = t1 + timedelta(hours=96)

        art1 = ArticleRecord(url="https://news/1", title="ข่าว 1", source="A", fetched_at=t1.isoformat())
        art2 = ArticleRecord(url="https://news/2", title="ข่าว 2", source="B", fetched_at=t2.isoformat())

        story1, is_new1 = service.assign_article(art1)
        story2, is_new2 = service.assign_article(art2)

        assert is_new1 is True
        assert is_new2 is True
        assert story1.story_id != story2.story_id


# ── 4. Cross-Category & Soft Category Tests ───────────────────────

class TestCrossCategoryAndSoftCategory:
    """Tests confirming category is a soft signal and never blocks cross-category merge."""

    def test_cross_category_merge_same_event(self, tmp_path: Path) -> None:
        """
        R1 Acceptance Criteria:
        Two articles about same event with different category values are merged.
        """
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = ["รัฐบาล", "เชียงราย"]

        base_v = [1.0] + [0.0] * 767
        embedder = MockEmbedder({"ข่าวการเมือง รัฐบาล": base_v, "ข่าวน้ำท่วม เชียงราย": base_v})

        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
        )

        art_politics = ArticleRecord(
            url="https://news/pol",
            title="ข่าวการเมือง รัฐบาล",
            category="politics",
            source="PoliticsDaily",
        )
        art_environment = ArticleRecord(
            url="https://news/env",
            title="ข่าวน้ำท่วม เชียงราย",
            category="environment",
            source="GreenNews",
        )

        story1, is_new1 = service.assign_article(art_politics)
        story2, is_new2 = service.assign_article(art_environment)

        assert is_new1 is True
        assert is_new2 is False
        assert story2.story_id == story1.story_id
        assert story2.article_count == 2

    def test_unrelated_articles_same_category_do_not_merge(self, tmp_path: Path) -> None:
        """
        R1 Acceptance Criteria:
        Two unrelated articles in same category with similar wording are not merged.
        """
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = []

        base_v = [1.0] + [0.0] * 767
        low_v = make_vector_with_target_cosine(base_v, 0.45)

        embedder = MockEmbedder({
            "เพื่อไทยเคาะประชุมพรรค": base_v,
            "ก้าวไกลเตรียมแถลงข่าว": low_v,
        })
        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            high_threshold=0.84,
            low_threshold=0.70,
        )

        art1 = ArticleRecord(
            url="https://news/pol1",
            title="เพื่อไทยเคาะประชุมพรรค",
            category="politics",
            source="NewsA",
        )
        art2 = ArticleRecord(
            url="https://news/pol2",
            title="ก้าวไกลเตรียมแถลงข่าว",
            category="politics",
            source="NewsB",
        )

        story1, is_new1 = service.assign_article(art1)
        story2, is_new2 = service.assign_article(art2)

        assert is_new1 is True
        assert is_new2 is True
        assert story1.story_id != story2.story_id

    def test_soft_category_ranking_preference(self, tmp_path: Path) -> None:
        """Soft category breaks ties when cosine similarity is equal."""
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = []

        now = datetime.now(timezone.utc)
        # Create Candidate 1 (economy, sim = 0.88)
        c1 = StoryRecord(
            story_id="story_eco",
            title="ข่าวเศรษฐกิจ",
            category="economy",
            centroid=[1.0] + [0.0] * 767,
            updated_at=now,
        )
        # Create Candidate 2 (politics, sim = 0.88)
        c2 = StoryRecord(
            story_id="story_pol",
            title="ข่าวการเมือง",
            category="politics",
            centroid=[1.0] + [0.0] * 767,
            updated_at=now,
        )
        repo.save_story(c1)
        repo.save_story(c2)

        base_v = [1.0] + [0.0] * 767
        embedder = MockEmbedder({"ข่าวนโยบายเศรษฐกิจรัฐบาล": base_v})

        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
        )

        incoming = ArticleRecord(
            url="https://news/incoming",
            title="ข่าวนโยบายเศรษฐกิจรัฐบาล",
            category="economy",  # matches story_eco
            source="BizTimes",
        )
        story, is_new = service.assign_article(incoming)
        assert is_new is False
        assert story.story_id == "story_eco"


# ── 5. Centroid EMA Mathematics Tests ─────────────────────────────

class TestCentroidEMAMathematics:
    """Tests for exact numerical updates of story centroid via EMA."""

    def test_centroid_ema_numerical_update(self, tmp_path: Path) -> None:
        """
        R1 Acceptance Criteria:
        Centroid EMA numerical update:
        Centroid_new = alpha * Centroid_old + (1 - alpha) * Embedding_new (alpha=0.85).
        """
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = []

        v1 = [1.0, 0.0] + [0.0] * 766
        v2 = [0.88, 0.47497] + [0.0] * 766  # Unit vector with high cosine ~ 0.88

        embedder = MockEmbedder({"ข่าวตั้งต้น": v1, "ข่าวอัปเดต": v2})
        alpha = 0.85
        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
            ema_alpha=alpha,
        )

        art1 = ArticleRecord(url="https://news/1", title="ข่าวตั้งต้น", source="A")
        art2 = ArticleRecord(url="https://news/2", title="ข่าวอัปเดต", source="B")

        story1, is_new1 = service.assign_article(art1)
        assert is_new1 is True
        assert story1.centroid is not None
        assert story1.centroid[0] == pytest.approx(1.0, 1e-5)
        assert story1.centroid[1] == pytest.approx(0.0, 1e-5)

        story2, is_new2 = service.assign_article(art2)
        assert is_new2 is False

        # Verify numerical EMA formula: 0.85 * old + 0.15 * new
        expected_dim0 = alpha * 1.0 + (1.0 - alpha) * 0.88
        expected_dim1 = alpha * 0.0 + (1.0 - alpha) * 0.47497

        assert story2.centroid is not None
        assert story2.centroid[0] == pytest.approx(expected_dim0, rel=1e-4)
        assert story2.centroid[1] == pytest.approx(expected_dim1, rel=1e-4)


# ── 6. Story Lifecycle & Dormant Reactivation Tests ───────────────

class TestStoryLifecycleAndDormantReactivation:
    """Tests for 72h active/dormant status and automatic reactivation."""

    def test_dormant_story_reactivates_under_same_story_id(self, tmp_path: Path) -> None:
        """
        R1 Acceptance Criteria:
        Dormant stories reactivate under same story id upon receiving new articles.
        """
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = ["คดีดัง"]

        base_v = [1.0] + [0.0] * 767
        embedder = MockEmbedder({"ข่าวคดีดัง เริ่มต้น": base_v, "ข่าวคดีดัง ความคืบหน้า": base_v})

        service = StoryService(
            story_repo=repo,
            embedder=embedder,
            entity_extractor=mock_extractor,
        )

        t_initial = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        art1 = ArticleRecord(
            url="https://news/trial/1",
            title="ข่าวคดีดัง เริ่มต้น",
            source="LawNews",
            fetched_at=t_initial.isoformat(),
        )
        story1, _ = service.assign_article(art1)
        assert story1.status == "active"

        # Advance time by 80 hours -> story becomes dormant
        t_after_80h = t_initial + timedelta(hours=80)
        story1.refresh_status(current_time=t_after_80h, inactivity_threshold_hours=72.0)
        assert story1.status == "dormant"
        repo.save_story(story1)

        # Confirm saved story is dormant
        saved_dormant = repo.get_story(story1.story_id)
        assert saved_dormant is not None
        assert saved_dormant.status == "dormant"

        # Now breaking news arrives within candidate window of the story's reactivation
        t_break = t_initial + timedelta(hours=20)  # within 72h window
        art2 = ArticleRecord(
            url="https://news/trial/2",
            title="ข่าวคดีดัง ความคืบหน้า",
            source="ThaiPBS",
            fetched_at=t_break.isoformat(),
        )
        reactivated_story, is_new = service.assign_article(art2)

        # Must merge and reactivate to 'active' under the same story id
        assert is_new is False
        assert reactivated_story.story_id == story1.story_id
        assert reactivated_story.status == "active"
        assert reactivated_story.article_count == 2

    def test_refresh_dormant_stories_batch(self, tmp_path: Path) -> None:
        """Batch refresh marks stories older than 72h as dormant."""
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        now = datetime.now(timezone.utc)

        # Active recent story (10h old)
        s_recent = StoryRecord(
            story_id="recent_story",
            title="Recent",
            status="active",
            updated_at=now - timedelta(hours=10),
        )
        # Active old story (80h old)
        s_old = StoryRecord(
            story_id="old_story",
            title="Old",
            status="active",
            updated_at=now - timedelta(hours=80),
        )
        repo.save_stories_batch([s_recent, s_old])

        service = StoryService(story_repo=repo)
        dormant_count = service.refresh_dormant_stories(current_time=now, inactivity_threshold_hours=72.0)

        assert dormant_count == 1
        assert repo.get_story("recent_story").status == "active"
        assert repo.get_story("old_story").status == "dormant"


# ── 7. Back-fill Stories Job Tests ─────────────────────────────────

class TestBackfillStoriesJob:
    """Tests for backend/backfill_stories_job.py migration utility."""

    def test_backfill_job_assigns_every_article_a_story_id(self, tmp_path: Path) -> None:
        """
        R1 Acceptance Criteria:
        Back-fill job runs and assigns every article in news repo a story id.
        """
        news_file = tmp_path / "news_data.json"
        story_file = tmp_path / "stories_data.json"

        news_repo = FileNewsRepository(data_file=news_file)
        story_repo = FileStoryRepository(data_file=story_file)

        now = datetime.now(timezone.utc)
        # 6 articles without story_id
        raw_articles = [
            {
                "url": f"https://sample.com/news/{i}",
                "title": f"หัวข้อข่าวทดสอบที่ {i}",
                "source": "ThaiPBS",
                "summary": f"เนื้อหาข่าวที่ {i}",
                "fetched_at": (now + timedelta(hours=i)).isoformat(),
                "category": "society",
                "story_id": None,
            }
            for i in range(1, 7)
        ]
        news_repo.save_news(raw_articles)

        # Mock embedder and entity extractor
        [1.0] + [0.0] * 767
        mock_embedder = MockEmbedder()
        mock_extractor = MagicMock(spec=EntityExtractor)
        mock_extractor.extract_entities.return_value = []

        service = StoryService(
            story_repo=story_repo,
            embedder=mock_embedder,
            entity_extractor=mock_extractor,
        )

        # Run backfill
        logs: list[str] = []
        stats = run_backfill(
            news_repo=news_repo,
            story_service=service,
            log_fn=logs.append,
        )

        assert stats["total_articles"] == 6
        assert stats["processed"] == 6

        # Verify news repo articles all have story_id
        updated_articles = news_repo.load_news()
        for art in updated_articles:
            assert art.get("story_id") is not None
            assert len(str(art["story_id"])) > 0
            assert art["story_id"].startswith("story_")

        # Verify stories were created in story repo
        assert story_repo.count_stories() > 0

    def test_backfill_job_empty_news(self, tmp_path: Path) -> None:
        """Verify backfill handles empty repository without failure."""
        news_file = tmp_path / "empty_news.json"
        story_file = tmp_path / "empty_stories.json"
        news_repo = FileNewsRepository(data_file=news_file)
        story_repo = FileStoryRepository(data_file=story_file)

        service = StoryService(story_repo=story_repo, embedder=MockEmbedder())
        stats = run_backfill(news_repo=news_repo, story_service=service, log_fn=lambda _: None)
        assert stats["total_articles"] == 0
        assert stats["processed"] == 0


# ── 8. Idempotency & Edge Cases Tests ──────────────────────────────

class TestStoryServiceIdempotencyAndEdgeCases:
    """Tests for edge cases, missing attributes, and duplicate URLs."""

    def test_assign_article_idempotent(self, tmp_path: Path) -> None:
        """Re-assigning the same article URL returns the existing story without duplicates."""
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        service = StoryService(story_repo=repo, embedder=MockEmbedder())

        art = ArticleRecord(url="https://news/same-url", title="ข่าวด่วน", source="A")
        s1, is_new1 = service.assign_article(art)
        assert is_new1 is True
        assert s1.article_count == 1

        # Re-assign same URL
        s2, is_new2 = service.assign_article(art)
        assert is_new2 is False
        assert s2.story_id == s1.story_id
        assert s2.article_count == 1
        assert repo.count_stories() == 1

    def test_assign_article_missing_metadata(self, tmp_path: Path) -> None:
        """Gracefully handle articles with empty title, summary, or missing category."""
        repo = FileStoryRepository(data_file=tmp_path / "stories.json")
        service = StoryService(story_repo=repo, embedder=MockEmbedder())

        art = ArticleRecord(url="https://news/empty", title="", summary="", source="")
        story, is_new = service.assign_article(art)
        assert is_new is True
        assert story.story_id.startswith("story_")

    def test_cosine_similarity_edge_cases(self) -> None:
        """Verify vector cosine similarity with zero vectors and unit vectors."""
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
