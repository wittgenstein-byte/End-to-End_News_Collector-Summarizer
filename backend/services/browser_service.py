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
import socket
import sys
import threading
from collections import defaultdict
from urllib.parse import urlparse

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


class UnsafeUrlError(ValueError):
    """Raised when a navigation target fails the SSRF/scheme allowlist check."""


class BrowserService:
    def __init__(self) -> None:
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

    # ── URL safety ──────────────────────────────────────────────

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
        # Allow safe in-memory pseudo schemes for subresources
        if req_url.startswith(("data:", "blob:", "about:")):
            if req.is_navigation_request() and not req_url.startswith("about:blank"):
                await route.abort("blockedbyclient")
                return
            await route.continue_()
            return

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

            # Launch local Chromium engine
            try:
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
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
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
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

                # Short grace period for initial DOM hydration / fonts / dynamic article elements
                await asyncio.sleep(0.5)
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
        content = await page.evaluate('''() => {
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

            // Remove blocking cookie consent banners, modal backdrops, and ad overlays
            // that freeze the landing page when scripts are disabled
            const overlays = clone.querySelectorAll(`
                #onetrust-consent-sdk,
                #cookie-notice,
                #cookie-law-info-bar,
                .cookie-banner,
                .cookie-consent,
                .pdpa-consent,
                .pdpa-banner,
                .modal-backdrop,
                .sp_veil,
                .didomi-popup-container,
                .qc-cmp2-container,
                [id*="cookie-banner"],
                [class*="cookie-banner"],
                [class*="consent-modal"]
            `);
            for (const el of overlays) el.remove();

            // Ensure body and html can scroll freely
            if (clone.style) clone.style.overflow = "auto";
            const body = clone.querySelector("body");
            if (body && body.style) {
                body.style.overflow = "auto";
                body.style.position = "static";
            }

            // Convert lazy-loaded images to standard src so images render without client JS
            const images = clone.querySelectorAll("img, picture source");
            for (const el of images) {
                const lazySrc = el.getAttribute("data-src") || el.getAttribute("data-original") || el.getAttribute("data-lazy-src") || el.getAttribute("data-lazy");
                if (lazySrc && (!el.getAttribute("src") || el.getAttribute("src").startsWith("data:image"))) {
                    el.setAttribute("src", lazySrc);
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
            // Handles <a>, <div data-url>, <button role="link">, and relative URL resolution
            const interceptor = document.createElement("script");
            interceptor.textContent = `
                document.addEventListener('click', function(e) {
                    const link = e.target.closest('a, [data-href], [data-url], [data-permalink], [role="link"]');
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

    # ── Public Async API (thread-safe dispatch) ─────────────────

    async def open_tab(self, tab_id: str) -> None:
        await self._dispatch(self._open_tab_inner(tab_id))

    async def close_tab(self, tab_id: str) -> None:
        await self._dispatch(self._close_tab_inner(tab_id))

    async def navigate(self, tab_id: str, url: str) -> dict:
        return await self._dispatch(self._navigate_inner(tab_id, url))

    async def go_back(self, tab_id: str) -> dict:
        return await self._dispatch(self._go_back_inner(tab_id))

    async def go_forward(self, tab_id: str) -> dict:
        return await self._dispatch(self._go_forward_inner(tab_id))

    async def refresh(self, tab_id: str) -> dict:
        return await self._dispatch(self._refresh_inner(tab_id))


browser_service = BrowserService()