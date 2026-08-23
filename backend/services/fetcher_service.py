"""
services/fetcher_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Re-exports FetcherService and strategies from backend.core.fetcher_service
SOLID  O — Open for extension via FetchStrategy subclasses
SOLID  L — All strategies conform to the FetchStrategy contract
GRASP  Low Coupling — Re-export alias to maintain clean module resolution
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from backend.core.fetcher_service import (
    FetcherService,
    FetchStrategy,
    HttpxBasicStrategy,
    HttpxHeadersStrategy,
    PlaywrightStrategy,
    get_fetcher_service,
)

__all__ = [
    "FetchStrategy",
    "FetcherService",
    "HttpxBasicStrategy",
    "HttpxHeadersStrategy",
    "PlaywrightStrategy",
    "get_fetcher_service",
]