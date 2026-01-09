from __future__ import annotations

import re
from typing import List

from storage.models import CleanRecord, RawRecord


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokenize(text: str) -> List[str]:
    return [token for token in text.split(" ") if token]


def detect_language(text: str) -> str:
    return "th" if re.search(r"[ก-๙]", text) else "en"


def preprocess(raw_record: RawRecord) -> CleanRecord:
    text = raw_record.payload.get("content", "")
    clean_text = _clean_text(text)
    tokens = _tokenize(clean_text)
    language = detect_language(clean_text)
    return CleanRecord(
        raw=raw_record,
        clean_text=clean_text,
        language=language,
        tokens=tokens,
    )
