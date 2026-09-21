"""
services/llm_grouper.py
─────────────────────────────────────────────────────────────────
SOLID  S — Batched metadata enrichment for story clusters (topic title,
           trending hashtags, and cross-publisher summary).
SOLID  O — Supports tiered model cascade with pluggable fallback.
SOLID  D — Injects OpenAI client and Settings abstractions.
GRASP  Information Expert — Knows prompt structure and Pydantic validation.
POLICY Strictly Zero Jaccard — Fallback never uses lexical overlap or Jaccard.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

from backend.config import settings

logger = logging.getLogger(__name__)

# Basic Thai stopwords for clean heuristic hashtag extraction fallback
_FALLBACK_STOPWORDS = frozenset({
    "ที่", "และ", "ใน", "เป็น", "มี", "ของ", "ให้", "ได้", "การ", "ความ",
    "จะ", "ไป", "มา", "จาก", "กับ", "ว่า", "นี้", "นั้น", "ผู้", "โดย",
    "ก็", "ไม่", "แต่", "เพื่อ", "ถูก", "ยัง", "อีก", "แล้ว", "ถึง", "ถ้า",
    "คน", "เมื่อ", "เลย", "ตาม", "อย่าง", "พบ", "เผย", "ชี้", "เร่ง", "แจง",
    "ฮือฮา", "สุด", "หลัง", "ก่อน", "เตรียม", "ยัน", "หวั่น", "วอน", "ลั่น",
    "วัน", "วันนี้", "ขึ้น", "ลง", "ใหม่", "เก่า", "ต่อ", "เนื่อง", "ทั่ว", "บาท",
    "the", "post", "appeared", "first", "on", "news", "read", "more", "com", "www", "https", "http",
})


class ClusterMetadata(BaseModel):
    """Authoritative metadata for a semantic story cluster."""
    cluster_id: str
    topic_title: str
    hashtags: list[str] = Field(default_factory=list)
    cluster_summary: str | None = None


class BatchEnrichmentResponse(BaseModel):
    """Pydantic model validating batch LLM enrichment output."""
    clusters: list[ClusterMetadata] = Field(default_factory=list)


ENRICHMENT_SYSTEM_PROMPT = """You are a senior news editor and data analyst.
Given groups of pre-clustered news articles reporting on the same event, generate authoritative Thai metadata for each cluster.

Your response must be ONLY valid JSON matching this schema:
{
  "clusters": [
    {
      "cluster_id": "c1",
      "topic_title": "หัวข้อข่าวภาพรวมที่กระชับ ตรงประเด็น เป็นกลาง",
      "hashtags": ["#แฮชแท็ก1", "#แฮชแท็ก2", "#แฮชแท็ก3"],
      "cluster_summary": "สรุปสาระสำคัญ 1-2 ประโยคที่สังเคราะห์จากทุกสำนักข่าว"
    }
  ]
}

