"""
services/summarizer_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — ส่ง Markdown ให้ LLM แล้วคืน NewsSummary เท่านั้น
           ไม่รู้จัก HTTP, storage, หรือ WebSocket
SOLID  D — รับ OpenAI client และ settings ผ่าน constructor
GRASP  Information Expert — รู้จัก SYSTEM_PROMPT และวิธีแปลง output
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from openai import OpenAI

from backend.core.cache import AsyncInMemoryCache, CachePort
from backend.schemas.news_schema import NewsSummary

logger = logging.getLogger(__name__)

# ── URL Normalization Helper ──────────────────────────────────────

_TRACKING_PARAMS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
    "_ga",
    "_gl",
    "mc_cid",
    "mc_eid",
})


def normalize_article_url(raw_url: str) -> str:
    """
    Normalize article URL for consistent cache key generation.
    Strips fragments, removes tracking query parameters, lowercases scheme/host,
    and strips trailing slash on path (unless path is '/').
    """
    if not raw_url or not raw_url.strip():
        return ""
    parsed = urlparse(raw_url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    query_params = parse_qsl(parsed.query, keep_blank_values=False)
    filtered_params = sorted(
        (k, v)
        for k, v in query_params
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
    )
    query = urlencode(filtered_params)
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


# ── System prompt ─────────────────────────────────────────────────
# แยกออกมาเป็น constant เพื่อ test ได้ง่าย และ modify โดยไม่แก้ logic

SYSTEM_PROMPT = """You are a professional news summarizer. Your task is to read news articles written 
in Markdown format and produce structured summaries.

## Language Rule
Always respond in the SAME language as the article. Do not translate.

## Output Format
Return ONLY a valid JSON object with this exact structure — no preamble, no markdown fences.

{
  "title": "...",
  "source_url": "...",
  "published_at": "...",
  "language": "...",
  "summary": "2–3 sentence paragraph summarizing the article.",
  "bullets": [
    "Key point 1 (concise, one sentence)",
    "Key point 2",
    "Key point 3",
    "Key point 4 (optional)",
    "Key point 5 (optional)"
  ],
  "category": "...",
  "sentiment": "positive | neutral | negative",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}

## Rules
- `bullets`: 3–5 items. Each bullet must be a complete, standalone sentence.
- `summary`: dense, factual, no filler words.
- `sentiment`: infer from overall tone and content.
- `keywords`: 3–5 most important topic keywords.
- `category`: one of: politics, economy, technology, health, environment, society, sports, entertainment, world
- If any field is unknown or unavailable, use null.
- Never include commentary, opinions, or content outside the JSON."""


# ── Service ───────────────────────────────────────────────────────

class SummarizerService:
    """ส่ง Markdown content ให้ LLM และแปลง JSON response เป็น NewsSummary พร้อม Tier Cascade Fallback & In-Memory Cache"""

    def __init__(
        self,
        client: OpenAI,
        model: str | None = None,
        models: list[str] | None = None,
        temperature: float = 0.3,
        cache: CachePort[NewsSummary] | None = None,
    ) -> None:
        self._client      = client
        self._temperature = temperature
        self._cache       = cache

        if models:
            self._models = list(models)
        elif model:
            self._models = [model]
        else:
            self._models = ["qwen3-next-80b-a3b-instruct"]

    @property
    def model(self) -> str:
        """Primary model (แรกสุดใน cascade)"""
        return self._models[0] if self._models else ""

    @property
    def models(self) -> list[str]:
        """Candidate models ทั้งหมดใน cascade"""
        return list(self._models)

    async def summarize_async(
        self,
        markdown_content: str,
        url: str = "",
    ) -> NewsSummary:
        """
        Summarize markdown content asynchronously with in-memory caching and stampede protection.
        """
        if url:
            normalized = normalize_article_url(url)
            key = f"summary:url:{normalized}"
        else:
            h = hashlib.sha256(markdown_content.strip().encode("utf-8")).hexdigest()
            key = f"summary:hash:{h}"

        if self._cache is not None:
            return await self._cache.get_or_compute(
                key,
                lambda: asyncio.to_thread(self.summarize, markdown_content),
            )

        return await asyncio.to_thread(self.summarize, markdown_content)

    def summarize(self, markdown_content: str) -> NewsSummary:
        """
        เรียก LLM แบบ sync พร้อม Tiered Cascading Fallback
        ถ้าโมเดลตัวแรกไม่พร้อม/Error จะ cascade ไปยังตัวถัดไปใน tier อัตโนมัติ
        """
        # Trimming content to speed up inference and avoid giant token counts
        max_chars = 4000
        truncated_content = markdown_content
        if len(markdown_content) > max_chars:
            truncated_content = markdown_content[:max_chars] + "\n\n...[Content Truncated]..."

        last_exception: Exception | None = None
        errors: list[str] = []
        for idx, current_model in enumerate(self._models):
            try:
                response = self._client.chat.completions.create(
                    model=current_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": truncated_content},
                    ],
                    stream=False,
                    temperature=self._temperature,
                    timeout=30.0,
                )

                content = response.choices[0].message.content or ""
                raw = content.strip()
                if not raw:
                    raise ValueError(f"Model '{current_model}' returned empty response content.")

                summary = self._parse_output(raw)
                if idx > 0:
                    logger.info(
                        "Cascade Fallback: Successfully summarized using fallback model '%s' (attempt %d/%d)",
                        current_model,
                        idx + 1,
                        len(self._models),
                    )
                return summary
            except Exception as exc:
                last_exception = exc
                err_msg = f"Model '{current_model}' failed: {exc}"
                errors.append(err_msg)
                logger.warning(
                    "⚠️ LLM Cascade: %s. Trying next candidate...",
                    err_msg,
                )

        error_summary = " | ".join(errors)
        logger.error(
            "❌ All %d models in LLM cascade failed. Details: %s",
            len(self._models),
            error_summary,
        )

        if len(self._models) == 1 and last_exception is not None:
            raise last_exception

        if last_exception is not None:
            raise RuntimeError(f"All LLM models in cascade failed: {error_summary}") from last_exception
        raise RuntimeError(f"All LLM models in cascade failed: {error_summary}")

    # ── Private ───────────────────────────────────────────────────

    @staticmethod
    def _parse_output(raw: str) -> NewsSummary:
        """Strip markdown fences แล้ว parse JSON → Pydantic model"""
        cleaned = raw
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        cleaned = cleaned.removesuffix("```").strip()

        data = json.loads(cleaned)
        return NewsSummary.model_validate(data)


# ── DI factory ────────────────────────────────────────────────────

_summary_cache: AsyncInMemoryCache[NewsSummary] | None = None


def get_summary_cache() -> AsyncInMemoryCache[NewsSummary]:
    """Retrieve or initialize the singleton in-memory summary cache."""
    global _summary_cache
    if _summary_cache is None:
        from backend.config import settings

        _summary_cache = AsyncInMemoryCache[NewsSummary](
            max_size=settings.summary_cache_max_size,
            default_ttl_seconds=float(settings.summary_cache_ttl_seconds),
        )
    return _summary_cache


def get_summarizer_service() -> SummarizerService:
    from backend.config import settings

    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return SummarizerService(
        client=client,
        models=settings.llm_cascade_models,
        temperature=settings.llm_temperature,
        cache=get_summary_cache(),
    )