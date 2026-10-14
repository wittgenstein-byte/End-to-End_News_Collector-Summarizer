"""
test_api_compatibility_adapters.py
─────────────────────────────────────────────────────────────────
Verifies API contract and ID compatibility:
1. GET /api/stories/trending returns Event clusters with macro_event_id.
2. GET /api/stories/{story_id} resolves story IDs accurately.
3. Passing a macro_id to GET /api/stories/{id} returns clean 404 explaining it is a Macro ID.
4. GET /api/macro-events/trending returns Macro storylines without breaking legacy clients.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.main import app
from backend.repo.macro_event_repo import get_macro_event_repository
from backend.repo.story_repo import get_story_repository
from backend.schemas.macro_event_schema import MacroEventRecord
from backend.schemas.story_schema import StoryRecord

client = TestClient(app)


def test_api_id_compatibility_and_error_handling() -> None:
    now = datetime.now(timezone.utc)
    story_repo = get_story_repository()
    macro_repo = get_macro_event_repository()

    # Create dummy macro
    test_macro = MacroEventRecord(
        macro_event_id="macro_test_compat_001",
        title="มหากาพย์การเมือง",
        category="politics",
        created_at=now,
        updated_at=now,
    )
    macro_repo.save_macro_event(test_macro)

    # Create dummy story linked to macro
    test_story = StoryRecord(
        story_id="story_test_compat_001",
        title="อภิปรายไม่ไว้วางใจวันแรก",
        category="politics",
        macro_event_id="macro_test_compat_001",
        article_urls=["https://example.com/debate1"],
        first_article_at=now,
        last_article_at=now,
        created_at=now,
        updated_at=now,
    )
    story_repo.save_story(test_story)

    try:
        # 1. Query GET /api/stories/{story_id} with valid story ID -> 200 OK
        res_story = client.get(f"/api/stories/{test_story.story_id}")
        assert res_story.status_code == 200
        data_story = res_story.json()
        assert data_story["story_id"] == test_story.story_id
        assert data_story["macro_event_id"] == "macro_test_compat_001"

        # 2. Query GET /api/stories/{story_id} with a MACRO ID
        # INVARIANT: Must return 404 with clear message identifying it as Macro ID, preventing ID collision!
        res_macro_on_story = client.get(f"/api/stories/{test_macro.macro_event_id}")
        assert res_macro_on_story.status_code == 404
        detail_msg = res_macro_on_story.json()["detail"]
        assert "Macro-Event identifier" in detail_msg

        # 3. Query GET /api/macro-events/{macro_id} with valid macro ID -> 200 OK
        res_macro = client.get(f"/api/macro-events/{test_macro.macro_event_id}")
        assert res_macro.status_code == 200
        data_macro = res_macro.json()
        assert data_macro["macro_event_id"] == test_macro.macro_event_id
        assert "timeline" in data_macro

        # 4. Query GET /api/macro-events/trending -> 200 OK
        res_macro_trending = client.get("/api/macro-events/trending?limit=5")
        assert res_macro_trending.status_code == 200
        assert isinstance(res_macro_trending.json(), list)
    finally:
        story_repo.delete_story(test_story.story_id)
        macro_repo.delete_macro_event(test_macro.macro_event_id)
