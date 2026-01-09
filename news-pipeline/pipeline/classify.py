from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from storage.models import CleanRecord


LABEL_KEYWORDS = {
    "economy": ["inflation", "stock", "market", "เศรษฐกิจ", "หุ้น"],
    "politics": ["election", "parliament", "รัฐบาล", "เลือกตั้ง"],
    "tech": ["ai", "software", "tech", "เทคโนโลยี"],
}


@dataclass(frozen=True)
class ClassificationResult:
    labels: List[str]
    probabilities: Dict[str, float]
    method: str
    confidence: float


def _score_label(text: str, keywords: List[str]) -> float:
    hits = sum(1 for keyword in keywords if keyword.lower() in text.lower())
    return min(1.0, hits / max(1, len(keywords)))


def classify(clean_record: CleanRecord) -> ClassificationResult:
    probabilities: Dict[str, float] = {}
    for label, keywords in LABEL_KEYWORDS.items():
        probabilities[label] = _score_label(clean_record.clean_text, keywords)
    sorted_labels = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
    labels = [label for label, score in sorted_labels if score > 0]
    max_prob = max(probabilities.values(), default=0.0)
    return ClassificationResult(
        labels=labels,
        probabilities=probabilities,
        method="model",
        confidence=max_prob,
    )


def needs_llm_route(confidence: float, threshold: float) -> bool:
    return confidence < threshold
