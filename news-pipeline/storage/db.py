from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .models import CleanRecord, FeatureRecord, RawRecord


@dataclass
class InMemoryDB:
    raw_records: List[RawRecord] = field(default_factory=list)
    clean_records: List[CleanRecord] = field(default_factory=list)
    feature_records: List[FeatureRecord] = field(default_factory=list)

    def store_raw(self, record: RawRecord) -> None:
        self.raw_records.append(record)

    def store_clean(self, record: CleanRecord) -> None:
        self.clean_records.append(record)

    def store_features(self, record: FeatureRecord) -> None:
        self.feature_records.append(record)
