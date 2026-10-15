"""
core/circuit_breaker.py
─────────────────────────────────────────────────────────────────
SOLID  S — Manages provider health state and cooldown transitions.
SOLID  O — Pluggable failure predicates and customizable cooldowns.
GRASP  Information Expert — Tracks failure counts, timestamps, and state.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: all calls allowed
    OPEN = "OPEN"            # Outage detected: fail fast, skip all calls until cooldown expires
    HALF_OPEN = "HALF_OPEN"  # Cooldown expired: allow a single canary probe to test health


class ProviderCircuitBreaker:
    """
    Thread-safe in-memory Circuit Breaker for an individual LLM provider.
    Trips to OPEN on provider-level outages (503, connection errors, gateway 401/403).
    Bypasses dead providers during cooldown to prevent compounding latency.
    """

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 2,
        cooldown_seconds: float = 45.0,
    ) -> None:
        self.provider_name = provider_name
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(0.0, cooldown_seconds)

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_state_change = time.monotonic()
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._evaluate_state()
            return self._state

    def can_execute(self) -> bool:
        """
        Returns True if the provider is healthy or ready for a canary probe.
        Returns False if currently in OPEN cooldown state (fail fast).
        """
        with self._lock:
            self._evaluate_state()
            return self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record successful call: resets failures and closes the circuit."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info(
                    "[CircuitBreaker] Provider '%s' recovered! State changed from %s to CLOSED.",
                    self.provider_name,
                    self._state.value,
                )
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._last_state_change = time.monotonic()

    def record_failure(self, is_provider_outage: bool = True) -> None:
        """
        Record failure: if provider outage (503, connection dropped, gateway 401/403),
        immediately trips the circuit breaker or increments failure counter toward threshold.
        """
        with self._lock:
            self._consecutive_failures += 1
            now = time.monotonic()

            # Immediate trip on explicit provider outage or when reaching threshold
            if is_provider_outage or self._consecutive_failures >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "[CircuitBreaker] Provider '%s' outage detected (%d consecutive failures). "
                        "Tripping circuit to OPEN for %.1fs cooldown.",
                        self.provider_name,
                        self._consecutive_failures,
                        self.cooldown_seconds,
                    )
                self._state = CircuitState.OPEN
                self._last_state_change = now

    def _evaluate_state(self) -> None:
        """Internal helper to transition from OPEN to HALF_OPEN when cooldown expires."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_state_change
            if elapsed >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                self._last_state_change = time.monotonic()
                logger.info(
                    "[CircuitBreaker] Cooldown (%.1fs) expired for provider '%s'. State set to HALF_OPEN (probing with canary).",
                    self.cooldown_seconds,
                    self.provider_name,
                )
