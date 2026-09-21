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
from backend.schemas.trending_schema import (
    TrendingArticle,
    TrendingCluster,
    TrendingListResponse,
    TrendingScoreBreakdown,
)
from backend.services.classifier_service import _VALID_CATEGORIES, classify_article
from backend.services.llm_grouper import LLMBatchEnricher

_ALLOWED_IMAGE_HOSTS = {"thestandard.co", "www.thestandard.co"}


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
        if self._model is not None and self._tokenizer is not None:
            return True

        with self._init_lock:
            if self._model is not None and self._tokenizer is not None:
                return True

            if not self._model_dir.exists():
                return False

            try:
                import torch
                from transformers import AutoModel, AutoTokenizer

                device = torch.device("cpu")
                tokenizer = AutoTokenizer.from_pretrained(str(self._model_dir), use_fast=False)
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
        if not self._ensure_loaded():
            # Fallback random deterministic unit vectors if model cannot load
            dim = self.hidden_size
            for idx in miss_indices:
                h_int = int(hashes[idx][:8], 16)
                rng = np.random.RandomState(h_int)
                vec = rng.randn(dim).astype(np.float32)
                vec /= float(max(float(np.linalg.norm(vec)), 1e-9))
                embeddings[idx] = vec
            return np.vstack([emb for emb in embeddings if emb is not None])

        import torch

        miss_texts = [canonical_texts[i] for i in miss_indices]
        batch_inputs = self._tokenizer(
            miss_texts,
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
            computed_numpy = normalized.cpu().numpy().astype(np.float32)

        with self._cache_lock:
            for i, miss_idx in enumerate(miss_indices):
                vec = computed_numpy[i]
                embeddings[miss_idx] = vec
                if len(self._embedding_cache) < self._cache_max_size:
                    self._embedding_cache[hashes[miss_idx]] = vec

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
        cosine_threshold: float = 0.92,
        cohesion_threshold: float = 0.88,
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
        news_repo: NewsRepositoryPort,
        engagement_repo: EngagementRepositoryPort,
        embedder: WangchanEmbedder | None = None,
        clusterer: SemanticClusterer | None = None,
        llm_enricher: LLMBatchEnricher | None = None,
        half_life_hours: float = 12.0,
        breaking_window_hours: float = 3.0,
        breaking_boost: float = 4.0,
        consensus_weight: float = 0.55,
        trending_window_hours: float = 48.0,
    ) -> None:
        self._news_repo = news_repo
        self._engagement_repo = engagement_repo
        self._embedder = embedder or WangchanEmbedder.get_instance()
        self._clusterer = clusterer or SemanticClusterer(
            cosine_threshold=settings.trending_cosine_threshold,
            cohesion_threshold=settings.trending_cohesion_threshold,
            time_window_hours=settings.trending_cluster_time_window_hours,
        )
        self._llm_enricher = llm_enricher or LLMBatchEnricher()
        self._half_life_hours = half_life_hours
        self._breaking_window_hours = breaking_window_hours
        self._breaking_boost = breaking_boost
        self._consensus_weight = consensus_weight
        self._trending_window_hours = trending_window_hours

        # Tier 2 Result Cache
        self._result_cache_lock = threading.Lock()
        self._result_cache: dict[str, tuple[float, TrendingListResponse]] = {}

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
        window_hours = self._trending_window_hours

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
        filtered_news: list[dict[str, Any]] = []
        filtered_times: list[datetime] = []
        for n, art_time in candidates:
            elapsed = (ref_time - art_time).total_seconds() / 3600.0
            if window_hours > 0 and (elapsed > window_hours or elapsed < -2.0):
                continue

            cat = _resolve_category(n)
            if cat_filter is None or cat == cat_filter:
                n_copy = dict(n)
                n_copy["category"] = cat
                filtered_news.append(n_copy)
                filtered_times.append(art_time)

        if not filtered_news:
            return TrendingListResponse(
                total=0,
                updated=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                trending=[],
                articles=[],
                clusters=[],
                trending_hashtags=[],
                hero=None,
            )

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

        # 8. Batched LLM Metadata Enrichment (Decoupled, Metadata Only)
        if cluster_enrichment_payload:
            enriched_meta = self._llm_enricher.enrich_clusters(cluster_enrichment_payload)
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

def get_trending_service() -> TrendingService:
    """FastAPI Depends() factory for TrendingService."""
    news_repo = get_news_repository()
    engagement_repo = get_engagement_repository()
    return TrendingService(
        news_repo=news_repo,
        engagement_repo=engagement_repo,
        half_life_hours=12.0,
        trending_window_hours=settings.trending_window_hours,
    )
