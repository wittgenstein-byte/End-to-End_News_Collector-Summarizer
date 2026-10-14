"""
test_dynamic_lifecycle_clock.py
─────────────────────────────────────────────────────────────────
Verifies precise dynamic lifecycle evaluation and clock injection:
1. Authoritative authority: last_article_at (or first_article_at)
2. Presentation/summary editing updates updated_at, but does NOT revive dormant stories
3. Boundary transitions at 71.9h (active) and 72.1h (dormant)
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.schemas.story_schema import StoryRecord


def test_lifecycle_clock_boundary_transitions() -> None:
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Active story: article arrived 71.9 hours ago (< 72h)
    story_active = StoryRecord(
        title="ข่าวน้ำท่วมฉับพลัน",
        category="environment",
        first_article_at=now - timedelta(hours=80.0),
        last_article_at=now - timedelta(hours=71.9),
        created_at=now - timedelta(hours=80.0),
        updated_at=now - timedelta(hours=71.9),
    )
    assert story_active.is_active_dynamic(now=now, inactivity_threshold_hours=72.0) is True
    assert story_active.refresh_status(current_time=now, inactivity_threshold_hours=72.0) == "active"

    # 2. Dormant story: article arrived 72.1 hours ago (> 72h)
    story_dormant = StoryRecord(
        title="ข่าวน้ำท่วมคลี่คลาย",
        category="environment",
        first_article_at=now - timedelta(hours=90.0),
        last_article_at=now - timedelta(hours=72.1),
        created_at=now - timedelta(hours=90.0),
        updated_at=now - timedelta(hours=72.1),
    )
    assert story_dormant.is_active_dynamic(now=now, inactivity_threshold_hours=72.0) is False
    assert story_dormant.refresh_status(current_time=now, inactivity_threshold_hours=72.0) == "dormant"


def test_presentation_edit_does_not_revive_dormant_story() -> None:
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
    old_article_time = now - timedelta(days=5)  # 120 hours ago

    story = StoryRecord(
        title="คดีเก่าที่ปิดแล้ว",
        category="politics",
        status="dormant",
        first_article_at=old_article_time,
        last_article_at=old_article_time,
        created_at=old_article_time,
        updated_at=old_article_time,
    )
    assert story.is_active_dynamic(now=now) is False

    # Simulate editor modifying headline / LLM enriching presentation right NOW
    story.headline = "สรุปพาดหัวใหม่ที่สังเคราะห์ในปัจจุบัน"
    story.updated_at = now  # updated_at changed to current time!
    story.enriched_at = now

    # Invariant: Despite updated_at being current, activity authority remains last_article_at!
    assert story.is_active_dynamic(now=now) is False
    assert story.refresh_status(current_time=now) == "dormant"
