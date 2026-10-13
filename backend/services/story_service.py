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

from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import StoryRecord, _now_utc, _parse_utc_datetime
from backend.services.entity_extractor import EntityExtractor, get_entity_extractor

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
        high_threshold: float = 0.84,
        low_threshold: float = 0.70,
        candidate_window_hours: float = 72.0,
        ema_alpha: float = 0.85,
    ) -> None:
        self._story_repo = story_repo or get_story_repository()
        self._embedder = embedder
        self._entity_extractor = entity_extractor or get_entity_extractor()
        self._high_threshold = high_threshold
        self._low_threshold = low_threshold
        self._candidate_window_hours = candidate_window_hours
        self._ema_alpha = ema_alpha
        self._lock = threading.RLock()

    def _get_embedder(self) -> Any:
        """Lazily initialize WangchanEmbedder if not injected."""
        if self._embedder is None:
            from backend.services.trending_service import WangchanEmbedder

            self._embedder = WangchanEmbedder.get_instance()
        return self._embedder

    def assign_article(
        self,
        article: ArticleRecord | dict[str, Any],
    ) -> tuple[StoryRecord, bool]:
        """
        Assign an article to an existing story cluster or start a new story.

        Returns:
            tuple[StoryRecord, bool]: (story, is_new_story)
        """
        with self._lock:
            # Normalize article record
            record: ArticleRecord
            if isinstance(article, dict):
                record = ArticleRecord.model_validate(article)
            else:
                record = article

            clean_url = record.url.strip() if record.url else ""

            # Idempotency check: if article already assigned to a story, return it
            if clean_url:
                existing_story = self._story_repo.get_story_by_article_url(clean_url)
                if existing_story is not None:
                    record.story_id = existing_story.story_id
                    return existing_story, False

            # Determine article timestamp
            article_dt = self._extract_article_time(record)

            # Compute article embedding
            article_embedding = self._compute_article_embedding(record)

            # Extract named entities from Title + Summary
            combined_text = f"{record.title} {record.summary}".strip()
            article_entities = self._entity_extractor.extract_entities(combined_text)

            # Query candidate stories within the 72h candidate window
            window_delta = timedelta(hours=self._candidate_window_hours)
            since_time = article_dt - window_delta

            # Soft category: search all candidates within window to NEVER block cross-category merges
            candidates = self._story_repo.find_candidate_stories(since_time=since_time)

            best_candidate: StoryRecord | None = None
            best_score: float = -1.0

            article_category = str(record.category or "society").strip().lower()

            for candidate in candidates:
                if not candidate.centroid or len(candidate.centroid) != len(article_embedding):
                    continue

                # Cosine similarity between article embedding and story centroid
                cos_sim = _cosine_similarity(article_embedding, candidate.centroid)

                # Check eligibility under two-band matching
                is_eligible = False
                has_entity_match = False

                if cos_sim >= self._high_threshold:
                    # High similarity: direct merge
                    is_eligible = True
                elif cos_sim >= self._low_threshold:
                    # Borderline similarity: requires named entity confirmation
                    has_entity_match = self.has_entity_confirmation(
                        article_entities, candidate.entities
                    )
                    if has_entity_match:
                        is_eligible = True
                else:
                    # Below low threshold: not eligible
                    is_eligible = False

                if not is_eligible:
                    continue

                # Soft category signal: small affinity bonus for same category
                # to break ties / rank, but NEVER blocks cross-category merge
                candidate_category = str(candidate.category or "").strip().lower()
                soft_bonus = 0.01 if candidate_category == article_category else 0.0
                effective_score = cos_sim + soft_bonus

                if effective_score > best_score:
                    best_score = effective_score
                    best_candidate = candidate

            if best_candidate is not None:
                # Merge into existing story
                best_candidate.add_article(
                    url=clean_url,
                    source=record.source,
                    article_time=article_dt,
                    article_entities=article_entities,
                )
                best_candidate.update_centroid_ema(
                    new_embedding=article_embedding,
                    alpha=self._ema_alpha,
                )
                self._story_repo.save_story(best_candidate)
                record.story_id = best_candidate.story_id
                return best_candidate, False

            # No confident match: start a new story
            new_story = StoryRecord(
                title=record.title,
                category=article_category or "society",
                status="active",
                created_at=article_dt,
                updated_at=article_dt,
                first_article_at=article_dt,
                last_article_at=article_dt,
                article_urls=[clean_url] if clean_url else [],
                article_count=1 if clean_url else 0,
                outlets=[record.source] if record.source else [],
                outlet_count=1 if record.source else 0,
                centroid=article_embedding,
                entities=list(article_entities),
            )
            self._story_repo.save_story(new_story)
            record.story_id = new_story.story_id
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

    def has_entity_confirmation(
        self,
        article_entities: list[str],
        story_entities: list[str],
    ) -> bool:
        """
        Evaluate named entity agreement between article entities and story entities.
        Returns True if at least one entity matches or shares substantive overlap.
        """
        if not article_entities or not story_entities:
            return False

        art_clean = {e.strip().lower() for e in article_entities if e and e.strip()}
        story_clean = {e.strip().lower() for e in story_entities if e and e.strip()}

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
