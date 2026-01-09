from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from storage.models import RawRecord


@dataclass(frozen=True)
class IngestResult:
    records: List[RawRecord]


def _hash_content(payload: dict) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest_from_jsonl(path: Path) -> IngestResult:
    records: List[RawRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            record = RawRecord(
                source=payload.get("source", "dataset"),
                url=payload.get("url", ""),
                payload=payload,
                collected_at=datetime.utcnow(),
                content_hash=_hash_content(payload),
            )
            records.append(record)
    return IngestResult(records=records)


def deduplicate(records: Iterable[RawRecord]) -> List[RawRecord]:
    seen_hashes = set()
    unique_records: List[RawRecord] = []
    for record in records:
        if record.content_hash in seen_hashes:
            continue
        seen_hashes.add(record.content_hash)
        unique_records.append(record)
    return unique_records
