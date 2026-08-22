"""
core/http_cache.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ HTTP Conditional Request Cache (ETag / If-Modified-Since)
SOLID  O — ขยายขนาด max_size และ TTL ได้ผ่าน constructor
SOLID  I — Narrow interface เฉพาะ fetch, get_entry, clear, size, stats
GRASP  Information Expert — รู้วิธี inject conditional headers และจัดการ 304 response
GRASP  Low Coupling — ใช้ httpx และ constants โดยไม่ผูกติดกับ scraper หรือ service ใด ๆ
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.core.constants import BROWSER_HEADERS


@dataclass
class HttpCacheEntry:
    url: str
    etag: str | None = None
    last_modified: str | None = None
    body: str = ""
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    last_checked: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class HttpConditionalCache:
    """
    In-memory async-safe HTTP Conditional Request Cache.
    Manages ETag (If-None-Match) and Last-Modified (If-Modified-Since) headers
    to handle HTTP 304 Not Modified responses and eliminate redundant downloads.
    """

    def __init__(self, max_size: int = 500, ttl_seconds: float = 86400.0) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be greater than 0")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than 0")

        self._max_size: int = max_size
        self._ttl_seconds: float = float(ttl_seconds)
        self._cache: OrderedDict[str, HttpCacheEntry] = OrderedDict()
        self._lock: asyncio.Lock = asyncio.Lock()

        # Metrics
        self.hits_304: int = 0
        self.fetches_200: int = 0
        self.errors: int = 0
        self.evictions: int = 0

    def _is_expired(self, entry: HttpCacheEntry, now: datetime) -> bool:
        elapsed = (now - entry.last_checked).total_seconds()
        return elapsed >= self._ttl_seconds

    async def fetch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> tuple[str, bool]:
        """
        Executes a conditional GET request.

        Returns:
            tuple[str, bool]: (response_text, not_modified)
            - If HTTP 304 Not Modified: returns (cached_body, True)
            - If HTTP 200 OK: stores cache entry and returns (fresh_body, False)
            - If non-200 / error: returns ("", False) without caching errors
        """
        now = datetime.now(timezone.utc)
        req_headers = dict(headers if headers is not None else BROWSER_HEADERS)

        async with self._lock:
            entry = self._cache.get(url)
            if entry is not None:
                if self._is_expired(entry, now):
                    self._cache.pop(url, None)
                    entry = None
                else:
                    if entry.etag:
                        req_headers["If-None-Match"] = entry.etag
                    if entry.last_modified:
                        req_headers["If-Modified-Since"] = entry.last_modified

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                resp = await client.get(url, headers=req_headers)

            if resp.status_code == 304:
                async with self._lock:
                    cached_entry = self._cache.get(url)
                    if cached_entry is not None:
                        cached_entry.last_checked = datetime.now(timezone.utc)
                        self._cache.move_to_end(url, last=True)
                        self.hits_304 += 1
                        return cached_entry.body, True
                    self.hits_304 += 1
                    return "", True

            if resp.status_code == 200:
                etag = resp.headers.get("etag") or resp.headers.get("ETag")
                last_modified = resp.headers.get("last-modified") or resp.headers.get("Last-Modified")
                text = resp.text

                async with self._lock:
                    # Enforce capacity bound before inserting a new key
                    if len(self._cache) >= self._max_size and url not in self._cache:
                        self._cache.popitem(last=False)
                        self.evictions += 1

                    self._cache[url] = HttpCacheEntry(
                        url=url,
                        etag=etag,
                        last_modified=last_modified,
                        body=text,
                        status_code=200,
                        headers=dict(resp.headers),
                        last_checked=datetime.now(timezone.utc),
                    )
                    self._cache.move_to_end(url, last=True)
                    self.fetches_200 += 1
                return text, False

            self.errors += 1
            return "", False

        except Exception:
            self.errors += 1
            return "", False

    async def get_entry(self, url: str) -> HttpCacheEntry | None:
        """Retrieve cache entry if present and not expired."""
        now = datetime.now(timezone.utc)
        async with self._lock:
            entry = self._cache.get(url)
            if entry is None:
                return None
            if self._is_expired(entry, now):
                self._cache.pop(url, None)
                return None
            return entry

    async def clear(self) -> None:
        """Clear all cache entries and reset metrics."""
        async with self._lock:
            self._cache.clear()
            self.hits_304 = 0
            self.fetches_200 = 0
            self.errors = 0
            self.evictions = 0

    def size(self) -> int:
        """Return current count of cached items."""
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Return cache performance statistics."""
        return {
            "hits_304": self.hits_304,
            "fetches_200": self.fetches_200,
            "errors": self.errors,
            "evictions": self.evictions,
            "size": len(self._cache),
            "max_size": self._max_size,
        }


# Global singleton instance
http_cache = HttpConditionalCache()
