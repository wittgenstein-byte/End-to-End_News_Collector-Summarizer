"""
core/cache.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ In-memory cache พร้อม LRU eviction, TTL, และ stampede protection
SOLID  O — Generic สำหรับ value type T นำไปใช้ซ้ำได้กับทุก subsystem
SOLID  L — Implement CachePort protocol สามารถแทนที่ด้วย Redis/Distributed cache ได้
SOLID  I — Narrow interface เฉพาะ cache operations ที่จำเป็น
GRASP  Pure Fabrication — Shared infrastructure utility สำหรับ Layer 2 and Layer 3 caching
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

T = TypeVar("T")


class CachePort(Protocol, Generic[T]):
    """Protocol defining the standard asynchronous caching contract."""

    async def get(self, key: str) -> T | None: ...

    async def set(self, key: str, value: T, ttl_seconds: float | None = None) -> None: ...

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Coroutine[Any, Any, T] | Awaitable[T]],
        ttl_seconds: float | None = None,
    ) -> T: ...

    async def delete(self, key: str) -> bool: ...

    async def clear(self) -> None: ...

    def size(self) -> int: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class _CacheEntry(Generic[T]):
    key: str
    value: T
    created_at: float
    expires_at: float


class AsyncInMemoryCache(Generic[T]):
    """
    Async-safe in-memory cache with:
      - Configurable TTL (time-to-live) in seconds
      - LRU capacity eviction (max_size) via collections.OrderedDict
      - Single-flight task deduplication (stampede / thundering herd protection)
      - Thread/async safety using asyncio.Lock
      - Real-time hit/miss/eviction metrics
    """

    def __init__(self, max_size: int = 1000, default_ttl_seconds: float = 86400.0) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be greater than 0")
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be greater than 0")

        self._max_size: int = max_size
        self._default_ttl: float = float(default_ttl_seconds)
        self._cache: OrderedDict[str, _CacheEntry[T]] = OrderedDict()
        self._in_flight: dict[str, asyncio.Task[T]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

        # Metrics
        self.hits: int = 0
        self.misses: int = 0
        self.evictions: int = 0

    def _is_expired(self, entry: _CacheEntry[T], now: float) -> bool:
        return now >= entry.expires_at

    def _set_entry(self, key: str, value: T, ttl_seconds: float | None = None) -> None:
        """Internal set implementation. Caller MUST hold self._lock."""
        ttl = float(ttl_seconds) if ttl_seconds is not None else self._default_ttl
        now = time.monotonic()
        expires_at = now + ttl

        # If key already present, update and move to end (MRU)
        if key in self._cache:
            self._cache[key] = _CacheEntry(key=key, value=value, created_at=now, expires_at=expires_at)
            self._cache.move_to_end(key, last=True)
            return

        # Check capacity: first purge expired entries
        if len(self._cache) >= self._max_size:
            expired_keys = [k for k, v in self._cache.items() if self._is_expired(v, now)]
            for k in expired_keys:
                self._cache.pop(k, None)

            # If still at capacity, evict the least recently used item (first item in OrderedDict)
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self.evictions += 1

        self._cache[key] = _CacheEntry(key=key, value=value, created_at=now, expires_at=expires_at)

    async def get(self, key: str) -> T | None:
        """Retrieve value if present and not expired; updates LRU position."""
        now = time.monotonic()
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self.misses += 1
                return None
            if self._is_expired(entry, now):
                self._cache.pop(key, None)
                self.misses += 1
                return None

            self._cache.move_to_end(key, last=True)
            self.hits += 1
            return entry.value

    async def set(self, key: str, value: T, ttl_seconds: float | None = None) -> None:
        """Set key to value with optional custom TTL."""
        async with self._lock:
            self._set_entry(key, value, ttl_seconds)

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Coroutine[Any, Any, T] | Awaitable[T]],
        ttl_seconds: float | None = None,
    ) -> T:
        """
        Retrieve value from cache or execute compute_fn with single-flight stampede protection.
        Concurrent requests for the same uncached key will await a single shared task.
        Failed tasks will not cache an erroneous result.
        """
        # 1. Fast-path lookup
        cached = await self.get(key)
        if cached is not None:
            return cached

        # 2. Concurrency stampede coordination
        task: asyncio.Task[T] | None = None

        async with self._lock:
            # Double-check cache under lock
            entry = self._cache.get(key)
            now = time.monotonic()
            if entry is not None and not self._is_expired(entry, now):
                self._cache.move_to_end(key, last=True)
                self.hits += 1
                return entry.value

            if key in self._in_flight:
                task = self._in_flight[key]
            else:
                async def _runner() -> T:
                    try:
                        coro = compute_fn()
                        res = await coro  # type: ignore[misc]
                        async with self._lock:
                            self._set_entry(key, res, ttl_seconds)
                        return res
                    finally:
                        async with self._lock:
                            self._in_flight.pop(key, None)

                task = asyncio.create_task(_runner())
                self._in_flight[key] = task

        # 3. Await computation outside lock to avoid blocking other cache accesses
        return await asyncio.shield(task)

    async def delete(self, key: str) -> bool:
        """Delete key from cache. Returns True if key was present."""
        async with self._lock:
            return self._cache.pop(key, None) is not None

    async def clear(self) -> None:
        """Clear all cached entries and reset in-flight state."""
        async with self._lock:
            self._cache.clear()
            self._in_flight.clear()

    def size(self) -> int:
        """Return current number of entries in cache."""
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Return cache performance metrics and state."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "size": len(self._cache),
            "max_size": self._max_size,
            "in_flight": len(self._in_flight),
        }
