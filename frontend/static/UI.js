/**
 * frontend/static/UI.js
 * ─────────────────────────────────────────────────────────────────
 * Central Backward-Compatible Barrel Facade for News Collector & Summarizer
 *
 * Decomposed in Milestone 3 from a 3,951-line monolith into 11 focused,
 * single-responsibility ES modules with a strict zero-cycle DAG architecture:
 *
 * 1. utils/common.js            - Escaping, Thai dates, badges, storyline cache
 * 2. components/status.js        - WebSocket badge, counters, toast, ticker, banners
 * 3. components/filters.js       - Category nav, unread badges, source pills
 * 4. components/cards.js         - Responsive feed card grid, skeletons, pagination
 * 5. components/reader.js        - Summary modal, inline accordion, preview drawer
 * 6. components/hero.js          - Trending carousel, touch swipe, autoplay
 * 7. components/sports-intelligence.js - 10-discipline NLP rules & cluster detector
 * 8. components/sports.js        - Multi-sport hub view, discipline tabs, score pills
 * 9. components/digest.js        - AI progression synthesis dossier, citations, audit
 * 10. components/storyline.js    - Macro storyline view, sub-events, timeline
 * 11. components/evaluation.js   - Academic thesis evaluation view & feedback
 * ─────────────────────────────────────────────────────────────────
 */

export * from "./utils/common.js";
export * from "./components/status.js";
export * from "./components/filters.js";
export * from "./components/cards.js";
export * from "./components/reader.js";
export * from "./components/hero.js";
export * from "./components/sports-intelligence.js";
export * from "./components/sports.js";
export * from "./components/digest.js";
export * from "./components/storyline.js";
export * from "./components/evaluation.js";