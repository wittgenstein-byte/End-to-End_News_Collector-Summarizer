"""
tests/test_macro_p0_p2_invariants.py
─────────────────────────────────────────────────────────────────
Comprehensive invariant tests for Stage B Macro-Event Identification (P0–P2):
- P0.1: Province-only Veto & No unknown entity fallback to actor
- P0.2: Temporal Predecessor, Relation Direction & Verification Status
- P0.3: Single Source of Truth, Deep-Copy Isolation & Cross-Worker Lock
- P1.1: Configurable Thresholds & True Margin Rule
- P1.2: Thai Normalization, Alias Resolution & Location Hierarchy
- P1.3: Episode-Scoped Storyline Anchors
- P1.4: Story Update Propagation & Pending Re-evaluation
- P2.1: False Link/Split, Pending Rate, and Latency p95 Calibration
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.core.thai_normalizer import (
    has_sublocation_conflict,
    is_province_only_match,
    normalize_thai_text,
    parse_thai_locations,
    resolve_entity_alias,
)
from backend.repo.macro_event_repo import (
    FileMacroEventRepository,
    InMemoryMacroEventRepository,
)
from backend.repo.story_repo import (
    FileStoryRepository,
    InMemoryStoryRepository,
    StoryRepositoryPort,
)
from backend.schemas.macro_event_schema import (
    MacroEventRecord,
)
from backend.schemas.story_schema import (
    EventTimeEvidence,
    StoryRecord,
    TypedEventAnchors,
)
from backend.services.entity_extractor import extract_typed_anchors
from backend.services.macro_event_service import MacroEventService
from scripts.evaluate_stories import (
    calibrate_macro_thresholds,
    evaluate_stage_b_macro_identification,
)

# ── P0.1 Tests: Province-only Veto & Strict Typing ────────────────

def test_p0_1_province_only_veto_and_no_unknown_actor_fallback() -> None:
    """
    P0.1:
    1. Unknown tokens (e.g. 'อยุธยา', 'หาดใหญ่', 'โต๊ะเก้าอี้') must not be classified as actor_names.
    2. Two events in the same province (e.g. 'เชียงใหม่' or 'อยุธยา') with zero shared districts,
       zero shared sub-locations, and zero shared substantive actors MUST receive a score of 0.0
       (Province-Only Hard Veto).
    """
    # 1. Unknown entity fallback test
    anchors = extract_typed_anchors(
        text="รายงานเหตุการณ์",
        entities=["อยุธยา", "หาดใหญ่", "โต๊ะเก้าอี้", "นายสมชาย"],
    )
    # 'อยุธยา' must map to province, 'หาดใหญ่' to district, 'นายสมชาย' to actor_names
    assert "พระนครศรีอยุธยา" in anchors.provinces
    assert "หาดใหญ่" in anchors.districts
    assert "นายสมชาย" in anchors.actor_names
    # 'อยุธยา', 'หาดใหญ่', and 'โต๊ะเก้าอี้' must NEVER be in actor_names
    assert "อยุธยา" not in anchors.actor_names
    assert "หาดใหญ่" not in anchors.actor_names
    assert "โต๊ะเก้าอี้" not in anchors.actor_names

    # 2. Province-only Hard Veto in score_macro
    macro_repo = InMemoryMacroEventRepository()
    story_repo = InMemoryStoryRepository()
    svc = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

    # Event 1: Car crash in Chiang Mai
    story1 = StoryRecord(
        title="เกิดอุบัติเหตุรถตู้คว่ำที่เชียงใหม่ มีผู้บาดเจ็บ 3 ราย",
        category="society",
        entities=["เชียงใหม่"],
        typed_anchors=TypedEventAnchors(
            provinces=["เชียงใหม่"],
            targets=["ผู้บาดเจ็บ"],
            actions=["คว่ำ"],
        ),
        centroid=[0.5] * 768,
    )
    macro1, _ = svc.assign_event(story1)
    assert macro1 is not None

    # Event 2: Boat drowning in Chiang Mai (different incident, same province, no district)
    story2 = StoryRecord(
        title="เรือล่องแพล่มกลางลำน้ำที่เชียงใหม่ นักท่องเที่ยวสูญหาย",
        category="society",
        entities=["เชียงใหม่"],
        typed_anchors=TypedEventAnchors(
            provinces=["เชียงใหม่"],
            targets=["นักท่องเที่ยว"],
            actions=["ล่ม"],
        ),
        centroid=[0.5] * 768,  # identical centroid to stress-test the veto
    )

    # Must be vetoed to 0.0 despite high centroid similarity
    score = svc.score_macro(story2, macro1)
    assert score == 0.0, f"Expected 0.0 due to province-only veto, got {score}"


# ── P0.2 Tests: Predecessor, Relation Direction & Status ──────────

def test_p0_2_relation_direction_temporal_predecessor_and_verification_status() -> None:
    """
    P0.2:
    1. Chronological predecessor lookup must be based on actual incident event_time,
       not arrival order in child_event_ids list.
    2. EventRelationRecord direction:
       - 'A precedes B': source=older, target=newer
       - 'B updates A': source=newer, target=older
    3. Verification status:
       - Heuristic link must start as 'proposed'.
       - Direct follow-up authoritative lineage (Step 0) must be 'verified'.
    """
    macro_repo = InMemoryMacroEventRepository()
    story_repo = InMemoryStoryRepository()
    svc = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

    base_time = datetime(2026, 8, 10, 10, 0, 0, tzinfo=timezone.utc)

    # Event 1 (Day 10)
    story_day10 = StoryRecord(
        title="ไฟไหม้โรงงานสารเคมีสมุทรปราการ ระลอกแรก",
        category="society",
        entities=["สมุทรปราการ", "บางพลี"],
        event_time=EventTimeEvidence(start_utc=base_time),
        typed_anchors=TypedEventAnchors(
            provinces=["สมุทรปราการ"],
            districts=["บางพลี"],
            actions=["ไฟไหม้"],
        ),
        centroid=[0.6] * 768,
    )
    macro, is_new = svc.assign_event(story_day10)
    assert is_new is True
    assert macro is not None

    # Event 2 (Day 12, arrives after Day 10)
    day12_time = base_time + timedelta(days=2)
    story_day12 = StoryRecord(
        title="ไฟไหม้โรงงานสารเคมีสมุทรปราการ เจ้าหน้าที่ควบคุมเพลิงได้แล้ว",
        category="society",
        entities=["สมุทรปราการ", "บางพลี"],
        event_time=EventTimeEvidence(start_utc=day12_time),
        typed_anchors=TypedEventAnchors(
            provinces=["สมุทรปราการ"],
            districts=["บางพลี"],
            actions=["ไฟไหม้", "ควบคุมเพลิง"],
        ),
        centroid=[0.6] * 768,
    )
    macro2, _ = svc.assign_event(story_day12)
    assert macro2 is not None
    assert len(macro2.relations) == 1
    rel1 = macro2.relations[0]

    # Day 12 updates Day 10 (or Day 10 precedes Day 12)
    if rel1.relation_type == "updates":
        assert rel1.source_event_id == story_day12.story_id
        assert rel1.target_event_id == story_day10.story_id
    else:
        assert rel1.relation_type == "precedes"
        assert rel1.source_event_id == story_day10.story_id
        assert rel1.target_event_id == story_day12.story_id
    assert rel1.verification_status == "proposed"

    # Event 3: Out-of-order older event arriving late (Day 8 event arriving after Day 10 & 12)
    day8_time = base_time - timedelta(days=2)
    story_day8 = StoryRecord(
        title="รายงานย้อนหลัง: สัญญาณเตือนไฟไหม้โรงงานสารเคมีสมุทรปราการ",
        category="society",
        entities=["สมุทรปราการ", "บางพลี"],
        event_time=EventTimeEvidence(start_utc=day8_time),
        typed_anchors=TypedEventAnchors(
            provinces=["สมุทรปราการ"],
            districts=["บางพลี"],
            actions=["ไฟไหม้"],
        ),
        centroid=[0.6] * 768,
    )
    macro3, _ = svc.assign_event(story_day8)
    assert macro3 is not None
    # Must correctly find that Day 8 precedes Day 10 (chronological successor),
    # NOT connecting backwards to Day 12 index
    rel2 = macro3.relations[-1]
    assert rel2.relation_type == "precedes"
    assert rel2.source_event_id == story_day8.story_id
    assert rel2.target_event_id == story_day10.story_id
    assert rel2.verification_status == "proposed"

    # Direct follow-up Step 0 verification
    story_followup = StoryRecord(
        title="ไฟไหม้โรงงานสมุทรปราการ: สรุปความเสียหายทั้งหมด",
        category="society",
        entities=["สมุทรปราการ", "บางพลี"],
        typed_anchors=TypedEventAnchors(provinces=["สมุทรปราการ"], districts=["บางพลี"]),
    )
    macro_fu, _ = svc.assign_event(story_followup, antecedent_story_id=story_day12.story_id)
    assert macro_fu is not None
    rel_fu = macro_fu.relations[-1]
    assert rel_fu.relation_type == "updates"
    assert rel_fu.source_event_id == story_followup.story_id
    assert rel_fu.target_event_id == story_day12.story_id
    assert rel_fu.verification_status == "verified"


# ── P0.3 Tests: SST Consistency & Deep-Copy Isolation ─────────────

def test_p0_3_story_macro_sst_consistency_and_deepcopy_isolation() -> None:
    """
    P0.3:
    1. Repository read methods must return deep copies; mutating returned object
       must NOT affect the in-memory cache until save is called.
    2. Two-phase commit with rollback when saving story fails.
    3. Reconcile consistency repairs orphan links between Story and Macro.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        s_file = Path(tmpdir) / "stories.json"
        m_file = Path(tmpdir) / "macros.json"

        story_repo = FileStoryRepository(s_file)
        macro_repo = FileMacroEventRepository(m_file)

        # 1. Deep-copy isolation test
        test_story = StoryRecord(title="ข่าวทดสอบ A", category="politics", entities=["กทม"])
        story_repo.save_story(test_story)

        fetched = story_repo.get_story(test_story.story_id)
        assert fetched is not None
        fetched.title = "ข่าวแก้ไขในหน่วยความจำ"

        fetched_again = story_repo.get_story(test_story.story_id)
        assert fetched_again is not None
        assert fetched_again.title == "ข่าวทดสอบ A", "Cache was modified by reference!"

        # Macro deep copy isolation
        test_macro = MacroEventRecord(title="แมโครทดสอบ A", child_event_ids=[test_story.story_id])
        macro_repo.save_macro_event(test_macro)

        fetched_macro = macro_repo.get_macro_event(test_macro.macro_event_id)
        assert fetched_macro is not None
        fetched_macro.child_event_ids.append("dummy_child")

        fetched_macro_again = macro_repo.get_macro_event(test_macro.macro_event_id)
        assert fetched_macro_again is not None
        assert fetched_macro_again.child_event_ids == [test_story.story_id]

        # 2. Atomic rollback test
        svc = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)
        failing_story_repo = MagicMock(spec=StoryRepositoryPort)
        failing_story_repo.save_story.side_effect = OSError("Disk full simulation")
        svc_failing = MacroEventService(macro_repo=macro_repo, story_repo=failing_story_repo)

        new_story = StoryRecord(title="ข่าวกระตุ้นข้อผิดพลาด", category="society")
        with pytest.raises(IOError):
            svc_failing.assign_event(new_story)

        # Ensure macro was rolled back and not orphaned
        assert macro_repo.count_macro_events() == 1

        # 3. Reconcile consistency test
        orphan_macro = MacroEventRecord(
            title="แมโครเด็กกำพร้า",
            child_event_ids=["non_existent_story_1", test_story.story_id],
        )
        macro_repo.save_macro_event(orphan_macro)

        stats = svc.reconcile_consistency()
        assert stats["orphans_removed"] >= 1
        cleaned_macro = macro_repo.get_macro_event(orphan_macro.macro_event_id)
        assert cleaned_macro is not None
        assert "non_existent_story_1" not in cleaned_macro.child_event_ids


