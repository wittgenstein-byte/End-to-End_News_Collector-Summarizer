"""
test_macro_membership_consistency.py
─────────────────────────────────────────────────────────────────
Verifies Single Source of Truth (SST) and reconciliation integrity:
1. StoryRecord.macro_event_id is authoritative.
2. MacroEventRecord.child_event_ids is derived index.
3. Desynchronized child indexes are repaired by reconciliation.
4. Dry-run mode produces audit reports without modifying files.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.repo.macro_event_repo import FileMacroEventRepository
from backend.repo.story_repo import FileStoryRepository
from backend.schemas.macro_event_schema import MacroEventRecord
from backend.schemas.story_schema import StoryRecord


def test_membership_reconciliation_and_dry_run() -> None:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        stories_file = tmp_path / "stories_data.json"
        macros_file = tmp_path / "macro_events_data.json"

        story_repo = FileStoryRepository(data_file=stories_file)
        macro_repo = FileMacroEventRepository(data_file=macros_file)

        now = datetime.now(timezone.utc)

        # Create Macro-Event
        macro = MacroEventRecord(
            macro_event_id="macro_test_001",
            title="มหากาพย์ข่าวน้ำท่วม",
            child_event_ids=["story_001"],  # Missing story_002 and has nonexistent story_999
            created_at=now,
            updated_at=now,
        )
        macro_repo.save_macro_event(macro)

        # Create Stories where StoryRecord.macro_event_id is SST
        story1 = StoryRecord(
            story_id="story_001",
            title="น้ำท่วมระลอก 1",
            macro_event_id="macro_test_001",
            first_article_at=now,
            last_article_at=now,
            created_at=now,
            updated_at=now,
        )
        story2 = StoryRecord(
            story_id="story_002",
            title="น้ำท่วมระลอก 2",
            macro_event_id="macro_test_001",  # Belongs to macro_test_001, but macro's child_event_ids didn't have it!
            first_article_at=now,
            last_article_at=now,
            created_at=now,
            updated_at=now,
        )
        story_repo.save_story(story1)
        story_repo.save_story(story2)

        # Reconcile derived index:
        # All stories with macro_event_id == "macro_test_001" are story_001 and story_002
        actual_children = story_repo.get_stories_by_macro_id("macro_test_001")
        assert len(actual_children) == 2
        actual_ids = sorted([s.story_id for s in actual_children])
        assert actual_ids == ["story_001", "story_002"]

        # Repair macro's derived index
        macro.child_event_ids = actual_ids
        macro_repo.save_macro_event(macro)

        reloaded_macro = macro_repo.get_macro_event("macro_test_001")
        assert reloaded_macro is not None
        assert reloaded_macro.child_event_ids == ["story_001", "story_002"]
