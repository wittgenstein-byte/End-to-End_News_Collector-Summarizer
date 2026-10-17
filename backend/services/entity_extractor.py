"""
services/entity_extractor.py
─────────────────────────────────────────────────────────────────
SOLID  S — Extracts Thai named entities (person, org, loc, facility).
SOLID  O — Supports configurable target entity types and pluggable NER engine.
SOLID  D — Supports dependency injection for testing and alternative NER backends.
GRASP  Information Expert — Parses BIO tag sequences into coherent entity spans.
GRASP  Pure Fabrication — EntityExtractor isolates PyThaiNLP NER execution and caching.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.schemas.story_schema import (
    EventTimeEvidence,
    TypedEventAnchors,
    _parse_utc_datetime,
)

logger = logging.getLogger(__name__)

BANGKOK_TZ = timezone(timedelta(hours=7))

# Target entity types required by R1 story identification
_TARGET_ENTITY_TYPES: set[str] = {
    # Person
    "PERSON",
    "PER",
    # Organization
    "ORGANIZATION",
    "ORGANISATION",
    "ORG",
    # Location
    "LOCATION",
    "LOC",
    "GPE",
    # Facility
    "FACILITY",
    "FAC",
}


class EntityExtractor:
    """
    PyThaiNLP thainer-v2 NER entity extractor with in-memory caching and fallback.

    Extracts:
    - Person (บุคคล)
    - Organization (องค์กร / หน่วยงาน)
    - Location (สถานที่ / เมือง / ประเทศ)
    - Facility (อาคาร / สิ่งปลูกสร้าง / สถานประกอบการ)

    Features:
    - Lazy singleton initialization of thainer-v2 model
    - In-memory thread-safe LRU cache
    - Graceful fallback on empty strings, short text, or engine errors
    - Deduplication preserving sequence order
    """

    def __init__(self, ner: Any = None, max_cache_size: int = 5000) -> None:
        self._ner = ner
        self._max_cache_size = max_cache_size
        self._cache: dict[str, list[str]] = {}
        self._cache_lock = threading.Lock()
        self._init_lock = threading.Lock()
        self._initialized: bool = ner is not None

    def _ensure_ner(self) -> bool:
        """Lazily load PyThaiNLP thainer-v2 NER engine with thread safety."""
        if self._initialized:
            return self._ner is not None

        with self._init_lock:
            if self._initialized:
                return self._ner is not None

            try:
                from pythainlp.tag.named_entity import NER

                self._ner = NER(engine="thainer-v2")
                self._initialized = True
                return True
            except Exception as exc:
                logger.warning(
                    "PyThaiNLP thainer-v2 NER failed to initialize (%s); fallback to empty entities",
                    exc,
                )
                self._ner = None
                self._initialized = True
                return False

    def extract_entities(self, text: str) -> list[str]:
        """
        Extract person, organization, location, and facility entities from Thai text.
        Returns a list of unique entity strings in order of occurrence.
        """
        if not text or not isinstance(text, str):
            return []

        clean_text = text.strip()
        if len(clean_text) < 3:
            return []

        # Check in-memory cache
        cache_key = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return list(cached)

        # Execute extraction with fallback
        entities = self._extract_raw(clean_text)

        # Store in bounded cache
        with self._cache_lock:
            if len(self._cache) >= self._max_cache_size:
                # Evict oldest entry (FIFO in dict)
                try:
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                except (StopIteration, KeyError):
                    pass
            self._cache[cache_key] = list(entities)

        return entities

    def _extract_raw(self, text: str) -> list[str]:
        """Execute NER model tagging and assemble BIO spans into entity strings."""
        if not self._ensure_ner() or self._ner is None:
            return []

        safe_text = text[:800] if len(text) > 800 else text
        try:
            tagged = self._ner.tag(safe_text)
        except Exception as exc:
            logger.warning("NER tagging failed on text (%s); returning empty list", exc)
            return []

        if not tagged or not isinstance(tagged, (list, tuple)):
            return []

        entities: list[str] = []
        seen: set[str] = set()

        current_tokens: list[str] = []
        current_type: str | None = None

        def flush() -> None:
            nonlocal current_tokens, current_type
            if current_tokens and current_type:
                span = "".join(current_tokens).strip()
                # Clean up outer quotes, brackets, and whitespace (preserving Thai acronym periods like ครม.)
                span = span.strip(" \t\n\r()[]{}\"'“”‘’«»,;:-_")
                if len(span) >= 2 and span not in seen:
                    entities.append(span)
                    seen.add(span)
            current_tokens = []
            current_type = None

        for item in tagged:
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                flush()
                continue

            word = str(item[0])
            raw_tag = str(item[1]).strip().upper()

            # Parse BIO tag e.g. B-PERSON, I-ORGANIZATION, B_LOCATION
            prefix: str
            tag_type: str
            if "-" in raw_tag:
                prefix, tag_type = raw_tag.split("-", 1)
            elif "_" in raw_tag:
                prefix, tag_type = raw_tag.split("_", 1)
            elif raw_tag in _TARGET_ENTITY_TYPES:
                prefix, tag_type = "B", raw_tag
            else:
                prefix, tag_type = raw_tag, ""

            if tag_type in _TARGET_ENTITY_TYPES:
                if prefix == "B":
                    flush()
                    current_tokens = [word]
                    current_type = tag_type
                elif prefix == "I":
                    if current_type == tag_type:
                        current_tokens.append(word)
                    else:
                        flush()
                        current_tokens = [word]
                        current_type = tag_type
                else:
                    flush()
            else:
                flush()

        flush()
        return entities

    def clear_cache(self) -> None:
        """Clear the in-memory entity cache."""
        with self._cache_lock:
            self._cache.clear()

    def extract_event_time_evidence(
        self,
        text: str,
        published_at: datetime | str | None = None,
    ) -> EventTimeEvidence:
        """
        Extract interval-based incident time evidence from Thai text,
        normalizing Buddhist Era years, UTC+7 timezone, and preserving ambiguity.
        """
        return extract_event_time_evidence(text, published_at=published_at)

    def extract_typed_anchors(
        self,
        text: str,
        entities: list[str] | None = None,
    ) -> TypedEventAnchors:
        """
        Extract typed entity anchors (locations, actor names, generic roles, targets, actions, storyline).
        """
        resolved_entities = entities if entities is not None else self.extract_entities(text)
        return extract_typed_anchors(text, resolved_entities)


# ── Global Constants & Thai Date/Time Parsers ─────────────────────

_THAI_MONTHS: dict[str, int] = {
    "มกราคม": 1, "ม.ค.": 1, "ม.ค": 1,
    "กุมภาพันธ์": 2, "ก.พ.": 2, "ก.พ": 2,
    "มีนาคม": 3, "มี.ค.": 3, "มี.ค": 3,
    "เมษายน": 4, "เม.ย.": 4, "เม.ย": 4,
    "พฤษภาคม": 5, "พ.ค.": 5, "พ.ค": 5,
    "มิถุนายน": 6, "มิ.ย.": 6, "มิ.ย": 6,
    "กรกฎาคม": 7, "ก.ค.": 7, "ก.ค": 7,
    "สิงหาคม": 8, "ส.ค.": 8, "ส.ค": 8,
    "กันยายน": 9, "ก.ย.": 9, "ก.ย": 9,
    "ตุลาคม": 10, "ต.ค.": 10, "ต.ค": 10,
    "พฤศจิกายน": 11, "พ.ย.": 11, "พ.ย": 11,
    "ธันวาคม": 12, "ธ.ค.": 12, "ธ.ค": 12,
}

_GENERIC_ROLES: frozenset[str] = frozenset({
    "นายกรัฐมนตรี", "นายกฯ", "รมว.", "รัฐมนตรี", "ผบ.ตร.", "ผู้ว่าฯ", "ผู้ว่าราชการจังหวัด",
    "ตำรวจ", "เจ้าหน้าที่ตำรวจ", "เจ้าหน้าที่", "เจ้าหน้าที่กู้ภัย", "แพทย์", "พยาบาล",
    "กู้ภัย", "มูลนิธิ", "ศาล", "อัยการ", "ทนายความ", "ทนาย", "ส.ส.", "ส.ว.", "ครม.",
    "โฆษกประจำสำนักนายกรัฐมนตรี", "พนักงานสอบสวน", "ฝ่ายสืบสวน", "ผู้การ", "รัฐบาล",
})

_TARGET_KEYWORDS: frozenset[str] = frozenset({
    "ผู้เสียชีวิต", "ผู้บาดเจ็บ", "เหยื่อ", "ผู้เสียหาย", "ประชาชน", "ชาวบ้าน",
    "บ้านเรือน", "สะพาน", "ถนน", "รถยนต์", "เรือ", "เครื่องบิน", "อาคาร", "โรงงาน",
})

_ACTION_KEYWORDS: frozenset[str] = frozenset({
    "จับกุม", "แจ้งข้อหา", "สอบสวน", "แถลงข่าว", "ฟ้องร้อง", "เยียวยา", "บุกค้น",
    "สั่งการ", "ลงพื้นที่", "เร่งช่วย", "อพยพ", "ควบคุมเพลิง", "กู้ซาก", "ชันสูตร",
    "ลอบยิง", "ยิง", "ชน", "ล่ม", "ถล่ม", "ไฟไหม้", "เพลิงไหม้", "ท่วม",
})

_STORYLINE_PATTERNS = [
    re.compile(r"(น้ำท่วม[ก-๙]+)"),
    re.compile(r"(ไฟไหม้[ก-๙]+)"),
    re.compile(r"(กราดยิง[ก-๙]+)"),
    re.compile(r"(คดี[ก-๙]+)"),
    re.compile(r"(เรือล่ม[ก-๙]+)"),
]

_WIRE_MARKERS: frozenset[str] = frozenset({
    "ที่มา:", "ขอบคุณข้อมูล", "รายงานโดยสำนักข่าวเดียวกัน", "สำนักข่าวไทย",
    "รอยเตอร์", "เอเอฟพี", "reuters", "afp", "ap news", "สำนักข่าว",
})

_DATE_REGEX = re.compile(
    r"(?:เมื่อ)?(?:วันที่\s*)?(\d{1,2})\s+("
    + "|".join(re.escape(k) for k in _THAI_MONTHS)
    + r")(?:\s+(?:พ\.ศ\.\s*)?(\d{2,4}))?",
    re.IGNORECASE,
)
_TIME_REGEX = re.compile(
    r"(?:เวลา\s*)?([012]?\d)[:.]([0-5]\d)(?:\s*น\.?)?",
    re.IGNORECASE,
)
_RELATIVE_REGEX = re.compile(
    r"(เมื่อวานนี้|เมื่อวาน|เมื่อคืนนี้|เมื่อคืนที่ผ่านมา|เมื่อเช้านี้|เมื่อเช้า|วันนี้)",
    re.IGNORECASE,
)


def _normalize_year(raw_year: int) -> int:
    if raw_year >= 2500:
        return raw_year - 543
    if raw_year < 100:
        return (2500 + raw_year) - 543
    return raw_year


def extract_event_time_evidence(
    text: str,
    published_at: datetime | str | None = None,
) -> EventTimeEvidence:
    """
    Contract A: Extract interval-based incident time evidence from Thai text.
    Handles Buddhist Era years, UTC+7 timezone conversion, relative intervals,
    and year-ambiguity semantics.
    """
    if not text or not isinstance(text, str):
        return EventTimeEvidence(precision="none", confidence="none")

    clean_text = text.strip()

    # 1. Explicit calendar date match
    date_match = _DATE_REGEX.search(clean_text)
    if date_match:
        day = int(date_match.group(1))
        month_name = date_match.group(2)
        month = _THAI_MONTHS.get(month_name, 1)
        year_str = date_match.group(3)

        if year_str:
            year = _normalize_year(int(year_str))
            time_match = _TIME_REGEX.search(clean_text)
            if time_match:
                h = int(time_match.group(1))
                m = int(time_match.group(2))
                try:
                    dt_bkk = datetime(year, month, day, h, m, 0, tzinfo=BANGKOK_TZ)
                    dt_utc = dt_bkk.astimezone(timezone.utc)
                    return EventTimeEvidence(
                        start_utc=dt_utc,
                        end_utc=dt_utc,
                        precision="datetime",
                        confidence="explicit",
                        evidence_span=date_match.group(0),
                    )
                except ValueError:
                    pass

            # Explicit date without clock time spans full Thai calendar day
            try:
                dt_start_bkk = datetime(year, month, day, 0, 0, 0, tzinfo=BANGKOK_TZ)
                dt_end_bkk = datetime(year, month, day, 23, 59, 59, tzinfo=BANGKOK_TZ)
                return EventTimeEvidence(
                    start_utc=dt_start_bkk.astimezone(timezone.utc),
                    end_utc=dt_end_bkk.astimezone(timezone.utc),
                    precision="date",
                    confidence="explicit",
                    evidence_span=date_match.group(0),
                )
            except ValueError:
                pass

        # Yearless date e.g. "เมื่อวันที่ 20 ส.ค."
        if published_at is not None:
            pub_dt = _parse_utc_datetime(published_at).astimezone(BANGKOK_TZ)
            try:
                cand_dt = datetime(pub_dt.year, month, day, tzinfo=BANGKOK_TZ)
            except ValueError:
                cand_dt = None

            if cand_dt and (pub_dt - timedelta(days=30) <= cand_dt <= pub_dt + timedelta(days=2)):
                year = pub_dt.year
                time_match = _TIME_REGEX.search(clean_text)
                if time_match:
                    h = int(time_match.group(1))
                    m = int(time_match.group(2))
                    dt_bkk = datetime(year, month, day, h, m, 0, tzinfo=BANGKOK_TZ)
                    return EventTimeEvidence(
                        start_utc=dt_bkk.astimezone(timezone.utc),
                        end_utc=dt_bkk.astimezone(timezone.utc),
                        precision="datetime",
                        confidence="explicit",
                        evidence_span=date_match.group(0),
                    )
                dt_start_bkk = datetime(year, month, day, 0, 0, 0, tzinfo=BANGKOK_TZ)
                dt_end_bkk = datetime(year, month, day, 23, 59, 59, tzinfo=BANGKOK_TZ)
                return EventTimeEvidence(
                    start_utc=dt_start_bkk.astimezone(timezone.utc),
                    end_utc=dt_end_bkk.astimezone(timezone.utc),
                    precision="date",
                    confidence="explicit",
                    evidence_span=date_match.group(0),
                )
            else:
                # Outside 30-day window -> ambiguous
                return EventTimeEvidence(
                    start_utc=None,
                    end_utc=None,
                    precision="ambiguous",
                    confidence="ambiguous",
                    evidence_span=date_match.group(0),
                )
        else:
            # Missing published_at -> ambiguous
            return EventTimeEvidence(
                start_utc=None,
                end_utc=None,
                precision="ambiguous",
                confidence="ambiguous",
                evidence_span=date_match.group(0),
            )

    # 2. Relative temporal expressions
    rel_match = _RELATIVE_REGEX.search(clean_text)
    if rel_match and published_at is not None:
        span_text = rel_match.group(1)
        pub_dt = _parse_utc_datetime(published_at).astimezone(BANGKOK_TZ)
        if "เมื่อวาน" in span_text:
            rel_d = (pub_dt - timedelta(days=1)).date()
            dt_s = datetime(rel_d.year, rel_d.month, rel_d.day, 0, 0, 0, tzinfo=BANGKOK_TZ).astimezone(timezone.utc)
            dt_e = datetime(rel_d.year, rel_d.month, rel_d.day, 23, 59, 59, tzinfo=BANGKOK_TZ).astimezone(timezone.utc)
            return EventTimeEvidence(
                start_utc=dt_s,
                end_utc=dt_e,
                precision="relative_interval",
                confidence="relative",
                evidence_span=span_text,
            )
        elif "เมื่อคืน" in span_text:
            prev_d = (pub_dt - timedelta(days=1)).date()
            dt_s = datetime(prev_d.year, prev_d.month, prev_d.day, 19, 0, 0, tzinfo=BANGKOK_TZ).astimezone(timezone.utc)
            dt_e = datetime(pub_dt.year, pub_dt.month, pub_dt.day, 6, 0, 0, tzinfo=BANGKOK_TZ).astimezone(timezone.utc)
            return EventTimeEvidence(
                start_utc=dt_s,
                end_utc=dt_e,
                precision="relative_interval",
                confidence="relative",
                evidence_span=span_text,
            )
        elif "เมื่อเช้า" in span_text or "วันนี้" in span_text:
            rel_d = pub_dt.date()
            dt_s = datetime(rel_d.year, rel_d.month, rel_d.day, 0, 0, 0, tzinfo=BANGKOK_TZ).astimezone(timezone.utc)
            dt_e = datetime(rel_d.year, rel_d.month, rel_d.day, 23, 59, 59, tzinfo=BANGKOK_TZ).astimezone(timezone.utc)
            return EventTimeEvidence(
                start_utc=dt_s,
                end_utc=dt_e,
                precision="relative_interval",
                confidence="relative",
                evidence_span=span_text,
            )

    return EventTimeEvidence(start_utc=None, end_utc=None, precision="none", confidence="none")


def extract_typed_anchors(
    text: str,
    entities: list[str] | None = None,
) -> TypedEventAnchors:
    """
    Extract structured typed event anchors from Thai text and named entities.
    Separates proper actor names from generic actor roles, extracts targets,
    incident actions, and storyline anchors.
    """
    locations: list[str] = []
    actor_names: list[str] = []
    actor_roles: list[str] = []
    targets: list[str] = []
    actions: list[str] = []
    storyline_anchor: str | None = None

    clean_text = text or ""

    # Process named entities
    raw_entities = entities if entities is not None else extract_entities(clean_text)
    for ent in raw_entities:
        ent_clean = ent.strip()
        if not ent_clean:
            continue

        if ent_clean in _GENERIC_ROLES or ent_clean.startswith(("เจ้าหน้าที่", "ตำรวจ", "พนักงาน")):
            if ent_clean not in actor_roles:
                actor_roles.append(ent_clean)
        elif ent_clean.startswith(("จังหวัด", "จ.", "อ.", "อำเภอ", "ต.", "ตำบล", "เมือง")) or any(
            loc_marker in ent_clean for loc_marker in ("กรุงเทพ", "เชียงใหม่", "ภูเก็ต", "น่าน", "สงขลา", "ขอนแก่น")
        ):
            if ent_clean not in locations:
                locations.append(ent_clean)
        else:
            # Specific named individual or organization
            if ent_clean not in actor_names:
                actor_names.append(ent_clean)

    # Extract target keywords
    for tgt in _TARGET_KEYWORDS:
        if tgt in clean_text and tgt not in targets:
            targets.append(tgt)

    # Extract action keywords
    for act in _ACTION_KEYWORDS:
        if act in clean_text and act not in actions:
            actions.append(act)

    # Extract storyline anchor pattern
    for pattern in _STORYLINE_PATTERNS:
        m = pattern.search(clean_text)
        if m:
            storyline_anchor = m.group(1)
            break

    return TypedEventAnchors(
        event_locations=locations,
        actor_names=actor_names,
        actor_roles=actor_roles,
        targets=targets,
        actions=actions,
        storyline_anchor=storyline_anchor,
    )


def is_syndicated_duplicate(
    article_a: dict[str, Any] | Any,
    article_b: dict[str, Any] | Any,
    cos_sim: float = 0.0,
) -> bool:
    """
    P0.1 Syndication / Near-Duplicate Detector:
    Returns True if article_b is a syndicated republish of article_a
    (or both originate from the same syndicated wire wire), using:
      1. Character 5-gram Jaccard index >= 0.80
      2. Explicit wire / republish attribution markers
      3. Cosine similarity >= 0.990 with zero novel information
    """
    def _val(obj: Any, key: str) -> str:
        if isinstance(obj, dict):
            return str(obj.get(key, "") or "")
        return str(getattr(obj, key, "") or "")

    title_a = _val(article_a, "title")
    summary_a = _val(article_a, "summary")
    source_a = _val(article_a, "source").lower().strip()

    title_b = _val(article_b, "title")
    summary_b = _val(article_b, "summary")
    source_b = _val(article_b, "source").lower().strip()

    text_a = f"{title_a} {summary_a}"
    text_b = f"{title_b} {summary_b}"

    clean_a = re.sub(r"[\s\W_]+", "", text_a)
    clean_b = re.sub(r"[\s\W_]+", "", text_b)

    def _get_5grams(s: str) -> set[str]:
        if len(s) < 5:
            return {s} if s else set()
        return {s[i : i + 5] for i in range(len(s) - 4)}

    grams_a = _get_5grams(clean_a)
    grams_b = _get_5grams(clean_b)

    if grams_a and grams_b:
        jaccard = len(grams_a & grams_b) / len(grams_a | grams_b)
        if jaccard >= 0.80:
            return True

    lower_a = text_a.lower()
    lower_b = text_b.lower()
    for wm in _WIRE_MARKERS:
        if wm in lower_a and (source_b in lower_a or "สำนักข่าว" in lower_a):
            return True
        if wm in lower_b and (source_a in lower_b or "สำนักข่าว" in lower_b):
            return True

    if cos_sim >= 0.990:
        words_a = set(re.findall(r"[\w]+", text_a.lower()))
        words_b = set(re.findall(r"[\w]+", text_b.lower()))
        novel = {w for w in (words_b - words_a) if not w.isdigit() and len(w) > 2}
        if len(novel) == 0:
            return True

    return False


# ── Global Singleton & Factory ────────────────────────────────────

_ENTITY_EXTRACTOR_INSTANCE: EntityExtractor | None = None
_INSTANCE_LOCK = threading.Lock()


def get_entity_extractor() -> EntityExtractor:
    """Thread-safe singleton factory for EntityExtractor."""
    global _ENTITY_EXTRACTOR_INSTANCE
    if _ENTITY_EXTRACTOR_INSTANCE is not None:
        return _ENTITY_EXTRACTOR_INSTANCE

    with _INSTANCE_LOCK:
        if _ENTITY_EXTRACTOR_INSTANCE is not None:
            return _ENTITY_EXTRACTOR_INSTANCE
        _ENTITY_EXTRACTOR_INSTANCE = EntityExtractor()
        return _ENTITY_EXTRACTOR_INSTANCE


def extract_entities(text: str) -> list[str]:
    """Convenience module function for named entity extraction."""
    return get_entity_extractor().extract_entities(text)


def reset_entity_extractor() -> None:
    """Reset singleton instance (used in tests for clean state)."""
    global _ENTITY_EXTRACTOR_INSTANCE
    with _INSTANCE_LOCK:
        _ENTITY_EXTRACTOR_INSTANCE = None