# ── P1.1 Tests: Configurable Thresholds & True Margin Rule ────────

def test_p1_1_configurable_thresholds_and_strict_margin_rule() -> None:
    """
    P1.1:
    1. Thresholds (link_threshold, pending_threshold, margin_threshold) are fully functional.
    2. True Margin Rule:
       If Top #1 gets 0.63 and Top #2 gets 0.60 (margin 0.03 < margin_threshold 0.05),
       even though #2 is below 0.62, the ambiguity holds the story as pending_macro!
    """
    macro_repo = InMemoryMacroEventRepository()
    story_repo = InMemoryStoryRepository()

    # Create two competing macro events
    macro1 = MacroEventRecord(
        macro_event_id="macro_target_1",
        title="น้ำท่วมอำเภอเมืองน่าน ระลอก 1",
        category="society",
        typed_anchors=TypedEventAnchors(provinces=["น่าน"], districts=["เมืองน่าน"]),
        centroid=[0.60] * 768,
    )
    macro2 = MacroEventRecord(
        macro_event_id="macro_target_2",
        title="น้ำท่วมอำเภอเวียงสาน่าน ระลอก 1",
        category="society",
        typed_anchors=TypedEventAnchors(provinces=["น่าน"], districts=["เวียงสา"]),
        centroid=[0.58] * 768,
    )
    macro_repo.save_macro_event(macro1)
    macro_repo.save_macro_event(macro2)

    svc = MacroEventService(
        macro_repo=macro_repo,
        story_repo=story_repo,
        link_threshold=0.62,
        margin_threshold=0.05,
        pending_threshold=0.52,
    )

    story = StoryRecord(
        title="สถานการณ์น้ำท่วมจังหวัดน่าน พื้นที่ลุ่มน้ำ",
        category="society",
        typed_anchors=TypedEventAnchors(provinces=["น่าน"]),
    )

    # Mock score_macro to return 0.63 for macro1 and 0.60 for macro2
    def mock_score(s: StoryRecord, m: MacroEventRecord) -> float:
        if m.macro_event_id == "macro_target_1":
            return 0.63
        if m.macro_event_id == "macro_target_2":
            return 0.60
        return 0.0

    svc.score_macro = mock_score  # type: ignore[assignment]

    result_macro, is_new = svc.assign_event(story)
    assert result_macro is None
    assert is_new is False
    assert story.macro_association_status == "pending_macro"
    assert story.pending_macro_reason == "competing_macros_margin_tie"
    assert "macro_target_1" in story.candidate_macro_ids
    assert "macro_target_2" in story.candidate_macro_ids


