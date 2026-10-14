"""
test_crisis_exemption_precision.py
─────────────────────────────────────────────────────────────────
Verifies context-aware severe disaster whitelist vs routine news:
1. Casual routine daily weather forecasts mentioning 'กรมอุตุนิยมวิทยา' receive routine penalty.
2. Official disaster warnings with 'ประกาศเตือนภัย' / 'น้ำท่วมฉับพลัน' are exempt from routine penalty.
3. Exemption reason is explainably logged in TrendingScoreBreakdown.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.schemas.story_schema import StoryRecord
from backend.services.trending_service import TrendingService


def test_routine_weather_forecast_receives_penalty() -> None:
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
    service = TrendingService(routine_penalty_factor=0.25)

    story = StoryRecord(
        title="พยากรณ์อากาศประจำวัน กรมอุตุนิยมวิทยาชี้ทั่วไทยมีฝนตกประปราย",
        category="society",
        created_at=now,
        updated_at=now,
        first_article_at=now,
        last_article_at=now,
    )
    articles = [
        {
            "url": "https://example.com/weather-daily",
            "title": "พยากรณ์อากาศวันนี้ กรมอุตุนิยมวิทยาเตือนฝนฟ้าคะนองร้อยละ 40",
            "summary": "สภาพอากาศวันนี้ อากาศร้อนและมีฝนตกประปรายในบางพื้นที่",
            "source": "ThaiPBS",
            "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
    ]

    is_routine, crisis_exempt, reason = service.check_routine_status(story, articles)
    assert is_routine is True
    assert crisis_exempt is False
    assert reason is None

    _score, breakdown, badges = service.calculate_story_score(story, articles, now=now)
    assert breakdown.is_routine is True
    assert breakdown.routine_penalty == 0.25
    assert breakdown.crisis_exemption_applied is False
    assert "⚠️ Routine" in badges


def test_severe_disaster_warning_receives_crisis_exemption() -> None:
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
    service = TrendingService(routine_penalty_factor=0.25)

    story = StoryRecord(
        title="กรมอุตุนิยมวิทยา ประกาศเตือนภัยพายุระดับ 3 เฝ้าระวังน้ำท่วมฉับพลัน",
        category="environment",
        created_at=now,
        updated_at=now,
        first_article_at=now,
        last_article_at=now,
    )
    articles = [
        {
            "url": "https://example.com/storm-warning",
            "title": "กรมอุตุนิยมวิทยา ประกาศเตือนภัยพายุดีเปรสชัน เตรียมรับมือน้ำท่วมฉับพลันน้ำป่าไหลหลาก",
            "summary": "ประกาศเตือนภัยฉุกเฉิน ยกระดับเตือนภัยระดับ 3 สั่งอพยพด่วนพื้นที่เสี่ยงภัยริมน้ำ",
            "source": "ThaiPBS",
            "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
    ]

    is_routine, crisis_exempt, reason = service.check_routine_status(story, articles)
    assert is_routine is False
    assert crisis_exempt is True
    assert reason is not None
    assert "severe_warning_confirmed" in reason or "disaster_impact_confirmed" in reason

    _score, breakdown, badges = service.calculate_story_score(story, articles, now=now)
    assert breakdown.is_routine is False
    assert breakdown.routine_penalty == 1.0  # Fully waived!
    assert breakdown.crisis_exemption_applied is True
    assert breakdown.crisis_exemption_reason == reason
    assert "🚨 Crisis Warning" in badges
    assert "⚠️ Routine" not in badges
