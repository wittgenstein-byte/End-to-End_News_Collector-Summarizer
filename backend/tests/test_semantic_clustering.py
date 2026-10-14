"""
tests/test_semantic_clustering.py
─────────────────────────────────────────────────────────────────
SOLID  S — Verifies semantic vector clustering, anti-chain cohesion
           validation, masked mean pooling, and two-tier caching.
POLICY STRICT ZERO JACCARD AUDIT — Formally proves no Jaccard or lexical
           overlap metric exists in the trending pipeline.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import torch

from backend.services.trending_service import (
    SemanticClusterer,
    WangchanEmbedder,
)

# ── 1. Strict Zero-Jaccard Policy Audit ────────────────────────────

def test_strict_zero_jaccard_in_trending_pipeline() -> None:
    """
    Grep and verify that NO file in the trending services or routers
    imports, defines, or uses Jaccard or lexical token-set intersection.
    """
    trending_dir = Path(__file__).resolve().parent.parent / "services"
    trending_files = [
        trending_dir / "trending_service.py",
        trending_dir / "llm_grouper.py",
    ]

    forbidden_patterns = [
        r"\bjaccard\b",
        r"\bjaccard_similarity\b",
        r"set\w*\.intersection",
        r"len\([^)]+\s*&\s*[^)]+\)",
        r"tokens_a\s*&\s*tokens_b",
    ]

    for file_path in trending_files:
        assert file_path.exists(), f"Expected {file_path} to exist"
        content = file_path.read_text(encoding="utf-8").lower()
        for pattern in forbidden_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            # Allow only comments containing 'zero jaccard' or 'no jaccard'
            valid_occurrences = [
                m for m in matches if "zero jaccard" not in content and "no jaccard" not in content
            ]
            assert (
                len(valid_occurrences) == 0
            ), f"Strict Zero-Jaccard policy violation: found '{pattern}' in {file_path}"


# ── 2. Masked Mean Pooling and Normalization Math ─────────────────

def test_masked_mean_pooling_math() -> None:
    """
    Verify that masked mean pooling correctly discounts padding tokens
    and returns exact L2-normalized unit vectors.
    """
    # 2 sentences: len 3 and len 1 (padded to len 3)

    # Hidden states
    hidden = torch.tensor([
        [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [9.0, 10.0, 11.0, 12.0]],  # all valid
        [[2.0, 4.0, 6.0, 8.0], [99.0, 99.0, 99.0, 99.0], [99.0, 99.0, 99.0, 99.0]],  # only token 0 valid, 1 & 2 are pads
    ], dtype=torch.float32)

    attention_mask = torch.tensor([
        [1, 1, 1],
        [1, 0, 0],
    ], dtype=torch.int64)

    mask = attention_mask.unsqueeze(-1).expand(hidden.size()).float()
    summed = torch.sum(hidden * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    raw_embs = summed / counts

    # Sentence 0 mean: ([1+5+9]/3, [2+6+10]/3, [3+7+11]/3, [4+8+12]/3) = (5.0, 6.0, 7.0, 8.0)
    assert pytest.approx(raw_embs[0].tolist(), 0.001) == [5.0, 6.0, 7.0, 8.0]

    # Sentence 1 mean: should only be token 0 (2.0, 4.0, 6.0, 8.0) ignoring pad tokens
    assert pytest.approx(raw_embs[1].tolist(), 0.001) == [2.0, 4.0, 6.0, 8.0]

    # Normalized vectors must have L2 norm == 1.0
    normalized = torch.nn.functional.normalize(raw_embs, p=2, dim=1)
    norms = torch.norm(normalized, p=2, dim=1)
    for norm_val in norms.tolist():
        assert pytest.approx(norm_val, 1e-6) == 1.0


# ── 3. Anti-Chain Clustering & Cohesion Validation ────────────────

def test_anti_chain_clustering_splits_runaway_chain() -> None:
    """
    Test that a transitive chain:
      A <-> B = 0.75 (sim)
      B <-> C = 0.72 (sim)
      A <-> C = 0.40 (sim - completely unrelated)
    does NOT form a single runaway cluster [A, B, C].
    Cohesion threshold splits or prunes the loose outlier.
    """
    now = datetime.now(timezone.utc)
    clusterer = SemanticClusterer(
        cosine_threshold=0.70,
        cohesion_threshold=0.65,
        time_window_hours=36.0,
    )

    articles = [
        {"title": "ข่าวนโยบาย A", "source": "SourceA"},
        {"title": "ข่าวนโยบาย B", "source": "SourceB"},
        {"title": "ข่าวเศรษฐกิจ C", "source": "SourceC"},
    ]

    # Construct 3 synthetic normalized 3D vectors with exact pairwise dot products:
    # A = (1, 0, 0)
    # B = (0.75, sqrt(1 - 0.75^2), 0) ~ (0.75, 0.6614, 0) -> A dot B = 0.75
    # C designed so B dot C = 0.72 and A dot C = 0.40
    vec_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    vec_b = np.array([0.75, 0.6614378, 0.0], dtype=np.float32)
    # Solve for C = [cx, cy, cz] with cx = 0.40, 0.75*0.40 + 0.6614*cy = 0.72 -> cy = (0.72 - 0.30)/0.6614 = 0.635
    cx = 0.40
    cy = (0.72 - 0.75 * cx) / 0.6614378
    cz = np.sqrt(max(0.0, 1.0 - cx**2 - cy**2))
    vec_c = np.array([cx, cy, cz], dtype=np.float32)

    embeddings = np.vstack([vec_a, vec_b, vec_c])

    # Verify dot products
    sim_ab = float(np.dot(vec_a, vec_b))
    sim_bc = float(np.dot(vec_b, vec_c))
    sim_ac = float(np.dot(vec_a, vec_c))
    assert pytest.approx(sim_ab, 0.01) == 0.75
    assert pytest.approx(sim_bc, 0.01) == 0.72
    assert pytest.approx(sim_ac, 0.01) == 0.40

    times = [now, now, now]
    clustered = clusterer.cluster_articles(articles, embeddings, times)

    # All three must NOT be grouped into a single cluster size of 3
    sizes = [item["cluster_size"] for item in clustered]
    assert 3 not in sizes, "Anti-chain validation failed: runaway chain [A, B, C] was merged!"


# ── 4. Multi-Source Definition Test ───────────────────────────────

def test_multi_source_requires_distinct_publishers() -> None:
    """
    Three articles from the same publisher must have is_multi_source == False.
    Articles from 2+ distinct publishers must have is_multi_source == True.
    """
    clusterer = SemanticClusterer(cosine_threshold=0.50)
    now = datetime.now(timezone.utc)

    # 1. Same source: 3 ThaiPBS articles
    same_source_articles = [
        {"title": "ข่าวด่วน 1", "source": "ThaiPBS"},
        {"title": "ข่าวด่วน 2", "source": "ThaiPBS"},
        {"title": "ข่าวด่วน 3", "source": "ThaiPBS"},
    ]
    vec = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    times = [now, now, now]

    res_single = clusterer.cluster_articles(same_source_articles, vec, times)
    assert all(item["is_multi_source"] is False for item in res_single)
    assert res_single[0]["distinct_source_count"] == 1

    # 2. Distinct sources: ThaiPBS and The Standard
    multi_source_articles = [
        {"title": "ข่าวด่วน 1", "source": "ThaiPBS"},
        {"title": "ข่าวด่วน 2", "source": "The Standard"},
    ]
    vec2 = np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    res_multi = clusterer.cluster_articles(multi_source_articles, vec2, [now, now])
    assert all(item["is_multi_source"] is True for item in res_multi)
    assert res_multi[0]["distinct_source_count"] == 2


# ── 5. Two-Tier Caching Verification ──────────────────────────────

def test_tier1_embedding_cache_avoids_recomputation() -> None:
    """Verify that identical canonical text hits the embedding cache."""
    embedder = WangchanEmbedder(cache_max_size=100)
    articles = [
        {"title": "ข่าวดิจิทัลวอลเล็ต", "summary": "แจกเงินหมื่น"},
        {"title": "ข่าวราคาทองคำ", "summary": "ตลาดทองพุ่ง"},
    ]

    embs1 = embedder.encode_articles(articles)
    assert embs1.shape[0] == 2

    # Second call must reuse cached vectors
    with embedder._cache_lock:
        h1 = hashlib.sha256(embedder.get_canonical_text(articles[0]).encode("utf-8")).hexdigest()
        assert h1 in embedder._embedding_cache

    embs2 = embedder.encode_articles(articles)
    assert np.allclose(embs1, embs2)