# ── P1.2 Tests: Normalization, Alias & Location Hierarchy ─────────

def test_p1_2_thai_normalization_alias_and_location_hierarchy() -> None:
    """
    P1.2:
    - Normalizes Thai digits: '๑๐' -> '10'
    - Normalizes acronyms: 'รพ.' -> 'โรงพยาบาล', 'กทม.' -> 'กรุงเทพมหานคร'
    - Resolves Aliases: 'บิ๊กต่าย' -> 'กิตติ์รัฐ พันธุ์เพ็ชร์'
    - Location hierarchy: 'วัดพนัญเชิง' -> sub_location, 'อยุธยา' -> 'พระนครศรีอยุธยา'
    """
    # 1. Text Normalization
    raw_text = "รพ.ตำรวจ รายงานผู้บาดเจ็บ ๑๒ ราย ณ แยกราชประสงค์ กทม."
    normalized = normalize_thai_text(raw_text)
    assert "โรงพยาบาล" in normalized
    assert "12" in normalized
    assert "กรุงเทพมหานคร" in normalized

    # 2. Alias Resolution
    assert resolve_entity_alias("บิ๊กต่าย") == "กิตติ์รัฐ พันธุ์เพ็ชร์"
    assert resolve_entity_alias("นายกฯ อิ๊งค์") == "แพทองธาร ชินวัตร"
    assert resolve_entity_alias("อยุธยา") == "พระนครศรีอยุธยา"

    # 3. Location Hierarchy
    locs = parse_thai_locations(["วัดพนัญเชิง", "อ.หาดใหญ่", "เชียงใหม่"])
    assert "วัดพนัญเชิง" in locs["sub_locations"]
    assert "พระนครศรีอยุธยา" in locs["provinces"]
    assert "หาดใหญ่" in locs["districts"]
    assert "สงขลา" in locs["provinces"]
    assert "เชียงใหม่" in locs["provinces"]

    # 4. Location Conflict & Province-only check
    locs_a = {"provinces": ["เชียงใหม่"], "districts": ["ฝาง"], "sub_locations": []}
    locs_b = {"provinces": ["เชียงใหม่"], "districts": ["แม่ริม"], "sub_locations": []}
    assert has_sublocation_conflict(locs_a, locs_b) is True

    locs_prov_a = {"provinces": ["เชียงใหม่"], "districts": [], "sub_locations": []}
    locs_prov_b = {"provinces": ["เชียงใหม่"], "districts": [], "sub_locations": []}
    assert is_province_only_match(locs_prov_a, locs_prov_b) is True


