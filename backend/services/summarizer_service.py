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

import json

from openai import OpenAI

from schemas.news_schema import NewsSummary


# ── System prompt ─────────────────────────────────────────────────
# แยกออกมาเป็น constant เพื่อ test ได้ง่าย และ modify โดยไม่แก้ logic

SYSTEM_PROMPT = """You are a professional news summarizer. Your task is to read news articles written in Markdown format and produce structured summaries.

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
    """ส่ง Markdown content ให้ LLM และแปลง JSON response เป็น NewsSummary"""

    def __init__(self, client: OpenAI, model: str, temperature: float) -> None:
        self._client      = client
        self._model       = model
        self._temperature = temperature

    def summarize(self, markdown_content: str) -> NewsSummary:
        """
        เรียก LLM แบบ sync (OpenAI SDK ไม่มี async ใน base class)
        ถ้าต้องการ async ให้ wrap ด้วย asyncio.to_thread
        """
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": markdown_content},
            ],
            stream=False,
            temperature=self._temperature,
        )

        raw = response.choices[0].message.content.strip()
        return self._parse_output(raw)

    # ── Private ───────────────────────────────────────────────────

    @staticmethod
    def _parse_output(raw: str) -> NewsSummary:
        """Strip markdown fences แล้ว parse JSON → Pydantic model"""
        cleaned = raw
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        return NewsSummary.model_validate(data)


# ── DI factory ────────────────────────────────────────────────────

def get_summarizer_service() -> SummarizerService:
    from config import settings
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return SummarizerService(
        client=client,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    )