Rules:
1. `topic_title`: Authoritative Thai headline synthesizing all sources in the cluster.
2. `hashtags`: 2-4 relevant Thai trending hashtags starting with '#' (e.g. #แจกเงินหมื่น, #ราคาทอง, #ครม).
3. `cluster_summary`: 1-2 factual, neutral sentences.
4. Respond in Thai. Return ONLY valid JSON, no markdown code block fences."""


class LLMBatchEnricher:
    """
    Enriches semantic clusters with topic titles, hashtags, and synthesis summaries.
    Decoupled: Does NOT alter cluster membership or mathematical trend scores.
    """

    def __init__(
        self,
        client: OpenAI | None = None,
        models: list[str] | None = None,
        temperature: float = 0.2,
    ) -> None:
        self._client = client or OpenAI(
            api_key=settings.llm_api_key or "dummy_key",
            base_url=settings.llm_base_url,
        )
        self._models = models or list(settings.llm_cascade_models)
        self._temperature = temperature

    def enrich_clusters(
        self,
        clusters_data: list[dict[str, Any]],
    ) -> dict[str, ClusterMetadata]:
        """
        Enrich multiple clusters in a single batched LLM prompt.
        clusters_data: list of dicts with keys:
          - 'cluster_id': str
          - 'articles': list of dicts (title, summary, source, fetched_at)
        Returns mapping of cluster_id -> ClusterMetadata.
        """
        if not clusters_data:
            return {}

        # If LLM is not configured, immediately use deterministic fallback
        if not settings.llm_api_key or not settings.llm_api_key.strip():
            return self._heuristic_fallback_batch(clusters_data)

        prompt_lines: list[str] = [
            "โปรดสังเคราะห์ชื่อประเด็นหลัก (topic_title), แฮชแท็ก (#hashtags), และสรุปภาพรวม (cluster_summary) สำหรับกลุ่มข่าวต่อไปนี้:\n"
        ]

        for cluster in clusters_data:
            cid = str(cluster.get("cluster_id", ""))
            articles = cluster.get("articles", [])
            prompt_lines.append(f"=== Cluster {cid} (จำนวน {len(articles)} สำนักข่าว) ===")
            for a in articles[:6]:  # Cap to top 6 representative articles per cluster
                title = str(a.get("title", "")).strip()
                summary = str(a.get("summary", "")).strip()[:100]
                source = str(a.get("source", "")).strip()
                prompt_lines.append(f"- [{source}] {title} | {summary}")
            prompt_lines.append("")

        user_content = "\n".join(prompt_lines)

        # Call LLM with Tiered Cascading Fallback
        for idx, model_name in enumerate(self._models):
            try:
                response = self._client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=self._temperature,
                    timeout=15.0,
                    stream=False,
                )
                raw_text = (response.choices[0].message.content or "").strip()
                parsed = self._parse_json_response(raw_text)
                if parsed:
                    result_map: dict[str, ClusterMetadata] = {
                        item.cluster_id: item for item in parsed.clusters
                    }
                    # Ensure all requested clusters have an entry
                    for c in clusters_data:
                        cid = str(c.get("cluster_id", ""))
                        if cid not in result_map:
                            result_map[cid] = self._heuristic_fallback_single(c)
                    if idx > 0:
                        logger.info("LLM Enricher: succeeded using fallback model '%s'", model_name)
                    return result_map
            except Exception as exc:
                logger.warning(
                    "LLM Enricher: model '%s' failed (%s). Trying next in cascade...",
                    model_name,
                    exc,
                )

        logger.warning("LLM Enricher: all cascade models failed. Falling back to deterministic heuristics.")
        return self._heuristic_fallback_batch(clusters_data)

    def _parse_json_response(self, raw: str) -> BatchEnrichmentResponse | None:
        """Strip markdown fences and validate JSON schema via Pydantic."""
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        cleaned = cleaned.removesuffix("```").strip()

        try:
            data = json.loads(cleaned)
            return BatchEnrichmentResponse.model_validate(data)
        except Exception:
            return None

    def _heuristic_fallback_single(self, cluster: dict[str, Any]) -> ClusterMetadata:
        """
        Deterministic fallback extracting clean title and frequency-based hashtags.
        STRICTLY ZERO JACCARD / ZERO LEXICAL OVERLAP METRICS.
        """
        cid = str(cluster.get("cluster_id", ""))
        articles = cluster.get("articles", [])
        if not articles:
            return ClusterMetadata(cluster_id=cid, topic_title="ข่าวด่วน", hashtags=["#ข่าวด่วน"])

        # Topic title defaults to highest-ranked / first article title
        primary_title = str(articles[0].get("title", "")).strip()

        # Extract high-frequency Thai words (length >= 3, not in stopwords)
        word_counts: dict[str, int] = {}
        try:
            from pythainlp.tokenize import word_tokenize
            has_pythainlp = True
        except ImportError:
            has_pythainlp = False

        for a in articles:
            text = f"{a.get('title', '')} {a.get('summary', '')}"
            if has_pythainlp:
                tokens = [t.strip() for t in word_tokenize(text, engine="newmm")]
            else:
                tokens = re.findall(r"[\u0E00-\u0E7Fa-zA-Z0-9]{3,}", text)

            for w in tokens:
                w_clean = w.strip()
                if (
                    len(w_clean) >= 3
                    and w_clean.lower() not in _FALLBACK_STOPWORDS
                    and not w_clean.isdigit()
                    and not re.match(r"^[\W_]+$", w_clean)
                ):
                    word_counts[w_clean] = word_counts.get(w_clean, 0) + 1

        top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        hashtags = [f"#{w}" for w, _ in top_words]
        if not hashtags:
            hashtags = ["#ข่าวเด่น", "#เกาะติดสถานการณ์"]

        summary = str(articles[0].get("summary", "")).strip()[:150]
        return ClusterMetadata(
            cluster_id=cid,
            topic_title=primary_title,
            hashtags=hashtags,
            cluster_summary=summary or None,
        )

    def _heuristic_fallback_batch(
        self, clusters_data: list[dict[str, Any]]
    ) -> dict[str, ClusterMetadata]:
        return {
            str(c.get("cluster_id", "")): self._heuristic_fallback_single(c)
            for c in clusters_data
        }
