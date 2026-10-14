"""
test_event_vs_macro_matching.py
─────────────────────────────────────────────────────────────────
Verifies staged matching pipeline invariant:
1. High similarity (>= 0.85) merges into the SAME Event (StoryRecord).
   Does NOT falsely split them into separate events connected by a macro link.
2. Moderate similarity (0.55 <= sim < 0.74) with shared LOC/ORG entities
   creates separate Events connected to the SAME Macro-Event storyline.
3. Unrelated events create separate Macro-Events.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from backend.repo.macro_event_repo import FileMacroEventRepository
from backend.repo.story_repo import FileStoryRepository
from backend.schemas.news_schema import ArticleRecord
from backend.services.macro_event_service import MacroEventService
from backend.services.story_service import StoryService


class DummyEmbedder:
    """Mock embedder returning controlled synthetic dense vectors."""
    def __init__(self, vector_map: dict[str, list[float]]) -> None:
        self.vector_map = vector_map

    def encode_article(self, title: str, summary: str = "") -> list[float]:
        for k, v in self.vector_map.items():
            if k in title:
                return v
        # Default random normalized unit vector
        rng = np.random.default_rng(42)
        v = rng.standard_normal(768).astype(np.float32)
        v /= float(np.linalg.norm(v))
        return [float(x) for x in v]


class DummyEntityExtractor:
    def __init__(self, entity_map: dict[str, list[str]]) -> None:
        self.entity_map = entity_map

    def extract_entities(self, text: str) -> list[str]:
        for k, v in self.entity_map.items():
            if k in text:
                return list(v)
        return []


def test_staged_matching_pipeline_invariant() -> None:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        stories_file = tmp_path / "stories_data.json"
        macros_file = tmp_path / "macro_events_data.json"

        story_repo = FileStoryRepository(data_file=stories_file)
        macro_repo = FileMacroEventRepository(data_file=macros_file)
        macro_service = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

        # Create three synthetic vectors:
        # Base vector v1
        v1 = np.zeros(768, dtype=np.float32)
        v1[0] = 1.0

        # v2 is very close to v1 (cos_sim ~ 0.90 >= 0.85 direct merge threshold)
        v2 = np.zeros(768, dtype=np.float32)
        v2[0] = 0.90
        v2[1] = np.sqrt(1.0 - 0.90**2)

        # v3 is moderately close to v1 (cos_sim ~ 0.65, in [0.55, 0.74) macro band)
        v3 = np.zeros(768, dtype=np.float32)
        v3[0] = 0.65
        v3[2] = np.sqrt(1.0 - 0.65**2)

        # v4 is orthogonal (cos_sim ~ 0.0)
        v4 = np.zeros(768, dtype=np.float32)
        v4[10] = 1.0

        embedder = DummyEmbedder({
            "เตือนน้ำท่วมน่าน A": [float(x) for x in v1],
            "เตือนน้ำท่วมน่าน B": [float(x) for x in v2],
            "งบเยียวยาน้ำท่วมน่าน": [float(x) for x in v3],
            "ผลฟุตบอลพรีเมียร์ลีก": [float(x) for x in v4],
        })

        entity_extractor = DummyEntityExtractor({
            "เตือนน้ำท่วมน่าน A": ["จ.น่าน", "อ.เวียงสา"],
            "เตือนน้ำท่วมน่าน B": ["จ.น่าน", "อ.เวียงสา"],
            "งบเยียวยาน้ำท่วมน่าน": ["จ.น่าน", "กระทรวงการคลัง"],
            "ผลฟุตบอลพรีเมียร์ลีก": ["ลิเวอร์พูล"],
        })

        story_service = StoryService(
            story_repo=story_repo,
            embedder=embedder,
            entity_extractor=entity_extractor,
            macro_service=macro_service,
            high_threshold=0.85,
            low_threshold=0.74,
        )

        # 1. Ingest Article 1: Flood Warning A
        art1 = ArticleRecord(
            url="https://example.com/art1",
            title="เตือนน้ำท่วมน่าน A ระดับน้ำเพิ่มสูง",
            source="ThaiPBS",
            category="environment",
            fetched_at="2026-08-23 10:00:00",
        )
        story1, is_new1 = story_service.assign_article(art1)
        assert is_new1 is True
        assert story1.macro_event_id is not None
        initial_macro_id = story1.macro_event_id

        # 2. Ingest Article 2: Flood Warning B (cos_sim ~ 0.90 >= 0.85)
        # INVARIANT: Must merge into the SAME Event (story1), NOT create a new event!
        art2 = ArticleRecord(
            url="https://example.com/art2",
            title="เตือนน้ำท่วมน่าน B คาดระดับน้ำขึ้นสูงสุดคืนนี้",
            source="Daily News",
            category="environment",
            fetched_at="2026-08-23 12:00:00",
        )
        story2, is_new2 = story_service.assign_article(art2)
        assert is_new2 is False
        assert story2.story_id == story1.story_id  # MERGED INTO SAME EVENT!
        assert story2.macro_event_id == initial_macro_id
        assert story_repo.count_stories() == 1

        # 3. Ingest Article 3: Relief Budget (cos_sim ~ 0.65 in [0.55, 0.74), shares entity 'จ.น่าน')
        # INVARIANT: Must create a NEW Event, but link to the SAME Macro-Event storyline!
        art3 = ArticleRecord(
            url="https://example.com/art3",
            title="งบเยียวยาน้ำท่วมน่าน ครม.เคาะเยียวยาเร่งด่วน",
            source="Khaosod",
            category="politics",
            fetched_at="2026-08-25 14:00:00",
        )
        story3, is_new3 = story_service.assign_article(art3)
        assert is_new3 is True
        assert story3.story_id != story1.story_id  # SEPARATE EVENT RECORD!
        assert story3.macro_event_id == initial_macro_id  # LINKED TO SAME MACRO STORYLINE!
        assert story_repo.count_stories() == 2
        assert macro_repo.count_macro_events() == 1

        # Check macro relations
        macro = macro_repo.get_macro_event(initial_macro_id)
        assert macro is not None
        assert len(macro.child_event_ids) == 2
        assert len(macro.relations) == 1
        rel = macro.relations[0]
        assert rel.source_event_id == story3.story_id
        assert rel.target_event_id == story1.story_id
        assert rel.relation_type in ("updates", "precedes")

        # 4. Ingest Article 4: Unrelated Sports News (orthogonal)
        # INVARIANT: Must create a separate Event AND a separate Macro-Event!
        art4 = ArticleRecord(
            url="https://example.com/art4",
            title="ผลฟุตบอลพรีเมียร์ลีก สรุปตารางคะแนน",
            source="Thairath",
            category="sports",
            fetched_at="2026-08-25 15:00:00",
        )
        story4, is_new4 = story_service.assign_article(art4)
        assert is_new4 is True
        assert story4.story_id != story1.story_id
        assert story4.story_id != story3.story_id
        assert story4.macro_event_id != initial_macro_id  # DIFFERENT MACRO STORYLINE!
        assert macro_repo.count_macro_events() == 2
