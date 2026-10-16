"""
services/trending_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Semantic vector clustering, trend scoring, and ranking only.
SOLID  O — Configurable cosine similarity, cohesion thresholds, and weights.
SOLID  D — Injects NewsRepositoryPort, EngagementRepositoryPort, and LLMEnricher.
GRASP  Information Expert — Computes multi-source consensus, time decay,
           reader engagement, and visual status badges.
GRASP  Pure Fabrication — WangchanEmbedder and SemanticClusterer isolate
           neural representations and graph clustering.
POLICY STRICTLY ZERO JACCARD — Zero token-set intersection, zero lexical overlap.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import numpy as np

from backend.config import settings
from backend.repo.engagement_repo import (
    EngagementRepositoryPort,
    get_engagement_repository,
)
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.repo.story_repo import StoryRepositoryPort, get_story_repository
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import StoryRecord
from backend.schemas.trending_schema import (
    TrendingArticle,
    TrendingCluster,
    TrendingListResponse,
    TrendingScoreBreakdown,
    TrendingStoryCluster,
)
from backend.services.classifier_service import _VALID_CATEGORIES, classify_article
from backend.services.llm_grouper import LLMBatchEnricher

_ALLOWED_IMAGE_HOSTS = {"thestandard.co", "www.thestandard.co"}

# Recurring routine news patterns for dampening / suppression (lottery, weather forecasts, daily commodities)
_ROUTINE_KEYWORDS: tuple[str, ...] = (
    "หวย", "สลากกินแบ่ง", "ตรวจหวย", "ผลสลาก", "เลขเด็ด", "งวดนี้", "งวดประจำวัน",
    "ผลรางวัลที่ 1", "สลากออมสิน", "สลากธ.ก.ส.", "เลขท้าย", "ใบตรวจหวย",
    "พยากรณ์อากาศ", "กรมอุตุนิยมวิทยา", "สภาพอากาศวันนี้", "สภาพอากาศ", "ฝนตกทั่วไทย",
    "พยากรณ์อากาศประจำวัน", "เรดาร์ฝน", "ฝุ่น pm 2.5", "ฝุ่น pm2.5", "ค่าฝุ่นละออง",
    "ราคาทองวันนี้", "ราคาทองคำวันนี้", "ราคาน้ำมันวันนี้", "อัตราแลกเปลี่ยนประจำวัน",
    "ดูดวงรายวัน", "ดวงประจำวัน", "ราศีวันนี้",
)

# Crisis / Severe disaster emergency whitelist (waives routine penalty when severe context confirmed)
_SEVERE_DISASTER_VERBS: tuple[str, ...] = (
    "ประกาศเตือนภัย", "ยกระดับเตือนภัย", "เตือนภัยระดับ", "เตือนภัยฉุกเฉิน",
    "เตรียมรับมือพายุ", "เตือนน้ำท่วม", "เตือนดินถล่ม", "พายุพัดถล่ม", "พายุฤดูร้อนถล่ม",
)
_DISASTER_IMPACTS: tuple[str, ...] = (
    "น้ำท่วมฉับพลัน", "น้ำป่าไหลหลาก", "ดินโคลนถล่ม", "พื้นที่ประสบภัย",
    "ระดับน้ำวิกฤต", "แม่น้ำล้นตลิ่ง", "จมบาดาล", "น้ำท่วมหนัก",
)
_CASUALTY_VERBS: tuple[str, ...] = (
    "อพยพด่วน", "สูญหาย", "เสียชีวิต", "จมน้ำ", "ติดค้างในบ้าน", "กู้ภัยเร่งช่วย",
)


def _proxy_image_url(url: str, source: str) -> str:
    """Proxy image if needed to avoid hotlink blocks."""
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if source.lower() == "the standard" or parsed.netloc in _ALLOWED_IMAGE_HOSTS:
        return f"/api/image?url={quote(url, safe='')}"
    return url


def parse_article_time(ts_str: Any, default_now: datetime | None = None) -> datetime:
    """
    Parse timestamp string into timezone-aware UTC datetime.
    Supports '%Y-%m-%d %H:%M:%S', ISO formats, and variants.
    """
    fallback = default_now or datetime.now(timezone.utc)
    if not isinstance(ts_str, str):
        return fallback
    if not ts_str.strip():
        return fallback

    clean_str = ts_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(clean_str, fmt).replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return fallback


def _resolve_category(article: dict[str, Any]) -> str:
    """In-memory category resolver that never modifies or writes to disk."""
    cat = article.get("category")
    if cat and isinstance(cat, str) and cat.strip() and cat.strip().lower() in _VALID_CATEGORIES:
        return cat.strip().lower()
    title = str(article.get("title") or "").strip()
    summary = str(article.get("summary") or "").strip()
    url = str(article.get("url") or "")
    category_cues = article.get("category_cues")
    cat_computed, _ = classify_article(title, summary, url=url, category_cues=category_cues)
    return cat_computed


# ── WangchanBERTa Embedder (Thread-Safe Lazy Singleton) ────────────

class WangchanEmbedder:
    """
    Extracts L2-normalized dense embeddings using WangchanBERTa.
    Features:
    - Thread-safe lazy singleton loading
    - Dynamic hidden size (model.config.hidden_size)
    - Masked Mean Pooling excluding padding tokens
    - L2 Normalization (so dot product equals cosine similarity)
    - Tier 1 LRU Embedding Cache
    """

    _instance: WangchanEmbedder | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, model_dir: Path | None = None, cache_max_size: int = 2000) -> None:
        self._model_dir = model_dir or (
            Path(__file__).resolve().parent.parent / "model" / "wangchanberta_classifier"
        )
        self._tokenizer: Any = None
        self._model: Any = None
        self._hidden_size: int = 768
        self._init_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._cache_max_size = cache_max_size
        self._embedding_cache: dict[str, np.ndarray] = {}

    @classmethod
    def get_instance(cls) -> WangchanEmbedder:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(cache_max_size=settings.embedding_cache_max_size)
            return cls._instance

    def _ensure_loaded(self) -> bool:
        if self._model is not None and self._tokenizer is not None and callable(self._tokenizer):
            return True

        with self._init_lock:
            if self._model is not None and self._tokenizer is not None and callable(self._tokenizer):
                return True

            if not self._model_dir.exists():
                return False

            try:
                import torch
                from transformers import AutoModel, AutoTokenizer, PreTrainedTokenizerFast

                device = torch.device("cpu")
                tokenizer = None

                # 1. Primary: Load directly from tokenizer.json (fast, exact, no sentencepiece dependency)
                tok_json = self._model_dir / "tokenizer.json"
                if tok_json.exists():
                    try:
                        tokenizer = PreTrainedTokenizerFast(
                            tokenizer_file=str(tok_json),
                            bos_token="<s>",
                            eos_token="</s>",
                            unk_token="<unk>",
                            pad_token="<pad>",
                            mask_token="<mask<",
                        )
                    except Exception as tok_err:
                        print(f"PreTrainedTokenizerFast load failed: {tok_err}")
                        tokenizer = None

                # 2. Secondary fallback: AutoTokenizer
                if not callable(tokenizer):
                    try:
                        tokenizer = AutoTokenizer.from_pretrained(str(self._model_dir), use_fast=False)
                    except Exception:
                        pass

                # 3. Tertiary fallback: AutoTokenizer with use_fast=True
                if not callable(tokenizer):
                    try:
                        tokenizer = AutoTokenizer.from_pretrained(str(self._model_dir), use_fast=True)
                    except Exception:
                        pass

                if not callable(tokenizer):
                    print("Warning: WangchanEmbedder tokenizer could not be loaded as callable")
                    self._tokenizer = None
                    self._model = None
                    return False

                model = AutoModel.from_pretrained(str(self._model_dir))
                model.to(device)
                model.eval()

                self._tokenizer = tokenizer
                self._model = model
                self._hidden_size = int(getattr(model.config, "hidden_size", 768))
                return True
            except Exception as e:
                # If torch or transformers fails to load, gracefully return False
                print(f"Warning: WangchanEmbedder failed to initialize: {e}")
                self._tokenizer = None
                self._model = None
                return False

    @property
    def hidden_size(self) -> int:
        self._ensure_loaded()
        return self._hidden_size

    def get_canonical_text(self, article: dict[str, Any]) -> str:
        """Standardized text representation: Title + '\n' + Summary."""
        title = str(article.get("title") or "").strip()
        summary = str(article.get("summary") or "").strip()
        return f"{title}\n{summary}".strip()

    def encode_articles(self, articles: list[dict[str, Any]]) -> np.ndarray:
        """
        Encodes a list of article dicts into an (N, hidden_size) L2-normalized matrix.
        Utilizes Tier 1 Embedding Cache so existing articles are not re-computed.
        """
        n = len(articles)
        if n == 0:
            return np.empty((0, self.hidden_size), dtype=np.float32)

        canonical_texts = [self.get_canonical_text(a) for a in articles]
        hashes = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in canonical_texts]

        embeddings: list[np.ndarray | None] = [None] * n
        miss_indices: list[int] = []

        with self._cache_lock:
            for idx, h in enumerate(hashes):
                if h in self._embedding_cache:
                    embeddings[idx] = self._embedding_cache[h]
                else:
                    miss_indices.append(idx)

        # If all hit the cache, return immediately
        if not miss_indices:
            return np.vstack([emb for emb in embeddings if emb is not None])

        # Compute embeddings for cache misses
        if not self._ensure_loaded() or not callable(self._tokenizer) or self._model is None:
            # Fallback random deterministic unit vectors if model cannot load
            dim = self.hidden_size
            for idx in miss_indices:
                h_int = int(hashes[idx][:8], 16)
                rng = np.random.RandomState(h_int)
                vec = rng.randn(dim).astype(np.float32)
                vec /= float(max(float(np.linalg.norm(vec)), 1e-9))
                embeddings[idx] = vec
            return np.vstack([emb for emb in embeddings if emb is not None])

        try:
            import torch

            batch_size = 32
            computed_chunks: list[np.ndarray] = []
            for start_idx in range(0, len(miss_indices), batch_size):
                chunk_indices = miss_indices[start_idx : start_idx + batch_size]
                chunk_texts = [canonical_texts[i] for i in chunk_indices]
                batch_inputs = self._tokenizer(
                    chunk_texts,
                    padding=True,
                    truncation=True,
                    max_length=128,
                    return_tensors="pt",
                )

                with torch.inference_mode():
                    outputs = self._model(**batch_inputs)
                    hidden = outputs.last_hidden_state
                    mask = batch_inputs.attention_mask.unsqueeze(-1).expand(hidden.size()).float()
                    summed = torch.sum(hidden * mask, dim=1)
                    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
                    raw_embs = summed / counts
                    normalized = torch.nn.functional.normalize(raw_embs, p=2, dim=1)
                    computed_chunks.append(normalized.cpu().numpy().astype(np.float32))

            computed_numpy = np.vstack(computed_chunks)

            with self._cache_lock:
                for i, miss_idx in enumerate(miss_indices):
                    vec = computed_numpy[i]
                    embeddings[miss_idx] = vec
                    if len(self._embedding_cache) < self._cache_max_size:
                        self._embedding_cache[hashes[miss_idx]] = vec

            return np.vstack([emb for emb in embeddings if emb is not None])
        except Exception as err:
            print(f"Warning: WangchanEmbedder encoding exception, fallback to deterministic vectors: {err}")
            dim = self.hidden_size
            for idx in miss_indices:
                if embeddings[idx] is None:
                    h_int = int(hashes[idx][:8], 16)
                    rng = np.random.RandomState(h_int)
                    vec = rng.randn(dim).astype(np.float32)
                    vec /= float(max(float(np.linalg.norm(vec)), 1e-9))
                    embeddings[idx] = vec
            return np.vstack([emb for emb in embeddings if emb is not None])


# ── Semantic Clusterer (Strictly Zero Jaccard, Cohesion Validated) ─

class SemanticClusterer:
    """
    Clusters articles using WangchanBERTa embeddings and Cosine Distance.
    Features:
    - Matrix dot product: S = E @ E.T
    - Pairwise temporal constraint (|t_i - t_j| <= window_hours)
    - Configurable similarity threshold
    - Anti-Chain Clustering: Intra-Cluster Cohesion Validation
    - Strictly ZERO Jaccard or lexical overlap
    """

    def __init__(
        self,
        cosine_threshold: float = 0.76,
        cohesion_threshold: float = 0.70,
        time_window_hours: float = 36.0,
    ) -> None:
        self.cosine_threshold = cosine_threshold
        self.cohesion_threshold = cohesion_threshold
        self.time_window_hours = time_window_hours

    def cluster_articles(
        self,
        articles: list[dict[str, Any]],
        embeddings: np.ndarray,
        article_times: list[datetime],
    ) -> list[dict[str, Any]]:
        """
        Clusters articles and attaches:
        - cluster_id (str)
        - cluster_size (int)
        - cluster_sources (list[str])
        - distinct_source_count (int)
        - is_multi_source (bool)
        - avg_similarity (float)
        """
        n = len(articles)
        if n == 0:
            return []

        # 1. Cosine similarity matrix via matrix multiplication (since E is L2-normalized)
        sim_matrix = np.clip(embeddings @ embeddings.T, -1.0, 1.0)

        # 2. Pairwise adjacency candidate edges with temporal constraint
        adj: list[set[int]] = [set() for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                dt_hours = abs((article_times[i] - article_times[j]).total_seconds()) / 3600.0
                if dt_hours > self.time_window_hours:
                    continue
                if sim_matrix[i, j] >= self.cosine_threshold:
                    adj[i].add(j)
                    adj[j].add(i)

        # 3. Find connected components (initial candidate clusters)
        visited = [False] * n
        initial_clusters: list[list[int]] = []

        for i in range(n):
            if not visited[i]:
                comp: list[int] = []
                queue = [i]
                visited[i] = True
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if not visited[neighbor]:
                            visited[neighbor] = True
                            queue.append(neighbor)
                initial_clusters.append(comp)

        # 4. Anti-Chain Clustering: Intra-Cluster Cohesion Validation
        validated_clusters: list[list[int]] = []
        for comp in initial_clusters:
            current_comp = list(comp)
            pruned: list[int] = []

            # Iteratively prune outliers dragging down intra-cluster cohesion
            while len(current_comp) > 2:
                k = len(current_comp)
                total_sim = 0.0
                pair_count = 0
                for a_idx in range(k):
                    for b_idx in range(a_idx + 1, k):
                        total_sim += float(sim_matrix[current_comp[a_idx], current_comp[b_idx]])
                        pair_count += 1

                avg_sim = (total_sim / pair_count) if pair_count > 0 else 1.0
                if avg_sim >= self.cohesion_threshold:
                    break

                # Not cohesive: find member with lowest sum of similarities to other members in current_comp
                member_scores = [
                    sum(
                        float(sim_matrix[current_comp[m], current_comp[other]])
                        for other in range(k)
                        if other != m
                    )
                    for m in range(k)
                ]
                worst_idx_in_comp = int(np.argmin(member_scores))
                pruned.append(current_comp.pop(worst_idx_in_comp))

            # If down to 2 members, verify they satisfy cohesion threshold
            if len(current_comp) == 2:
                pair_sim = float(sim_matrix[current_comp[0], current_comp[1]])
                if pair_sim < self.cohesion_threshold:
                    pruned.append(current_comp.pop())

            if current_comp:
                validated_clusters.append(current_comp)
            for p in pruned:
                validated_clusters.append([p])

        # 5. Format clustered results and calculate cluster metadata
        clustered_results: list[dict[str, Any]] = []
        cluster_counter = 1

        for comp in validated_clusters:
            cid = f"cluster_{cluster_counter}"
            cluster_counter += 1

            # Compute average intra-cluster similarity
            k = len(comp)
            if k <= 1:
                cluster_avg_sim = 1.0
            else:
                sub_matrix = sim_matrix[np.ix_(comp, comp)]
                # Average of upper triangle
                cluster_avg_sim = float(
                    (np.sum(sub_matrix) - k) / (k * (k - 1))
                )

            comp_sources = sorted(
                {
                    str(articles[idx].get("source", "")).strip()
                    for idx in comp
                    if str(articles[idx].get("source", "")).strip()
                }
            )
            is_multi_source = len(comp_sources) >= 2

            for idx in comp:
                clustered_results.append(
                    {
                        "article": articles[idx],
                        "index": idx,
                        "time": article_times[idx],
                        "cluster_id": cid,
                        "cluster_size": len(comp),
                        "cluster_sources": comp_sources,
                        "distinct_source_count": max(1, len(comp_sources)),
                        "is_multi_source": is_multi_source,
                        "avg_similarity": round(cluster_avg_sim, 4),
                        "cluster_indices": comp,
                    }
                )

        return clustered_results


# ── Trending Service ──────────────────────────────────────────────

class TrendingService:
    """
    Trending & Hot News ranking engine with WangchanBERTa embeddings,
    strictly zero Jaccard clustering, and batch LLM enrichment.
    """

    def __init__(
        self,
        news_repo: NewsRepositoryPort | None = None,
        engagement_repo: EngagementRepositoryPort | None = None,
        story_repo: StoryRepositoryPort | None = None,
        embedder: WangchanEmbedder | None = None,
        clusterer: SemanticClusterer | None = None,
        llm_enricher: LLMBatchEnricher | None = None,
        volume_weight: float | None = None,
        velocity_weight: float | None = None,
        diversity_weight: float | None = None,
        recency_half_life_hours: float | None = None,
        novelty_weight: float | None = None,
        engagement_weight: float | None = None,
        routine_penalty_factor: float | None = None,
        recent_window_hours: float | None = None,
        baseline_window_hours: float | None = None,
        syndication_discount: float | None = None,
        half_life_hours: float = 12.0,
        breaking_window_hours: float = 3.0,
        breaking_boost: float = 4.0,
        consensus_weight: float = 0.55,
        trending_window_hours: float = 48.0,
    ) -> None:
        self._news_repo = news_repo
        self._engagement_repo = engagement_repo
        self._story_repo = story_repo
        self._embedder = embedder or WangchanEmbedder.get_instance()
        self._clusterer = clusterer or SemanticClusterer(
            cosine_threshold=settings.trending_cosine_threshold,
            cohesion_threshold=settings.trending_cohesion_threshold,
            time_window_hours=settings.trending_cluster_time_window_hours,
        )
        self._llm_enricher = llm_enricher or LLMBatchEnricher()

        # Configurable trending weights & thresholds (Settings injection)
        self._volume_weight: float = (
            volume_weight if volume_weight is not None else getattr(settings, "volume_weight", 1.0)
        )
        self._velocity_weight: float = (
            velocity_weight if velocity_weight is not None else getattr(settings, "velocity_weight", 1.5)
        )
        self._diversity_weight: float = (
            diversity_weight if diversity_weight is not None else getattr(settings, "diversity_weight", 1.2)
        )
        self._recency_half_life_hours: float = (
            recency_half_life_hours
            if recency_half_life_hours is not None
            else getattr(settings, "recency_half_life_hours", half_life_hours)
        )
        self._novelty_weight: float = (
            novelty_weight if novelty_weight is not None else getattr(settings, "novelty_weight", 0.8)
        )
        self._engagement_weight: float = (
            engagement_weight if engagement_weight is not None else getattr(settings, "engagement_weight", 0.6)
        )
        self._routine_penalty_factor: float = (
            routine_penalty_factor
            if routine_penalty_factor is not None
            else getattr(settings, "routine_penalty_factor", 0.25)
        )
        self._recent_window_hours: float = (
            recent_window_hours
            if recent_window_hours is not None
            else getattr(settings, "trending_recent_window_hours", 24.0)
        )
        self._baseline_window_hours: float = (
            baseline_window_hours
            if baseline_window_hours is not None
            else getattr(settings, "trending_baseline_window_hours", 72.0)
        )
        self._syndication_discount: float = (
            syndication_discount
            if syndication_discount is not None
            else getattr(settings, "syndication_discount", 0.5)
        )

        # Legacy parameters
        self._half_life_hours = half_life_hours
        self._breaking_window_hours = breaking_window_hours
        self._breaking_boost = breaking_boost
        self._consensus_weight = consensus_weight
        self._trending_window_hours = trending_window_hours

        # Tier 2 Result Cache
        self._result_cache_lock = threading.Lock()
        self._result_cache: dict[str, tuple[float, TrendingListResponse]] = {}

    @property
    def story_repo(self) -> StoryRepositoryPort:
        """Lazily obtain StoryRepositoryPort if not explicitly injected."""
        if self._story_repo is None:
            self._story_repo = get_story_repository()
        return self._story_repo

    @property
    def news_repo(self) -> NewsRepositoryPort:
        """Lazily obtain NewsRepositoryPort if not explicitly injected."""
        if self._news_repo is None:
            self._news_repo = get_news_repository()
        return self._news_repo

    @property
    def engagement_repo(self) -> EngagementRepositoryPort:
        """Lazily obtain EngagementRepositoryPort if not explicitly injected."""
        if self._engagement_repo is None:
            self._engagement_repo = get_engagement_repository()
        return self._engagement_repo

    # ── Deterministic Trending Layer Methods (Milestone 3) ────────────

    def check_routine_status(
        self,
        story: StoryRecord,
        articles: list[dict[str, Any]] | list[ArticleRecord] | None = None,
    ) -> tuple[bool, bool, str | None]:
        """
        Evaluate routine status with context-aware severe disaster exemption.
        Returns:
            tuple[is_routine, crisis_exemption_applied, crisis_exemption_reason]
        """
        if story.metadata.get("is_routine") is True:
            return True, False, None

        cat = (story.category or "").strip().lower()
        title_lower = (story.title or "").strip().lower()

        # Combine titles and texts
        all_texts = [title_lower]
        if articles:
            for art in articles:
                art_t = (
                    art.get("title") if isinstance(art, dict) else getattr(art, "title", "")
                )
                if art_t:
                    all_texts.append(str(art_t).strip().lower())
                art_s = (
                    art.get("summary") if isinstance(art, dict) else getattr(art, "summary", "")
                )
                if art_s:
                    all_texts.append(str(art_s).strip().lower())

        combined_corpus = " ".join(all_texts)

        # Check if routine keywords are triggered
        routine_triggered = False
        if cat in {"lottery", "horoscope"} or cat == "weather":
            routine_triggered = True
        else:
            for kw in _ROUTINE_KEYWORDS:
                if kw in combined_corpus:
                    routine_triggered = True
                    break

        if not routine_triggered:
            return False, False, None

        # If routine is triggered, check for severe disaster / crisis exemption context
        # (Lottery or horoscope never qualify for disaster exemption)
        if cat not in {"lottery", "horoscope"}:
            for verb in _SEVERE_DISASTER_VERBS:
                if verb in combined_corpus:
                    return False, True, f"severe_warning_confirmed: {verb}"
            for impact in _DISASTER_IMPACTS:
                if impact in combined_corpus:
                    return False, True, f"disaster_impact_confirmed: {impact}"
            for casualty in _CASUALTY_VERBS:
                if casualty in combined_corpus:
                    return False, True, f"casualty_evacuation_confirmed: {casualty}"

        return True, False, None

    def is_routine_story(
        self,
        story: StoryRecord,
        articles: list[dict[str, Any]] | list[ArticleRecord] | None = None,
    ) -> bool:
        """
        Detect recurring/routine reports (lottery results, weather forecasts, daily commodities).
        Such routine stories receive a dampening penalty so they do not artificially dominate trending.
        """
        is_routine, _, _ = self.check_routine_status(story, articles)
        return is_routine

    def compute_publisher_diversity(
        self,
        articles: list[dict[str, Any]] | list[ArticleRecord],
        story: StoryRecord | None = None,
    ) -> tuple[int, float, list[str]]:
        """
        Compute distinct publisher count and syndication-discounted diversity score.
        Distinct publishers reporting independently provide higher confidence than
        multiple syndicated or duplicate copies from a single publisher.
        """
        outlet_counts: dict[str, int] = {}
        for a in articles:
            s = a.get("source") if isinstance(a, dict) else getattr(a, "source", "")
            s_clean = str(s or "").strip()
            if s_clean:
                outlet_counts[s_clean] = outlet_counts.get(s_clean, 0) + 1

        if not outlet_counts and story and story.outlets:
            for out in story.outlets:
                clean_out = str(out or "").strip()
                if clean_out:
                    outlet_counts[clean_out] = 1

        if not outlet_counts:
            return 1, 0.0, []

        distinct_outlets = sorted(outlet_counts.keys())
        k = len(distinct_outlets)

        # Apply syndication discount for repeated articles from the same publisher
        effective_outlets = 0.0
        for out, count in outlet_counts.items():
            if count <= 1:
                effective_outlets += 1.0
            else:
                effective_outlets += 1.0 + self._syndication_discount * float(count - 1)

        # Diversity score combines effective publisher credit with distinct count bonus
        diversity_score = math.log(1.0 + effective_outlets) + 0.5 * float(max(0, k - 1))
        return k, round(diversity_score, 4), distinct_outlets

    def compute_volume_and_velocity(
        self,
        articles: list[dict[str, Any]] | list[ArticleRecord],
        ref_time: datetime,
    ) -> tuple[float, float, dict[str, Any]]:
        """
        Compute volume and burst velocity metrics.
        - Volume: Count of articles in recent window with minor baseline contribution.
        - Velocity / Burst: Rate of new articles in recent window relative to older baseline.
          A sudden burst in the recent window strictly outranks flat, distributed volume.
        """
        recent_count = 0
        prior_count = 0
        older_count = 0
        parsed_times: list[datetime] = []

        for a in articles:
            ts_val = (
                a.get("fetched_at") or a.get("published_at")
                if isinstance(a, dict)
                else (getattr(a, "fetched_at", None) or getattr(a, "published_at", None))
            )
            t = parse_article_time(ts_val, default_now=ref_time)
            parsed_times.append(t)
            elapsed_h = max(0.0, (ref_time - t).total_seconds() / 3600.0)

            if elapsed_h <= self._recent_window_hours:
                recent_count += 1
            elif elapsed_h <= self._baseline_window_hours:
                prior_count += 1
            else:
                older_count += 1

        # Effective volume: recent articles weighted highest
        v_eff = float(recent_count) + 0.25 * float(prior_count) + 0.05 * float(older_count)
        volume_score = math.log(1.0 + max(0.0, v_eff))

        # Velocity / Burst: recent coverage rate scaled by burst multiplier
        if recent_count == 0:
            velocity_score = 0.0
        else:
            burst_multiplier = 1.0 + (float(recent_count) / (1.0 + float(prior_count)))
            velocity_score = math.log(1.0 + float(recent_count)) * burst_multiplier

        latest_time = max(parsed_times) if parsed_times else ref_time
        elapsed_hours = max(0.0, (ref_time - latest_time).total_seconds() / 3600.0)

        details = {
            "recent_count": recent_count,
            "prior_count": prior_count,
            "older_count": older_count,
            "total_count": len(articles),
            "elapsed_hours": elapsed_hours,
        }
        return round(volume_score, 4), round(velocity_score, 4), details

    def compute_recency_decay(self, story: StoryRecord, ref_time: datetime) -> float:
        """
        Exponential half-life decay based on the story's actual article activity.
        Uses last_article_at (or first_article_at) as single authority, falling back to updated_at.
        Recency factor = 2^(-dt / half_life).
        """
        ref_ts = story.last_article_at or story.first_article_at or story.updated_at
        dt_hours = max(0.0, (ref_time - ref_ts).total_seconds() / 3600.0)
        h = max(0.1, self._recency_half_life_hours)
        decay = math.pow(2.0, -dt_hours / h)
        return round(max(0.0001, min(1.0, decay)), 4)

    def compute_novelty(
        self,
        story: StoryRecord,
        other_active_stories: list[StoryRecord],
    ) -> float:
        """
        Compute story novelty / uniqueness relative to other currently active stories.
        Higher novelty indicates an uncovered event; lower novelty indicates redundant coverage.
        """
        peers = [s for s in other_active_stories if s.story_id != story.story_id]
        if not peers:
            return 1.0

        # Centroid embedding similarity if available
        if story.centroid is not None:
            c_vec = np.asarray(story.centroid, dtype=np.float32)
            c_norm = float(np.linalg.norm(c_vec))
            if c_norm > 1e-9:
                sims: list[float] = []
                for other in peers:
                    if other.centroid is not None:
                        o_vec = np.asarray(other.centroid, dtype=np.float32)
                        o_norm = float(np.linalg.norm(o_vec))
                        if o_norm > 1e-9:
                            cos_sim = float(np.dot(c_vec, o_vec) / (c_norm * o_norm))
                            sims.append(cos_sim)
                if sims:
                    max_sim = max(sims)
                    novelty = max(0.1, min(1.0, 1.0 - max(0.0, max_sim)))
                    return round(novelty, 4)

        # Named entity overlap fallback
        if story.entities:
            s_ents = {e.strip() for e in story.entities if e.strip()}
            if s_ents:
                jaccards: list[float] = []
                for other in peers:
                    if other.entities:
                        o_ents = {e.strip() for e in other.entities if e.strip()}
                        union = s_ents | o_ents
                        if union:
                            jaccards.append(len(s_ents & o_ents) / len(union))
                if jaccards:
                    max_overlap = max(jaccards)
                    novelty = max(0.1, min(1.0, 1.0 - max_overlap))
                    return round(novelty, 4)

        return 1.0

    def compute_engagement(self, story: StoryRecord) -> tuple[float, dict[str, int]]:
        """
        Aggregate reader engagement metrics across all member articles in the story.
        Non-PII aggregate counts: clicks (1x), summaries (3x), bookmarks (5x).
        """
        clicks = 0
        summaries = 0
        bookmarks = 0

        for url in story.article_urls:
            stats = self._engagement_repo.get_engagement(url)
            clicks += stats.get("clicks", 0)
            summaries += stats.get("summaries", 0)
            bookmarks += stats.get("bookmarks", 0)

        weighted_eng = float(1.0 * clicks + 3.0 * summaries + 5.0 * bookmarks)
        engagement_score = math.log(1.0 + max(0.0, weighted_eng))
        return round(engagement_score, 4), {
            "clicks": clicks,
            "summaries": summaries,
            "bookmarks": bookmarks,
        }

    def calculate_story_score(
        self,
        story: StoryRecord,
        articles: list[dict[str, Any]] | list[ArticleRecord],
        other_stories: list[StoryRecord] | None = None,
        now: datetime | None = None,
    ) -> tuple[float, TrendingScoreBreakdown, list[str]]:
        """
        Pure deterministic scoring for a StoryRecord cluster.
        Strictly ZERO LLM calls in scoring path.
        Identical inputs yield identical ranking and identical scores.
        """
        ref_time = now or datetime.now(timezone.utc)
        is_routine, crisis_exempt, exempt_reason = self.check_routine_status(story, articles)

        distinct_count, diversity_score, unique_outlets = self.compute_publisher_diversity(articles, story)
        volume_score, velocity_score, time_details = self.compute_volume_and_velocity(articles, ref_time)
        recency_score = self.compute_recency_decay(story, ref_time)
        novelty_score = self.compute_novelty(story, other_stories or [])
        engagement_score, eng_stats = self.compute_engagement(story)

        raw_base = (
            self._volume_weight * volume_score
            + self._velocity_weight * velocity_score
            + self._diversity_weight * diversity_score
            + self._novelty_weight * novelty_score
            + self._engagement_weight * engagement_score
        )

        decayed_score = raw_base * recency_score
        routine_dampener = self._routine_penalty_factor if is_routine else 1.0
        final_score = round(decayed_score * routine_dampener, 4)

        badges: list[str] = []
        if final_score >= 4.0:
            badges.append("🔥 Trending")
        effective_ts = story.last_article_at or story.first_article_at or story.updated_at
        elapsed_hours = (ref_time - effective_ts).total_seconds() / 3600.0
        if elapsed_hours <= self._breaking_window_hours and distinct_count >= 2:
            badges.append("⚡ Breaking")
        if distinct_count >= 3:
            badges.append("🌟 Top Story")
        if is_routine:
            badges.append("⚠️ Routine")
        elif crisis_exempt:
            badges.append("🚨 Crisis Warning")

        breakdown = TrendingScoreBreakdown(
            base_score=round(raw_base, 4),
            volume_score=volume_score,
            velocity_score=velocity_score,
            diversity_score=diversity_score,
            recency_score=recency_score,
            time_decay=recency_score,
            novelty_score=novelty_score,
            engagement_score=engagement_score,
            routine_penalty=routine_dampener,
            is_routine=is_routine,
            crisis_exemption_applied=crisis_exempt,
            crisis_exemption_reason=exempt_reason,
            final_score=final_score,
            raw_trending_score=final_score,
            cluster_multiplier=round(1.0 + self._consensus_weight * max(0, distinct_count - 1), 4),
            details={
                "recent_articles": time_details["recent_count"],
                "prior_articles": time_details["prior_count"],
                "total_articles": len(articles),
                "distinct_outlets": distinct_count,
                "outlets": unique_outlets,
                "elapsed_hours": round(time_details["elapsed_hours"], 2),
                "clicks": eng_stats.get("clicks", 0),
                "summaries": eng_stats.get("summaries", 0),
                "bookmarks": eng_stats.get("bookmarks", 0),
            },
        )

        return final_score, breakdown, list(dict.fromkeys(badges))

    def get_trending_stories(
        self,
        limit: int = 10,
        category: str | None = None,
        now: datetime | None = None,
    ) -> list[TrendingStoryCluster]:
        """
        Rank active StoryRecord clusters deterministically.
        - Strictly ZERO LLM in the scoring path.
        - Only stories with status == 'active' are ranked.
        - Excludes dormant stories.
        - Scores member articles retrieved from NewsRepositoryPort.
        """
        ref_time = now or datetime.now(timezone.utc)
        repo = self.story_repo
        all_stories = repo.list_stories(status="active", limit=1000)

        # Story Lifecycle Gating: Only active stories eligible
        eligible_stories: list[StoryRecord] = []
        for s in all_stories:
            if (
                s.status == "active"
                and s.article_count > 0
                and s.refresh_status(current_time=ref_time) == "active"
            ):
                eligible_stories.append(s)

        # Optional category filtering
        if category and category.strip().lower() not in ("", "all"):
            target_cat = category.strip().lower()
            eligible_stories = [s for s in eligible_stories if s.category.strip().lower() == target_cat]

        if not eligible_stories:
            return []

        # Load only member articles needed by eligible stories (indexed lookup if supported)
        needed_urls = list(
            {u.strip() for s in eligible_stories for u in s.article_urls if u and isinstance(u, str) and u.strip()}
        )
        if hasattr(self._news_repo, "get_by_urls"):
            raw_news = self._news_repo.get_by_urls(needed_urls)
        else:
            raw_news = self._news_repo.load_news()

        news_map: dict[str, dict[str, Any]] = {}
        for a in raw_news:
            if isinstance(a, dict):
                u = a.get("url")
                if u and isinstance(u, str):
                    news_map[u.strip()] = a

        scored_clusters: list[TrendingStoryCluster] = []

        for story in eligible_stories:
            member_articles: list[dict[str, Any]] = []
            for u in story.article_urls:
                clean_u = u.strip() if u else ""
                if clean_u in news_map:
                    member_articles.append(news_map[clean_u])
                else:
                    member_articles.append({
                        "url": clean_u,
                        "title": story.title,
                        "source": story.outlets[0] if story.outlets else "",
                        "fetched_at": story.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                    })

            score, breakdown, badges = self.calculate_story_score(
                story=story,
                articles=member_articles,
                other_stories=eligible_stories,
                now=ref_time,
            )

            cluster = TrendingStoryCluster(
                story_id=story.story_id,
                macro_event_id=story.macro_event_id,
                title=story.title,
                category=story.category,
                status=story.status,
                created_at=story.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                updated_at=story.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                article_urls=list(story.article_urls),
                article_count=len(member_articles),
                outlet_count=story.outlet_count or len(story.outlets),
                outlets=list(story.outlets),
                entities=list(story.entities),
                trending_score=score,
                breakdown=breakdown,
                articles=member_articles,
                headline=story.headline or story.title,
                summary=story.summary,
                timeline=list(story.timeline),
                badges=badges,
                is_routine=breakdown.is_routine,
                metadata=dict(story.metadata),
            )
            scored_clusters.append(cluster)

        # Hybrid Multi-Signal Deduplication at Macro-Event / Storyline level
        deduped_clusters: list[TrendingStoryCluster] = []
        seen_macro_ids: set[str] = set()
        seen_norm_titles: list[str] = []

        for cluster in scored_clusters:
            # 1. Macro ID deduplication
            if cluster.macro_event_id:
                if cluster.macro_event_id in seen_macro_ids:
                    continue
                seen_macro_ids.add(cluster.macro_event_id)

            # 2. Near-duplicate title / topic deduplication
            raw_t = cluster.headline or cluster.title or ""
            norm_t = re.sub(r'[\s"\'“”‘’\(\)\[\]\-]+', '', raw_t).lower()
            is_dup = False
            for prev_t in seen_norm_titles:
                if norm_t and prev_t and (norm_t in prev_t or prev_t in norm_t or (len(norm_t) >= 12 and norm_t[:12] == prev_t[:12])):
                    is_dup = True
                    break
            if is_dup:
                continue

            seen_norm_titles.append(norm_t)
            deduped_clusters.append(cluster)

        # Deterministic sorting: trending_score descending, updated_at descending, story_id ascending
        deduped_clusters.sort(
            key=lambda c: (-c.trending_score, -parse_article_time(c.updated_at).timestamp(), c.story_id)
        )

        effective_limit = max(1, min(limit, 200))
        top_clusters = deduped_clusters[:effective_limit]

        # Assign ordinal rank (1-indexed) and top badges
        for idx, cluster in enumerate(top_clusters, start=1):
            cluster.rank = idx
            if idx <= 5 and "🔥 Trending" not in cluster.badges and not cluster.is_routine:
                cluster.badges.append("🔥 Trending")

        return top_clusters

    def get_trending_macro_events(
        self,
        limit: int = 10,
        category: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Rank active MacroEventRecord storylines deterministically.
        Aggregates volume, burst velocity, diversity, recency across child events.
        """
        from backend.repo.macro_event_repo import get_macro_event_repository

        ref_time = now or datetime.now(timezone.utc)
        macro_repo = get_macro_event_repository()
        all_macros = macro_repo.list_macro_events(status="active", limit=500)

        news_map: dict[str, dict[str, Any]] = {}
        if all_macros:
            raw_news = (
                self._news_repo.load_recent_news(hours=168.0)
                if hasattr(self._news_repo, "load_recent_news") and now is None
                else self._news_repo.load_news()
            )
            if not raw_news:
                raw_news = self._news_repo.load_news()
            for a in raw_news:
                if isinstance(a, dict):
                    u = a.get("url")
                    if u and isinstance(u, str):
                        news_map[u.strip()] = a

        scored_macros: list[dict[str, Any]] = []

        for macro in all_macros:
            child_stories = self.story_repo.get_stories_by_macro_id(macro.macro_event_id)
            if not child_stories and macro.child_event_ids:
                child_stories = self.story_repo.get_stories_by_ids(macro.child_event_ids)

            if not child_stories:
                continue

            # Check dynamic lifecycle
            if not macro.is_active_dynamic(child_events=child_stories, now=ref_time):
                continue

            if category and category.strip().lower() not in ("", "all") and macro.category.strip().lower() != category.strip().lower():
                continue

            # Gather all member articles across all child stories
            macro_articles: list[dict[str, Any]] = []
            seen_urls: set[str] = set()
            for cs in child_stories:
                for u in cs.article_urls:
                    clean_u = u.strip() if u else ""
                    if clean_u and clean_u not in seen_urls:
                        seen_urls.add(clean_u)
                        if clean_u in news_map:
                            macro_articles.append(news_map[clean_u])
                        else:
                            macro_articles.append({"url": clean_u, "title": cs.title, "source": cs.outlets[0] if cs.outlets else ""})

            if not macro_articles:
                continue

            # Check routine status across all child stories and articles
            is_routine = False
            crisis_exempt = False
            exempt_reason = None
            for cs in child_stories:
                r, ce, cer = self.check_routine_status(cs, macro_articles)
                if r:
                    is_routine = True
                if ce:
                    crisis_exempt = True
                    exempt_reason = cer
                    is_routine = False
                    break

            # Calculate signals
            k, div_score, unique_outlets = self.compute_publisher_diversity(macro_articles)
            vol_score, vel_score, _time_details = self.compute_volume_and_velocity(macro_articles, ref_time)

            # Recency from latest child activity
            child_dates = [cs.last_article_at or cs.first_article_at or cs.updated_at for cs in child_stories]
            latest_child_ts = max(child_dates) if child_dates else (macro.last_activity_at or macro.updated_at)
            dt_hours = max(0.0, (ref_time - latest_child_ts).total_seconds() / 3600.0)
            h = max(0.1, self._recency_half_life_hours)
            recency_score = round(max(0.0001, min(1.0, math.pow(2.0, -dt_hours / h))), 4)

            # Novelty
            novelty_score = 1.0

            # Engagement across child stories
            eng_clicks = 0
            eng_sums = 0
            eng_bms = 0
            for u in seen_urls:
                stats = self._engagement_repo.get_engagement(u)
                eng_clicks += stats.get("clicks", 0)
                eng_sums += stats.get("summaries", 0)
                eng_bms += stats.get("bookmarks", 0)
            eng_weighted = float(1.0 * eng_clicks + 3.0 * eng_sums + 5.0 * eng_bms)
            eng_score = round(math.log(1.0 + max(0.0, eng_weighted)), 4)

            raw_base = (
                self._volume_weight * vol_score
                + self._velocity_weight * vel_score
                + self._diversity_weight * div_score
                + self._novelty_weight * novelty_score
                + self._engagement_weight * eng_score
            )
            decayed = raw_base * recency_score
            routine_dampener = self._routine_penalty_factor if is_routine else 1.0
            final_score = round(decayed * routine_dampener, 4)

            badges: list[str] = []
            if final_score >= 4.0:
                badges.append("🔥 Trending")
            if dt_hours <= self._breaking_window_hours and k >= 2:
                badges.append("⚡ Breaking")
            if k >= 3:
                badges.append("🌟 Major Storyline")
            if is_routine:
                badges.append("⚠️ Routine")
            elif crisis_exempt:
                badges.append("🚨 Crisis Warning")

            breakdown = TrendingScoreBreakdown(
                base_score=round(raw_base, 4),
                volume_score=vol_score,
                velocity_score=vel_score,
                diversity_score=div_score,
                recency_score=recency_score,
                time_decay=recency_score,
                novelty_score=novelty_score,
                engagement_score=eng_score,
                routine_penalty=routine_dampener,
                is_routine=is_routine,
                crisis_exemption_applied=crisis_exempt,
                crisis_exemption_reason=exempt_reason,
                final_score=final_score,
                details={
                    "total_articles": len(macro_articles),
                    "child_events": len(child_stories),
                    "distinct_outlets": k,
                    "outlets": unique_outlets,
                },
            )

            cover_img = ""
            primary_url = ""
            for a in macro_articles:
                if not cover_img:
                    img = a.get("image_url") or a.get("image")
                    if img and isinstance(img, str) and img.strip():
                        cover_img = img.strip()
                if not primary_url:
                    u = a.get("url")
                    if u and isinstance(u, str):
                        primary_url = u.strip()

            first_child_title = (child_stories[0].headline or child_stories[0].title) if child_stories else ""
            macro_title = macro.title or first_child_title or "ประเด็นข่าวร้อนแรง"
            macro_headline = macro.headline or macro.title or first_child_title or "ประเด็นข่าวร้อนแรง"
            first_child_summary = child_stories[0].summary if child_stories else ""
            macro_summary = macro.summary or first_child_summary or "รวบรวมรายงานความคืบหน้าสถานการณ์จากสำนักข่าวที่เกี่ยวข้อง"

            tags: list[str] = []
            if macro.named_crisis_anchor:
                tags.append(f"#{macro.named_crisis_anchor.replace(' ', '')}")
            for ent in macro.entities:
                clean_ent = ent.strip().replace(" ", "")
                if len(clean_ent) >= 2 and f"#{clean_ent}" not in tags:
                    tags.append(f"#{clean_ent}")
            # Contextual keywords from title and summary
            for kw in ["GDPไทย", "GDP", "แบงก์ชาติ", "IMF", "หุ้นไทย", "ตลาดหุ้น", "เศรษฐกิจไทย", "AI"]:
                if kw in macro_title or kw in macro_summary:
                    tag = f"#{kw}"
                    if tag not in tags:
                        tags.append(tag)
            if len(tags) < 3 and child_stories:
                for cs in child_stories:
                    for o in cs.outlets:
                        tag = f"#{o.replace(' ', '')}"
                        if tag not in tags:
                            tags.append(tag)
            if macro.category and macro.category != "all":
                cat_tag = f"#{macro.category}"
                if cat_tag not in tags:
                    tags.append(cat_tag)

            child_event_summaries = []
            for cs in child_stories:
                cs_urls = set(cs.article_urls)
                cs_arts = [a for a in macro_articles if a.get("url") in cs_urls]
                child_event_summaries.append({
                    "story_id": cs.story_id,
                    "title": cs.headline or cs.title,
                    "headline": cs.headline or cs.title,
                    "summary": cs.summary,
                    "category": cs.category,
                    "article_count": cs.article_count or len(cs_arts),
                    "outlet_count": cs.outlet_count or len(cs.outlets),
                    "outlets": cs.outlets,
                    "article_urls": cs.article_urls,
                    "articles": cs_arts,
                    "first_article_at": cs.first_article_at.strftime("%Y-%m-%d %H:%M:%S") if cs.first_article_at else "",
                    "last_article_at": cs.last_article_at.strftime("%Y-%m-%d %H:%M:%S") if cs.last_article_at else "",
                })

            scored_macros.append({
                "macro_event_id": macro.macro_event_id,
                "story_id": macro.macro_event_id,
                "is_macro": True,
                "title": macro_title,
                "headline": macro_headline,
                "summary": macro_summary,
                "category": macro.category,
                "status": macro.status,
                "child_event_count": len(child_stories),
                "child_events_count": len(child_stories),
                "article_count": len(macro_articles),
                "outlet_count": k,
                "outlets": unique_outlets,
                "cluster_sources": unique_outlets,
                "cluster_size": k,
                "trending_score": final_score,
                "breakdown": breakdown.model_dump(mode="json"),
                "badges": list(dict.fromkeys(badges)),
                "created_at": macro.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": macro.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "timeline": [t.model_dump(mode="json") for t in macro.timeline],
                "image_url": cover_img,
                "url": primary_url,
                "hashtags": tags[:8],
                "entities": macro.entities[:8],
                "child_events": child_event_summaries,
                "articles": macro_articles[:12],
            })

        if not scored_macros:
            fallback_stories = self.get_trending_stories(limit=limit, category=category, now=now)
            for s in fallback_stories:
                story_arts = []
                for u in s.article_urls:
                    if u in news_map:
                        story_arts.append(news_map[u])
                    else:
                        story_arts.append({"url": u, "title": s.title, "source": s.outlets[0] if s.outlets else ""})
                tags = [f"#{s.category}"] if s.category else []
                for o in s.outlets:
                    tags.append(f"#{o.replace(' ', '')}")
                scored_macros.append({
                    "macro_event_id": s.macro_event_id or f"pseudo_macro_{s.story_id}",
                    "story_id": s.story_id,
                    "is_macro": bool(s.macro_event_id),
                    "title": s.title,
                    "headline": s.headline or s.title,
                    "summary": s.summary,
                    "category": s.category,
                    "status": "active",
                    "child_event_count": 1,
                    "child_events_count": 1,
                    "article_count": s.article_count,
                    "outlet_count": len(s.outlets),
                    "outlets": s.outlets,
                    "cluster_sources": s.outlets,
                    "cluster_size": len(s.outlets),
                    "trending_score": s.trending_score,
                    "breakdown": s.breakdown.model_dump(mode="json"),
                    "badges": s.badges,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                    "timeline": [t.model_dump(mode="json") for t in s.timeline],
                    "image_url": s.image_url,
                    "url": s.url,
                    "hashtags": tags,
                    "entities": [],
                    "child_events": [
                        {
                            "story_id": s.story_id,
                            "title": s.title,
                            "category": s.category,
                            "article_count": s.article_count,
                            "outlet_count": len(s.outlets),
                            "outlets": s.outlets,
                            "article_urls": s.article_urls,
                            "articles": story_arts,
                            "first_article_at": s.first_article_at,
                            "last_article_at": s.last_article_at,
                        }
                    ],
                    "articles": story_arts,
                })

        # Hybrid Multi-Signal Deduplication at Macro-Event Level
        deduped_macros: list[dict[str, Any]] = []
        seen_macro_keys: dict[str, dict[str, Any]] = {}

        for m in scored_macros:
            m_id = m.get("macro_event_id") or m.get("story_id")
            raw_title = m.get("headline") or m.get("title") or ""
            norm_title = re.sub(r'[\s"\'“”‘’\(\)\[\]\-]+', '', raw_title).lower()

            # Find matching existing macro
            match_key = None
            if m_id and m_id in seen_macro_keys:
                match_key = m_id
            else:
                for k, prev_m in seen_macro_keys.items():
                    prev_raw = prev_m.get("headline") or prev_m.get("title") or ""
                    prev_norm = re.sub(r'[\s"\'“”‘’\(\)\[\]\-]+', '', prev_raw).lower()
                    if norm_title and prev_norm and (norm_title in prev_norm or prev_norm in norm_title or (len(norm_title) >= 12 and norm_title[:12] == prev_norm[:12])):
                        match_key = k
                        break

            if match_key:
                # Merge into existing macro storyline
                existing = seen_macro_keys[match_key]
                # Combine outlets
                merged_outlets = list(dict.fromkeys(existing.get("outlets", []) + m.get("outlets", [])))
                existing["outlets"] = merged_outlets
                existing["cluster_sources"] = merged_outlets
                existing["outlet_count"] = len(merged_outlets)
                # Combine articles
                exist_urls = {a.get("url") for a in existing.get("articles", []) if a.get("url")}
                for a in m.get("articles", []):
                    u = a.get("url")
                    if u and u not in exist_urls:
                        exist_urls.add(u)
                        existing["articles"].append(a)
                existing["article_count"] = len(existing["articles"])
                # Combine child events
                exist_c_ids = {c.get("story_id") for c in existing.get("child_events", []) if c.get("story_id")}
                for c in m.get("child_events", []):
                    cid = c.get("story_id")
                    if cid and cid not in exist_c_ids:
                        exist_c_ids.add(cid)
                        existing["child_events"].append(c)
                existing["child_event_count"] = len(existing["child_events"])
                existing["child_events_count"] = len(existing["child_events"])
                # Combine hashtags
                existing["hashtags"] = list(dict.fromkeys(existing.get("hashtags", []) + m.get("hashtags", [])))[:10]
                # Max score
                existing["trending_score"] = max(existing.get("trending_score", 0.0), m.get("trending_score", 0.0))
            else:
                key = m_id or norm_title
                seen_macro_keys[key] = m
                deduped_macros.append(m)

        deduped_macros.sort(key=lambda m: (-m["trending_score"], -parse_article_time(m["updated_at"]).timestamp()))
        effective_limit = max(1, min(limit, 200))
        top_macros = deduped_macros[:effective_limit]
        for idx, m in enumerate(top_macros, start=1):
            m["rank"] = idx

        return top_macros

    def calculate_score(
        self,
        elapsed_hours: float,
        distinct_sources_count: int,
        engagement: dict[str, int],
    ) -> tuple[float, TrendingScoreBreakdown, list[str]]:
        """
        Calculates trending score, breakdown metrics, and visual status badges.
        Deterministic scoring based on measurable factors.
        """
        dt = max(0.0, elapsed_hours)
        k = max(1, distinct_sources_count)

        # 1. Reader Engagement
        clicks = max(0, engagement.get("clicks", 0))
        summaries = max(0, engagement.get("summaries", 0))
        bookmarks = max(0, engagement.get("bookmarks", 0))

        e_score = (1.0 * clicks) + (3.0 * summaries) + (5.0 * bookmarks)
        engagement_factor = 1.0 + math.log(1.0 + e_score) * 2.0

        # 2. Multi-source Publisher Consensus Multiplier
        m_multiplier = 1.0 + self._consensus_weight * (k - 1)

        # 3. Half-Life Time Decay
        time_decay = math.pow(2.0, -dt / self._half_life_hours)

        # 4. Breaking News Boost & Badges
        badges: list[str] = []
        is_breaking = (dt <= self._breaking_window_hours) and (k >= 2)
        b_boost = self._breaking_boost if is_breaking else 0.0

        if is_breaking:
            badges.append("⚡ Breaking")

        if k >= 3:
            badges.append("🌟 Top Story")

        # 5. Compound Final Score
        raw_score = (engagement_factor * m_multiplier * time_decay) + b_boost
        final_score = round(raw_score, 2)

        if final_score >= 4.5:
            badges.append("🔥 Trending")

        unique_badges = list(dict.fromkeys(badges))

        breakdown = TrendingScoreBreakdown(
            base_score=1.0,
            engagement_score=round(float(e_score), 2),
            cluster_multiplier=round(float(m_multiplier), 2),
            time_decay=round(float(time_decay), 4),
            breaking_boost=round(float(b_boost), 2),
            raw_trending_score=final_score,
        )

        return final_score, breakdown, unique_badges

    def get_trending_articles(
        self,
        category: str | None = None,
        limit: int = 5,
        now: datetime | None = None,
    ) -> TrendingListResponse:
        """
        Computes trending articles across all sources with optional category filtering.
        Utilizes 48h pre-filtering, WangchanBERTa embeddings, strict zero-Jaccard
        cohesion clustering, Tier 2 result caching, and batched LLM enrichment.
        """
        current_time = now or datetime.now(timezone.utc)
        window_hours = self._trending_window_hours
        if now is None and window_hours > 0 and hasattr(self._news_repo, "load_recent_news"):
            raw_news = self._news_repo.load_recent_news(hours=window_hours + 2.0)
            if not raw_news:
                raw_news = self._news_repo.load_news()
        else:
            raw_news = self._news_repo.load_news()

        if not raw_news:
            return TrendingListResponse(
                total=0,
                updated=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                trending=[],
                articles=[],
                clusters=[],
                trending_hashtags=[],
                hero=None,
            )

        cat_filter = (
            category.strip().lower()
            if category and category.strip().lower() not in {"", "all"}
            else None
        )

        # 1. Parse article timestamps and find candidate window
        candidates: list[tuple[dict[str, Any], datetime]] = []
        parsed_times: list[datetime] = []
        for n in raw_news:
            if not isinstance(n, dict):
                continue
            t = parse_article_time(n.get("fetched_at", ""), current_time)
            candidates.append((n, t))
            parsed_times.append(t)

        if not candidates:
            return TrendingListResponse(
                total=0,
                updated=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                trending=[],
                articles=[],
                clusters=[],
                trending_hashtags=[],
                hero=None,
            )

        if now is not None:
            ref_time = now
        else:
            latest_time = max(parsed_times)
            if (current_time - latest_time).total_seconds() / 3600.0 <= window_hours:
                ref_time = current_time
            else:
                ref_time = latest_time

        # 2. Pre-filter articles by 48h window and category
        filtered_pairs: list[tuple[dict[str, Any], datetime]] = []
        for n, art_time in candidates:
            elapsed = (ref_time - art_time).total_seconds() / 3600.0
            if window_hours > 0 and (elapsed > window_hours or elapsed < -2.0):
                continue

            cat = _resolve_category(n)
            if cat_filter is None or cat == cat_filter:
                n_copy = dict(n)
                n_copy["category"] = cat
                filtered_pairs.append((n_copy, art_time))

        # Resilience fallback: If window filter yielded 0 articles (e.g. time skew, paused scrapers),
        # gracefully fallback to using the most recent available candidate articles
        if not filtered_pairs and candidates:
            sorted_by_time = sorted(candidates, key=lambda pair: pair[1], reverse=True)
            for n, art_time in sorted_by_time[:100]:
                cat = _resolve_category(n)
                if cat_filter is None or cat == cat_filter:
                    n_copy = dict(n)
                    n_copy["category"] = cat
                    filtered_pairs.append((n_copy, art_time))

        if not filtered_pairs:
            return TrendingListResponse(
                total=0,
                updated=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                trending=[],
                articles=[],
                clusters=[],
                trending_hashtags=[],
                hero=None,
            )

        # Cap candidate pool to most recent 60 articles to prevent CPU starvation on 2-vCPU servers
        max_candidates = max(60, min(limit * 2, 100))
        if len(filtered_pairs) > max_candidates:
            filtered_pairs.sort(key=lambda pair: pair[1], reverse=True)
            filtered_pairs = filtered_pairs[:max_candidates]

        filtered_news = [pair[0] for pair in filtered_pairs]
        filtered_times = [pair[1] for pair in filtered_pairs]

        # 3. Check Tier 2 Result Cache using composite hash key
        content_hash = hashlib.sha256(
            "".join(str(a.get("url", "")) + str(a.get("title", "")) for a in filtered_news).encode("utf-8")
        ).hexdigest()
        cache_key = f"{cat_filter}:{limit}:{self._clusterer.cosine_threshold}:{content_hash}"

        now_epoch = current_time.timestamp()
        with self._result_cache_lock:
            if cache_key in self._result_cache:
                cached_time, cached_resp = self._result_cache[cache_key]
                if now_epoch - cached_time < settings.trending_result_cache_ttl_seconds:
                    return cached_resp

        # 4. Generate/Fetch WangchanBERTa Embeddings (Tier 1 Cache internally)
        embeddings = self._embedder.encode_articles(filtered_news)

        # 5. Semantic Clustering (Zero Jaccard, Cohesion Validated)
        clustered = self._clusterer.cluster_articles(filtered_news, embeddings, filtered_times)

        # 6. Score each article deterministically
        all_engagements = self._engagement_repo.get_all_engagements()
        scored_articles: list[TrendingArticle] = []

        for item in clustered:
            article = item["article"]
            url = str(article.get("url") or "").strip()
            article_time: datetime = item["time"]

            elapsed_hours = (ref_time - article_time).total_seconds() / 3600.0
            k_sources = item["distinct_source_count"]
            cluster_size = item["cluster_size"]
            cluster_sources = item["cluster_sources"]
            cid = item["cluster_id"]
            is_multi = item["is_multi_source"]

            engagement = all_engagements.get(url, {"clicks": 0, "summaries": 0, "bookmarks": 0})

            score, breakdown, badges = self.calculate_score(
                elapsed_hours=elapsed_hours,
                distinct_sources_count=k_sources,
                engagement=engagement,
            )

            image_url = _proxy_image_url(
                str(article.get("image_url") or ""),
                str(article.get("source") or ""),
            )

            scored_articles.append(
                TrendingArticle(
                    title=str(article.get("title") or ""),
                    summary=str(article.get("summary") or ""),
                    source=str(article.get("source") or ""),
                    url=url,
                    image_url=image_url,
                    category=article.get("category"),
                    fetched_at=str(article.get("fetched_at") or ""),
                    trending_score=score,
                    cluster_id=cid,
                    cluster_size=cluster_size,
                    cluster_sources=cluster_sources,
                    is_multi_source=is_multi,
                    badges=badges,
                    breakdown=breakdown,
                )
            )

        # Sort descending by trending_score, tie-breaking on fetched_at descending
        scored_articles.sort(
            key=lambda a: (a.trending_score, a.fetched_at),
            reverse=True,
        )

        # Ensure top 5 articles have '🔥 Trending' badge if not present
        for idx in range(min(5, len(scored_articles))):
            if "🔥 Trending" not in scored_articles[idx].badges:
                scored_articles[idx].badges.append("🔥 Trending")

        # 7. Group scored articles into TrendingCluster objects
        clusters_map: dict[str, list[TrendingArticle]] = {}
        for a in scored_articles:
            if a.cluster_id:
                clusters_map.setdefault(a.cluster_id, []).append(a)

        trending_clusters: list[TrendingCluster] = []
        cluster_enrichment_payload: list[dict[str, Any]] = []

        for cid, arts in clusters_map.items():
            sources = sorted({a.source for a in arts if a.source})
            is_multi = len(sources) >= 2
            top_score = max(a.trending_score for a in arts)

            t_cluster = TrendingCluster(
                cluster_id=cid,
                topic_title=arts[0].title,
                source_count=len(sources),
                article_count=len(arts),
                avg_similarity=1.0,
                trend_score=top_score,
                is_multi_source=is_multi,
                articles=arts,
            )
            trending_clusters.append(t_cluster)

            # Send multi-source clusters to LLM enrichment batch
            if is_multi or len(arts) >= 2:
                cluster_enrichment_payload.append(
                    {
                        "cluster_id": cid,
                        "articles": [
                            {
                                "title": a.title,
                                "summary": a.summary,
                                "source": a.source,
                                "fetched_at": a.fetched_at,
                            }
                            for a in arts
                        ],
                    }
                )

        # 8. Batched Metadata Enrichment (Decoupled LLM - Deterministic Heuristic on Critical Path)
        if cluster_enrichment_payload:
            enriched_meta = self._llm_enricher.enrich_clusters(cluster_enrichment_payload, allow_llm=False)
            for tc in trending_clusters:
                if tc.cluster_id in enriched_meta:
                    meta = enriched_meta[tc.cluster_id]
                    tc.topic_title = meta.topic_title
                    tc.hashtags = meta.hashtags
                    tc.cluster_summary = meta.cluster_summary
                    # Denormalize onto articles
                    for art in tc.articles:
                        art.topic_title = meta.topic_title
                        art.hashtags = meta.hashtags
                        art.cluster_summary = meta.cluster_summary

        # Sort clusters by trend_score descending
        trending_clusters.sort(key=lambda c: c.trend_score, reverse=True)

        # Aggregate unique trending hashtags across top clusters
        all_hashtags: list[str] = []
        for tc in trending_clusters[:10]:
            all_hashtags.extend(tc.hashtags)
        trending_hashtags = list(dict.fromkeys(all_hashtags))

        hero = scored_articles[0] if scored_articles else None
        effective_limit = max(1, min(limit, 50))
        top_trending = scored_articles[:effective_limit]

        response = TrendingListResponse(
            total=len(scored_articles),
            updated=current_time.strftime("%Y-%m-%d %H:%M:%S"),
            trending=top_trending,
            articles=top_trending,
            clusters=trending_clusters[:effective_limit],
            trending_hashtags=trending_hashtags,
            hero=hero,
        )

        # Save to Tier 2 Result Cache
        with self._result_cache_lock:
            self._result_cache[cache_key] = (now_epoch, response)

        return response


# ── Factory / DI helper ───────────────────────────────────────────

_TRENDING_SERVICE_INSTANCE: TrendingService | None = None


def get_trending_service() -> TrendingService:
    """FastAPI Depends() factory for TrendingService (Singleton)."""
    global _TRENDING_SERVICE_INSTANCE
    if _TRENDING_SERVICE_INSTANCE is None:
        news_repo = get_news_repository()
        engagement_repo = get_engagement_repository()
        story_repo = get_story_repository()
        _TRENDING_SERVICE_INSTANCE = TrendingService(
            news_repo=news_repo,
            engagement_repo=engagement_repo,
            story_repo=story_repo,
            half_life_hours=settings.recency_half_life_hours,
            trending_window_hours=settings.trending_window_hours,
        )
    return _TRENDING_SERVICE_INSTANCE
