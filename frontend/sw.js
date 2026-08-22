/**
 * sw.js - Service Worker for NEWSROOM PWA
 * 
 * Strategy:
 * 1. App Shell (Static Assets & First-party Placeholders): Cache-First
 * 2. API (/api/news, /api/categories, /api/sources): Network-First with Cache Fallback
 * 3. Third-party News Images: NO-CACHE in Cache API (Copyright & storage safe)
 * 4. Offline Fallback: Serves cached app shell and cached API data seamlessly
 */

const CACHE_NAME = "newsroom-pwa-v2.3.0";
const API_CACHE_NAME = "newsroom-api-v2.3.0";

const PRECACHE_ASSETS = [
  "/",
  "/frontend/static/app.css",
  "/frontend/static/main.js",
  "/frontend/static/UI.js",
  "/frontend/static/api.js",
  "/frontend/static/config.js",
  "/manifest.webmanifest",
  "/frontend/static/icons/icon-192.svg",
  "/frontend/static/icons/icon-512.svg",
  "/frontend/static/icons/placeholder-default.svg",
  "/frontend/static/icons/placeholder-technology.svg",
  "/frontend/static/icons/placeholder-economy.svg",
  "/frontend/static/icons/placeholder-politics.svg",
  "/frontend/static/icons/placeholder-world.svg",
  "/frontend/static/icons/placeholder-environment.svg",
  "/frontend/static/icons/placeholder-sports.svg"
];

// ── Install Event ──────────────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("[SW] Pre-caching App Shell");
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn("[SW] Pre-cache error on some assets:", err);
      });
    }).then(() => self.skipWaiting())
  );
});

// ── Activate Event (Clean old caches) ───────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && key !== API_CACHE_NAME) {
            console.log("[SW] Removing old cache:", key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// ── Fetch Event ─────────────────────────────────────────────────────
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // 1. Ignore non-GET requests and WebSocket / Socket.io
  if (request.method !== "GET" || url.pathname.startsWith("/socket.io/")) {
    return;
  }

  // 2. Copyright Safety Rule: Do NOT cache external third-party images or domains
  const isFirstParty = url.origin === self.location.origin;
  if (!isFirstParty) {
    // External resource (e.g. news photos, google fonts) -> Let browser fetch without storing in SW Cache
    return;
  }

  // 3. API Requests (/api/news, /api/categories, /api/sources) -> Network First, Cache Fallback
  if (url.pathname.startsWith("/api/")) {
    // Do not cache heavy write or streaming requests like summarize
    if (url.pathname.includes("/collect-md")) {
      return;
    }

    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(API_CACHE_NAME).then((cache) => {
              cache.put(request, responseToCache);
            });
          }
          return networkResponse;
        })
        .catch(async () => {
          const cachedResponse = await caches.match(request);
          if (cachedResponse) {
            return cachedResponse;
          }
          // Return empty JSON fallback if API is not cached
          return new Response(JSON.stringify({ ok: false, offline: true, news: [] }), {
            headers: { "Content-Type": "application/json" }
          });
        })
    );
    return;
  }

  // 4. HTML Navigation Requests -> Network First, Cache Fallback to '/'
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => {
        return caches.match("/");
      })
    );
    return;
  }

  // 5. Static Assets (CSS, JS, SVGs) -> Cache First, Network Fallback
  event.respondWith(
    caches.match(request, { ignoreSearch: true }).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseToCache);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          return new Response("", { status: 404, statusText: "Offline Not Found" });
        });
    })
  );
});
