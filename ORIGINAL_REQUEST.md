# Original User Request

## Initial Request — 2026-08-22T15:59:23Z

Refactor the News Collector and Summarizer web application into a secure Progressive Web App (PWA) architecture featuring:
1. PWA Standalone & Service Worker:
   - Web App Manifest (frontend/manifest.webmanifest), icons, install prompt banner/button, and offline status indicator.
   - Service Worker (frontend/sw.js) pre-caches application shell and UI assets. Network-first with cache-fallback for API responses.
   - FastAPI backend serves /sw.js and /manifest.webmanifest with appropriate headers (e.g. Service-Worker-Allowed: /) and root scope.
2. Copyright-Safe Image & Local Placeholder Architecture:
   - Strictly avoid caching, storing, or server-side copying/proxying of third-party copyrighted news photos in Cache API or backend.
   - Categorized SVG placeholder images (politics, technology, economy, world, default) in frontend/static/icons/ for offline display and missing thumbnails.
3. Snippet Preview Sub-View Navigation:
   - Single Page App (SPA) hash routing (#/, #/preview/{id}, #/history) with seamless navigation between news feed and full-page article preview with scroll restoration and smooth back navigation.
   - Preview screen displays thumbnail/placeholder, title, metadata, short 2-3 line excerpt, and action triggers.
4. On-Demand AI Summarization & Reading State Management:
   - "สรุปเนื้อหาด้วย AI" button triggers on-demand AI synthesis (takeaways, sentiment, keywords) and caches results in client storage (IndexedDB/LocalStorage).
   - Auto-record viewed articles to local reading history and support bookmarking for offline reading.
5. Clean & Secure External Link Launching:
   - Prominent "อ่านข่าวฉบับเต็ม" button opens original news source in a new window/tab using target="_blank" rel="noopener noreferrer" with automated tracking parameters (utm_*, fbclid, gclid, etc.) stripped for user privacy.

Verification:
- uv run ruff check backend/
- uv run mypy backend/
- uv run pytest backend/tests/ -v
