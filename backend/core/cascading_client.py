"""
core/cascading_client.py
─────────────────────────────────────────────────────────────────
SOLID  S — Centralized multi-provider LLM orchestration and failover.
SOLID  O — Pluggable providers, models, validators, and circuit breakers.
SOLID  D — Depends on OpenAI-compatible client abstractions and Settings.
GRASP  Controller — Coordinates timeouts, circuit breakers, and retries.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from backend.config import settings
from backend.core.circuit_breaker import CircuitState, ProviderCircuitBreaker

logger = logging.getLogger(__name__)


class ErrorClassification(str, Enum):
    PROVIDER_OUTAGE = "provider_outage"   # 401/403 gateway auth, 502/503/504, ConnectionError
    MODEL_ERROR = "model_error"           # 404 Model Not Found
    CLIENT_ERROR = "client_error"         # 400 Bad Request, context window exceeded
    RATE_LIMIT = "rate_limit"             # 429 Rate Limit
    TIMEOUT = "timeout"                   # Per-target timeout
    PARSE_ERROR = "parse_error"           # Malformed schema/JSON output
    UNKNOWN = "unknown"


def classify_error(exc: Exception) -> ErrorClassification:
    """Classify exception to determine precise cascade behavior."""
    if isinstance(exc, (BadRequestError, UnprocessableEntityError)):
        return ErrorClassification.CLIENT_ERROR
    if isinstance(exc, NotFoundError):
        return ErrorClassification.MODEL_ERROR
    if isinstance(exc, RateLimitError):
        return ErrorClassification.RATE_LIMIT
    if isinstance(exc, (APITimeoutError, TimeoutError)):
        return ErrorClassification.TIMEOUT
    if isinstance(exc, (PermissionDeniedError, InternalServerError, APIConnectionError, ConnectionError)):
        return ErrorClassification.PROVIDER_OUTAGE

    # Inspect HTTP status code or message strings if available
    status_code = getattr(exc, "status_code", None)
    err_str = str(exc).lower()

    if status_code in (401, 403, 502, 503, 504):
        return ErrorClassification.PROVIDER_OUTAGE
    if status_code == 404 or "invalid model" in err_str or "not found" in err_str:
        return ErrorClassification.MODEL_ERROR
    if status_code == 400 or "context_length" in err_str or "maximum context" in err_str:
        return ErrorClassification.CLIENT_ERROR
    if isinstance(exc, (json.JSONDecodeError, ValueError)) or "json" in err_str or "validation" in err_str:
        return ErrorClassification.PARSE_ERROR
    if status_code == 429 or "rate limit" in err_str or "quota" in err_str:
        return ErrorClassification.RATE_LIMIT
    if "timeout" in err_str or "timed out" in err_str:
        return ErrorClassification.TIMEOUT
    if "connection" in err_str or "unreachable" in err_str or "failed to connect" in err_str:
        return ErrorClassification.PROVIDER_OUTAGE

    return ErrorClassification.UNKNOWN


@dataclass(frozen=True)
class LLMTarget:
    """Represents a specific provider + model execution candidate."""
    provider: str        # e.g., "kku", "google", "thai_llm"
    model: str           # e.g., "gemini-3.5-flash-lite"
    client: OpenAI       # configured OpenAI client for this provider
    label: str           # e.g., "KKU (gemini-3.5-flash-lite)"


@dataclass
class LLMExecutionResult:
    """Result of successful LLM execution."""
    content: str
    parsed: Any | None
    provider: str
    model: str
    latency_seconds: float
    is_fallback: bool
    attempt_count: int


class CascadingLLMClient:
    """
    Enterprise-grade multi-provider cascading LLM engine.
    Enforces per-call timeout, overall deadline budget, max_retries=0,
    provider-level circuit breakers, and structured error classification.
    """

    def __init__(
        self,
        targets: list[LLMTarget] | None = None,
        per_target_timeout: float = 10.0,
        overall_timeout: float = 30.0,
        circuit_breaker_cooldown: float = 45.0,
    ) -> None:
        self.per_target_timeout = max(1.0, per_target_timeout)
        self.overall_timeout = max(2.0, overall_timeout)
        self._targets = list(targets or [])

        # Initialize circuit breaker for each unique provider
        self._circuit_breakers: dict[str, ProviderCircuitBreaker] = {}
        unique_providers = {t.provider for t in self._targets}
        for p in unique_providers:
            self._circuit_breakers[p] = ProviderCircuitBreaker(
                provider_name=p,
                failure_threshold=2,
                cooldown_seconds=circuit_breaker_cooldown,
            )

    @property
    def targets(self) -> list[LLMTarget]:
        return list(self._targets)

    @property
    def providers(self) -> list[str]:
        return list(self._circuit_breakers.keys())

    def get_circuit_state(self, provider: str) -> CircuitState | None:
        cb = self._circuit_breakers.get(provider)
        return cb.state if cb else None

    @classmethod
    def from_client_and_models(
        cls,
        client: Any,
        models: list[str],
        per_target_timeout: float = 10.0,
        overall_timeout: float = 30.0,
        circuit_breaker_cooldown: float = 0.0,
        provider_name: str = "custom",
    ) -> CascadingLLMClient:
        """Helper to construct CascadingLLMClient wrapping an existing OpenAI or mock client."""
        targets = [
            LLMTarget(
                provider=f"{provider_name}_{idx}",
                model=m,
                client=client,
                label=f"{provider_name} ({m})",
            )
            for idx, m in enumerate(models)
        ]
        return cls(
            targets=targets,
            per_target_timeout=per_target_timeout,
            overall_timeout=overall_timeout,
            circuit_breaker_cooldown=circuit_breaker_cooldown,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        validator: Callable[[str], Any] | None = None,
        temperature: float = 0.3,
        response_format: dict[str, Any] | None = None,
    ) -> LLMExecutionResult:
        """
        Execute completion with multi-provider failover, deadline budget, and error classification.
        """
        if not self._targets:
            raise RuntimeError("No LLM targets configured in CascadingLLMClient.")

        start_time = time.monotonic()
        deadline = start_time + self.overall_timeout
        skipped_providers: set[str] = set()
        errors: list[str] = []
        last_exception: Exception | None = None
        attempt = 0

        for target in self._targets:
            # 1. Skip if entire provider was marked down during this request or in open circuit cooldown
            if target.provider in skipped_providers:
                continue

            cb = self._circuit_breakers.get(target.provider)
            if cb and not cb.can_execute():
                err_msg = f"Target '{target.label}' skipped: Provider circuit is in cooldown (OPEN)."
                logger.debug("[HA Engine] %s", err_msg)
                errors.append(err_msg)
                skipped_providers.add(target.provider)
                continue

            # 2. Check remaining deadline budget
            now = time.monotonic()
            remaining_time = deadline - now
            if remaining_time < 2.0:
                err_msg = f"Overall deadline budget expired ({self.overall_timeout:.1f}s). Remaining: {remaining_time:.2f}s."
                logger.warning("[HA Engine] %s", err_msg)
                errors.append(err_msg)
                break

            target_timeout = min(self.per_target_timeout, remaining_time)
            attempt += 1
            call_start = time.monotonic()

            try:
                # Prepare call kwargs
                kwargs: dict[str, Any] = {
                    "model": target.model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                    "timeout": target_timeout,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                response = target.client.chat.completions.create(**kwargs)
                content = (response.choices[0].message.content or "").strip()
                if not content:
                    raise ValueError(f"Target '{target.label}' returned empty message content.")

                parsed = validator(content) if validator else None

                # Call succeeded: update circuit breaker & record metrics
                if cb:
                    cb.record_success()

                call_latency = time.monotonic() - call_start
                is_fallback = attempt > 1

                if parsed is not None and type(parsed).__name__ == "NewsSummary":
                    try:
                        if getattr(parsed, "provider", None) is None:
                            parsed.provider = target.provider
                        if getattr(parsed, "model", None) is None:
                            parsed.model = target.model
                        parsed.is_fallback = is_fallback
                    except Exception:
                        pass

                if is_fallback:
                    logger.info(
                        "[HA Engine] Fallback success: Target '%s' succeeded on attempt %d (latency: %.2fs).",
                        target.label,
                        attempt,
                        call_latency,
                    )
                else:
                    logger.debug(
                        "[HA Engine] Primary target '%s' succeeded (latency: %.2fs).",
                        target.label,
                        call_latency,
                    )

                return LLMExecutionResult(
                    content=content,
                    parsed=parsed,
                    provider=target.provider,
                    model=target.model,
                    latency_seconds=call_latency,
                    is_fallback=is_fallback,
                    attempt_count=attempt,
                )

            except Exception as exc:
                last_exception = exc
                call_latency = time.monotonic() - call_start
                classification = classify_error(exc)
                err_detail = f"Target '{target.label}' failed [{classification.value}]: {exc}"
                errors.append(err_detail)

                logger.warning(
                    "[HA Engine] %s (elapsed: %.2fs)",
                    err_detail,
                    call_latency,
                )

                # ── Structured Error Actions ─────────────────────────
                if classification == ErrorClassification.CLIENT_ERROR:
                    # Client errors (400 Bad Request, context length exceeded) are deterministic.
                    # Cascading to other models will fail identically and burn quota. Abort immediately!
                    logger.error(
                        "[HA Engine] Client error detected on '%s'. Aborting cascade immediately.",
                        target.label,
                    )
                    raise

                elif classification == ErrorClassification.PROVIDER_OUTAGE:
                    # Provider-level outage (401/403 gateway auth, 502/503/504, connection refused):
                    # Immediately trip breaker and skip ALL remaining models of this provider!
                    if cb:
                        cb.record_failure(is_provider_outage=True)
                    skipped_providers.add(target.provider)
                    logger.warning(
                        "[HA Engine] Provider outage confirmed for '%s'. Skipping all remaining models for this provider.",
                        target.provider,
                    )

                elif classification in (ErrorClassification.TIMEOUT, ErrorClassification.RATE_LIMIT):
                    if cb:
                        cb.record_failure(is_provider_outage=False)

                elif classification == ErrorClassification.MODEL_ERROR:
                    # 404 Model Not Found: skip only this model, continue to other models in same provider
                    pass

                elif classification == ErrorClassification.PARSE_ERROR:
                    # Malformed JSON from model
                    pass

        # If all candidates exhausted, raise informative failure
        err_summary = " | ".join(errors)
        logger.error(
            "[HA Engine] All %d LLM targets across providers failed. Summary: %s",
            len(self._targets),
            err_summary,
        )
        if len(self._targets) == 1 and last_exception is not None:
            raise last_exception

        if last_exception is not None:
            raise RuntimeError(f"All LLM models in cascade failed: {err_summary}") from last_exception
        raise RuntimeError(f"All LLM models in cascade failed: {err_summary}")


# ── DI Factory & Target Discovery ──────────────────────────────────

_cascading_client_instance: CascadingLLMClient | None = None


def build_ha_targets() -> list[LLMTarget]:
    """
    Construct ordered LLM targets across KKU, Google Gemini, and Thai LLM providers.
    Enforces max_retries=0 on all underlying OpenAI client instances.
    """
    targets: list[LLMTarget] = []
    provider_order = [p.strip().lower() for p in settings.llm_provider_order if p.strip()]

    # Cached client instances to reuse connection pools across targets
    clients: dict[str, OpenAI] = {}

    for provider in provider_order:
        if provider == "kku":
            key = settings.kku_api_key
            if not key or not key.strip():
                logger.debug("[HA Engine] KKU provider skipped: no API key configured.")
                continue
            if "kku" not in clients:
                clients["kku"] = OpenAI(
                    api_key=key.strip(),
                    base_url=settings.kku_base_url,
                    max_retries=0,  # CRITICAL: Eliminate nested SDK retries
                )
            for m in settings.kku_models:
                targets.append(LLMTarget(
                    provider="kku",
                    model=m,
                    client=clients["kku"],
                    label=f"KKU ({m})",
                ))

        elif provider in ("google", "gemini"):
            key = settings.google_api_key
            if not key or not key.strip():
                logger.debug("[HA Engine] Google Gemini provider skipped: no API key configured.")
                continue
            if "google" not in clients:
                clients["google"] = OpenAI(
                    api_key=key.strip(),
                    base_url=settings.google_base_url,
                    max_retries=0,  # CRITICAL: Eliminate nested SDK retries
                )
            for m in settings.google_models:
                targets.append(LLMTarget(
                    provider="google",
                    model=m,
                    client=clients["google"],
                    label=f"Google ({m})",
                ))

        elif provider in ("thai_llm", "typhoon"):
            if not settings.thai_llm_enabled:
                logger.debug("[HA Engine] Thai LLM provider skipped: disabled by default (THAI_LLM_ENABLED=false).")
                continue
            key = settings.thai_llm_api_key
            if not key or not key.strip():
                logger.debug("[HA Engine] Thai LLM provider skipped: no API key configured.")
                continue
            if "thai_llm" not in clients:
                clients["thai_llm"] = OpenAI(
                    api_key=key.strip(),
                    base_url=settings.thai_llm_base_url,
                    max_retries=0,  # CRITICAL: Eliminate nested SDK retries
                )
            for m in settings.thai_llm_models:
                targets.append(LLMTarget(
                    provider="thai_llm",
                    model=m,
                    client=clients["thai_llm"],
                    label=f"Thai LLM ({m})",
                ))

        else:
            logger.warning("[HA Engine] Unrecognized provider '%s' in LLM_PROVIDER_ORDER. Ignored.", provider)

    return targets


def get_cascading_client() -> CascadingLLMClient:
    """Retrieve or initialize the singleton HA CascadingLLMClient."""
    global _cascading_client_instance
    if _cascading_client_instance is None:
        targets = build_ha_targets()
        _cascading_client_instance = CascadingLLMClient(
            targets=targets,
            per_target_timeout=settings.llm_per_target_timeout,
            overall_timeout=settings.llm_overall_request_timeout,
            circuit_breaker_cooldown=settings.llm_circuit_breaker_cooldown,
        )
    return _cascading_client_instance
