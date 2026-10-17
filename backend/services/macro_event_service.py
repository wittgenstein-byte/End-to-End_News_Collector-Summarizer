"""
services/macro_event_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Macro-Event / Storyline identification and event relationship linking.
SOLID  O — Configurable macro candidate window, similarity bands, and EMA alpha.
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
from datetime import timedelta, timezone

import numpy as np

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


def _cosine_similarity(vec_a: np.ndarray | list[float], vec_b: np.ndarray | list[float]) -> float:
    """Compute cosine similarity between two dense vectors."""
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a <= 1e-9 or norm_b <= 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class MacroEventService:
    """
    Orchestrator for Macro-Event Storylines and Event Relations.

    Rules:
    1. Staged Pipeline: Only called after StoryService has determined the StoryRecord (Event).
    2. Candidate Retrieval: Considers macro-events within candidate_days (default 14 days)
       PLUS dormant macro-events with matching storyline/crisis anchor.
    3. Multi-Signal Qualification (Calibrated score_macro):
       - Cosine similarity between 768-d centroids.
       - Storyline crisis / campaign anchor matching.
       - Specific named entity / anchor agreement (actors, targets, locations).
       - Hard Veto: Excludes pairs sharing solely generic roles or a single province name.
    4. Deterministic Relations:
       - Follow-up stories inherit antecedent macro with 'updates' relation (Step 0).
       - Direct atomic events add directional relation with the latest preceding event.
    5. Single Source of Truth: Updates story.macro_event_id and saves both records atomically.
    """

    def __init__(
        self,
        macro_repo: MacroEventRepositoryPort | None = None,
        story_repo: StoryRepositoryPort | None = None,
        min_sim: float = 0.55,
        max_sim: float = 0.74,
        candidate_days: int = 14,
        ema_alpha: float = 0.85,
    ) -> None:
        self._macro_repo = macro_repo or get_macro_event_repository()
        self._story_repo = story_repo or get_story_repository()
        self._min_sim = min_sim
        self._max_sim = max_sim
        self._candidate_days = candidate_days
        self._ema_alpha = ema_alpha
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

    def score_macro(
        self,
        story: StoryRecord,
        candidate: MacroEventRecord,
    ) -> float:
        """
        Compute calibrated macro-event compatibility score in [0.0, 1.0].
        Applies Hard Veto if shared anchors consist solely of actor_roles or
        a single province name without shared targets, actions, or storyline_anchor.
        """
        # Cosine similarity between 768-d centroids
        story_vec = story.centroid
        cand_vec = candidate.centroid
        cos_sim = 0.0
        if story_vec and cand_vec and len(story_vec) == len(cand_vec):
            cos_sim = _cosine_similarity(story_vec, cand_vec)

        # Storyline / crisis anchor match
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
                storyline_match = True

        I_storyline = 1.0 if storyline_match else 0.0

        # Anchor overlap evaluation
        s_actors: set[str] = set()
        s_roles: set[str] = set()
        s_targets: set[str] = set()
        s_actions: set[str] = set()
        s_locs: set[str] = set()

        if story.typed_anchors:
            s_actors.update(a.strip().lower() for a in story.typed_anchors.actor_names if a.strip())
            s_roles.update(r.strip().lower() for r in story.typed_anchors.actor_roles if r.strip())
            s_targets.update(t.strip().lower() for t in story.typed_anchors.targets if t.strip())
            s_actions.update(a.strip().lower() for a in story.typed_anchors.actions if a.strip())
            s_locs.update(l.strip().lower() for l in story.typed_anchors.event_locations if l.strip())

        for e in story.entities:
            clean_e = e.strip().lower()
            if clean_e and clean_e not in _GENERIC_ENTITY_STOPWORDS:
                if any(clean_e.startswith(p) for p in ("จ.", "อ.", "ต.", "ถ.", "แยก", "สะพาน", "แม่น้ำ", "เกาะ", "วัด")):
                    s_locs.add(clean_e)
                else:
                    s_actors.add(clean_e)

        c_actors: set[str] = set()
        c_roles: set[str] = set()
        c_targets: set[str] = set()
        c_actions: set[str] = set()
        c_locs: set[str] = set()

        if candidate.typed_anchors:
            c_actors.update(a.strip().lower() for a in candidate.typed_anchors.actor_names if a.strip())
            c_roles.update(r.strip().lower() for r in candidate.typed_anchors.actor_roles if r.strip())
            c_targets.update(t.strip().lower() for t in candidate.typed_anchors.targets if t.strip())
            c_actions.update(a.strip().lower() for a in candidate.typed_anchors.actions if a.strip())
            c_locs.update(l.strip().lower() for l in candidate.typed_anchors.event_locations if l.strip())

        for e in candidate.entities:
            clean_e = e.strip().lower()
            if clean_e and clean_e not in _GENERIC_ENTITY_STOPWORDS:
                if any(clean_e.startswith(p) for p in ("จ.", "อ.", "ต.", "ถ.", "แยก", "สะพาน", "แม่น้ำ", "เกาะ", "วัด")):
                    c_locs.add(clean_e)
                else:
                    c_actors.add(clean_e)

        shared_actors = s_actors & c_actors
        shared_targets = s_targets & c_targets
        shared_actions = s_actions & c_actions
        shared_locs = s_locs & c_locs

        # Hard Veto: If shared anchors consist solely of actor_roles or a single province name
        # without shared targets, actions, or storyline_anchor
        if not storyline_match and not shared_targets and not shared_actions:
            substantive_actors = {
                a for a in shared_actors
                if a not in _GENERIC_ENTITY_STOPWORDS
                and not any(r in a for r in ("นายก", "รัฐมนตรี", "ตำรวจ", "เจ้าหน้าที่", "โฆษก", "สภา", "ศาล", "พรรค"))
            }
            substantive_locs = {
                l for l in shared_locs
                if l not in _GENERIC_ENTITY_STOPWORDS
            }
            if not substantive_actors and len(substantive_locs) <= 1:
                return 0.0

        specific_anchor_overlap = len(shared_actors) + len(shared_targets) + len(shared_locs)
        raw_score = (
            0.55 * cos_sim
            + 0.25 * I_storyline
            + 0.20 * min(1.0, specific_anchor_overlap / 2.0)
        )
        return float(np.clip(raw_score, 0.0, 1.0))

    def assign_event(
        self,
        story: StoryRecord,
        antecedent_story_id: str | None = None,
    ) -> tuple[MacroEventRecord | None, bool]:
        """
        Assign an Event (StoryRecord) to a MacroEventRecord.

        Stage B Rules:
        - Step 0 (Authoritative Lineage): If antecedent_story_id is provided, inherit
          the antecedent story's macro event, establish an 'updates' relation, and link.
        - Retrieval: Candidates within candidate_days (14d) PLUS anchored long-running macros.
        - Score: Calibrated multi-signal score_macro with hard veto against generic roles / single province.
        - Decision:
          * Top score >= 0.62 and margin over #2 >= 0.05 -> link MacroEventRecord.
          * Competing macros >= 0.62 with margin < 0.05, OR borderline [0.52, 0.62) -> hold as pending_macro.
          * All candidates < 0.52 -> create new MacroEventRecord.

        Returns:
            tuple[MacroEventRecord | None, bool]: (macro_event, is_new_macro)
        """
        with self._lock:
            event_time = story.last_article_at or story.first_article_at or story.updated_at
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            # 1. Idempotency check: if story already has macro_event_id and macro exists, return it
            if story.macro_event_id:
                existing_macro = self._macro_repo.get_macro_event(story.macro_event_id)
                if existing_macro is not None:
                    # Ensure child is in derived index
                    existing_macro.add_child_event(
                        event_id=story.story_id,
                        event_time=event_time,
                        entities=story.entities,
                    )
                    self._macro_repo.save_macro_event(existing_macro)
                    return existing_macro, False

            story_vec = story.centroid

            # Step 0: Direct Follow-Up Authoritative Lineage (P0.4)
            if antecedent_story_id and antecedent_story_id.strip():
                clean_ant_id = antecedent_story_id.strip()
                ant_story = self._story_repo.get_story(clean_ant_id)
                if ant_story is not None:
                    ant_macro: MacroEventRecord | None = None
                    if ant_story.macro_event_id:
                        ant_macro = self._macro_repo.get_macro_event(ant_story.macro_event_id)
                    if ant_macro is None:
                        # Antecedent story does not yet have a macro event; create one for it first
                        ant_macro, _ = self.assign_event(ant_story)

                    if ant_macro is not None:
                        story.macro_event_id = ant_macro.macro_event_id
                        story.macro_association_status = "linked"
                        story.candidate_macro_ids = []
                        story.pending_macro_reason = None
                        self._story_repo.save_story(story)

                        ant_macro.add_child_event(
                            event_id=story.story_id,
                            event_time=event_time,
                            entities=story.entities,
                        )
                        relation = EventRelationRecord(
                            source_event_id=story.story_id,
                            target_event_id=clean_ant_id,
                            relation_type="updates",
                            verification_status="verified",
                        )
                        ant_macro.add_relation(relation)
                        if story_vec:
                            ant_macro.update_centroid_ema(story_vec, alpha=self._ema_alpha)

                        self._macro_repo.save_macro_event(ant_macro)
                        return ant_macro, False

            anchor = (
                (story.typed_anchors.storyline_anchor if story.typed_anchors else None)
                or self.extract_crisis_anchor(story.title, story.entities)
            )
            since_time = event_time - timedelta(days=self._candidate_days)

            # Query candidate macro-events within 14 days OR matching crisis anchor
            candidates = self._macro_repo.find_candidate_macro_events(
                since_time=since_time,
                anchor=anchor,
            )

            # Score all candidate macros with calibrated multi-signal score_macro
            evaluated_candidates: list[tuple[float, MacroEventRecord]] = []
            for candidate in candidates:
                score = self.score_macro(story, candidate)
                if score > 0.0:
                    evaluated_candidates.append((score, candidate))

            evaluated_candidates.sort(key=lambda item: (-item[0], item[1].macro_event_id))

            # Selection & Tie Resolution Matrix
            # 1. Top score >= 0.62
            if evaluated_candidates and evaluated_candidates[0][0] >= 0.62:
                top_score, top_macro = evaluated_candidates[0]
                # Tie Check: Competing macros >= 0.62 with margin < 0.05
                if len(evaluated_candidates) >= 2 and evaluated_candidates[1][0] >= 0.62:
                    runner_score, runner_macro = evaluated_candidates[1]
                    if (top_score - runner_score) < 0.05:
                        # Hold as pending_macro
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
                self._story_repo.save_story(story)

                if top_macro.status == "dormant":
                    top_macro.status = "active"

                top_macro.add_child_event(
                    event_id=story.story_id,
                    event_time=event_time,
                    entities=story.entities,
                )

                if len(top_macro.child_event_ids) > 1:
                    prior_event_id = top_macro.child_event_ids[-2]
                    relation_type = "updates" if top_score >= 0.70 else "precedes"
                    relation = EventRelationRecord(
                        source_event_id=story.story_id,
                        target_event_id=prior_event_id,
                        relation_type=relation_type,
                        verification_status="verified",
                    )
                    top_macro.add_relation(relation)

                if story_vec:
                    top_macro.update_centroid_ema(story_vec, alpha=self._ema_alpha)

                self._macro_repo.save_macro_event(top_macro)
                return top_macro, False

            # 2. Borderline (0.52 <= top_score < 0.62) -> Hold as pending_macro
            elif evaluated_candidates and evaluated_candidates[0][0] >= 0.52:
                top_score, top_macro = evaluated_candidates[0]
                story.macro_event_id = None
                story.macro_association_status = "pending_macro"
                story.candidate_macro_ids = [top_macro.macro_event_id]
                story.pending_macro_reason = "borderline_macro_similarity"
                self._story_repo.save_story(story)
                return None, False

            # 3. All < 0.52 or no candidates -> Create new MacroEventRecord
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
                self._macro_repo.save_macro_event(new_macro)

                story.macro_event_id = new_macro.macro_event_id
                story.macro_association_status = "new_macro"
                story.candidate_macro_ids = []
                story.pending_macro_reason = None
                self._story_repo.save_story(story)

                return new_macro, True

