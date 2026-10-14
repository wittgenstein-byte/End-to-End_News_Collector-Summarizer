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
import threading
from typing import Any

logger = logging.getLogger(__name__)

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

        try:
            tagged = self._ner.tag(text)
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
