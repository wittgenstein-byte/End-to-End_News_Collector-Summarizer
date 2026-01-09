from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    data_path: Path
    confidence_threshold: float = 0.55
    max_summary_sentences: int = 2


DEFAULT_CONFIG = PipelineConfig(
    data_path=Path(__file__).parent / "data" / "sample_news.jsonl",
)
