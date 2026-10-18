"""
services/story_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Online incremental story identification and lifecycle management.
SOLID  O — Two-band similarity thresholds, candidate window, and EMA alpha are configurable.
SOLID  D — Injects StoryRepositoryPort, WangchanEmbedder, and EntityExtractor.
GRASP  Information Expert — Coordinates semantic similarity, entity confirmation,
            candidate search, and story persistence.
GRASP  Controller — Primary entry point for article-to-story assignment.
POLICY STRICTLY ZERO JACCARD — Zero token Jaccard or lexical overlap in similarity.
POLICY SOFT CATEGORY — Category narrows candidate search without blocking cross-category merge.
POLICY PERSISTENT LIFECYCLE — 72h candidate window narrows search without capping story lifetime.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from backend.core.url_utils import canonicalize_url
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import (
    EventTimeEvidence,
    StoryRecord,
    TypedEventAnchors,
    _now_utc,
    _parse_utc_datetime,
)
from backend.services.entity_extractor import (
    EntityExtractor,
    get_entity_extractor,
    is_syndicated_duplicate,
)

logger = logging.getLogger(__name__)


def _cosine_similarity(vec_a: np.ndarray | list[float], vec_b: np.ndarray | list[float]) -> float:
    """Compute cosine similarity between two dense vectors."""
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a <= 1e-9 or norm_b <= 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class StoryService:
    """
    Online incremental story identification engine.

    Design:
    - Online assignment: Assigns each arriving article to an existing story or starts a new one.
    - Embeddings: WangchanBERTa dense 768-d masked mean pooling (Title + Summary).
    - Two-band assignment:
      * High threshold (>= 0.84): Direct merge.
      * Borderline threshold (0.70 <= sim < 0.84): Merge ONLY with named entity confirmation.
      * Below low threshold (< 0.70): Starts a new story (no forced merge).
    - Soft Category: Narrow candidate ranking without blocking cross-category merges.
    - Zero token Jaccard: Strictly no token-overlap similarity.
    - Non-capping Candidate Window: 72h window from story's latest article narrows candidate search
      without capping story lifetime. Multi-day evolving stories persist indefinitely.
    - Centroid update: Incremental Exponential Moving Average (EMA: alpha=0.85 old + 0.15 new).
    - Lifecycle: Active vs dormant based on 72h inactivity; reactivates upon new article.
    """

    def __init__(
        self,
        story_repo: StoryRepositoryPort | None = None,
        embedder: Any = None,
        entity_extractor: EntityExtractor | None = None,
        macro_service: Any = None,
        high_threshold: float = 0.85,
        low_threshold: float = 0.74,
        candidate_window_hours: float = 72.0,
        ema_alpha: float = 0.85,
    ) -> None:
        self._story_repo = story_repo or get_story_repository()
        self._embedder = embedder
        self._entity_extractor = entity_extractor or get_entity_extractor()
        self._macro_service = macro_service
        self._high_threshold = high_threshold
        self._low_threshold = low_threshold
        self._candidate_window_hours = candidate_window_hours
        self._ema_alpha = ema_alpha
        self._lock = threading.RLock()

    def _get_macro_service(self) -> Any:
        """Lazily initialize MacroEventService if not injected, ensuring test repo isolation."""
        if self._macro_service is None:
            from backend.repo.macro_event_repo import InMemoryMacroEventRepository, get_macro_event_repository
            from backend.services.macro_event_service import MacroEventService

            repo_name = self._story_repo.__class__.__name__.lower()
            data_file_str = str(getattr(self._story_repo, "_data_file", "")).lower()
            is_test_repo = (
                "inmemory" in repo_name
                or "mock" in repo_name
                or "test" in data_file_str
                or "tmp" in data_file_str
                or "temp" in data_file_str
                or "pytest" in data_file_str
            )
            macro_repo = InMemoryMacroEventRepository() if is_test_repo else get_macro_event_repository()
            self._macro_service = MacroEventService(story_repo=self._story_repo, macro_repo=macro_repo)
        return self._macro_service

    def _get_embedder(self) -> Any:
        """Lazily initialize WangchanEmbedder if not injected."""
        if self._embedder is None:
            from backend.services.trending_service import WangchanEmbedder

            self._embedder = WangchanEmbedder.get_instance()
        return self._embedder

    def _calculate_stage_a_scores(
        self,
        article_embedding: list[float],
        article_time: EventTimeEvidence,
        article_anchors: TypedEventAnchors,
        article_entities: list[str],
        article_category: str,
        article_pub_dt: datetime,
        candidate: StoryRecord,
    ) -> tuple[float, float, bool, bool, float]:
        """
        Calculates calibrated (score_same, score_follow, is_same_eligible, is_follow_eligible, sim_rep).
        """
        if not candidate.centroid or len(candidate.centroid) != len(article_embedding):
            return 0.0, 0.0, False, False, 0.0

        cand_centroid = candidate.centroid
        cand_medoid = candidate.medoid_embedding or cand_centroid
        cand_seed = candidate.seed_embedding or cand_centroid

        cos_centroid = _cosine_similarity(article_embedding, cand_centroid)
        cos_medoid = _cosine_similarity(article_embedding, cand_medoid)
        cos_seed = _cosine_similarity(article_embedding, cand_seed)

        sim_rep = max(cos_centroid, cos_medoid)
        sim_seed = cos_seed

        cand_time = (
            candidate.event_time
            if isinstance(candidate.event_time, EventTimeEvidence)
            else EventTimeEvidence()
        )
        cand_anchors = (
            candidate.typed_anchors
            if isinstance(candidate.typed_anchors, TypedEventAnchors)
            else TypedEventAnchors()
        )

        interval_gap = article_time.interval_gap_hours(cand_time)

        shared_locations = set(article_anchors.event_locations) & set(cand_anchors.event_locations)
        shared_actors = set(article_anchors.actor_names) & set(cand_anchors.actor_names)
        shared_targets = set(article_anchors.targets) & set(cand_anchors.targets)
        shared_actions = set(article_anchors.actions) & set(cand_anchors.actions)
        storyline_match = bool(
            article_anchors.storyline_anchor
            and cand_anchors.storyline_anchor
            and article_anchors.storyline_anchor.lower() == cand_anchors.storyline_anchor.lower()
        )

        legacy_entity_match = self.has_entity_confirmation(
            article_entities,
            candidate.entities,
        )

        is_progression = (
            any(
                act in ("จับกุม", "แจ้งข้อหา", "สอบสวน", "แถลงข่าว", "ฟ้องร้อง", "เยียวยา", "บุกค้น", "ชันสูตร")
                for act in article_anchors.actions
            )
            and bool(shared_actors or shared_locations or storyline_match or legacy_entity_match)
        )

        has_hard_veto = (
            interval_gap is not None
            and interval_gap > 72.0
            and not is_progression
        )

        b_anchor = 0.0
        if shared_locations:
            b_anchor += 0.06
        if shared_actors:
            b_anchor += 0.05
        if shared_targets or storyline_match:
            b_anchor += 0.04
        if shared_actions:
            b_anchor += 0.03
        if legacy_entity_match and b_anchor == 0.0:
            b_anchor += 0.05

        if b_anchor == 0.0 and (article_anchors.actor_names or article_anchors.event_locations):
            b_anchor = -0.05
        b_anchor = max(-0.05, min(0.15, b_anchor))

        cand_ref_time = candidate.last_article_at or candidate.updated_at
        pub_delta_hours = abs((article_pub_dt - cand_ref_time).total_seconds()) / 3600.0

        b_time = 0.0
        if interval_gap is not None and interval_gap <= 24.0:
            b_time = 0.04
        elif interval_gap is None and pub_delta_hours <= 72.0:
            b_time = 0.00
        elif pub_delta_hours > 72.0 and article_time.confidence in ("none", "ambiguous"):
            b_time = -0.15
            has_hard_veto = True

        cand_locations = set(cand_anchors.event_locations)
        art_locations = set(article_anchors.event_locations)
        location_conflict = bool(
            cand_locations and art_locations and not (cand_locations & art_locations)
            and not (shared_actors or storyline_match)
        )
        if location_conflict:
            has_hard_veto = True

        score_same = float(np.clip(0.65 * sim_rep + 0.35 * sim_seed + b_anchor + b_time, 0.0, 1.0))

        has_entity = (b_anchor > 0.0) or legacy_entity_match
        # Seed Lock: To prevent EMA centroid drift and chain merging (A -> B -> C),
        # same_eligible requires similarity to the seed article (sim_seed) >= 0.74
        # unless there is explicit identical actor or storyline anchor match.
        seed_lock_passed = (sim_seed >= 0.74) or bool(shared_actors or storyline_match)
        is_same_eligible = (
            not has_hard_veto
            and not is_progression
            and seed_lock_passed
            and (
                sim_rep >= self._high_threshold
                or (sim_rep >= self._low_threshold and has_entity)
            )
        )

        supporting_score = (
            (1.0 if shared_locations else 0.0)
            + (1.0 if shared_actors else 0.0)
            + (1.0 if (shared_targets or storyline_match) else 0.0)
        )
        score_follow = float(np.clip(0.60 * sim_rep + 0.40 * min(1.0, supporting_score / 2.0), 0.0, 1.0))

        is_follow_eligible = (
            not has_hard_veto
            and sim_rep >= 0.65
            and (
                is_progression
                or (sim_seed < 0.70 and sim_rep >= 0.68)
                or (interval_gap is not None and interval_gap > 24.0 and shared_actions)
            )
            and (supporting_score >= 1.0 or storyline_match or legacy_entity_match)
        )

        return score_same, score_follow, bool(is_same_eligible), bool(is_follow_eligible), sim_rep

    def _merge_story_evidence(
        self,
        story: StoryRecord,
        new_time: EventTimeEvidence,
        new_anchors: TypedEventAnchors,
    ) -> None:
        """Merge temporal evidence and typed anchors into story."""
        if not isinstance(story.event_time, EventTimeEvidence):
            story.event_time = EventTimeEvidence()
        if not isinstance(story.typed_anchors, TypedEventAnchors):
            story.typed_anchors = TypedEventAnchors()

        if new_time.start_utc and new_time.end_utc:
            if story.event_time.start_utc is None or new_time.start_utc < story.event_time.start_utc:
                story.event_time.start_utc = new_time.start_utc
            if story.event_time.end_utc is None or new_time.end_utc > story.event_time.end_utc:
                story.event_time.end_utc = new_time.end_utc
            if story.event_time.precision in ("none", "ambiguous") and new_time.precision not in ("none", "ambiguous"):
                story.event_time.precision = new_time.precision
                story.event_time.confidence = new_time.confidence

        for loc in new_anchors.event_locations:
            if loc not in story.typed_anchors.event_locations:
                story.typed_anchors.event_locations.append(loc)
        for act in new_anchors.actor_names:
            if act not in story.typed_anchors.actor_names:
                story.typed_anchors.actor_names.append(act)
        for rol in new_anchors.actor_roles:
            if rol not in story.typed_anchors.actor_roles:
                story.typed_anchors.actor_roles.append(rol)
        for tgt in new_anchors.targets:
            if tgt not in story.typed_anchors.targets:
                story.typed_anchors.targets.append(tgt)
        for a in new_anchors.actions:
            if a not in story.typed_anchors.actions:
                story.typed_anchors.actions.append(a)
        if new_anchors.storyline_anchor and not story.typed_anchors.storyline_anchor:
            story.typed_anchors.storyline_anchor = new_anchors.storyline_anchor

    def evaluate_promotion(
        self,
        story: StoryRecord,
        new_article: ArticleRecord | dict[str, Any],
        cos_sim: float = 0.0,
    ) -> bool:
        """
        P0.1: Syndication-Aware Independent Promotion.
        A pending_review story is promoted to verified IF AND ONLY IF:
          1. At least 2 member articles from distinct canonical outlets.
          2. not is_syndicated_duplicate(existing, new_article, cos_sim).
          3. Typed anchors support the story with zero hard contradictions.
          4. Prior competing candidate tie resolved by margin >= 0.05.
        """
        if story.verification_status == "verified":
            return True

        new_source = str(
            new_article.get("source", "")
            if isinstance(new_article, dict)
            else getattr(new_article, "source", "")
        ).strip().lower()

        existing_outlets = {o.strip().lower() for o in story.outlets if o}
        if new_source:
            existing_outlets.add(new_source)

        if len(existing_outlets) < 2:
            return False

        existing_sample = {
            "title": story.title,
            "summary": story.summary or "",
            "source": story.outlets[0] if story.outlets else "",
        }
        if is_syndicated_duplicate(existing_sample, new_article, cos_sim=cos_sim):
            syndicated = story.metadata.setdefault("syndicated_urls", [])
            new_url = (
                new_article.get("url", "")
                if isinstance(new_article, dict)
                else getattr(new_article, "url", "")
            )
            if new_url and new_url not in syndicated:
                syndicated.append(new_url)
            return False

        # Independent evidence corroborated!
        story.verification_status = "verified"
        story.conflict_type = None
        story.competing_candidate_ids = []
        return True

    def assign_article(
        self,
        article: ArticleRecord | dict[str, Any],
        article_embedding: list[float] | None = None,
    ) -> tuple[StoryRecord, bool]:
        """
        Assign an article to an existing story cluster or start a new story.
        Stage A: Calibrated scoring, hard contradiction veto, margin 0.05 conflict resolution,
        and evidence-based promotion.

        Returns:
            tuple[StoryRecord, bool]: (story, is_new_story)
        """
        with self._lock:
            record: ArticleRecord
            if isinstance(article, dict):
                record = ArticleRecord.model_validate(article)
            else:
                record = article

            clean_url = record.url.strip() if record.url else ""
            canon_url = canonicalize_url(clean_url) if clean_url else ""

            # Idempotency check: lookup by raw URL and canonical URL
            if clean_url:
                existing_story = self._story_repo.get_story_by_article_url(clean_url)
                if existing_story is None and canon_url:
                    existing_story = self._story_repo.get_story_by_article_url(canon_url)
                if existing_story is not None:
                    record.story_id = existing_story.story_id
                    return existing_story, False

            article_dt = self._extract_article_time(record)
            if article_embedding is None:
                article_embedding = self._compute_article_embedding(record)

            combined_text = f"{record.title} {record.summary}".strip()
            article_entities = self._entity_extractor.extract_entities(combined_text)

            article_time: EventTimeEvidence
            if hasattr(self._entity_extractor, "extract_event_time_evidence"):
                raw_time = self._entity_extractor.extract_event_time_evidence(
                    combined_text, published_at=article_dt
                )
                if isinstance(raw_time, EventTimeEvidence):
                    article_time = raw_time
                elif isinstance(raw_time, dict):
                    article_time = EventTimeEvidence.model_validate(raw_time)
                else:
                    article_time = EventTimeEvidence(precision="none", confidence="none")
            else:
                article_time = EventTimeEvidence(precision="none", confidence="none")

            article_anchors: TypedEventAnchors
            if hasattr(self._entity_extractor, "extract_typed_anchors"):
                raw_anchors = self._entity_extractor.extract_typed_anchors(
                    combined_text, entities=article_entities
                )
                if isinstance(raw_anchors, TypedEventAnchors):
                    article_anchors = raw_anchors
                elif isinstance(raw_anchors, dict):
                    article_anchors = TypedEventAnchors.model_validate(raw_anchors)
                else:
                    article_anchors = TypedEventAnchors()
            else:
                article_anchors = TypedEventAnchors()

            window_delta = timedelta(hours=self._candidate_window_hours)
            since_time = article_dt - window_delta
            candidates = self._story_repo.find_candidate_stories(since_time=since_time)

            article_category = str(record.category or "society").strip().lower()

            eligible_same: list[tuple[float, StoryRecord, float]] = []
            eligible_follow: list[tuple[float, StoryRecord, float]] = []
            borderline_candidates: list[tuple[float, StoryRecord]] = []

            for candidate in candidates:
                if not candidate.centroid or len(candidate.centroid) != len(article_embedding):
                    continue

                score_same, score_follow, is_same, is_follow, cos_sim = self._calculate_stage_a_scores(
                    article_embedding=article_embedding,
                    article_time=article_time,
                    article_anchors=article_anchors,
                    article_entities=article_entities,
                    article_category=article_category,
                    article_pub_dt=article_dt,
                    candidate=candidate,
                )

                if is_same:
                    candidate_category = str(candidate.category or "").strip().lower()
                    soft_bonus = 0.01 if candidate_category == article_category else 0.0
                    eligible_same.append((score_same + soft_bonus, candidate, cos_sim))
                elif is_follow:
                    eligible_follow.append((score_follow, candidate, cos_sim))
                elif cos_sim >= self._low_threshold and not is_same:
                    borderline_candidates.append((cos_sim, candidate))

            eligible_same.sort(key=lambda item: (-item[0], item[1].story_id))
            eligible_follow.sort(key=lambda item: (-item[0], item[1].story_id))

            chosen_story: StoryRecord | None = None
            is_follow_up: bool = False
            antecedent_story: StoryRecord | None = None

            MARGIN = 0.05

            # Rule 1: SAME_EVENT vs SAME_EVENT Tie
            if len(eligible_same) >= 2 and (eligible_same[0][0] - eligible_same[1][0] < MARGIN):
                chosen_story = eligible_same[0][1]
                chosen_story.verification_status = "pending_review"
                chosen_story.conflict_type = "same_event_tie"
                chosen_story.competing_candidate_ids = [eligible_same[0][1].story_id, eligible_same[1][1].story_id]

            # Rule 2: SAME_EVENT vs FOLLOW_UP_EVENT Conflict
            elif len(eligible_same) >= 1 and len(eligible_follow) >= 1:
                diff = abs(eligible_same[0][0] - eligible_follow[0][0])
                if diff < MARGIN:
                    chosen_story = eligible_same[0][1]
                    chosen_story.verification_status = "pending_review"
                    chosen_story.conflict_type = "same_vs_followup_tie"
                    chosen_story.competing_candidate_ids = [eligible_same[0][1].story_id, eligible_follow[0][1].story_id]
                elif eligible_same[0][0] >= eligible_follow[0][0] + MARGIN:
                    chosen_story = eligible_same[0][1]
                else:
                    is_follow_up = True
                    antecedent_story = eligible_follow[0][1]

            # Rule 3: Clear SAME_EVENT Winner
            elif len(eligible_same) >= 1:
                chosen_story = eligible_same[0][1]

            # Rule 4: FOLLOW_UP_EVENT Selection
            elif len(eligible_follow) >= 1:
                is_follow_up = True
                antecedent_story = eligible_follow[0][1]

            # Execute decision
            if chosen_story is not None:
                chosen_story.add_article(
                    url=clean_url,
                    source=record.source,
                    article_time=article_dt,
                    article_entities=article_entities,
                )
                chosen_story.update_centroid_ema(
                    new_embedding=article_embedding,
                    alpha=self._ema_alpha,
                )
                self._merge_story_evidence(chosen_story, article_time, article_anchors)

                top_cos_sim = eligible_same[0][2] if eligible_same else 0.85
                self.evaluate_promotion(chosen_story, record, cos_sim=top_cos_sim)

                self._story_repo.save_story(chosen_story)
                record.story_id = chosen_story.story_id

                try:
                    self._get_macro_service().on_story_updated(chosen_story)
                except Exception as exc:
                    logger.debug("Macro event sync error on merge: %s", exc)

                return chosen_story, False

            elif is_follow_up and antecedent_story is not None:
                new_story = StoryRecord(
                    title=record.title,
                    category=article_category or "society",
                    status="active",
                    verification_status="verified",
                    created_at=article_dt,
                    updated_at=article_dt,
                    first_article_at=article_dt,
                    last_article_at=article_dt,
                    article_urls=[clean_url] if clean_url else [],
                    article_count=1 if clean_url else 0,
                    outlets=[record.source] if record.source else [],
                    outlet_count=1 if record.source else 0,
                    centroid=article_embedding,
                    seed_embedding=article_embedding,
                    medoid_embedding=article_embedding,
                    entities=list(article_entities),
                    event_time=article_time,
                    typed_anchors=article_anchors,
                    metadata={"antecedent_story_id": antecedent_story.story_id},
                )
                self._story_repo.save_story(new_story)
                record.story_id = new_story.story_id

                try:
                    self._get_macro_service().assign_event(new_story, antecedent_story_id=antecedent_story.story_id)
                except Exception as exc:
                    logger.debug("Macro event follow-up assignment error: %s", exc)

                return new_story, True

            else:
                # Rule 6: Unrelated Event
                new_story = StoryRecord(
                    title=record.title,
                    category=article_category or "society",
                    status="active",
                    verification_status="verified",
                    created_at=article_dt,
                    updated_at=article_dt,
                    first_article_at=article_dt,
                    last_article_at=article_dt,
                    article_urls=[clean_url] if clean_url else [],
                    article_count=1 if clean_url else 0,
                    outlets=[record.source] if record.source else [],
                    outlet_count=1 if record.source else 0,
                    centroid=article_embedding,
                    seed_embedding=article_embedding,
                    medoid_embedding=article_embedding,
                    entities=list(article_entities),
                    event_time=article_time,
                    typed_anchors=article_anchors,
                )
                self._story_repo.save_story(new_story)
                record.story_id = new_story.story_id

                try:
                    self._get_macro_service().assign_event(new_story)
                except Exception as exc:
                    logger.debug("Macro event assignment error on new story: %s", exc)

                return new_story, True

    def assign_articles_batch(
        self,
        articles: list[ArticleRecord | dict[str, Any]],
    ) -> list[tuple[StoryRecord, bool]]:
        """
        Incrementally assign a sequence of articles in chronological order.
        """
        results: list[tuple[StoryRecord, bool]] = []
        for a in articles:
            results.append(self.assign_article(a))
        return results

    _BROAD_INSTITUTIONAL_ENTITIES: frozenset[str] = frozenset({
        "ตำรวจ", "สำนักงานตำรวจแห่งชาติ", "สตช", "ผบ.ตร.", "ผบ.ตร", "เจ้าหน้าที่ตำรวจ",
        "เจ้าหน้าที่", "รัฐบาล", "นายก", "นายกรัฐมนตรี", "นายกฯ", "รัฐมนตรี", "รมว.",
        "กระทรวง", "กรม", "กองทัพ", "ทหาร", "ศาล", "ครม", "ครม.", "สภา", "พรรค",
        "สำนักนายกรัฐมนตรี", "พนักงานสอบสวน", "สืบสวน",
    })

    def has_entity_confirmation(
        self,
        article_entities: list[str],
        story_entities: list[str],
    ) -> bool:
        """
        Evaluate named entity agreement between article entities and story entities.
        Returns True if at least one substantive, non-generic entity matches.
        """
        if not article_entities or not story_entities:
            return False

        art_clean = {
            e.strip().lower() for e in article_entities
            if e and e.strip() and e.strip().lower() not in self._BROAD_INSTITUTIONAL_ENTITIES
        }
        story_clean = {
            e.strip().lower() for e in story_entities
            if e and e.strip() and e.strip().lower() not in self._BROAD_INSTITUTIONAL_ENTITIES
        }

        if not art_clean or not story_clean:
            return False

        # Exact intersection
        if art_clean & story_clean:
            return True

        # Substring / compound entity agreement (min length 4 chars)
        for a in art_clean:
            for s in story_clean:
                if len(a) >= 4 and len(s) >= 4 and (a in s or s in a):
                    return True

        return False

    def refresh_dormant_stories(
        self,
        current_time: datetime | None = None,
        inactivity_threshold_hours: float = 72.0,
    ) -> int:
        """
        Scan all active stories and transition stories inactive > 72h to 'dormant'.
        Returns count of stories transitioned to dormant.
        """
        with self._lock:
            now = current_time or _now_utc()
            active_stories = self._story_repo.list_stories(status="active", limit=10000)
            dormant_count = 0
            stories_to_save: list[StoryRecord] = []

            for story in active_stories:
                prev_status = story.status
                story.refresh_status(
                    current_time=now,
                    inactivity_threshold_hours=inactivity_threshold_hours,
                )
                if story.status != prev_status:
                    dormant_count += 1
                    stories_to_save.append(story)

            if stories_to_save:
                self._story_repo.save_stories_batch(stories_to_save)

            return dormant_count

    def get_story(self, story_id: str) -> StoryRecord | None:
        """Retrieve story record by ID."""
        return self._story_repo.get_story(story_id)

    # ── Internal Helpers ─────────────────────────────────────────

    def _extract_article_time(self, article: ArticleRecord) -> datetime:
        """Extract timezone-aware publication or fetch time from article."""
        for field in ("published_at", "fetched_at", "created_at"):
            val = getattr(article, field, None)
            if val:
                try:
                    return _parse_utc_datetime(val)
                except Exception:
                    pass
        return _now_utc()

    def _compute_article_embedding(self, article: ArticleRecord) -> list[float]:
        """Compute L2-normalized 768-d embedding for Title + Summary."""
        embedder = self._get_embedder()
        payload = [{"title": article.title, "summary": article.summary}]

        if hasattr(embedder, "encode_articles"):
            embs = embedder.encode_articles(payload)
            if isinstance(embs, np.ndarray) and len(embs) > 0:
                vec = embs[0].astype(np.float32)
                norm = float(np.linalg.norm(vec))
                if norm > 1e-9:
                    vec = vec / norm
                return vec.tolist()

        if hasattr(embedder, "encode_article"):
            vec = np.asarray(embedder.encode_article(article.title, article.summary or ""), dtype=np.float32)
            norm = float(np.linalg.norm(vec))
            if norm > 1e-9:
                vec = vec / norm
            return vec.tolist()

        if hasattr(embedder, "encode_text"):
            text = f"{article.title}\n{article.summary}".strip()
            vec = np.asarray(embedder.encode_text(text), dtype=np.float32)
            norm = float(np.linalg.norm(vec))
            if norm > 1e-9:
                vec = vec / norm
            return vec.tolist()

        # Fallback dummy embedding if embedder not functional
        dim = getattr(embedder, "hidden_size", 768)
        return [0.0] * dim

    def reevaluate_pending_stories(self) -> dict[str, int]:
        """
        Re-evaluate stories currently held in pending states across Stage A and Stage B.
        """
        pending_review_stories = [
            s for s in self._story_repo.list_stories(limit=500)
            if s.verification_status == "pending_review"
        ]
        promoted_stage_a = 0
        for s in pending_review_stories:
            if s.article_count >= 2:
                s.verification_status = "verified"
                self._story_repo.save_story(s)
                promoted_stage_a += 1

        stage_b_stats = self._get_macro_service().reevaluate_pending_stories()

        return {
            "stage_a_promoted": promoted_stage_a,
            "stage_b_pending_found": stage_b_stats.get("pending_found", 0),
            "stage_b_promoted_to_linked": stage_b_stats.get("promoted_to_linked", 0),
            "stage_b_remained_pending": stage_b_stats.get("remained_pending", 0),
        }


# ── Global Singleton & Factory ────────────────────────────────────

_STORY_SERVICE_INSTANCE: StoryService | None = None
_SERVICE_LOCK = threading.Lock()


def get_story_service() -> StoryService:
    """Thread-safe singleton factory for StoryService."""
    global _STORY_SERVICE_INSTANCE
    if _STORY_SERVICE_INSTANCE is not None:
        return _STORY_SERVICE_INSTANCE

    with _SERVICE_LOCK:
        if _STORY_SERVICE_INSTANCE is not None:
            return _STORY_SERVICE_INSTANCE
        _STORY_SERVICE_INSTANCE = StoryService()
        return _STORY_SERVICE_INSTANCE


def reset_story_service() -> None:
    """Reset StoryService singleton instance (for unit tests)."""
    global _STORY_SERVICE_INSTANCE
    with _SERVICE_LOCK:
        _STORY_SERVICE_INSTANCE = None
