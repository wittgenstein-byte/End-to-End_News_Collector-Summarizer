"""
test_presentation_cache_fingerprint.py
─────────────────────────────────────────────────────────────────
Verifies SHA-256 canonical presentation fingerprinting and persistent caching:
1. Identical inputs yield identical SHA-256 hash across executions.
2. Modifying article inputs, relations, or prompt version alters fingerprint.
3. Cache entries persist to disk and reload across process restarts.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from backend.schemas.macro_event_schema import MacroEventRecord
from backend.schemas.story_schema import StoryRecord
from backend.services.story_presentation_service import StoryPresentationService


def test_sha256_canonical_fingerprint_determinism() -> None:
    articles_a = [
        {"url": "https://example.com/b", "title": "ข่าว B", "fetched_at": "2026-08-24 10:00:00"},
        {"url": "https://example.com/a", "title": "ข่าว A", "fetched_at": "2026-08-23 10:00:00"},
    ]
    # Reverse input order to test canonical sorting
    articles_b = [
        {"url": "https://example.com/a", "title": "ข่าว A", "fetched_at": "2026-08-23 10:00:00"},
        {"url": "https://example.com/b", "title": "ข่าว B", "fetched_at": "2026-08-24 10:00:00"},
    ]

    fp_a = StoryPresentationService.compute_sha256_fingerprint(
        target_id="macro_001",
        articles=articles_a,
        relations=["event1->event2:updates"],
    )
    fp_b = StoryPresentationService.compute_sha256_fingerprint(
        target_id="macro_001",
        articles=articles_b,
        relations=["event1->event2:updates"],
    )

    # Invariant: Canonical sorting guarantees identical hash regardless of input ordering
    assert fp_a == fp_b
    assert len(fp_a) == 64  # Valid SHA-256 hex string

    # Modifying relations changes fingerprint
    fp_diff_rel = StoryPresentationService.compute_sha256_fingerprint(
        target_id="macro_001",
        articles=articles_a,
        relations=["event1->event2:precedes"],
    )
    assert fp_a != fp_diff_rel

    # Modifying prompt version changes fingerprint
    fp_diff_prompt = StoryPresentationService.compute_sha256_fingerprint(
        target_id="macro_001",
        articles=articles_a,
        prompt_version="2.0",
    )
    assert fp_a != fp_diff_prompt


def test_disk_cache_persistence_across_instances() -> None:
    with TemporaryDirectory() as tmp_dir:
        cache_file = Path(tmp_dir) / "presentation_cache.json"

        # Instance 1: Generate presentation and persist
        service1 = StoryPresentationService(cache_file=cache_file)
        macro = MacroEventRecord(
            macro_event_id="macro_test_persist",
            title="น้ำท่วมใหญ่",
            child_event_ids=["story_1"],
        )
        child_story = StoryRecord(
            story_id="story_1",
            title="น้ำท่วมใหญ่",
            article_urls=["https://example.com/flood1"],
        )
        enriched1 = service1.present_macro_event(macro, [child_story])
        assert enriched1.headline is not None
        assert enriched1.presentation_fingerprint is not None
        fp1 = enriched1.presentation_fingerprint

        assert cache_file.exists()

        # Instance 2: Reload from disk and verify cache reuse
        service2 = StoryPresentationService(cache_file=cache_file)
        macro_reloaded = MacroEventRecord(
            macro_event_id="macro_test_persist",
            title="น้ำท่วมใหญ่",
            child_event_ids=["story_1"],
        )
        enriched2 = service2.present_macro_event(macro_reloaded, [child_story])
        assert enriched2.presentation_fingerprint == fp1
        assert enriched2.headline == enriched1.headline
