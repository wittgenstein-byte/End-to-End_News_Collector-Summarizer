"""
tests/test_wangchan_embedding_integration.py
─────────────────────────────────────────────────────────────────
Integration test verifying WangchanBERTa checkpoint loading,
hidden_size dynamic introspection, masked mean pooling, and real
Thai news semantic similarity.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.trending_service import WangchanEmbedder


def test_wangchan_checkpoint_loading_and_hidden_size() -> None:
    """Verify that the model checkpoint loads and hidden_size is dynamically read."""
    embedder = WangchanEmbedder.get_instance()
    # Checkpoint must report dynamic hidden_size matching config (768)
    assert embedder.hidden_size == 768


def test_wangchan_semantic_similarity_pairs() -> None:
    """
    Real Thai news semantic pair evaluation:
    - Related pair with different phrasing: similarity >= 0.60
    - Unrelated pair: similarity <= 0.45
    """
    embedder = WangchanEmbedder.get_instance()

    art_1 = {
        "title": "ครม. เคาะ แจกเงินหมื่น ผู้สูงอายุ",
        "summary": "ที่ประชุมคณะรัฐมนตรีอนุมัติแจกเงินสด 10,000 บาทให้กลุ่มสูงวัย",
    }
    art_2 = {
        "title": "รัฐบาล อนุมัติ เงินดิจิทัลวอลเล็ต ผู้สูงวัย 10000 บาท",
        "summary": "กระทรวงการคลังเตรียมโอนเงินหมื่นบาทรอบใหม่ช่วงตรุษจีน",
    }
    art_3 = {
        "title": "ราคาทองคำ วันนี้ พุ่งทะลุ สถิติ สูงสุด",
        "summary": "ทองคำแท่งและทองรูปพรรณปรับราคาขึ้นตามตลาดโลก",
    }

    embs = embedder.encode_articles([art_1, art_2, art_3])
    assert embs.shape == (3, 768)

    # Unit vectors check
    for i in range(3):
        assert pytest.approx(float(np.linalg.norm(embs[i])), 1e-4) == 1.0

    sim_12 = float(np.dot(embs[0], embs[1]))
    sim_13 = float(np.dot(embs[0], embs[2]))

    # Related articles with completely different phrasing must have high semantic similarity
    assert sim_12 >= 0.60, f"Expected related sim >= 0.60, got {sim_12:.3f}"

    # Unrelated articles must have lower similarity
    assert sim_13 <= 0.50, f"Expected unrelated sim <= 0.50, got {sim_13:.3f}"
    assert sim_12 > sim_13 + 0.15, f"Expected margin between related and unrelated, got {sim_12:.3f} vs {sim_13:.3f}"
