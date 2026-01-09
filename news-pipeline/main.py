from __future__ import annotations

from storage.db import InMemoryDB
from storage.models import FeatureRecord, PipelineResult

from config import DEFAULT_CONFIG
from pipeline.classify import classify, needs_llm_route
from pipeline.ingest import deduplicate, ingest_from_jsonl
from pipeline.preprocess import preprocess
from pipeline.summarize import summarize


def run_pipeline() -> list[PipelineResult]:
    config = DEFAULT_CONFIG
    db = InMemoryDB()

    ingest_result = ingest_from_jsonl(config.data_path)
    deduped_records = deduplicate(ingest_result.records)

    results: list[PipelineResult] = []
    for raw_record in deduped_records:
        db.store_raw(raw_record)

        clean_record = preprocess(raw_record)
        db.store_clean(clean_record)

        classification = classify(clean_record)
        low_confidence = needs_llm_route(classification.confidence, config.confidence_threshold)

        summaries = summarize(clean_record, config.max_summary_sentences)
        features = FeatureRecord(
            clean=clean_record,
            embedding=[0.0] * 8,
            labels=classification.labels,
            label_probs=classification.probabilities,
            method=classification.method,
            confidence=classification.confidence,
            summaries=summaries,
            extra={"routed_to_llm": low_confidence},
        )
        db.store_features(features)

        results.append(
            PipelineResult(
                raw=raw_record,
                clean=clean_record,
                features=features,
                low_confidence=low_confidence,
                routed_to_llm=low_confidence,
            )
        )

    return results


if __name__ == "__main__":
    pipeline_results = run_pipeline()
    for result in pipeline_results:
        print("---")
        print(result.features.summaries["abstractive"])
        print("Labels:", result.features.labels)
        print("Confidence:", result.features.confidence)
        if result.low_confidence:
            print("Routed to LLM")
