"""
services/trending_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Trending scoring, text clustering, and ranking algorithm only.
SOLID  O — Configurable similarity thresholds, half-life decay, and weights.
SOLID  D — Depends on NewsRepositoryPort and EngagementRepositoryPort abstractions.
GRASP  Information Expert — Computes multi-source consensus, time decay,
          reader engagement, and visual status badges.
GRASP  Pure Fabrication — TextClusterer isolates Thai NLP & similarity logic.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

try:
    from pythainlp.tokenize import word_tokenize
    _PYTHAINLP_AVAILABLE = True
except ImportError:
    _PYTHAINLP_AVAILABLE = False

from backend.repo.engagement_repo import (
    EngagementRepositoryPort,
    get_engagement_repository,
)
from backend.repo.news_repo import NewsRepositoryPort, get_news_repository
from backend.schemas.trending_schema import (
    TrendingArticle,
    TrendingListResponse,
    TrendingScoreBreakdown,
)
from backend.services.classifier_service import _VALID_CATEGORIES, classify_article

# Curated Thai stopwords for news titles (preserving key topic nouns like 'ราคา', 'ทองคำ', 'หุ้น')
_FALLBACK_THAI_STOPWORDS = {
    "ที่", "และ", "ใน", "เป็น", "มี", "ของ", "ให้", "ได้", "การ", "ความ",
    "จะ", "ไป", "มา", "จาก", "กับ", "ว่า", "นี้", "นั้น", "ผู้", "โดย",
    "ก็", "ไม่", "แต่", "เพื่อ", "ถูก", "ยัง", "อีก", "แล้ว", "ถึง", "ถ้า",
    "คน", "เมื่อ", "เลย", "ตาม", "อย่าง", "พบ", "เผย", "ชี้", "เร่ง", "แจง",
    "ฮือฮา", "สุด", "หลัง", "ก่อน", "เตรียม", "ยัน", "หวั่น", "วอน", "ลั่น",
    "วัน", "วันนี้", "ขึ้น", "ลง", "ใหม่", "เก่า", "ต่อ", "เนื่อง", "ทั่ว", "บาท",
    "แห่ง", "ด้าน", "ร่วม", "เข้า", "ออก", "รับ", "แรง",
}

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


# ── Text Clusterer ────────────────────────────────────────────────

class TextClusterer:
    """
    Groups news articles into story clusters based on Thai/multilingual
    title token Jaccard similarity and publication time proximity.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.35,
        window_hours: float = 36.0,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.window_hours = window_hours

        # Load Thai stopwords
        self._stopwords = set(_FALLBACK_THAI_STOPWORDS)

    def tokenize_title(self, title: str) -> set[str]:
        """
        Tokenize Thai/English news title into a clean set of salient keywords.
        """
        if not title:
            return set()

        text = title.strip().lower()

        tokens: list[str]
        if _PYTHAINLP_AVAILABLE:
            try:
                tokens = word_tokenize(text, engine="newmm")
            except Exception:
                tokens = re.findall(r"[\w\u0E00-\u0E7F]+", text)
        else:
            tokens = re.findall(r"[\w\u0E00-\u0E7F]+", text)

        cleaned_tokens: set[str] = set()
        for tok in tokens:
            t = tok.strip()
            if not t:
                continue
            # Remove punctuation, pure digits, single characters, and stopwords
            if len(t) <= 1:
                continue
            if t.isdigit():
                continue
            if t in self._stopwords:
                continue
            if re.fullmatch(r"[^\w\u0E00-\u0E7F]+", t):
                continue
            cleaned_tokens.add(t)

        return cleaned_tokens

    def jaccard_similarity(self, tokens_a: set[str], tokens_b: set[str]) -> float:
        """Compute Jaccard similarity score between two token sets."""
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        if union == 0:
            return 0.0
        return intersection / union

    def cluster_articles(
        self,
        articles: list[dict[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        """
        Groups articles into clusters and attaches cluster metadata:
        - cluster_id (int)
        - cluster_size (int)
        - cluster_sources (list[str])
        - distinct_source_count (int)
        """
        n = len(articles)
        if n == 0:
            return []

        # Precompute tokens and times
        article_tokens: list[set[str]] = [
            self.tokenize_title(a.get("title", "")) for a in articles
        ]
        article_times: list[datetime] = [
            parse_article_time(a.get("fetched_at", ""), now) for a in articles
        ]

        # Union-Find Disjoint Set for clustering
        parent = list(range(n))

        def find(i: int) -> int:
            path = []
            while parent[i] != i:
                path.append(i)
                i = parent[i]
            for node in path:
                parent[node] = i
            return i

        def union(i: int, j: int) -> None:
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        # Pairwise comparison within time window
        for i in range(n):
            for j in range(i + 1, n):
                time_diff_hours = abs((article_times[i] - article_times[j]).total_seconds()) / 3600.0
                if time_diff_hours > self.window_hours:
                    continue

                sim = self.jaccard_similarity(article_tokens[i], article_tokens[j])
                if sim >= self.similarity_threshold:
                    union(i, j)

        # Build clusters
        clusters_map: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            clusters_map.setdefault(root, []).append(i)

        # Build result list with cluster metadata
        clustered_results: list[dict[str, Any]] = []
        for i, article in enumerate(articles):
            root = find(i)
            member_indices = clusters_map[root]
            member_sources = sorted(
                {
                    articles[idx].get("source", "").strip()
                    for idx in member_indices
                    if articles[idx].get("source", "").strip()
                }
            )
            clustered_results.append(
                {
                    "article": article,
                    "tokens": article_tokens[i],
                    "time": article_times[i],
                    "cluster_size": len(member_indices),
                    "cluster_sources": member_sources,
                    "distinct_source_count": max(1, len(member_sources)),
                }
            )

        return clustered_results


# ── Trending Service ──────────────────────────────────────────────

class TrendingService:
    """
    Trending & Hot News ranking engine.
    Calculates multi-source consensus multiplier, half-life time decay,
    and reader engagement telemetry to compute ranking scores.
    """

    def __init__(
        self,
        news_repo: NewsRepositoryPort,
        engagement_repo: EngagementRepositoryPort,
        clusterer: TextClusterer | None = None,
        half_life_hours: float = 12.0,
        breaking_window_hours: float = 3.0,
        breaking_boost: float = 4.0,
        consensus_weight: float = 0.55,
    ) -> None:
        self._news_repo = news_repo
        self._engagement_repo = engagement_repo
        self._clusterer = clusterer or TextClusterer()
        self._half_life_hours = half_life_hours
        self._breaking_window_hours = breaking_window_hours
        self._breaking_boost = breaking_boost
        self._consensus_weight = consensus_weight

    def calculate_score(
        self,
        elapsed_hours: float,
        distinct_sources_count: int,
        engagement: dict[str, int],
    ) -> tuple[float, TrendingScoreBreakdown, list[str]]:
        """
        Calculates trending score, breakdown metrics, and visual status badges.

        Formula:
          Score = [1.0 + ln(1.0 + E) * 2.0] * M(K) * D(dt) + B
          where:
            E = 1.0*clicks + 3.0*summaries + 5.0*bookmarks
            M(K) = 1.0 + 0.55 * (K - 1)
            D(dt) = 2^(-dt / 12.0)
            B = 4.0 if dt <= 3.0 and K >= 2 else 0.0
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

        # Deduplicate badges while maintaining order
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
        Read-only query: does not modify or save to disk.
        """
        current_time = now or datetime.now(timezone.utc)
        raw_news = self._news_repo.load_news()

        # Resolve categories in memory without modifying or saving the repository
        cat_filter = category.strip().lower() if category and category.strip().lower() not in {"", "all"} else None

        filtered_news: list[dict[str, Any]] = []
        for n in raw_news:
            if not isinstance(n, dict):
                continue
            cat = _resolve_category(n)
            if cat_filter is None or cat == cat_filter:
                n_copy = dict(n)
                n_copy["category"] = cat
                filtered_news.append(n_copy)

        if not filtered_news:
            return TrendingListResponse(
                total=0,
                updated=current_time.strftime("%Y-%m-%d %H:%M:%S"),
                trending=[],
                articles=[],
                hero=None,
            )

        # Cluster articles
        clustered = self._clusterer.cluster_articles(filtered_news, current_time)

        # Fetch all engagement stats
        all_engagements = self._engagement_repo.get_all_engagements()

        scored_articles: list[TrendingArticle] = []

        for item in clustered:
            article = item["article"]
            url = str(article.get("url") or "").strip()
            article_time: datetime = item["time"]

            elapsed_hours = (current_time - article_time).total_seconds() / 3600.0
            k_sources = item["distinct_source_count"]
            cluster_size = item["cluster_size"]
            cluster_sources = item["cluster_sources"]

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
                    cluster_size=cluster_size,
                    cluster_sources=cluster_sources,
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

        hero = scored_articles[0] if scored_articles else None
        effective_limit = max(1, min(limit, 50))
        top_trending = scored_articles[:effective_limit]

        return TrendingListResponse(
            total=len(scored_articles),
            updated=current_time.strftime("%Y-%m-%d %H:%M:%S"),
            trending=top_trending,
            articles=top_trending,
            hero=hero,
        )


# ── Factory / DI helper ───────────────────────────────────────────

def get_trending_service() -> TrendingService:
    """FastAPI Depends() factory for TrendingService."""
    news_repo = get_news_repository()
    engagement_repo = get_engagement_repository()
    return TrendingService(
        news_repo=news_repo,
        engagement_repo=engagement_repo,
    )