# ── P1.3 Tests: Episode-Scoped Storyline Anchor ───────────────────

def test_p1_3_episode_scoped_storyline_anchor() -> None:
    """
    P1.3:
    Storyline anchor (e.g. 'น้ำท่วมน่าน') only links across events within
    anchor_episode_days (default 45 days). An event 180 days later must create
    a distinct MacroEventRecord for the new crisis wave.
    """
    macro_repo = InMemoryMacroEventRepository()
    story_repo = InMemoryStoryRepository()
    svc = MacroEventService(
        macro_repo=macro_repo,
        story_repo=story_repo,
        anchor_episode_days=45,
    )

    t0 = datetime(2025, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Event 1: Flood in Nan (Wave 1)
    story1 = StoryRecord(
        title="สถานการณ์ น้ำท่วมน่าน ระลอกใหญ่แม่น้ำเอ่อล้น",
        category="society",
        event_time=EventTimeEvidence(start_utc=t0),
        typed_anchors=TypedEventAnchors(
            provinces=["น่าน"],
            storyline_anchor="น้ำท่วมน่าน",
            storyline_episode_key="น้ำท่วมน่าน:2025-08",
        ),
        centroid=[0.7] * 768,
    )
    macro1, is_new1 = svc.assign_event(story1)
    assert is_new1 is True
    assert macro1 is not None

    # Event 2: Follow-up 5 days later (Same wave)
    t1 = t0 + timedelta(days=5)
    story2 = StoryRecord(
        title="น้ำท่วมน่าน คลี่คลายลงแล้ว ระดับน้ำลดลง",
        category="society",
        event_time=EventTimeEvidence(start_utc=t1),
        typed_anchors=TypedEventAnchors(
            provinces=["น่าน"],
            storyline_anchor="น้ำท่วมน่าน",
            storyline_episode_key="น้ำท่วมน่าน:2025-08",
        ),
        centroid=[0.7] * 768,
    )
    macro2, is_new2 = svc.assign_event(story2)
    assert is_new2 is False
    assert macro2 is not None
    assert macro2.macro_event_id == macro1.macro_event_id

    # Event 3: Flood in Nan next year (180 days later -> New Episode Wave)
    t2 = t0 + timedelta(days=180)
    story3 = StoryRecord(
        title="เกิดเหตุ น้ำท่วมน่าน ระลอกใหม่หลังฝนตกหนัก",
        category="society",
        event_time=EventTimeEvidence(start_utc=t2),
        typed_anchors=TypedEventAnchors(
            provinces=["น่าน"],
            storyline_anchor="น้ำท่วมน่าน",
            storyline_episode_key="น้ำท่วมน่าน:2026-02",
        ),
        centroid=[0.7] * 768,
    )
    macro3, is_new3 = svc.assign_event(story3)
    assert is_new3 is True, "Event 180 days later should not merge into previous episode!"
    assert macro3 is not None
    assert macro3.macro_event_id != macro1.macro_event_id


# ── P1.4 Tests: Story Update Propagation & Pending Re-evaluation ──

def test_p1_4_story_update_propagation_and_pending_reevaluation() -> None:
    """
    P1.4:
    1. A story initially held in 'pending_macro' is re-evaluated when updated with new articles/evidence.
    2. on_story_updated automatically promotes stories from 'pending_macro' to 'linked'.
    """
    macro_repo = InMemoryMacroEventRepository()
    story_repo = InMemoryStoryRepository()
    svc = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

    # Existing macro with rich information
    existing_macro = MacroEventRecord(
        title="คดีแตงโม",
        category="society",
        named_crisis_anchor="คดีแตงโม",
        storyline_anchor="คดีแตงโม",
        typed_anchors=TypedEventAnchors(
            provinces=["นนทบุรี"],
            districts=["เมืองนนทบุรี"],
            actions=["สอบสวน", "ฟ้องร้อง"],
            storyline_anchor="คดีแตงโม",
        ),
        centroid=[1.0] + [0.0] * 767,
    )
    macro_repo.save_macro_event(existing_macro)

    # Initial borderline story that gets pending_macro (score in [0.52, 0.62))
    # cos_sim = 0.8, specific_anchor_overlap = 1 (district "เมืองนนทบุรี"), storyline_match = False
    # raw_score = 0.55 * 0.8 + 0.25 * 0.0 + 0.20 * (1 / 2.0) = 0.44 + 0.10 = 0.54
    initial_story = StoryRecord(
        title="ความคืบหน้าการพิจารณาคดี",
        category="society",
        typed_anchors=TypedEventAnchors(
            provinces=["นนทบุรี"],
            districts=["เมืองนนทบุรี"],
        ),
        centroid=[0.70, 0.7141428] + [0.0] * 766,
    )
    story_repo.save_story(initial_story)

    # First assignment -> borderline pending (0.585 in [0.52, 0.62))
    res_macro, is_new = svc.assign_event(initial_story)
    assert res_macro is None
    assert is_new is False
    assert initial_story.macro_association_status == "pending_macro"

    # Second article arrives and updates initial_story with explicit crisis anchor
    # score becomes: 0.54 + 0.25 = 0.79 >= 0.62 -> linked
    initial_story.typed_anchors = TypedEventAnchors(
        provinces=["นนทบุรี"],
        districts=["เมืองนนทบุรี"],
        storyline_anchor="คดีแตงโม",
    )
    story_repo.save_story(initial_story)

    # Call on_story_updated
    promoted_macro, _ = svc.on_story_updated(initial_story)
    assert promoted_macro is not None
    assert initial_story.macro_association_status == "linked"
    assert initial_story.macro_event_id == existing_macro.macro_event_id


# ── P2.1 Tests: False Link/Split, Pending Rate & Latency p95 ──────

def test_p2_1_evaluation_metrics_false_link_split_pending_and_latency_p95() -> None:
    """
    P2.1:
    Test calculation of False Link Rate, False Split Rate, Pending Rate,
    and Latency p95 distribution on a dataset with grid calibration.
    """
    stories: list[StoryRecord] = [
        StoryRecord(
            title="น้ำท่วมน่าน ข่าวที่ 1",
            category="society",
            typed_anchors=TypedEventAnchors(provinces=["น่าน"], storyline_anchor="น้ำท่วมน่าน"),
            centroid=[0.8] * 768,
        ),
        StoryRecord(
            title="น้ำท่วมน่าน ข่าวที่ 2",
            category="society",
            typed_anchors=TypedEventAnchors(provinces=["น่าน"], storyline_anchor="น้ำท่วมน่าน"),
            centroid=[0.8] * 768,
        ),
        StoryRecord(
            title="ไฟไหม้โรงงานสมุทรปราการ",
            category="society",
            typed_anchors=TypedEventAnchors(provinces=["สมุทรปราการ"], actions=["ไฟไหม้"]),
            centroid=[0.1] * 768,
        ),
    ]
    gt_macro_ids = ["macro_nan", "macro_nan", "macro_samutprakan"]

    results = evaluate_stage_b_macro_identification(stories, gt_macro_ids)
    assert "false_link_rate" in results
    assert "false_split_rate" in results
    assert "pending_rate" in results
    assert "latency_ms" in results
    assert results["latency_ms"]["p95"] >= 0.0

    # Grid calibration test
    calib = calibrate_macro_thresholds(
        stories,
        gt_macro_ids,
        link_candidates=[0.60, 0.65],
        margin_candidates=[0.05],
    )
    assert "best_configuration" in calib
    assert len(calib["grid_results"]) == 2


def test_file_lock_reentrancy_and_multi_instance(tmp_path: Path) -> None:
    """Verify that InterProcessFileLock supports nested re-entrancy and multiple instances."""
    from backend.core.file_lock import InterProcessFileLock

    lock_file = tmp_path / "test_nested.lock"
    lock1 = InterProcessFileLock(lock_file, timeout=2.0)
    lock2 = InterProcessFileLock(lock_file, timeout=2.0)

    # Nested with blocks on same instance
    with lock1, lock1:
        pass

    # Nested with blocks across different instances pointing to same file
    with lock1, lock2:
        pass


def test_typed_ner_person_retention_without_prefix() -> None:
    """Verify that NER-recognized PERSON/ORG entities are retained in actor_names while unknown tokens are excluded."""
    # Simulation with typed entities passed from NER
    anchors = extract_typed_anchors(
        text="นายสมชาย และ อนุทิน เข้าร่วมประชุมที่เชียงใหม่",
        entities=["นายสมชาย", "อนุทิน", "เชียงใหม่", "เอกสารวาระ"],
        typed_entities=[
            ("นายสมชาย", "PERSON"),
            ("อนุทิน", "PERSON"),
            ("เชียงใหม่", "LOCATION"),
            ("เอกสารวาระ", "OBJECT"),
        ],
    )
    assert "นายสมชาย" in anchors.actor_names
    assert "อนุทิน" in anchors.actor_names
    assert "เชียงใหม่" in anchors.provinces
    assert "เอกสารวาระ" not in anchors.actor_names
    assert "เชียงใหม่" not in anchors.actor_names
