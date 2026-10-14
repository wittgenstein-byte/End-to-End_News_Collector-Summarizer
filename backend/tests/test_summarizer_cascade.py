from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.config import _build_cascade_models
from backend.schemas.news_schema import NewsSummary
from backend.services.summarizer_service import SummarizerService


def test_build_cascade_models_deduplication():
    primary = "my-custom-model"
    custom_env = "my-custom-model, gemini-3.5-flash-lite, gpt-5.4-mini, gemini-3.5-flash-lite"
    models = _build_cascade_models(primary, custom_env)
    assert models[0] == "my-custom-model"
    assert models == ["my-custom-model", "gemini-3.5-flash-lite", "gpt-5.4-mini"]


def test_build_cascade_models_default():
    primary = "gemini-3.5-flash-lite"
    models = _build_cascade_models(primary, "")
    assert models[0] == "gemini-3.5-flash-lite"
    assert "nova-2-lite-v1" in models
    assert "llama-4-maverick" in models
    assert "gpt-5.6-luna" in models
    assert len(models) == len(set(models))


def test_summarizer_cascade_first_model_success():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content="""{
                    "title": "Test Title",
                    "source_url": "https://example.com/news/1",
                    "published_at": null,
                    "language": "th",
                    "summary": "This is a test summary.",
                    "bullets": ["Point 1", "Point 2", "Point 3"],
                    "category": "technology",
                    "sentiment": "neutral",
                    "keywords": ["tech", "ai", "news"]
                }"""
            )
        )
    ]
    mock_client.chat.completions.create.return_value = mock_response

    service = SummarizerService(
        client=mock_client,
        models=["model-1", "model-2", "model-3"],
        temperature=0.3,
    )

    result = service.summarize("# Markdown Article Content")
    assert isinstance(result, NewsSummary)
    assert result.title == "Test Title"
    assert mock_client.chat.completions.create.call_count == 1
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "model-1"


def test_summarizer_cascade_fallback_to_second_model():
    mock_client = MagicMock()

    # First call raises Exception, second succeeds
    mock_response_2 = MagicMock()
    mock_response_2.choices = [
        MagicMock(
            message=MagicMock(
                content="""{
                    "title": "Fallback Title",
                    "source_url": "https://example.com/news/2",
                    "published_at": null,
                    "language": "th",
                    "summary": "Fallback summary sentence.",
                    "bullets": ["Point A", "Point B", "Point C"],
                    "category": "economy",
                    "sentiment": "positive",
                    "keywords": ["finance", "market"]
                }"""
            )
        )
    ]

    mock_client.chat.completions.create.side_effect = [
        RuntimeError("Model model-1 quota exceeded (429)"),
        mock_response_2,
    ]

    service = SummarizerService(
        client=mock_client,
        models=["model-1", "model-2", "model-3"],
        temperature=0.3,
    )

    result = service.summarize("# Content for fallback")
    assert isinstance(result, NewsSummary)
    assert result.title == "Fallback Title"
    assert mock_client.chat.completions.create.call_count == 2
    assert mock_client.chat.completions.create.call_args_list[0].kwargs["model"] == "model-1"
    assert mock_client.chat.completions.create.call_args_list[1].kwargs["model"] == "model-2"


def test_summarizer_cascade_all_fail():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        RuntimeError("Model 1 unavailable"),
        RuntimeError("Model 2 timeout"),
    ]

    service = SummarizerService(
        client=mock_client,
        models=["model-1", "model-2"],
        temperature=0.3,
    )

    with pytest.raises(RuntimeError, match="All LLM models in cascade failed"):
        service.summarize("# Broken article")

    assert mock_client.chat.completions.create.call_count == 2
