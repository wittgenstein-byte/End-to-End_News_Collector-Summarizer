"""
backend/issue_explorer/analyzer.py
─────────────────────────────────────────────────────────────────
SOLID  S — ทำการวิเคราะห์เชิงสถิติ (Clustering, Timeline, Outlier, Related terms) โดยไม่ใช้ LLM
GRASP  Information Expert — คำนวณ TF-IDF, Cosine Distance, Medoid, และ Frequency
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any

import numpy as np
from pythainlp.corpus import thai_stopwords
from pythainlp.tokenize import word_tokenize
from sklearn.cluster import AgglomerativeClustering  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

from backend.config import settings
from backend.issue_explorer.schemas import (
    CountItem,
    IssueArticle,
    IssueCluster,
    PossiblyUnrelatedArticle,
    RelatedTerm,
    TimelinePoint,
)

logger = logging.getLogger(__name__)

# Common boilerplate and junk tokens to strip
_BOILERPLATE_TOKENS = {
    "the", "post", "appeared", "first", "on", "standard", "daily", "news",
    "ต.ค.", "พ.ย.", "ธ.ค.", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.",
    "2567", "2568", "2569", "2570", "2024", "2025", "2026", "2027",
    "อ่าน", "ข่าว", "ล่าสุด", "เผย", "ชี้", "ระบุ", "เมื่อ", "เวลา", "ที่", "วัน", "นี้", "โดย", "กับ", "และ", "ใน",
}

_STOPWORDS = set(thai_stopwords()) | _BOILERPLATE_TOKENS


def thai_clean_tokenize(text: str, custom_stops: set[str] | None = None) -> list[str]:
    """Tokenize Thai text with newmm engine, stripping punctuation, stopwords, and digits."""
    stops = _STOPWORDS if custom_stops is None else (_STOPWORDS | custom_stops)
    words = word_tokenize(text, engine="newmm", keep_whitespace=False)
    cleaned: list[str] = []
    for w in words:
        w_clean = w.strip(" .,'\"“”‘’-–()[]{}…!?:;#/|\\_`~*")
        if len(w_clean) >= 2 and w_clean.lower() not in stops and not w_clean.isdigit():
            cleaned.append(w_clean)
    return cleaned


def calculate_relevance_score(
    article: dict[str, Any],
    query_terms: list[str],
    expanded_terms: list[str],
) -> tuple[float, list[str]]:
    """
    Score article relevance deterministically:
      - Title match with primary term: 3.0 pts
      - Summary match with primary term: 1.0 pt
      - Title match with expanded alias: 2.0 pts
      - Summary match with expanded alias: 0.5 pt
    Returns (score, list_of_matched_terms).
    """
    title = str(article.get("title") or "").lower()
    summary = str(article.get("summary") or "").lower()

    score = 0.0
    matched: list[str] = []

    for term in query_terms:
        t_low = term.lower()
        t_matched = False
        if t_low in title:
            score += 3.0
            t_matched = True
        if t_low in summary:
            score += 1.0
            t_matched = True
        if t_matched and term not in matched:
            matched.append(term)

    # Check expanded terms not in primary query_terms
    for term in expanded_terms:
        if term in query_terms:
            continue
        t_low = term.lower()
        t_matched = False
        if t_low in title:
            score += 2.0
            t_matched = True
        if t_low in summary:
            score += 0.5
            t_matched = True
        if t_matched and term not in matched:
            matched.append(term)

    return max(0.5, score), matched


def analyze_issue(
    raw_articles: list[dict[str, Any]],
    query_terms: list[str],
    expanded_terms: list[str],
    cluster_distance_threshold: float | None = None,
    background_word_counts: Counter[str] | None = None,
) -> dict[str, Any]:
    """
    Perform deterministic clustering, timeline extraction, outlier filtering,
    and related keyword analysis across retrieved articles.
    """
    if cluster_distance_threshold is None:
        cluster_distance_threshold = settings.issue_cluster_distance

    if not raw_articles:
        return {
            "clusters": [],
            "possibly_unrelated": [],
            "timeline": [],
            "sources": [],
            "categories": [],
            "related_terms": [],
            "articles": [],
        }

    # 1. Timeline and Distributions
    timeline_counter: Counter[str] = Counter()
    sources_counter: Counter[str] = Counter()
    categories_counter: Counter[str] = Counter()

    # Pre-score articles and sort deterministically
    scored_items: list[tuple[dict[str, Any], float, list[str]]] = []
    for art in raw_articles:
        score, matched = calculate_relevance_score(art, query_terms, expanded_terms)
        scored_items.append((art, score, matched))

        f_at = str(art.get("fetched_at") or "")
        dt_str = f_at[:10] if len(f_at) >= 10 else "Unknown"
        timeline_counter[dt_str] += 1

        src = str(art.get("source") or "Unknown")
        sources_counter[src] += 1

        cat = str(art.get("category") or "uncategorized")
        categories_counter[cat] += 1

    # Sorted timeline points ascending
    timeline = [
        TimelinePoint(date=d, count=c)
        for d, c in sorted(timeline_counter.items(), key=lambda x: x[0])
    ]

    sources_list = [
        CountItem(name=s, count=c)
        for s, c in sources_counter.most_common()
    ]

    categories_list = [
        CountItem(name=k, count=c)
        for k, c in categories_counter.most_common()
    ]

    # 2. Text preparation for clustering & TF-IDF
    # Exclude the active query terms and aliases from clustering features so clusters represent sub-topics
    query_stops = {t.lower() for t in (query_terms + expanded_terms)}
    
    docs: list[str] = []
    for art, _, _ in scored_items:
        t = str(art.get("title") or "")
        s = str(art.get("summary") or "")
        # Give title 2x weight in the document representation
        docs.append(f"{t} {t} {s[:350]}")

    def custom_tokenizer(s: str) -> list[str]:
        return thai_clean_tokenize(s, custom_stops=query_stops)

    cluster_labels = np.zeros(len(scored_items), dtype=int)
    cluster_centroids: dict[int, np.ndarray] = {}
    feature_names: list[str] = []
    doc_vectors: np.ndarray | None = None

    # Run TF-IDF if we have at least 3 articles
    if len(docs) >= 3:
        try:
            vec = TfidfVectorizer(
                tokenizer=custom_tokenizer,
                lowercase=False,
                token_pattern=None,
                min_df=1 if len(docs) < 5 else 2,
                max_df=0.85,
                sublinear_tf=True,
            )
            X = vec.fit_transform(docs)
            feature_names = list(vec.get_feature_names_out())

            if len(feature_names) >= 2 and X.shape[0] >= 3:
                doc_vectors = X.toarray()
                cl = AgglomerativeClustering(
                    n_clusters=None,
                    distance_threshold=cluster_distance_threshold,
                    metric="cosine",
                    linkage="average",
                )
                cluster_labels = cl.fit_predict(doc_vectors)
        except Exception as exc:
            logger.warning("Clustering encountered exception: %s. Using default single cluster.", exc)

    # 3. Calculate cluster centroids, medoids, and summaries
    clusters_dict: dict[int, list[int]] = defaultdict(list)
    for idx, c_id in enumerate(cluster_labels):
        clusters_dict[int(c_id)].append(idx)

    built_clusters: list[IssueCluster] = []
    doc_cluster_id_map: dict[int, str] = {}

    for c_id, doc_indices in sorted(clusters_dict.items(), key=lambda x: len(x[1]), reverse=True):
        cluster_id_str = f"c{c_id + 1}"
        for idx in doc_indices:
            doc_cluster_id_map[idx] = cluster_id_str

        # Find medoid article (article with highest similarity to other cluster members)
        if doc_vectors is not None and len(doc_indices) > 1:
            sub_vecs = doc_vectors[doc_indices]
            centroid = np.asarray(sub_vecs.mean(axis=0)).ravel()
            cluster_centroids[c_id] = centroid

            # Distances to centroid
            norm_centroid = np.linalg.norm(centroid)
            if norm_centroid > 1e-6:
                normed_centroid = centroid / norm_centroid
                sims = np.dot(sub_vecs, normed_centroid)
                best_sub_idx = int(np.argmax(sims))
                medoid_idx = doc_indices[best_sub_idx]
            else:
                medoid_idx = doc_indices[0]

            # Top terms for this cluster
            top_kw_idx = centroid.argsort()[::-1][:5]
            top_terms = [feature_names[i] for i in top_kw_idx if centroid[i] > 0]
        else:
            medoid_idx = doc_indices[0]
            top_terms = []

        medoid_article = scored_items[medoid_idx][0]
        label = str(medoid_article.get("title") or f"กลุ่มประเด็นที่ {c_id + 1}")

        # Gather cluster metadata
        c_sources: Counter[str] = Counter()
        c_dates: list[str] = []
        c_article_ids: list[int] = []

        for idx in doc_indices:
            a = scored_items[idx][0]
            c_sources[str(a.get("source") or "Unknown")] += 1
            f_str = str(a.get("fetched_at") or "")
            if f_str:
                c_dates.append(f_str[:10])
            c_article_ids.append(int(a.get("id", idx)))

        c_dates.sort()
        built_clusters.append(
            IssueCluster(
                id=cluster_id_str,
                label=label,
                top_terms=top_terms,
                size=len(doc_indices),
                first_seen=c_dates[0] if c_dates else None,
                last_seen=c_dates[-1] if c_dates else None,
                sources=dict(c_sources.most_common(5)),
                article_ids=c_article_ids,
            )
        )

    # 4. Outlier detection (False positive filtering, e.g. tennis 'Gaston')
    # If overall doc similarity to mean centroid is very low (< 0.05) AND its category is a small minority (< 10%)
    possibly_unrelated: list[PossiblyUnrelatedArticle] = []
    normal_articles: list[IssueArticle] = []

    total_count = len(scored_items)
    category_proportions = {cat: count / total_count for cat, count in categories_counter.items()}

    overall_centroid: np.ndarray | None = None
    if doc_vectors is not None and len(doc_vectors) > 0:
        overall_centroid = np.asarray(doc_vectors.mean(axis=0)).ravel()
        norm_all = np.linalg.norm(overall_centroid)
        if norm_all > 1e-6:
            overall_centroid /= norm_all
        else:
            overall_centroid = None

    for idx, (art, score, matched) in enumerate(scored_items):
        cat = str(art.get("category") or "uncategorized")
        is_unrelated = False
        reason = ""

        # 1. Token check: does the article contain the query term/alias as an actual word/token,
        # or was it matched merely as a substring inside an unrelated transliterated word (e.g. กาสตง vs สตง)?
        text_full = f"{art.get('title', '')} {art.get('summary', '')}"
        art_tokens = set(thai_clean_tokenize(text_full))
        has_token = any(
            t.lower() in art_tokens or f"{t.lower()}." in art_tokens or t.lower() in text_full.lower().split()
            for t in (query_terms + expanded_terms)
        )

        if not has_token:
            is_unrelated = True
            reason = "พบคำค้นเป็นเพียงส่วนย่อยของคำอื่นในบริบท (Subword in unrelated transliterated token)"

        # 2. Vector similarity check against overall query centroid
        if not is_unrelated and overall_centroid is not None and doc_vectors is not None:
            doc_vec = doc_vectors[idx]
            d_norm = np.linalg.norm(doc_vec)
            cos_sim = float(np.dot(doc_vec / d_norm, overall_centroid)) if d_norm > 1e-6 else 0.0

            if cos_sim < 0.30 and category_proportions.get(cat, 0.0) < 0.10:
                is_unrelated = True
                reason = f"ความคล้ายคลึงบริบทต่ำ ({cos_sim:.2f}) และอยู่ในหมวดหมู่ส่วนน้อย ({cat})"

        if is_unrelated:
            possibly_unrelated.append(
                PossiblyUnrelatedArticle(
                    id=int(art.get("id", idx)),
                    title=str(art.get("title") or ""),
                    url=str(art.get("url") or ""),
                    source=str(art.get("source") or ""),
                    fetched_at=str(art.get("fetched_at") or ""),
                    category=art.get("category"),
                    reason=reason,
                )
            )
        else:
            normal_articles.append(
                IssueArticle(
                    id=int(art.get("id", idx)),
                    url=str(art.get("url") or ""),
                    title=str(art.get("title") or ""),
                    source=str(art.get("source") or ""),
                    fetched_at=str(art.get("fetched_at") or ""),
                    category=art.get("category"),
                    summary=str(art.get("summary") or ""),
                    score=round(score, 2),
                    cluster_id=doc_cluster_id_map.get(idx),
                    matched_terms=matched,
                )
            )

    # 5. Related Terms (Significant keywords with high document frequency in this result)
    related_terms: list[RelatedTerm] = []
    if feature_names and doc_vectors is not None:
        term_dfs = (doc_vectors > 0).sum(axis=0)
        # Find terms with highest frequency in this result set
        term_indices = term_dfs.argsort()[::-1]
        for t_idx in term_indices[:15]:
            t_name = feature_names[t_idx]
            df_count = int(term_dfs[t_idx])
            if df_count < 2:
                continue

            # Calculate score / lift against background if available
            bg_df = background_word_counts.get(t_name, 1) if background_word_counts else 1
            lift_score = round(float(df_count / (bg_df + 1)), 2)

            related_terms.append(
                RelatedTerm(
                    term=t_name,
                    df=df_count,
                    score=lift_score,
                )
            )

    return {
        "clusters": built_clusters,
        "possibly_unrelated": possibly_unrelated,
        "timeline": timeline,
        "sources": sources_list,
        "categories": categories_list,
        "related_terms": related_terms,
        "articles": normal_articles,
    }
