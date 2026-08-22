"""
services/browser_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — Manages In-App Browser sessions via Playwright / Obscura
SOLID  D — Depends on settings for service URL (injected config)
GRASP  Controller — Orchestrates Playwright CDP / Local interactions
─────────────────────────────────────────────────────────────────
WINDOWS COMPATIBILITY NOTE:
  On Windows, Uvicorn (with reload=True) uses SelectorEventLoop,
  which does not support subprocess execution (NotImplementedError).
  To make Playwright work seamlessly across all platforms without
  interfering with Uvicorn's event loop, all Playwright operations
  are executed inside a dedicated ProactorEventLoop background worker
  thread, exposed via clean non-blocking async dispatch methods.
─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import sys
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined,union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined,union-attr]

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Request,
    Route,
    async_playwright,
)

from backend.config import settings

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}

# Heavy media streams, sockets, and continuous event polling
BLOCKED_RESOURCE_TYPES = {"media", "websocket", "eventsource", "manifest", "other"}

# Telemetry, crash reporting, analytics, and heavy script networks that cause headless browser hang
BLOCKED_TRACKER_DOMAINS = {
    "google-analytics.com",
    "googletagmanager.com",
    "analytics.google.com",
    "connect.facebook.net",
    "clarity.ms",
    "hotjar.com",
    "scorecardresearch.com",
    "browser.sentry-cdn.com",
    "sentry.io",
    "crashlytics.com",
    "app-measurement.com",
    "taboola.com",
    "outbrain.com",
    "criteo.com",
    "criteo.net",
    "rubiconproject.com",
    "amazon-adsystem.com",
    "adnxs.com",
    "adop.cc",
    "compass.adop.cc",
    "innity.com",
    "innity.net",
    "mgid.com",
    "revcontent.com",
    "popads.net",
    "ad-delivery.net",
}

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process,Translate,BackForwardCache,MediaRouter",
    "--mute-audio",
    "--autoplay-policy=user-gesture-required",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]

# Tracking query parameters to strip during normalization
TRACKING_QUERY_PARAMS: set[str] = {
    "fbclid",
    "gclid",
    "_ga",
    "_gl",
    "ref",
    "ref_src",
    "mc_cid",
    "mc_eid",
}


def normalize_browser_url(url: str) -> str:
    """
    Canonicalize a URL for snapshot caching.
    - Strips hash fragments (#...)
    - Normalizes schemes and hostnames to lowercase
    - Strips default ports (:80 for http, :443 for https)
    - Strips tracking query parameters (utm_*, fbclid, gclid, etc.)
    - Sorts remaining query parameters alphabetically
    """
    url = url.strip()
    if not url:
        return ""
    if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        url = "https://" + url

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip standard default ports
    try:
        port = parsed.port
    except ValueError:
        port = None

    if (
        port is not None
        and ((scheme == "http" and port == 80) or (scheme == "https" and port == 443))
        and ":" in netloc
    ):
        netloc = netloc.rsplit(":", 1)[0]

    # Normalize path (collapse redundant slashes)
    path = parsed.path or "/"
    path = re.sub(r"/+", "/", path)

    # Filter tracking query parameters and sort remaining
    if parsed.query:
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered = [
            (k, v)
            for k, v in query_pairs
            if not (k.lower().startswith("utm_") or k.lower() in TRACKING_QUERY_PARAMS)
        ]
        filtered.sort(key=lambda x: (x[0], x[1]))
        query = urlencode(filtered)
    else:
        query = ""

    # Strip hash fragment (5th element is empty)
    return urlunsplit((scheme, netloc, path, query, ""))


@dataclass(slots=True)
class SnapshotEntry:
    """Cached DOM snapshot entry with timestamp."""

    html: str
    url: str
    title: str
    timestamp: float


class BrowserSnapshotCache:
    """
    Thread-safe and async-safe in-memory LRU cache for DOM snapshots.
    Default TTL: 15 minutes (900 seconds), Max Size: 100 entries.
    """

    def __init__(self, ttl_seconds: int = 900, max_size: int = 100) -> None:
        self._ttl_seconds: int = ttl_seconds
        self._max_size: int = max_size
        self._cache: OrderedDict[str, SnapshotEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0

    def get(self, url: str) -> dict[str, Any] | None:
        """
        Lookup cached snapshot by URL.
        Returns dict with keys {html, url, title, cached} on hit, or None on miss/expiry.
        """
        if not url:
            return None
        key = normalize_browser_url(url)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            now = time.time()
            if now - entry.timestamp > self._ttl_seconds:
                del self._cache[key]
                self._misses += 1
                return None

            # LRU update: move accessed key to most-recently used position
            self._cache.move_to_end(key)
            self._hits += 1
            return {
                "html": entry.html,
                "url": entry.url,
                "title": entry.title,
                "cached": True,
            }

    def set(self, url: str, html: str, final_url: str = "", title: str = "") -> None:
        """
        Store DOM snapshot in cache.
        Ignores empty or invalid HTML/URL.
        """
        if not url or not html or not html.strip():
            return

        key = normalize_browser_url(url)
        resolved_url = final_url if final_url else url
        entry = SnapshotEntry(
            html=html,
            url=resolved_url,
            title=title or "",
            timestamp=time.time(),
        )

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = entry

            # Also index under final_url if a redirect occurred
            if final_url:
                final_key = normalize_browser_url(final_url)
                if final_key != key:
                    if final_key in self._cache:
                        self._cache.move_to_end(final_key)
                    self._cache[final_key] = entry

            # Enforce max capacity (evict least recently used entries)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self, url: str) -> bool:
        """Invalidate a specific URL from cache. Returns True if found and removed."""
        if not url:
            return False
        key = normalize_browser_url(url)
        with self._lock:
            return self._cache.pop(key, None) is not None

    def clear(self) -> None:
        """Clear all entries and reset hit/miss counters."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @property
    def size(self) -> int:
        """Return the current number of cached snapshot entries."""
        with self._lock:
            return len(self._cache)

    def __len__(self) -> int:
        return self.size

    def stats(self) -> dict[str, Any]:
        """Return cache statistics including hits, misses, and utilization."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_ratio = (self._hits / total_requests) if total_requests > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl": self._ttl_seconds,
                "ttl_seconds": self._ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": round(hit_ratio, 4),
            }


class UnsafeUrlError(ValueError):
    """Raised when a navigation target fails the SSRF/scheme allowlist check."""


class BrowserService:
    def __init__(self, snapshot_cache: BrowserSnapshotCache | None = None) -> None:
        # In-memory HTML snapshot cache (Layer 3)
        self._snapshot_cache = (
            snapshot_cache
            if snapshot_cache is not None
            else BrowserSnapshotCache(
                ttl_seconds=getattr(settings, "browser_snapshot_cache_ttl_seconds", 900),
                max_size=getattr(settings, "browser_snapshot_cache_max_size", 100),
            )
        )

        # Dedicated event loop thread for Playwright operations
        self._loop = (
            asyncio.ProactorEventLoop()
            if sys.platform == "win32"
            else asyncio.new_event_loop()
        )
        self._thread = threading.Thread(
            target=self._run_worker_loop, daemon=True, name="PlaywrightWorker"
        )
        self._thread.start()

        # State managed exclusively within the worker thread
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}
        self._lock: asyncio.Lock | None = None
        self._tab_locks: dict[str, asyncio.Lock] | None = None
        self._obscura_available: bool = True
        self._dns_cache: dict[str, tuple[float, bool, str]] = {}

    def _run_worker_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._lock = asyncio.Lock()
        self._tab_locks = defaultdict(asyncio.Lock)
        self._loop.run_forever()

    def _dispatch(self, coro):
        """Submit a coroutine to the worker loop and wrap as an asyncio Future."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return asyncio.wrap_future(future)

    def _lock_for(self, tab_id: str) -> asyncio.Lock:
        if self._tab_locks is None:
            self._tab_locks = defaultdict(asyncio.Lock)
        return self._tab_locks[tab_id]

    # ── URL safety & Route filtering ────────────────────────────

    async def _assert_safe_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ALLOWED_SCHEMES:
            raise UnsafeUrlError(f"Scheme '{parsed.scheme}' is not allowed")
        host = parsed.hostname
        if not host:
            raise UnsafeUrlError("URL has no hostname")
        if host.lower() in BLOCKED_HOSTNAMES:
            raise UnsafeUrlError(f"Host '{host}' is blocked")

        loop = asyncio.get_running_loop()
        now = loop.time()
        cached = self._dns_cache.get(host.lower())
        if cached is not None:
            cached_time, is_safe, err_msg = cached
            if now - cached_time < 30.0:
                if not is_safe:
                    raise UnsafeUrlError(err_msg)
                return

        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
        except socket.gaierror as e:
            err_msg = f"Could not resolve host '{host}': {e}"
            self._dns_cache[host.lower()] = (now, False, err_msg)
            raise UnsafeUrlError(err_msg) from e

        for family, _, _, _, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                err_msg = f"Host '{host}' resolves to a blocked IP range ({ip})"
                self._dns_cache[host.lower()] = (now, False, err_msg)
                raise UnsafeUrlError(err_msg)

        self._dns_cache[host.lower()] = (now, True, "")

    async def _handle_route(self, route: Route) -> None:
        req = route.request
        req_url = req.url

        # 1. Block heavy streaming media, WebSockets, and continuous event streams
        if req.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort("blockedbyclient")
            return

        # 2. Allow safe in-memory pseudo schemes for subresources
        if req_url.startswith(("data:", "blob:", "about:")):
            if req.is_navigation_request() and not req_url.startswith("about:blank"):
                await route.abort("blockedbyclient")
                return
            await route.continue_()
            return

        # 3. Block telemetry, analytics, crashlytics, and heavy tracker scripts
        parsed = urlparse(req_url)
        host = (parsed.hostname or "").lower()
        if any(tracker in host for tracker in BLOCKED_TRACKER_DOMAINS):
            await route.abort("blockedbyclient")
            return

        # 4. Security check: enforce SSRF and IP safety
        try:
            await self._assert_safe_url(req_url)
            await route.continue_()
        except Exception:
            await route.abort("blockedbyclient")

    # ── internal worker lifecycle ───────────────────────────────

    async def _ensure_browser_inner(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser

        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser

            if self._playwright is None:
                self._playwright = await async_playwright().start()

            # Attempt Obscura CDP connection if available
            if self._obscura_available:
                try:
                    self._browser = await self._playwright.chromium.connect_over_cdp(
                        settings.obscura_service_url,
                        timeout=1000,
                    )
                    print(f"  🌐 Connected to Obscura browser at {settings.obscura_service_url}", flush=True)
                    return self._browser
                except Exception as e:
                    print(f"  ⚠️ Obscura not active ({e}). Using local Chromium engine...", flush=True)
                    self._obscura_available = False

            # Launch local Chromium engine with performance optimization flags
            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=LAUNCH_ARGS,
                )
            except Exception as e:
                print(f"  ⚠️ Local launch retry ({e}). Resetting Playwright instance...", flush=True)
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=LAUNCH_ARGS,
                )

            return self._browser

    async def _close_existing_tab_locked(self, tab_id: str) -> None:
        page = self._pages.pop(tab_id, None)
        if page:
            try:
                await page.close()
            except Exception:
                pass
        context = self._contexts.pop(tab_id, None)
        if context:
            try:
                await context.close()
            except Exception:
                pass

    async def _open_tab_inner(self, tab_id: str) -> None:
        async with self._lock_for(tab_id):
            await self._open_tab_locked(tab_id)

    async def _close_tab_inner(self, tab_id: str) -> None:
        async with self._lock_for(tab_id):
            await self._close_existing_tab_locked(tab_id)
        if self._tab_locks is not None:
            self._tab_locks.pop(tab_id, None)

    async def _navigate_inner(self, tab_id: str, url: str) -> dict:
        try:
            await self._assert_safe_url(url)
        except UnsafeUrlError as e:
            return {"error": f"Blocked URL: {e}"}

        async with self._lock_for(tab_id):
            page = self._pages.get(tab_id)
            if not page or page.is_closed():
                await self._open_tab_locked(tab_id)
                page = self._pages.get(tab_id)

            if not page:
                return {"error": "Failed to create tab"}

            try:
                # Fast initial load using domcontentloaded
                response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)

                # Validate final URL and all redirect chain hops before returning snapshot
                final_url = page.url
                await self._assert_safe_url(final_url)

                if response:
                    curr_req: Request | None = response.request.redirected_from
                    while curr_req is not None:
                        await self._assert_safe_url(curr_req.url)
                        curr_req = curr_req.redirected_from

                # Grace period for initial DOM hydration, web fonts, and dynamic article elements
                try:
                    await page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
                except Exception:
                    pass
                await asyncio.sleep(0.8)
                content = await self._get_snapshot_content(page)
                return {"html": content, "url": page.url, "title": await page.title()}
            except UnsafeUrlError as e:
                try:
                    await page.goto("about:blank")
                except Exception:
                    pass
                return {"error": f"Blocked URL: {e}"}
            except Exception as e:
                return {"error": f"Navigation failed: {e!s}"}

    async def _open_tab_locked(self, tab_id: str) -> None:
        existing_page = self._pages.get(tab_id)
        if existing_page and not existing_page.is_closed():
            return

        await self._close_existing_tab_locked(tab_id)
        browser = await self._ensure_browser_inner()
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            await context.route("**/*", self._handle_route)
            page = await context.new_page()
        except Exception:
            self._browser = None
            browser = await self._ensure_browser_inner()
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            await context.route("**/*", self._handle_route)
            page = await context.new_page()

        self._contexts[tab_id] = context
        self._pages[tab_id] = page

    async def _go_back_inner(self, tab_id: str) -> dict:
        async with self._lock_for(tab_id):
            page = self._pages.get(tab_id)
            if not page:
                return {"error": "Tab not found"}
            try:
                await page.go_back()
                await self._assert_safe_url(page.url)
                content = await self._get_snapshot_content(page)
                return {"html": content, "url": page.url, "title": await page.title()}
            except UnsafeUrlError as e:
                try:
                    await page.goto("about:blank")
                except Exception:
                    pass
                return {"error": f"Blocked URL: {e}"}
            except Exception as e:
                return {"error": str(e)}

    async def _go_forward_inner(self, tab_id: str) -> dict:
        async with self._lock_for(tab_id):
            page = self._pages.get(tab_id)
            if not page:
                return {"error": "Tab not found"}
            try:
                await page.go_forward()
                await self._assert_safe_url(page.url)
                content = await self._get_snapshot_content(page)
                return {"html": content, "url": page.url, "title": await page.title()}
            except UnsafeUrlError as e:
                try:
                    await page.goto("about:blank")
                except Exception:
                    pass
                return {"error": f"Blocked URL: {e}"}
            except Exception as e:
                return {"error": str(e)}

    async def _refresh_inner(self, tab_id: str) -> dict:
        async with self._lock_for(tab_id):
            page = self._pages.get(tab_id)
            if not page:
                return {"error": "Tab not found"}
            try:
                await page.reload()
                await self._assert_safe_url(page.url)
                content = await self._get_snapshot_content(page)
                return {"html": content, "url": page.url, "title": await page.title()}
            except UnsafeUrlError as e:
                try:
                    await page.goto("about:blank")
                except Exception:
                    pass
                return {"error": f"Blocked URL: {e}"}
            except Exception as e:
                return {"error": str(e)}

    # ── snapshot extraction & sanitization ──────────────────────

    async def _get_snapshot_content(self, page: Page) -> str:
        content = await page.evaluate(r'''() => {
            const clone = document.documentElement.cloneNode(true);

            // Inject <base href="..."> so images, fonts, styles resolve correctly
            let head = clone.querySelector("head");
            if (!head) {
                head = document.createElement("head");
                clone.insertBefore(head, clone.firstChild);
            }
            const base = document.createElement("base");
            base.href = document.location.href;
            head.insertBefore(base, head.firstChild);

            // 1. Inline all stylesheets into <style> tags where accessible,
            // or resolve href to absolute URL with CORS fallback
            const linkEls = Array.from(clone.querySelectorAll('link[rel~="stylesheet"]'));
            for (const link of linkEls) {
                const rawHref = link.getAttribute("href") || "";
                let cssText = "";
                for (const sheet of document.styleSheets) {
                    try {
                        if (sheet.href === link.href || (rawHref && sheet.href && (sheet.href.includes(rawHref) || rawHref.includes(sheet.href)))) {
                            const rules = Array.from(sheet.cssRules || []);
                            cssText = rules.map(r => r.cssText).join("\\n");
                            break;
                        }
                    } catch (e) {
                        // Cross-origin stylesheet SecurityError
                    }
                }
                if (cssText) {
                    const styleEl = document.createElement("style");
                    styleEl.textContent = cssText;
                    link.replaceWith(styleEl);
                } else if (rawHref) {
                    try {
                        link.href = new URL(rawHref, document.baseURI).href;
                        link.setAttribute("crossorigin", "anonymous");
                    } catch (e) {}
                }
            }

            // 2. Extract Adopted StyleSheets (Constructed Stylesheets / Shadow DOM / Frameworks)
            if (document.adoptedStyleSheets && document.adoptedStyleSheets.length > 0) {
                for (const sheet of document.adoptedStyleSheets) {
                    try {
                        const rules = Array.from(sheet.cssRules || []);
                        const cssText = rules.map(r => r.cssText).join("\\n");
                        if (cssText) {
                            const styleEl = document.createElement("style");
                            styleEl.textContent = cssText;
                            head.appendChild(styleEl);
                        }
                    } catch (e) {}
                }
            }

            // 3. Ensure high-fidelity Thai font fallback stack
            const fontFallback = document.createElement("style");
            fontFallback.textContent = `
                body, button, input, select, textarea {
                    font-family: inherit, -apple-system, BlinkMacSystemFont, "Sarabun", "Sukhumvit Set", "Prompt", "Segoe UI", Roboto, sans-serif;
                }
            `;
            head.appendChild(fontFallback);

            // Ensure body and html can scroll freely
            if (clone.style) clone.style.overflow = "auto";
            const body = clone.querySelector("body");
            if (body && body.style) {
                body.style.overflow = "auto";
                body.style.position = "static";
            }

            // Convert lazy-loaded images to standard src so images render without client JS
            const images = clone.querySelectorAll("img, picture source, [data-src], [data-lazy-src], [data-original]");
            for (const el of images) {
                const lazySrc = el.getAttribute("data-src") || el.getAttribute("data-original") || el.getAttribute("data-lazy-src") || el.getAttribute("data-lazy") || el.getAttribute("data-url");
                if (lazySrc && (!el.getAttribute("src") || el.getAttribute("src").startsWith("data:image"))) {
                    try {
                        el.setAttribute("src", new URL(lazySrc, document.baseURI).href);
                    } catch(e) {
                        el.setAttribute("src", lazySrc);
                    }
                }
                const lazySrcset = el.getAttribute("data-srcset");
                if (lazySrcset && !el.getAttribute("srcset")) {
                    el.setAttribute("srcset", lazySrcset);
                }
                el.removeAttribute("loading");
            }

            // Remove dangerous scripts/iframes to prevent execution loops
            const dangerous = clone.querySelectorAll("script, iframe, noscript, object, embed");
            for (const el of dangerous) el.remove();

            // Remove unused script preloads, modulepreloads, and preconnects to prevent
            // "resource was preloaded using link preload but not used" warnings and unneeded downloads
            const uselessPreloads = clone.querySelectorAll(`
                link[rel="preload"][as="script"],
                link[rel="modulepreload"],
                link[rel="prefetch"],
                link[rel="dns-prefetch"],
                link[rel="preconnect"]
            `);
            for (const el of uselessPreloads) el.remove();

            // Strip tracking pixels and 1x1 ad beacons (Privacy by Design / PDPA minimization)
            const trackingPixels = clone.querySelectorAll(`
                img[width="1"], img[height="1"],
                img[src*="adop.cc"], img[src*="doubleclick"],
                img[src*="analytics"], img[src*="tracker"],
                img[src*="pixel"]
            `);
            for (const el of trackingPixels) el.remove();

            // Strip every inline event-handler attribute (onerror, onload,
            // onclick, onmouseover, ...) and javascript:/data: URIs from
            // *all* elements.
            const all = clone.querySelectorAll("*");
            for (const el of all) {
                for (const attr of Array.from(el.attributes)) {
                    const name = attr.name.toLowerCase();
                    const value = attr.value.trim().toLowerCase();
                    if (name.startsWith("on")) {
                        el.removeAttribute(attr.name);
                    } else if ((name === "href" || name === "src" || name === "action" || name === "formaction")
                               && (value.startsWith("javascript:") || value.startsWith("data:text/html"))) {
                        el.removeAttribute(attr.name);
                    }
                }
            }

            // Inject global click interceptor script with event capturing (useCapture: true)
            // 1. Handles Cookie / PDPA / Consent / Popup dismiss & accept buttons
            // 2. Handles <a>, <div data-url>, <button role="link">, and relative URL resolution
            const interceptor = document.createElement("script");
            interceptor.textContent = `
                document.addEventListener('click', function(e) {
                    const target = e.target;

                    // --- 1. Interactive Cookie / Consent / Banner / Popup Dismiss Handler ---
                    const interactiveEl = target.closest('button, a, input, [role="button"], [data-dismiss], [aria-label], span, svg, div');
                    if (interactiveEl) {
                        const text = (interactiveEl.textContent || "").trim().toLowerCase();
                        const ariaLabel = (interactiveEl.getAttribute("aria-label") || "").toLowerCase();
                        const cls = (interactiveEl.className || "").toString().toLowerCase();
                        const elId = (interactiveEl.id || "").toLowerCase();

                        const isCloseOrAccept = 
                            /^(ยอมรับ|ตกลง|เข้าใจแล้ว|รับทราบ|ยินยอม|ปิด|accept|agree|got it|allow|ok|okay|i agree|close|reject|decline|dismiss|x|✕|✖|×|hide)$/i.test(text) ||
                            /(close|dismiss|accept|agree|consent|pdpa)/i.test(ariaLabel) ||
                            /(close|dismiss|accept|agree|consent|pdpa)/i.test(cls) ||
                            /(close|dismiss|accept|agree|consent|pdpa)/i.test(elId);

                        if (isCloseOrAccept) {
                            const banner = interactiveEl.closest(\`
                                [id*="cookie" i], [class*="cookie" i],
                                [id*="consent" i], [class*="consent" i],
                                [id*="pdpa" i], [class*="pdpa" i],
                                [id*="popup" i], [class*="popup" i],
                                [id*="modal" i], [class*="modal" i],
                                [id*="banner" i], [class*="banner" i],
                                [id*="notice" i], [class*="notice" i],
                                [id*="dialog" i], [class*="dialog" i],
                                [id*="overlay" i], [class*="overlay" i]
                            \`) || (function() {
                                let p = interactiveEl.parentElement;
                                let count = 0;
                                while (p && p !== document.body && count < 6) {
                                    const pos = window.getComputedStyle ? window.getComputedStyle(p).position : "";
                                    if (pos === "fixed" || pos === "sticky" || (pos === "absolute" && p.offsetWidth > 200)) {
                                        return p;
                                    }
                                    p = p.parentElement;
                                    count++;
                                }
                                return null;
                            })();

                            if (banner) {
                                e.preventDefault();
                                e.stopPropagation();
                                banner.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
                                banner.style.opacity = '0';
                                banner.style.pointerEvents = 'none';
                                setTimeout(() => {
                                    try { banner.remove(); } catch(err) { banner.style.display = 'none'; }
                                    document.documentElement.style.overflow = 'auto';
                                    document.body.style.overflow = 'auto';
                                }, 200);
                                return;
                            }
                        }
                    }

                    // --- 2. Navigation Link Handling ---
                    const link = target.closest('a, [data-href], [data-url], [data-permalink], [role="link"]');
                    if (!link) return;
                    const rawUrl = link.getAttribute('href') || link.getAttribute('data-href') || link.getAttribute('data-url') || link.getAttribute('data-permalink');
                    if (rawUrl && rawUrl !== '#' && !rawUrl.startsWith('javascript:')) {
                        e.preventDefault();
                        e.stopPropagation();
                        try {
                            const resolved = new URL(rawUrl, document.baseURI).href;
                            window.parent.postMessage({ type: 'BROWSER_NAVIGATE', url: resolved }, '*');
                        } catch(err) {
                            console.warn('URL resolution error:', err);
                        }
                    }
                }, true);
            `;
            (body || clone).appendChild(interceptor);

            return clone.outerHTML;
        }''')
        return content

    # ── Snapshot Cache Management (Layer 3) ─────────────────────

    @property
    def snapshot_cache(self) -> BrowserSnapshotCache:
        """Access the underlying snapshot cache instance."""
        return self._snapshot_cache

    def clear_snapshot_cache(self) -> None:
        """Clear all stored snapshots in the LRU cache."""
        self._snapshot_cache.clear()

    def snapshot_cache_stats(self) -> dict[str, Any]:
        """Return statistics (size, hits, misses, etc.) of the snapshot cache."""
        return self._snapshot_cache.stats()

    # ── Public Async API (thread-safe dispatch) ─────────────────

    async def open_tab(self, tab_id: str) -> None:
        await self._dispatch(self._open_tab_inner(tab_id))

    async def close_tab(self, tab_id: str) -> None:
        await self._dispatch(self._close_tab_inner(tab_id))

    async def navigate(self, tab_id: str, url: str) -> dict:
        # 1. Enforce SSRF & Scheme safety before cache lookup
        try:
            await self._assert_safe_url(url)
        except UnsafeUrlError as e:
            return {"error": f"Blocked URL: {e}"}

        # 2. Check Snapshot Cache (Layer 3) to bypass Playwright/CDP execution
        cached_snapshot = self._snapshot_cache.get(url)
        if cached_snapshot is not None:
            return cached_snapshot

        # 3. Cache Miss: Dispatch to Playwright / Obscura worker thread
        result = await self._dispatch(self._navigate_inner(tab_id, url))

        # 4. Strict Error Isolation: Cache ONLY valid snapshots
        if isinstance(result, dict) and "error" not in result and bool(result.get("html")):
            final_url = result.get("url", url)
            title = result.get("title", "")
            self._snapshot_cache.set(
                url=url,
                html=result["html"],
                final_url=final_url,
                title=title,
            )

        return result

    async def go_back(self, tab_id: str) -> dict:
        result = await self._dispatch(self._go_back_inner(tab_id))
        if isinstance(result, dict) and "error" not in result and bool(result.get("html")):
            page_url = result.get("url", "")
            if page_url:
                self._snapshot_cache.set(
                    url=page_url,
                    html=result["html"],
                    final_url=page_url,
                    title=result.get("title", ""),
                )
        return result

    async def go_forward(self, tab_id: str) -> dict:
        result = await self._dispatch(self._go_forward_inner(tab_id))
        if isinstance(result, dict) and "error" not in result and bool(result.get("html")):
            page_url = result.get("url", "")
            if page_url:
                self._snapshot_cache.set(
                    url=page_url,
                    html=result["html"],
                    final_url=page_url,
                    title=result.get("title", ""),
                )
        return result

    async def refresh(self, tab_id: str) -> dict:
        result = await self._dispatch(self._refresh_inner(tab_id))
        if isinstance(result, dict) and "error" not in result and bool(result.get("html")):
            refreshed_url = result.get("url", "")
            if refreshed_url:
                title = result.get("title", "")
                self._snapshot_cache.set(
                    url=refreshed_url,
                    html=result["html"],
                    final_url=refreshed_url,
                    title=title,
                )
        return result


browser_service = BrowserService()