from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from openai import (
    APIConnectionError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)

from backend.core.cascading_client import (
    CascadingLLMClient,
    ErrorClassification,
    LLMTarget,
    build_ha_targets,
    classify_error,
)
from backend.core.circuit_breaker import CircuitState, ProviderCircuitBreaker


def _make_mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    resp.choices = [choice]
    return resp


def test_classify_error_mapping():
    # 400 Client error
    mock_req = MagicMock()
    bad_req = BadRequestError("Context window exceeded", response=MagicMock(status_code=400), body={})
    assert classify_error(bad_req) == ErrorClassification.CLIENT_ERROR

    # 404 Model error
    not_found = NotFoundError("Model not found", response=MagicMock(status_code=404), body={})
    assert classify_error(not_found) == ErrorClassification.MODEL_ERROR

    # 401 / 403 Provider outage
    perm_denied = PermissionDeniedError("Invalid API key", response=MagicMock(status_code=401), body={})
    assert classify_error(perm_denied) == ErrorClassification.PROVIDER_OUTAGE

    conn_err = APIConnectionError(request=mock_req)
    assert classify_error(conn_err) == ErrorClassification.PROVIDER_OUTAGE


def test_provider_outage_skips_remaining_models_and_fails_over():
    """
    Core HA requirement: If KKU returns 401/403 or network failure,
    it must skip all remaining KKU models and immediately fail over to Google.
    """
    mock_kku_client = MagicMock()
    # KKU model 1 raises 401 Unauthorized
    mock_kku_client.chat.completions.create.side_effect = PermissionDeniedError(
        "Unauthorized gateway access",
        response=MagicMock(status_code=401),
        body={},
    )

    mock_google_client = MagicMock()
    mock_google_client.chat.completions.create.return_value = _make_mock_response('{"result": "google_success"}')

    targets = [
        LLMTarget(provider="kku", model="gemini-3.5-flash-lite", client=mock_kku_client, label="KKU (gemini)"),
        LLMTarget(provider="kku", model="nova-2-lite-v1", client=mock_kku_client, label="KKU (nova)"),
        LLMTarget(provider="kku", model="llama-4-maverick", client=mock_kku_client, label="KKU (llama)"),
        LLMTarget(provider="google", model="gemini-3.5-flash", client=mock_google_client, label="Google (gemini)"),
    ]

    engine = CascadingLLMClient(targets=targets, per_target_timeout=5.0, overall_timeout=15.0)

    result = engine.complete(messages=[{"role": "user", "content": "Hello"}])

    # KKU should only be called ONCE (model 1), not 3 times!
    assert mock_kku_client.chat.completions.create.call_count == 1
    assert mock_google_client.chat.completions.create.call_count == 1

    # Result should come from Google as fallback
    assert result.provider == "google"
    assert result.model == "gemini-3.5-flash"
    assert result.is_fallback is True
    assert result.content == '{"result": "google_success"}'

    # KKU circuit breaker must now be OPEN
    assert engine.get_circuit_state("kku") == CircuitState.OPEN


def test_circuit_breaker_open_state_skips_provider_without_calling():
    """
    When a provider's circuit is OPEN, future requests must bypass it immediately
    without waiting for network timeouts.
    """
    mock_kku_client = MagicMock()
    mock_google_client = MagicMock()
    mock_google_client.chat.completions.create.return_value = _make_mock_response("fast_google_reply")

    targets = [
        LLMTarget(provider="kku", model="gemini-3.5-flash-lite", client=mock_kku_client, label="KKU (gemini)"),
        LLMTarget(provider="google", model="gemini-3.5-flash", client=mock_google_client, label="Google (gemini)"),
    ]

    engine = CascadingLLMClient(targets=targets)
    # Trip KKU circuit breaker manually
    cb = engine._circuit_breakers["kku"]
    cb.record_failure(is_provider_outage=True)
    assert cb.state == CircuitState.OPEN

    # Run request
    result = engine.complete(messages=[{"role": "user", "content": "ping"}])

    # KKU client should NOT have been called at all!
    assert mock_kku_client.chat.completions.create.call_count == 0
    assert mock_google_client.chat.completions.create.call_count == 1
    assert result.provider == "google"


