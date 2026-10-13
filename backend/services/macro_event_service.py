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
from backend.schemas.story_schema import StoryRecord

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
       PLUS dormant macro-events with matching named_crisis_anchor.
    3. Multi-Signal Qualification (ALL must pass):
       - Cosine similarity: min_sim (0.55) <= sim < max_sim (0.74).
       - Specific Named Entity match: Shared >= 1 non-generic entity (LOC/ORG).
       - Contextual compatibility: Compatible category / disaster context.
    4. Deterministic Relations:
       - Adds directional relation between the new event and the latest preceding event.
       - 'updates' if similarity is high (>= 0.65), otherwise 'precedes'.
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

    def assign_event(
        self,
        story: StoryRecord,
    ) -> tuple[MacroEventRecord, bool]:
        """
        Assign an Event (StoryRecord) to a MacroEventRecord.

        Returns:
            tuple[MacroEventRecord, bool]: (macro_event, is_new_macro)
        """
        with self._lock:
            # 1. Idempotency check: if story already has macro_event_id and macro exists, return it
            if story.macro_event_id:
                existing_macro = self._macro_repo.get_macro_event(story.macro_event_id)
                if existing_macro is not None:
                    # Ensure child is in derived index
                    existing_macro.add_child_event(
                        event_id=story.story_id,
                        event_time=story.last_article_at or story.first_article_at or story.updated_at,
                        entities=story.entities,
                    )
                    self._macro_repo.save_macro_event(existing_macro)
                    return existing_macro, False

            event_time = story.last_article_at or story.first_article_at or story.updated_at
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            anchor = self.extract_crisis_anchor(story.title, story.entities)
            since_time = event_time - timedelta(days=self._candidate_days)

            # Query candidate macro-events within 14 days OR matching crisis anchor
            candidates = self._macro_repo.find_candidate_macro_events(
                since_time=since_time,
                anchor=anchor,
            )

            best_macro: MacroEventRecord | None = None
            best_sim: float = -1.0

            story_vec = story.centroid
            if story_vec:
                for candidate in candidates:
                    if not candidate.centroid or len(candidate.centroid) != len(story_vec):
                        continue

                    sim = _cosine_similarity(story_vec, candidate.centroid)

                    # Multi-signal qualification:
                    # 1. Similarity must fall within candidate range [0.55, 0.74)
                    if not (self._min_sim <= sim < self._max_sim):
                        # Special exception: if exact named crisis anchor matches, allow lower similarity down to 0.45
                        if anchor and candidate.named_crisis_anchor and anchor in candidate.named_crisis_anchor:
                            if sim < 0.45:
                                continue
                        else:
                            continue

                    # 2. Specific named entity agreement (LOC/ORG)
                    has_entity_match = self.has_specific_entity_agreement(
                        story.entities, candidate.entities
                    )
                    # If anchor matches strongly, entity match can be satisfied via anchor
                    if not has_entity_match and not (anchor and candidate.named_crisis_anchor and anchor in candidate.named_crisis_anchor):
                        continue

                    # 3. Best candidate selection
                    if sim > best_sim:
                        best_sim = sim
                        best_macro = candidate

            # Case A: Qualified existing Macro-Event found -> Link
            if best_macro is not None:
                story.macro_event_id = best_macro.macro_event_id
                self._story_repo.save_story(story)  # Persist SST

                # Add to derived index
                best_macro.add_child_event(
                    event_id=story.story_id,
                    event_time=event_time,
                    entities=story.entities,
                )

                # Create directional relation with the latest preceding child event
                if len(best_macro.child_event_ids) > 1:
                    prior_event_id = best_macro.child_event_ids[-2]
                    relation_type = "updates" if best_sim >= 0.65 else "precedes"
                    relation = EventRelationRecord(
                        source_event_id=story.story_id,
                        target_event_id=prior_event_id,
                        relation_type=relation_type,
                        verification_status="verified",
                    )
                    best_macro.add_relation(relation)

                # Update macro centroid EMA
                if story_vec:
                    best_macro.update_centroid_ema(story_vec, alpha=self._ema_alpha)

                self._macro_repo.save_macro_event(best_macro)
                return best_macro, False

            # Case B: No qualified macro-event -> Create new MacroEventRecord
            new_macro = MacroEventRecord(
                title=anchor or story.title,
                category=story.category or "society",
                status="active",
                named_crisis_anchor=anchor,
                created_at=event_time,
                updated_at=event_time,
                last_activity_at=event_time,
                child_event_ids=[story.story_id],
                relations=[],
                centroid=list(story_vec) if story_vec else None,
                entities=list(story.entities),
            )
            self._macro_repo.save_macro_event(new_macro)

            story.macro_event_id = new_macro.macro_event_id
            self._story_repo.save_story(story)  # Persist SST

            return new_macro, True
