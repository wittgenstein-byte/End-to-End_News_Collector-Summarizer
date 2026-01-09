from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RawRecord:
    source: str
    url: str
    payload: Dict[str, Any]
    collected_at: datetime
    content_hash: str


@dataclass
class CleanRecord:
    raw: RawRecord
    clean_text: str
    language: str
    tokens: List[str]


@dataclass
class FeatureRecord:
    clean: CleanRecord
    embedding: List[float]
    labels: List[str]
    label_probs: Dict[str, float]
    method: str
    confidence: float
    summaries: Dict[str, str]
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    raw: RawRecord
    clean: CleanRecord
    features: FeatureRecord
    low_confidence: bool
    routed_to_llm: bool
    metadata: Optional[Dict[str, Any]] = None
