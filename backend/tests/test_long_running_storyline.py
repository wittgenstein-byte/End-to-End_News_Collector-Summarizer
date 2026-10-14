"""
test_long_running_storyline.py
─────────────────────────────────────────────────────────────────
Verifies that storylines exceeding standard candidate windows (>14 days)
remain persistent across multi-week resurgence using Named-Crisis Anchors:
1. Nan flood event starts on Day 1.
2. Resurgence / secondary wave arrives on Day 22 (> 14 days later).
3. Anchored candidate search links back to original Macro-Event,
   preventing duplicate storyline creation.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from backend.repo.macro_event_repo import FileMacroEventRepository
from backend.repo.story_repo import FileStoryRepository
from backend.schemas.story_schema import StoryRecord
from backend.services.macro_event_service import MacroEventService


def test_long_running_crisis_anchor_relinking() -> None:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        stories_file = tmp_path / "stories_data.json"
        macros_file = tmp_path / "macro_events_data.json"

        story_repo = FileStoryRepository(data_file=stories_file)
        macro_repo = FileMacroEventRepository(data_file=macros_file)
        macro_service = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

        day1 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        day22 = day1 + timedelta(days=21)  # 21 days later!

        v = np.zeros(768, dtype=np.float32)
        v[0] = 1.0

        # Day 1: First crisis sub-event
        story1 = StoryRecord(
            title="วิกฤตน้ำท่วมน่าน มวลน้ำหลากทะลักท่วมบ้านเรือน",
            category="environment",
            first_article_at=day1,
            last_article_at=day1,
            created_at=day1,
            updated_at=day1,
            centroid=[float(x) for x in v],
            entities=["จ.น่าน", "อ.เวียงสา"],
        )
        story_repo.save_story(story1)

        macro1, is_new1 = macro_service.assign_event(story1)
        assert is_new1 is True
        assert macro1.named_crisis_anchor == "น้ำท่วมน่าน"
        original_macro_id = macro1.macro_event_id

        # Mark macro dormant after 2 weeks
        macro1.status = "dormant"
        macro_repo.save_macro_event(macro1)

        # Day 22: Resurgence arrives (> 14 days standard window)
        # Vector is moderately similar (cos_sim ~ 0.60)
        v2 = np.zeros(768, dtype=np.float32)
        v2[0] = 0.60
        v2[1] = np.sqrt(1.0 - 0.60**2)

        story2 = StoryRecord(
            title="น้ำท่วมน่าน ระลอกสองมวลน้ำใหม่เข้าซ้ำพื้นที่เดิม",
            category="environment",
            first_article_at=day22,
            last_article_at=day22,
            created_at=day22,
            updated_at=day22,
            centroid=[float(x) for x in v2],
            entities=["จ.น่าน", "อ.เวียงสา"],
        )
        story_repo.save_story(story2)

        macro2, is_new2 = macro_service.assign_event(story2)

        # INVARIANT: Must link to original Macro-Event, NOT create a duplicate!
        assert is_new2 is False
        assert macro2.macro_event_id == original_macro_id
        assert macro_repo.count_macro_events() == 1
        assert story2.macro_event_id == original_macro_id
        assert original_macro_id in macro2.child_event_ids or len(macro2.child_event_ids) == 2
        assert macro2.status == "active"  # Reactivated upon resurgence!
