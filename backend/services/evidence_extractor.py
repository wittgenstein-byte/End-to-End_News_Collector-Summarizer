"""
services/evidence_extractor.py
─────────────────────────────────────────────────────────────────
SOLID  S — Deterministic heuristic extraction of claims, quotes,
           speakers, and event timestamps from raw news articles.
GRASP  Information Expert — Transforms unstructured article text
           into structured EvidenceInputPayload for LLM synthesis.
POLICY Decoupled Architecture — Completely offline, deterministic,
       and fast (<5ms), running without external LLM calls.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from backend.schemas.event_evidence_schema import (
    ClaimType,
    EvidenceArticle,
    EvidenceClaim,
    EvidenceInputPayload,
)

# Regular expressions for direct quote extraction
_QUOTE_PATTERN = re.compile(r'["“]([^"”]{10,250})["”]')

# Regular expressions for Thai speaker attributions and speech verbs
_SPEECH_VERBS = (
    "เผยว่า", "ระบุว่า", "ชี้ว่า", "แถลงว่า", "ยืนยันว่า", "เปิดเผยว่า",
    "เตือนว่า", "กล่าวว่า", "โพสต์ข้อความว่า", "แย้งว่า", "วิจารณ์ว่า",
    "ประเมินว่า", "มองว่า", "คาดว่า", "รายงานว่า", "ประกาศว่า"
)

_SPEAKER_TITLES = (
    "นาย", "นาง", "นางสาว", "ดร.", "ผศ.", "รศ.", "ศ.", "พล.อ.", "พล.ต.ท.",
    "พล.ต.ต.", "พ.ต.อ.", "โฆษก", "รัฐมนตรี", "ประธาน", "เลขาธิการ",
    "ผู้ว่าการ", "ผู้ว่าฯ", "อธิบดี", "ผบ.ตร.", "นายกฯ", "นายกรัฐมนตรี",
)


class EvidenceExtractor:
    """
    Lightweight deterministic extractor converting article records or dictionaries
    into structured evidence objects.
    """

    @classmethod
    def extract_claims(cls, text: str, article_id: str) -> list[EvidenceClaim]:
        """
        Extract direct quotes and attribution claims from article text.
        """
        if not text:
            return []

        claims: list[EvidenceClaim] = []
        claim_counter = 1

        # 1. Extract direct quotes
        quote_matches = _QUOTE_PATTERN.findall(text)
        for quote in quote_matches[:3]:  # Top 3 quotes
            clean_quote = quote.strip()
            if len(clean_quote) < 15:
                continue

            # Heuristically detect speaker before or after quote
            speaker = cls._find_speaker_near(text, clean_quote)
            claim_type = cls._classify_claim_type(clean_quote, speaker)

            claims.append(
                EvidenceClaim(
                    claim_id=f"{article_id}_c{claim_counter:02d}",
                    text=clean_quote,
                    claim_type=claim_type,
                    speaker=speaker or "แหล่งข่าว",
                    evidence_quote=clean_quote,
                )
            )
            claim_counter += 1

        # 2. Extract speech verb sentences if quotes were sparse
        if len(claims) < 2:
            for verb in _SPEECH_VERBS:
                if verb in text:
                    parts = text.split(verb)
                    if len(parts) >= 2:
                        left = parts[0].strip().split()[-3:]
                        right = parts[1].strip()
                        # Take up to end of sentence or 120 chars
                        sentence = right.split("।")[0].split("\n")[0][:120].strip()
                        speaker_hint = " ".join(left)
                        speaker = cls._clean_speaker(speaker_hint)

                        if sentence and len(sentence) >= 15:
                            claim_type = cls._classify_claim_type(sentence, verb)
                            claims.append(
                                EvidenceClaim(
                                    claim_id=f"{article_id}_c{claim_counter:02d}",
                                    text=sentence,
                                    claim_type=claim_type,
                                    speaker=speaker or "ผู้ให้ข้อมูล",
                                    evidence_quote=f"{verb} {sentence}",
                                )
                            )
                            claim_counter += 1
                            if len(claims) >= 3:
                                break

        return claims

    @classmethod
    def _find_speaker_near(cls, full_text: str, quote: str) -> str:
        """Find likely speaker title or name in proximity to the quote."""
        idx = full_text.find(quote)
        if idx == -1:
            return ""

        # Search 100 characters before quote
        prefix = full_text[max(0, idx - 100):idx]
        for title in _SPEAKER_TITLES:
            if title in prefix:
                sub = prefix[prefix.rfind(title):]
                words = sub.split()[:3]
                return cls._clean_speaker(" ".join(words))

        # Search 100 characters after quote
        suffix = full_text[idx + len(quote):min(len(full_text), idx + len(quote) + 100)]
        for verb in _SPEECH_VERBS:
            if verb in suffix:
                sub = suffix[:suffix.find(verb)]
                for title in _SPEAKER_TITLES:
                    if title in sub:
                        t_idx = sub.find(title)
                        words = sub[t_idx:].split()[:3]
                        return cls._clean_speaker(" ".join(words))

        return ""

    @classmethod
    def _clean_speaker(cls, raw: str) -> str:
        """Clean speaker name or title from punctuation and conjunctions."""
        cleaned = re.sub(r'[^\w\s\.\-ก-๙]', '', raw).strip()
        words = cleaned.split()
        return " ".join(words[:4]) if words else ""

    @classmethod
    def _classify_claim_type(cls, text: str, context: str) -> ClaimType:
        """Categorize the statement into a typed ClaimType."""
        combined = f"{context} {text}"
        if any(w in combined for w in ("แถลง", "ประกาศ", "แถลงการณ์", "หนังสือเวียน")):
            return "official_statement"
        if any(w in combined for w in ("กล่าวหา", "แฉ", "ร้องเรียน", "ยื่นฟ้อง", "ชี้ช่อง", "ฮั้ว")):
            return "accusation"
        if any(w in combined for w in ("คาดการณ์", "ประเมิน", "แนวโน้ม", "ลุ้น", "คาดว่า")):
            return "forecast"
        if any(w in combined for w in ("มองว่า", "เห็นว่า", "วิจารณ์", "ทัศนะ", "เตือนว่า")):
            return "opinion"
        return "fact_report"

    @classmethod
    def build_payload(
        cls,
        event_id: str,
        title: str,
        articles: Sequence[Any],
        first_seen_at: str | None = None,
        updated_at: str | None = None,
    ) -> EvidenceInputPayload:
        """
        Assemble the full EvidenceInputPayload from a collection of raw articles.
        """
        evidence_articles: list[EvidenceArticle] = []

        timestamps: list[str] = []

        for idx, art in enumerate(articles, start=1):
            # Support both Pydantic model and dict
            if isinstance(art, dict):
                art_id = str(art.get("article_id") or f"art_{idx:02d}")
                art_title = str(art.get("title") or "").strip()
                art_summary = str(art.get("summary") or "").strip()
                art_source = str(art.get("source") or "สำนักข่าว").strip()
                art_url = str(art.get("url") or "").strip()
                art_time = str(art.get("fetched_at") or art.get("published_at") or "").strip()
            else:
                art_id = str(getattr(art, "article_id", None) or f"art_{idx:02d}")
                art_title = getattr(art, "title", "")
                art_summary = getattr(art, "summary", "")
                art_source = getattr(art, "source", "สำนักข่าว")
                art_url = getattr(art, "url", "")
                art_time = str(getattr(art, "fetched_at", "") or getattr(art, "published_at", "") or "")

            if art_time:
                timestamps.append(art_time)

            content_text = f"{art_title}\n{art_summary}"
            claims = cls.extract_claims(content_text, art_id)

            evidence_articles.append(
                EvidenceArticle(
                    article_id=art_id,
                    source=art_source,
                    published_at=art_time,
                    event_time=art_time or None,
                    title=art_title,
                    summary=art_summary,
                    claims=claims,
                    canonical_url=art_url,
                )
            )

        sorted_ts = sorted(timestamps)
        effective_first = first_seen_at or (sorted_ts[0] if sorted_ts else "")
        effective_updated = updated_at or (sorted_ts[-1] if sorted_ts else "")

        return EvidenceInputPayload(
            event_id=event_id,
            title=title,
            first_seen_at=effective_first,
            updated_at=effective_updated,
            articles=evidence_articles,
        )
