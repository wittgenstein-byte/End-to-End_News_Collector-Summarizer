"""
backend/issue_explorer/service.py
─────────────────────────────────────────────────────────────────
SOLID  S — ควบคุมกระบวนการค้นหาและเจาะประเด็น (Search, Expand, Analyze, Cache)
SOLID  D — พึ่งพา ArticleSourcePort ผ่าน dependency injection
GRASP  Controller — ประสานงานระหว่าง QueryParser, Source, Analyzer, และ Cache
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from typing import Any

from backend.config import settings
from backend.core.cache import AsyncInMemoryCache
from backend.issue_explorer.aliases import expand_term
from backend.issue_explorer.analyzer import analyze_issue, thai_clean_tokenize
from backend.issue_explorer.query_parser import parse_query
from backend.issue_explorer.schemas import (
    HealthResponse,
    IssueSearchResponse,
    QueryInfo,
    StatsInfo,
)
from backend.issue_explorer.source import ArticleSourcePort, SqliteReadOnlyArticleSource

logger = logging.getLogger(__name__)


class IssueExplorerService:
    """
    High-performance, LLM-free Issue Drill-Down Engine.
    Executes parsing, SQL retrieval, clustering, and aggregations asynchronously.
    """

    def __init__(self, source: ArticleSourcePort | None = None) -> None:
        self._source: ArticleSourcePort = source if source is not None else SqliteReadOnlyArticleSource()
        self._cache: AsyncInMemoryCache[dict[str, Any]] = AsyncInMemoryCache(
            max_size=200,
            default_ttl_seconds=float(settings.issue_cache_ttl_seconds),
        )
        self._bg_word_counts: Counter[str] | None = None
        self._bg_updated_at: float = 0.0
        self._bg_lock = asyncio.Lock()

    async def _get_background_word_counts(self) -> Counter[str]:
        """Lazy background word frequency cache with concurrency lock (1 hour TTL)."""
        now = time.time()
        if self._bg_word_counts is not None and (now - self._bg_updated_at) < 3600.0:
            return self._bg_word_counts

        async with self._bg_lock:
            if self._bg_word_counts is not None and (now - self._bg_updated_at) < 3600.0:
                return self._bg_word_counts

            def _compute_bg() -> Counter[str]:
                try:
                    titles = self._source.get_background_sample(limit=2500)
                    counter: Counter[str] = Counter()
                    for t in titles:
                        for word in thai_clean_tokenize(t):
                            counter[word] += 1
                    return counter
                except Exception as exc:
                    logger.warning("Could not compute background word frequencies: %s", exc)
                    return Counter()

            counts = await asyncio.to_thread(_compute_bg)
            self._bg_word_counts = counts
            self._bg_updated_at = time.time()
            return self._bg_word_counts

    async def search(
        self,
        q: str,
        expand: bool = True,
        date_from: str | None = None,
        date_to: str | None = None,
        source: str | None = None,
        category: str | None = None,
        limit: int = 200,
    ) -> IssueSearchResponse:
        t_start = time.perf_counter()
        raw_query = q.strip()

        # Check data version to invalidate stale cache entries when new articles arrive
        data_ver = await asyncio.to_thread(self._source.data_version)

        cache_key = (
            f"issue:{raw_query.lower()}:exp={expand}:df={date_from}:dt={date_to}:"
            f"src={source}:cat={category}:lim={limit}:ver={data_ver}"
        )
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return IssueSearchResponse(**cached)

        # 1. Parse user query
        parsed = parse_query(raw_query)

        # Flatten positive query terms
        primary_terms: list[str] = []
        for grp in parsed.groups:
            primary_terms.extend(grp)

        # 2. Expand synonyms if enabled
        expanded_all: list[str] = []
        expanded_groups: list[tuple[str, ...]] = []

        if expand and parsed.groups:
            for grp in parsed.groups:
                new_grp: list[str] = []
                for term in grp:
                    aliases = expand_term(term)
                    for a in aliases:
                        if a not in new_grp:
                            new_grp.append(a)
                        if a not in expanded_all:
                            expanded_all.append(a)
                expanded_groups.append(tuple(new_grp))
        else:
            expanded_groups = list(parsed.groups)
            expanded_all = list(primary_terms)

        # Rebuild SQL query with expanded groups
        from backend.issue_explorer.query_parser import ParsedQuery
        expanded_parsed = ParsedQuery(groups=tuple(expanded_groups), excludes=parsed.excludes)
        where_sql, params = expanded_parsed.to_sql(fields=["title", "summary"])

        # 3. Retrieve matching articles from read-only storage
        def _fetch() -> list[dict[str, Any]]:
            return self._source.search(
                where_sql=where_sql,
                params=params,
                limit=settings.issue_max_matches,
                date_from=date_from,
                date_to=date_to,
                source=source,
                category=category,
            )

        raw_articles = await asyncio.to_thread(_fetch)
        total_matches = len(raw_articles)

        # Slice up to analysis cap to preserve sub-second response time
        analysis_articles = raw_articles[: settings.issue_analysis_cap]

        # 4. Get background word counts for lift computation
        bg_counts = await self._get_background_word_counts()

        # 5. Deterministic analysis in worker thread
        def _analyze() -> dict[str, Any]:
            return analyze_issue(
                raw_articles=analysis_articles,
                query_terms=primary_terms,
                expanded_terms=expanded_all,
                cluster_distance_threshold=settings.issue_cluster_distance,
                background_word_counts=bg_counts,
            )

        analysis_result = await asyncio.to_thread(_analyze)
        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 1)

        first_seen: str | None = None
        last_seen: str | None = None
        if raw_articles:
            dates = [str(a.get("fetched_at") or "")[:10] for a in raw_articles if a.get("fetched_at")]
            if dates:
                dates.sort()
                first_seen = dates[0]
                last_seen = dates[-1]

        stats = StatsInfo(
            total_matches=total_matches,
            analyzed=len(analysis_articles),
            sources_count=len(analysis_result.get("sources", [])),
            categories_count=len(analysis_result.get("categories", [])),
            first_seen=first_seen,
            last_seen=last_seen,
            elapsed_ms=elapsed_ms,
        )

        query_info = QueryInfo(
            raw=raw_query,
            expanded_terms=expanded_all,
            excludes=list(parsed.excludes),
        )

        response = IssueSearchResponse(
            query=query_info,
            stats=stats,
            clusters=analysis_result["clusters"],
            possibly_unrelated=analysis_result["possibly_unrelated"],
            timeline=analysis_result["timeline"],
            sources=analysis_result["sources"],
            categories=analysis_result["categories"],
            related_terms=analysis_result["related_terms"],
            articles=analysis_result["articles"][:limit],
            data_version=data_ver,
        )

        # Cache valid responses
        await self._cache.set(cache_key, response.model_dump())

        return response

    async def get_health(self) -> HealthResponse:
        data = await asyncio.to_thread(self._source.health)
        return HealthResponse(**data)


_SERVICE_INSTANCE: IssueExplorerService | None = None


def get_issue_service() -> IssueExplorerService:
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = IssueExplorerService()
    return _SERVICE_INSTANCE
