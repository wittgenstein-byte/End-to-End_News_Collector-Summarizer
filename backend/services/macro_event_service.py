"""
services/macro_event_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Macro-Event / Storyline identification and event relationship linking.
SOLID  O — Configurable macro candidate window, similarity thresholds, and margins.
SOLID  D — Injects MacroEventRepositoryPort and StoryRepositoryPort.
GRASP  Information Expert — Evaluates multi-signal macro qualifications,
            maintains directional event relations, and updates storyline centroids.
GRASP  Controller — Primary entry point for Event-to-MacroEvent assignment.
POLICY STAGED PIPELINE — Event matching must precede Macro linking.
       Macro linking is NEVER a bypass for ambiguous event merges.
POLICY SINGLE SOURCE OF TRUTH — StoryRecord.macro_event_id is the primary truth;
       MacroEventRecord.child_event_ids is the derived index.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

import numpy as np

from backend.core.thai_normalizer import (
    ENTITY_ALIASES,
    has_sublocation_conflict,
    is_province_only_match,
    normalize_thai_text,
    parse_thai_locations,
    resolve_entity_alias,
)
from backend.repo.macro_event_repo import (
    MacroEventRepositoryPort,
    get_macro_event_repository,
)
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.macro_event_schema import (
    EventRelationRecord,
    MacroEventRecord,
)
from backend.schemas.story_schema import StoryRecord, TypedEventAnchors
from backend.services.entity_extractor import _ACTOR_PREFIXES, _GENERIC_ROLES

logger = logging.getLogger(__name__)

# Common stopwords to exclude from named entity overlap confirmation
_GENERIC_ENTITY_STOPWORDS: frozenset[str] = frozenset({
    "ไทย", "ประเทศไทย", "รัฐบาล", "นายกรัฐมนตรี", "เจ้าหน้าที่", "ตำรวจ", "ประชาชน",
    "กรุงเทพ", "กรุงเทพฯ", "กทม", "กทม.", "สภา", "ศาล", "พรรค",
})

# High-salience patterns for Named Crisis Anchor extraction
_CRISIS_ANCHOR_PATTERNS: tuple[str, ...] = (
    "น้ำท่วมน่าน", "น้ำท่วมเชียงราย", "น้ำท่วมพะเยา", "น้ำท่วมแพร่", "น้ำท่วมสุโขทัย",
    "เลือกตั้งสว", "เลือกตั้ง สว", "สว.ฮั้ว", "คดีตากใบ", "คดีแตงโม", "คดีดิไอคอน",
    "ชายแดนใต้", "ไฟใต้", "ระเบิดปัตตานี", "พาราลิมปิก", "โอลิมปิก",
)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two 768-d embeddings."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class MacroEventService:
    """
    Orchestrator for Macro-Event Storylines and Event Relations.

    Rules:
    1. Staged Pipeline: Only called after StoryService has determined the StoryRecord (Event).
    2. Candidate Retrieval: Considers macro-events within candidate_days (default 14 days)
       PLUS macros with matching storyline/crisis anchor within anchor_episode_days (default 45 days).
    3. Multi-Signal Qualification (Calibrated score_macro):
       - Cosine similarity between 768-d centroids.
       - Storyline crisis / campaign anchor matching with episode scoping.
       - Specific named entity / anchor agreement (actors, targets, locations).
       - Hard Veto: Excludes pairs sharing solely generic roles, conflicting locations,
         or a single province name (Province-Only Hard Veto).
    4. Deterministic Relations:
       - Chronological Predecessor lookup based on actual incident time.
       - Semantic relation direction: A precedes B (source=older, target=newer),
         B updates A (source=newer, target=older).
       - Honest verification status: 'proposed' for heuristic scoring, 'verified' for authoritative lineage.
    5. Single Source of Truth & Consistency:
       - Atomic commit with automatic rollback between Story (SST) and Macro.
    """

    def __init__(
        self,
        macro_repo: MacroEventRepositoryPort | None = None,
        story_repo: StoryRepositoryPort | None = None,
        link_threshold: float = 0.62,
        pending_threshold: float = 0.52,
        updates_relation_threshold: float = 0.70,
        margin_threshold: float = 0.05,
        candidate_days: int = 14,
        anchor_episode_days: int = 45,
        ema_alpha: float = 0.85,
        min_sim: float | None = None,
        max_sim: float | None = None,
    ) -> None:
        self._macro_repo: MacroEventRepositoryPort = macro_repo or get_macro_event_repository()
        self._story_repo: StoryRepositoryPort = story_repo or get_story_repository()
        # Backward compatibility for legacy min_sim / max_sim kwargs
        self._link_threshold: float = link_threshold
        self._pending_threshold: float = pending_threshold
        self._updates_relation_threshold: float = updates_relation_threshold
        self._margin_threshold: float = margin_threshold
        self._candidate_days: int = candidate_days
        self._anchor_episode_days: int = anchor_episode_days
        self._ema_alpha: float = ema_alpha
        self._min_sim: float = min_sim if min_sim is not None else self._pending_threshold
        self._max_sim: float = max_sim if max_sim is not None else self._link_threshold
        self._lock = threading.RLock()

    def extract_crisis_anchor(self, text: str, entities: list[str]) -> str | None:
        """Extract a high-salience crisis/campaign anchor if present in title or entities."""
        combined = f"{text} {' '.join(entities)}".lower()
        for pattern in _CRISIS_ANCHOR_PATTERNS:
            if pattern.lower() in combined:
                return pattern
        return None

    def has_specific_entity_agreement(
        self,
        event_entities: list[str],
        macro_entities: list[str],
    ) -> bool:
        """
        Verify that the event shares at least one substantive, non-generic entity with the macro.
        Guards against broad stopwords like 'ไทย', 'รัฐบาล', 'ตำรวจ'.
        """
        s_ents = {
            e.strip() for e in event_entities
            if e.strip() and e.strip() not in _GENERIC_ENTITY_STOPWORDS and len(e.strip()) > 1
        }
        m_ents = {
            e.strip() for e in macro_entities
            if e.strip() and e.strip() not in _GENERIC_ENTITY_STOPWORDS and len(e.strip()) > 1
        }
        if not s_ents or not m_ents:
            return False
        return bool(s_ents & m_ents)

    def _extract_structured_anchors(
        self,
        record: StoryRecord | MacroEventRecord,
    ) -> tuple[set[str], set[str], set[str], set[str], dict[str, set[str]]]:
        """
        Extract structured typed anchors with strict separation:
        - actors: verified PERSON/ORG proper names and resolved aliases
        - roles: generic functional roles
        - targets: victims, objects
        - actions: incident actions
        - loc_dict: {'provinces', 'districts', 'sub_locations', 'all'}
        """
        actors: set[str] = set()
        roles: set[str] = set()
        targets: set[str] = set()
        actions: set[str] = set()
        loc_dict: dict[str, set[str]] = {
            "provinces": set(),
            "districts": set(),
            "sub_locations": set(),
            "all": set(),
        }

        if getattr(record, "typed_anchors", None):
            ta = record.typed_anchors
            actors.update(resolve_entity_alias(a).strip().lower() for a in ta.actor_names if a.strip())
            roles.update(r.strip().lower() for r in ta.actor_roles if r.strip())
            targets.update(t.strip().lower() for t in ta.targets if t.strip())
            actions.update(a.strip().lower() for a in ta.actions if a.strip())
            for p in ta.provinces:
                clean_p = p.strip()
                if clean_p:
                    loc_dict["provinces"].add(clean_p)
                    loc_dict["all"].add(clean_p)
            for d in ta.districts:
                clean_d = d.strip()
                if clean_d:
                    loc_dict["districts"].add(clean_d)
                    loc_dict["all"].add(clean_d)
            for s in ta.sub_locations:
                clean_s = s.strip()
                if clean_s:
                    loc_dict["sub_locations"].add(clean_s)
                    loc_dict["all"].add(clean_s)
            for l in ta.event_locations:
                clean_l = l.strip()
                if clean_l:
                    loc_dict["all"].add(clean_l)
                    parsed_l = parse_thai_locations(clean_l)
                    for p in parsed_l["provinces"]:
                        loc_dict["provinces"].add(p)
                        loc_dict["all"].add(p)
                    for d in parsed_l["districts"]:
                        loc_dict["districts"].add(d)
                        loc_dict["all"].add(d)
                    for s in parsed_l["sub_locations"]:
                        loc_dict["sub_locations"].add(s)
                        loc_dict["all"].add(s)

        # Parse unstructured entities safely without falling back to actors
        entities = getattr(record, "entities", []) or []
        for e in entities:
            clean_e = normalize_thai_text(e).strip()
            if not clean_e or clean_e in _GENERIC_ENTITY_STOPWORDS:
                continue

            # 1. Parse location
            e_loc = parse_thai_locations(clean_e)
            if e_loc["provinces"] or e_loc["districts"] or e_loc["sub_locations"]:
                for p in e_loc["provinces"]:
                    loc_dict["provinces"].add(p)
                    loc_dict["all"].add(p)
                for d in e_loc["districts"]:
                    loc_dict["districts"].add(d)
                    loc_dict["all"].add(d)
                for s in e_loc["sub_locations"]:
                    loc_dict["sub_locations"].add(s)
                    loc_dict["all"].add(s)
                continue
            elif clean_e.startswith(("จ.", "อ.", "ต.", "ถ.", "แยก", "สะพาน", "แม่น้ำ", "เกาะ", "วัด", "ดอย")):
                loc_dict["sub_locations"].add(clean_e)
                loc_dict["all"].add(clean_e)
                continue

            # 2. Check roles
            if clean_e in _GENERIC_ROLES or clean_e.startswith(("เจ้าหน้าที่", "ตำรวจ", "พนักงาน", "ผู้ว่า")):
                roles.add(clean_e.lower())
                continue

            # 3. Known actor / alias
            resolved = resolve_entity_alias(clean_e)
            is_known = (
                resolved in ENTITY_ALIASES.values()
                or any(clean_e.startswith(p) for p in _ACTOR_PREFIXES)
                or (resolved != clean_e)
            )
            if is_known:
                actors.add(resolved.lower())
            # Unknown tokens are ignored; NOT added to actors!

        return actors, roles, targets, actions, loc_dict

    def score_macro(
        self,
        story: StoryRecord,
        candidate: MacroEventRecord,
    ) -> float:
        """
        Compute calibrated macro-event compatibility score in [0.0, 1.0].
        Applies Hard Veto if:
        1. Conflicting sub-locations/districts or different provinces without substantive actors.
        2. Province-Only Veto: pair shares solely a single province name without shared
           districts, sub-locations, substantive actors, or storyline anchors.
        3. Pair lacks substantive actors, specific location, or matching crisis anchor.
        """
        # Cosine similarity between 768-d centroids
        story_vec = story.centroid
        cand_vec = candidate.centroid
        cos_sim = 0.0
        if story_vec and cand_vec and len(story_vec) == len(cand_vec):
            cos_sim = _cosine_similarity(story_vec, cand_vec)

        # Storyline / crisis anchor match with episode scope check (P1.3)
        s_anchor = (
            (story.typed_anchors.storyline_anchor if story.typed_anchors else None)
            or self.extract_crisis_anchor(story.title, story.entities)
        )
        c_anchor = candidate.storyline_anchor or candidate.named_crisis_anchor
        storyline_match = False
        if s_anchor and c_anchor:
            s_clean = s_anchor.strip().lower()
            c_clean = c_anchor.strip().lower()
            if s_clean in c_clean or c_clean in s_clean:
                cand_act = candidate.last_activity_at or candidate.updated_at
                story_time = (
                    (story.event_time.start_utc if story.event_time else None)
                    or story.first_article_at
                    or story.updated_at
                )
                if cand_act and story_time:
                    cand_act_utc = cand_act if cand_act.tzinfo else cand_act.replace(tzinfo=timezone.utc)
                    story_time_utc = story_time if story_time.tzinfo else story_time.replace(tzinfo=timezone.utc)
                    gap_days = abs((story_time_utc - cand_act_utc).total_seconds()) / 86400.0
                    if gap_days <= self._anchor_episode_days:
                        storyline_match = True
                else:
                    storyline_match = True

        I_storyline = 1.0 if storyline_match else 0.0

        # Structured anchor extraction
        s_actors, _s_roles, s_targets, s_actions, s_locs = self._extract_structured_anchors(story)
        c_actors, _c_roles, c_targets, c_actions, c_locs = self._extract_structured_anchors(candidate)

        shared_actors = s_actors & c_actors
        shared_targets = s_targets & c_targets
        shared_actions = s_actions & c_actions

        shared_provinces = s_locs["provinces"] & c_locs["provinces"]
        shared_districts = s_locs["districts"] & c_locs["districts"]
        shared_sub = s_locs["sub_locations"] & c_locs["sub_locations"]

        substantive_actors = {
            a for a in shared_actors
            if a not in _GENERIC_ENTITY_STOPWORDS
            and not any(r in a for r in ("นายก", "รัฐมนตรี", "ตำรวจ", "เจ้าหน้าที่", "โฆษก", "สภา", "ศาล", "พรรค"))
        }

        # Hard Veto 1: Location Conflict Veto (conflicting districts in same province, or different provinces)
        loc_conflict = has_sublocation_conflict(
            {"provinces": list(s_locs["provinces"]), "districts": list(s_locs["districts"])},
            {"provinces": list(c_locs["provinces"]), "districts": list(c_locs["districts"])},
        )
        if loc_conflict and not substantive_actors and not storyline_match:
            return 0.0

        # Hard Veto 2: Province-Only Veto (P0.1)
        # If the only geographic match is at province level with ZERO shared districts and ZERO shared sub-locations
        is_prov_only = is_province_only_match(
            {
                "provinces": list(s_locs["provinces"]),
                "districts": list(s_locs["districts"]),
                "sub_locations": list(s_locs["sub_locations"]),
            },
            {
                "provinces": list(c_locs["provinces"]),
                "districts": list(c_locs["districts"]),
                "sub_locations": list(c_locs["sub_locations"]),
            },
        )
        if is_prov_only and not substantive_actors and not storyline_match and not (shared_targets or shared_actions):
            return 0.0

        # Hard Veto 3: Disjoint events without actors, locations, or matching crisis anchor cannot merge
        if not storyline_match and not substantive_actors and not shared_districts and not shared_sub and not shared_provinces:
            return 0.0

        valid_provinces = (
            shared_provinces
            if (storyline_match or substantive_actors or shared_districts or shared_sub or shared_targets or shared_actions)
            else set()
        )
        specific_anchor_overlap = (
            len(substantive_actors)
            + len(shared_targets)
            + len(shared_actions)
            + len(shared_districts)
            + len(shared_sub)
            + len(valid_provinces)
        )
        raw_score = (
            0.55 * cos_sim
            + 0.25 * I_storyline
            + 0.20 * min(1.0, specific_anchor_overlap / 2.0)
        )
        return float(np.clip(raw_score, 0.0, 1.0))

    def _find_temporal_predecessor(
        self,
        macro: MacroEventRecord,
        current_story: StoryRecord,
    ) -> tuple[str | None, bool]:
        """
        Find chronological predecessor/successor by actual incident time, not arrival index (P0.2).
        Returns (target_event_id, is_predecessor) where is_predecessor is True if target occurred
        before current_story, or False if target occurred after current_story.
        """
        sibling_ids = [cid for cid in macro.child_event_ids if cid != current_story.story_id]
        if not sibling_ids:
            return None, True

        child_stories = self._story_repo.get_stories_by_ids(sibling_ids)
        if not child_stories:
            return None, True

        def _get_time(s: StoryRecord) -> datetime:
            t = (
                (s.event_time.start_utc if s.event_time else None)
                or s.first_article_at
                or s.updated_at
                or s.created_at
            )
            if t.tzinfo is None:
                return t.replace(tzinfo=timezone.utc)
            return t.astimezone(timezone.utc)

        current_time = _get_time(current_story)

        # Candidates that occurred strictly before or at current_time
        prior_stories = [s for s in child_stories if _get_time(s) <= current_time]
        if prior_stories:
            prior_stories.sort(key=_get_time, reverse=True)
            return prior_stories[0].story_id, True

        # Current story is an out-of-order older event arriving late:
        # Find the earliest succeeding event
        succeeding_stories = [s for s in child_stories if _get_time(s) > current_time]
        if succeeding_stories:
            succeeding_stories.sort(key=_get_time)
            return succeeding_stories[0].story_id, False

        return sibling_ids[-1], True

    def _commit_story_and_macro(
        self,
        story: StoryRecord,
        macro: MacroEventRecord,
    ) -> None:
        """
        Two-phase commit with rollback ensuring consistency between Story (SST) and MacroEvent (P0.3).
        """
        prev_macro = self._macro_repo.get_macro_event(macro.macro_event_id)
        self._macro_repo.save_macro_event(macro)
        try:
            self._story_repo.save_story(story)
        except Exception:
            logger.exception(
                "Failed to save story %s; rolling back macro %s",
                story.story_id,
                macro.macro_event_id,
            )
            if prev_macro is not None:
                self._macro_repo.save_macro_event(prev_macro)
            else:
                self._macro_repo.delete_macro_event(macro.macro_event_id)
            raise

    def assign_event(
        self,
        story: StoryRecord,
        antecedent_story_id: str | None = None,
    ) -> tuple[MacroEventRecord | None, bool]:
        """
        Assign an Event (StoryRecord) to a MacroEventRecord.

        Stage B Rules:
        - Step 0 (Authoritative Lineage): If antecedent_story_id is provided, inherit
          antecedent macro, establish directional 'updates' relation, and link with verified status.
        - Retrieval: Candidates within candidate_days (14d) PLUS anchored macros within anchor_episode_days (45d).
        - Score: Calibrated multi-signal score_macro with strict Hard Vetos.
        - Decision:
          * Top score >= link_threshold AND margin over #2 >= margin_threshold -> link MacroEventRecord.
          * Competing macros with margin < margin_threshold OR borderline [pending_threshold, link_threshold) -> pending_macro.
          * All candidates < pending_threshold -> create new MacroEventRecord.

        Returns:
            tuple[MacroEventRecord | None, bool]: (macro_event, is_new_macro)
        """
        with self._lock:
            event_time = (
                (story.event_time.start_utc if story.event_time else None)
                or story.last_article_at
                or story.first_article_at
                or story.updated_at
            )
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            # 1. Idempotency check: if story already has macro_event_id and macro exists
            if story.macro_event_id:
                existing_macro = self._macro_repo.get_macro_event(story.macro_event_id)
                if existing_macro is not None:
                    existing_macro.add_child_event(
                        event_id=story.story_id,
                        event_time=event_time,
                        entities=story.entities,
                        typed_anchors=story.typed_anchors,
                    )
                    if story.centroid:
                        existing_macro.update_centroid_ema(story.centroid, alpha=self._ema_alpha)
                    self._commit_story_and_macro(story, existing_macro)
                    return existing_macro, False

            story_vec = story.centroid

            # Step 0: Direct Follow-Up Authoritative Lineage (P0.2, P0.4)
            if antecedent_story_id and antecedent_story_id.strip():
                clean_ant_id = antecedent_story_id.strip()
                ant_story = self._story_repo.get_story(clean_ant_id)
                if ant_story is not None:
                    ant_macro: MacroEventRecord | None = None
                    if ant_story.macro_event_id:
                        ant_macro = self._macro_repo.get_macro_event(ant_story.macro_event_id)
                    if ant_macro is None:
                        ant_macro, _ = self.assign_event(ant_story)

                    if ant_macro is not None:
                        story.macro_event_id = ant_macro.macro_event_id
                        story.macro_association_status = "linked"
                        story.candidate_macro_ids = []
                        story.pending_macro_reason = None

                        ant_macro.add_child_event(
                            event_id=story.story_id,
                            event_time=event_time,
                            entities=story.entities,
                            typed_anchors=story.typed_anchors,
                        )
                        # Direction: B updates A (source=story [new], target=ant_story [old])
                        relation = EventRelationRecord(
                            source_event_id=story.story_id,
                            target_event_id=clean_ant_id,
                            relation_type="updates",
                            verification_status="verified",
                        )
                        ant_macro.add_relation(relation)
                        if story_vec:
                            ant_macro.update_centroid_ema(story_vec, alpha=self._ema_alpha)

                        self._commit_story_and_macro(story, ant_macro)
                        return ant_macro, False

            anchor = (
                (story.typed_anchors.storyline_anchor if story.typed_anchors else None)
                or self.extract_crisis_anchor(story.title, story.entities)
            )
            since_time = event_time - timedelta(days=self._candidate_days)

            # Query candidate macro-events with episode scoping
            candidates = self._macro_repo.find_candidate_macro_events(
                since_time=since_time,
                anchor=anchor,
                max_anchor_episode_days=self._anchor_episode_days,
            )

            evaluated_candidates: list[tuple[float, MacroEventRecord]] = []
            for candidate in candidates:
                score = self.score_macro(story, candidate)
                if score > 0.0:
                    evaluated_candidates.append((score, candidate))

            evaluated_candidates.sort(key=lambda item: (-item[0], item[1].macro_event_id))

            # Selection & Margin Rule Matrix (P1.1)
            if evaluated_candidates and evaluated_candidates[0][0] >= self._link_threshold:
                top_score, top_macro = evaluated_candidates[0]

                # True Margin Rule: Top candidate must beat runner-up by at least self._margin_threshold,
                # REGARDLESS of whether #2 is above or below self._link_threshold!
                if len(evaluated_candidates) >= 2:
                    runner_score, runner_macro = evaluated_candidates[1]
                    if (top_score - runner_score) < self._margin_threshold:
                        story.macro_event_id = None
                        story.macro_association_status = "pending_macro"
                        story.candidate_macro_ids = [top_macro.macro_event_id, runner_macro.macro_event_id]
                        story.pending_macro_reason = "competing_macros_margin_tie"
                        self._story_repo.save_story(story)
                        return None, False

                # Clear winner: Link to top macro
                story.macro_event_id = top_macro.macro_event_id
                story.macro_association_status = "linked"
                story.candidate_macro_ids = []
                story.pending_macro_reason = None

                if top_macro.status == "dormant":
                    top_macro.status = "active"

                top_macro.add_child_event(
                    event_id=story.story_id,
                    event_time=event_time,
                    entities=story.entities,
                    typed_anchors=story.typed_anchors,
                )

                if len(top_macro.child_event_ids) > 1:
                    target_id, is_predecessor = self._find_temporal_predecessor(top_macro, story)
                    if target_id:
                        relation_type = (
                            "updates"
                            if top_score >= self._updates_relation_threshold
                            else "precedes"
                        )
                        # Fix relation direction (P0.2)
                        if is_predecessor:
                            if relation_type == "updates":
                                source_id, dest_id = story.story_id, target_id
                            else:
                                source_id, dest_id = target_id, story.story_id
                        else:
                            source_id, dest_id = story.story_id, target_id
                            relation_type = "precedes"

                        relation = EventRelationRecord(
                            source_event_id=source_id,
                            target_event_id=dest_id,
                            relation_type=relation_type,
                            verification_status="proposed",
                        )
                        top_macro.add_relation(relation)

                if story_vec:
                    top_macro.update_centroid_ema(story_vec, alpha=self._ema_alpha)

                self._commit_story_and_macro(story, top_macro)
                return top_macro, False

            # Borderline similarity score -> Hold as pending_macro
            elif evaluated_candidates and evaluated_candidates[0][0] >= self._pending_threshold:
                top_score, top_macro = evaluated_candidates[0]
                story.macro_event_id = None
                story.macro_association_status = "pending_macro"
                story.candidate_macro_ids = [top_macro.macro_event_id]
                story.pending_macro_reason = "borderline_macro_similarity"
                self._story_repo.save_story(story)
                return None, False

            # All < pending_threshold -> Create new MacroEventRecord
            else:
                new_macro = MacroEventRecord(
                    title=anchor or story.title,
                    category=story.category or "society",
                    status="active",
                    named_crisis_anchor=anchor,
                    storyline_anchor=anchor,
                    created_at=event_time,
                    updated_at=event_time,
                    last_activity_at=event_time,
                    child_event_ids=[story.story_id],
                    relations=[],
                    centroid=list(story_vec) if story_vec else None,
                    entities=list(story.entities),
                    typed_anchors=story.typed_anchors if story.typed_anchors else TypedEventAnchors(),
                )

                story.macro_event_id = new_macro.macro_event_id
                story.macro_association_status = "new_macro"
                story.candidate_macro_ids = []
                story.pending_macro_reason = None
                self._commit_story_and_macro(story, new_macro)

                return new_macro, True

    def on_story_updated(
        self,
        story: StoryRecord,
    ) -> tuple[MacroEventRecord | None, bool]:
        """
        Propagate story updates (new articles, refreshed centroid/anchors) to enclosing MacroEvent,
        or re-evaluate pending_macro stories that now have sufficient evidence to link (P1.4).
        """
        with self._lock:
            event_time = (
                (story.event_time.start_utc if story.event_time else None)
                or story.last_article_at
                or story.first_article_at
                or story.updated_at
            )
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            # Case 1: Story is already linked to a macro
            if story.macro_event_id:
                macro = self._macro_repo.get_macro_event(story.macro_event_id)
                if macro is not None:
                    macro.add_child_event(
                        event_id=story.story_id,
                        event_time=event_time,
                        entities=story.entities,
                        typed_anchors=story.typed_anchors,
                    )
                    if story.centroid:
                        macro.update_centroid_ema(story.centroid, alpha=self._ema_alpha)
                    self._commit_story_and_macro(story, macro)
                    return macro, False

            # Case 2: Story was pending or unlinked -> re-evaluate with enriched evidence
            return self.assign_event(story)

    def reevaluate_pending_stories(self) -> dict[str, int]:
        """
        Sweep all stories currently held as 'pending_macro' and re-evaluate them (P1.4).
        """
        with self._lock:
            pending_stories = [
                s for s in self._story_repo.list_stories(limit=500)
                if getattr(s, "macro_association_status", None) == "pending_macro"
            ]
            promoted = 0
            remained = 0
            for story in pending_stories:
                res_macro, _ = self.assign_event(story)
                if res_macro is not None and story.macro_association_status == "linked":
                    promoted += 1
                else:
                    remained += 1

            return {
                "pending_found": len(pending_stories),
                "promoted_to_linked": promoted,
                "remained_pending": remained,
            }

    def reconcile_consistency(self) -> dict[str, int]:
        """
        Reconcile bidirectional consistency between StoryRecord.macro_event_id (SST)
        and MacroEventRecord.child_event_ids (P0.3).
        """
        with self._lock:
            all_stories = self._story_repo.list_stories(limit=1000)
            all_macros = {m.macro_event_id: m for m in self._macro_repo.list_macro_events(limit=500)}

            reconciled_links = 0
            orphans_removed = 0

            # 1. Check all stories and ensure macro knows about them
            for story in all_stories:
                if story.macro_event_id and story.macro_event_id in all_macros:
                    macro = all_macros[story.macro_event_id]
                    if story.story_id not in macro.child_event_ids:
                        macro.child_event_ids.append(story.story_id)
                        reconciled_links += 1

            # 2. Check all macros and remove child_ids that don't belong to them
            for macro in all_macros.values():
                valid_children: list[str] = []
                for cid in macro.child_event_ids:
                    s = self._story_repo.get_story(cid)
                    if s and s.macro_event_id == macro.macro_event_id:
                        valid_children.append(cid)
                    else:
                        orphans_removed += 1
                if len(valid_children) != len(macro.child_event_ids):
                    macro.child_event_ids = valid_children
                self._macro_repo.save_macro_event(macro)

            return {
                "stories_checked": len(all_stories),
                "reconciled_links": reconciled_links,
                "orphans_removed": orphans_removed,
            }


_macro_event_service_instance: MacroEventService | None = None
_service_lock = threading.Lock()


def get_macro_event_service(
    macro_repo: MacroEventRepositoryPort | None = None,
    story_repo: StoryRepositoryPort | None = None,
    link_threshold: float = 0.62,
    pending_threshold: float = 0.52,
    updates_relation_threshold: float = 0.70,
    margin_threshold: float = 0.05,
    candidate_days: int = 14,
    anchor_episode_days: int = 45,
    ema_alpha: float = 0.85,
) -> MacroEventService:
    """Dependency injection factory for FastAPI and worker services."""
    global _macro_event_service_instance
    with _service_lock:
        if _macro_event_service_instance is None:
            _macro_event_service_instance = MacroEventService(
                macro_repo=macro_repo,
                story_repo=story_repo,
                link_threshold=link_threshold,
                pending_threshold=pending_threshold,
                updates_relation_threshold=updates_relation_threshold,
                margin_threshold=margin_threshold,
                candidate_days=candidate_days,
                anchor_episode_days=anchor_episode_days,
                ema_alpha=ema_alpha,
            )
        return _macro_event_service_instance