def test_circuit_breaker_recovery_to_half_open_and_closed():
    """
    Test cooldown expiration transitions to HALF_OPEN, and successful probe returns to CLOSED.
    """
    cb = ProviderCircuitBreaker("test_provider", failure_threshold=2, cooldown_seconds=10.0)
    cb.record_failure(is_provider_outage=True)
    assert cb.state == CircuitState.OPEN

    with patch("time.monotonic") as mock_time:
        # Before cooldown expires
        mock_time.return_value = cb._last_state_change + 5.0
        assert cb.can_execute() is False
        assert cb.state == CircuitState.OPEN

        # After cooldown expires (11s later)
        mock_time.return_value = cb._last_state_change + 11.0
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

        # Success probe closes circuit
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


def test_client_error_aborts_cascade_immediately():
    """
    Client error (400 Bad Request, context length exceeded) is deterministic.
    Cascading to other models will fail identically. Must abort immediately!
    """
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = BadRequestError(
        "Context window exceeded maximum 8192 tokens",
        response=MagicMock(status_code=400),
        body={},
    )

    targets = [
        LLMTarget(provider="p1", model="m1", client=mock_client, label="P1 (m1)"),
        LLMTarget(provider="p1", model="m2", client=mock_client, label="P1 (m2)"),
        LLMTarget(provider="p2", model="m3", client=mock_client, label="P2 (m3)"),
    ]

    engine = CascadingLLMClient(targets=targets)

    with pytest.raises(BadRequestError, match="Context window exceeded"):
        engine.complete(messages=[{"role": "user", "content": "giant prompt"}])

    # Must only be called ONCE - no cascading for 400!
    assert mock_client.chat.completions.create.call_count == 1


def test_model_error_404_skips_only_that_model():
    """
    404 Model Not Found skips only that specific model, trying next model in same provider.
    """
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        NotFoundError("Model retired", response=MagicMock(status_code=404), body={}),
        _make_mock_response("model_2_success"),
    ]

    targets = [
        LLMTarget(provider="kku", model="retired-model", client=mock_client, label="KKU (retired)"),
        LLMTarget(provider="kku", model="active-model", client=mock_client, label="KKU (active)"),
    ]

    engine = CascadingLLMClient(targets=targets)
    result = engine.complete(messages=[{"role": "user", "content": "hi"}])

    assert mock_client.chat.completions.create.call_count == 2
    assert result.content == "model_2_success"
    assert result.model == "active-model"
    # Circuit breaker remains CLOSED because model error is not a provider outage
    assert engine.get_circuit_state("kku") == CircuitState.CLOSED


def test_overall_timeout_deadline_budget_exhaustion():
    """
    Enforces overall deadline budget. If deadline expires, cascade halts cleanly.
    """
    mock_client = MagicMock()
    # Simulate slow call that burns all budget
    def slow_call(**kwargs):
        time.sleep(0.1)
        raise TimeoutError("Per target timeout")

    mock_client.chat.completions.create.side_effect = slow_call

    targets = [
        LLMTarget(provider="p1", model="m1", client=mock_client, label="P1 (m1)"),
        LLMTarget(provider="p2", model="m2", client=mock_client, label="P2 (m2)"),
    ]

    # Set very small overall budget
    engine = CascadingLLMClient(targets=targets, overall_timeout=2.0)

    with pytest.raises(RuntimeError, match="All LLM models in cascade failed"):
        engine.complete(messages=[{"role": "user", "content": "test"}])


def test_build_ha_targets_enforces_max_retries_zero():
    """
    Verify build_ha_targets sets max_retries=0 on OpenAI clients to avoid nested retries.
    """
    mock_settings = MagicMock()
    mock_settings.kku_api_key = "test-kku-key"
    mock_settings.kku_base_url = "https://gen.ai.kku.ac.th/api/v1"
    mock_settings.kku_models = ["gemini-3.5-flash-lite"]
    mock_settings.google_api_key = "test-google-key"
    mock_settings.google_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    mock_settings.google_models = ["gemini-3.5-flash"]
    mock_settings.thai_llm_api_key = "test-thai-key"
    mock_settings.thai_llm_base_url = "https://api.opentyphoon.ai/v1"
    mock_settings.thai_llm_models = ["typhoon-v2.5-30b-a3b-instruct"]
    mock_settings.thai_llm_enabled = False  # Thai LLM disabled by default
    mock_settings.llm_provider_order = ["kku", "google", "thai_llm"]

    with patch("backend.core.cascading_client.settings", mock_settings):
        targets = build_ha_targets()

    assert len(targets) > 0
    for target in targets:
        assert target.client.max_retries == 0

    # Thai LLM should not be in targets because thai_llm_enabled is False
    providers = {t.provider for t in targets}
    assert "kku" in providers
    assert "google" in providers
    assert "thai_llm" not in providers
