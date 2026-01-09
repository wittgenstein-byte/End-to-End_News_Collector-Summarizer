from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import main as pipeline_main  # noqa: E402

app = FastAPI()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/demo")
def demo() -> dict:
    results = pipeline_main.run_pipeline()
    return {
        "items": [
            {
                "summary": result.features.summaries["abstractive"],
                "labels": result.features.labels,
                "confidence": result.features.confidence,
            }
            for result in results
        ]
    }
