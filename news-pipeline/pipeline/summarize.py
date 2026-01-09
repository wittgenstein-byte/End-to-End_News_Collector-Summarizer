from __future__ import annotations

from typing import Dict, List

from storage.models import CleanRecord


def extractive_summary(clean_record: CleanRecord, max_sentences: int) -> str:
    sentences = [sentence.strip() for sentence in clean_record.clean_text.split(".") if sentence.strip()]
    selected = sentences[:max_sentences]
    return ". ".join(selected) + ("." if selected else "")


def abstractive_summary(clean_record: CleanRecord, extractive: str) -> str:
    title = clean_record.raw.payload.get("title", "")
    if title:
        return f"{title} - Summary: {extractive}"
    return f"Summary: {extractive}"


def summarize(clean_record: CleanRecord, max_sentences: int) -> Dict[str, str]:
    extractive = extractive_summary(clean_record, max_sentences)
    abstractive = abstractive_summary(clean_record, extractive)
    return {
        "extractive": extractive,
        "abstractive": abstractive,
    }
