# Project: Headless Decoupling & Modular Frontend Architecture
# Scope: Full Decoupling, Modularization & Performance Optimization

## Architecture
- **Backend Architecture**: Headless FastAPI REST & python-socketio ASGI service.
  - `backend/config.py`: Headless toggle (`headless: bool`), dynamic CORS origins (`cors_origins: list[str]`), and origin regex (`cors_origin_regex: str | None`).
  - `backend/main.py`: Headless mode skips frontend static mounting; root `/` serves API service catalog JSON. Dynamic CORS middleware.
  - `backend/core/socket_manager.py`: Socket.IO CORS unified with `settings.cors_origins`.
- **Frontend Architecture**: Pure Vanilla JS (ES Modules) + Tailwind CSS client architecture.
  - `frontend/static/config.js`: 4-tier API_BASE & SOCKET_URL resolution hierarchy supporting standalone static hosting & dev servers (Vite/Node).
  - `frontend/static/socket.js`: Dedicated WebSocket communication and reconnection service isolated from DOM.
  - `frontend/static/api.js`: Dedicated HTTP client with standardized error handling and dynamic base URL resolution.
  - `frontend/static/components/`: Modular, single-responsibility ES components (all strictly <800 LOC).
    * `components/common.js`: Pure helpers, HTML escaping, Thai date/time formatters, badges. (~197 LOC)
    * `components/status.js`: Toast notifications, offline banner, PWA install prompt. (~120 LOC)
    * `components/filters.js`: Category chips, source dropdown, date filters, search bar. (~161 LOC)
    * `components/cards.js`: News feed grid, card rendering, pagination, skeleton loaders. (~199 LOC)
    * `components/reader.js`: Full article preview drawer/view, inline summary, share actions. (~436 LOC)
    * `components/hero.js`: Top news hero carousel, multi-image montage, slide controls. (~650 LOC)
    * `components/sports-intelligence.js`: 10-discipline rule classifier, cluster detection. (~169 LOC)
    * `components/sports.js`: Sports hub, 10 discipline tabs, AI digest cards, multi-image montage. (~712 LOC)
    * `components/storyline.js`: Macro storyline view, executive dossier, progression timeline, citations. (~750 LOC)
    * `components/digest.js`: AI synthesis dossier modal, quality audit panel. (~290 LOC)
    * `components/evaluation.js`: Academic feedback and evaluation interface. (~150 LOC)
  - `frontend/static/UI.js`: Thin backward-compatible barrel facade re-exporting component methods (~50 LOC).
  - `frontend/static/main.js`: Application bootstrapper, routing orchestrator, dynamic lazy imports for heavy views.

## Code Layout
- `backend/config.py`: Server configuration settings
- `backend/main.py`: FastAPI server setup & CORS middleware
- `backend/core/socket_manager.py`: Socket.IO server & event emitter
- `frontend/static/config.js`: Client runtime endpoint configuration
- `frontend/static/socket.js`: Client WebSocket manager
- `frontend/static/api.js`: Client REST API service
- `frontend/static/components/*.js`: Decomposed UI component modules
- `frontend/static/UI.js`: Facade re-exporting components
- `frontend/static/main.js`: Main entry point and dynamic router

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Headless Mode Toggle | `HEADLESS=true` or `--headless` flag to run purely headless | M1 | Survey D1 |
| 2 | Service Catalog at Root | Headless root `/` returns JSON API catalog instead of HTML | M1 | Survey D1 |
| 3 | Dynamic CORS Middleware | Configurable CORS supporting multiple origins and dev ports | M1 | Survey D1 |
| 4 | Socket.IO CORS Unification | Align `socket_manager.py` CORS with `settings.cors_origins` | M1 | Survey D1 |
| 5 | Standalone Client Config | 4-tier API_BASE & SOCKET_URL resolution hierarchy | M1 | Survey D1 |
| 6 | Image Proxy Resolution | Absolute URL resolution for `/api/image` proxy in detached client | M1 | Survey D1 |
| 7 | Client Socket Layer | Dedicated `socket.js` for WebSocket lifecycle & events | M2 | Survey D2 |
| 8 | Isolated HTTP API Layer | Standardized REST client in `api.js` with dynamic base URL | M2 | Survey D2 |
| 9 | UI Common Utilities Module | Extract `components/common.js` (<800 LOC) | M3 | Survey D2 |
| 10 | UI Status & Feedback Module | Extract `components/status.js` (<800 LOC) | M3 | Survey D2 |
| 11 | UI Filters & Navigation Module | Extract `components/filters.js` (<800 LOC) | M3 | Survey D2 |
| 12 | UI News Cards Module | Extract `components/cards.js` (<800 LOC) | M3 | Survey D2 |
| 13 | UI Reader Drawer Module | Extract `components/reader.js` (<800 LOC) | M3 | Survey D2 |
| 14 | UI Hero & Montage Module | Extract `components/hero.js` (<800 LOC) | M3 | Survey D2 |
| 15 | Sports Intelligence Module | Extract `components/sports-intelligence.js` (<800 LOC) | M3 | Survey D2 |
| 16 | Sports Hub View Module | Extract `components/sports.js` (<800 LOC) | M3 | Survey D2 |
| 17 | Storyline Dossier View Module | Extract `components/storyline.js` (<800 LOC) | M3 | Survey D2 |
| 18 | AI Digest Synthesis Module | Extract `components/digest.js` (<800 LOC) | M3 | Survey D2 |
| 19 | Evaluation View Module | Extract `components/evaluation.js` (<800 LOC) | M3 | Survey D2 |
| 20 | Barrel Facade UI.js | Compatibility facade re-exporting all UI methods (<100 LOC) | M3 | Survey D2 |
| 21 | Dead Code Elimination | Remove 340+ lines of dead functions, stubs, and obsolete stubs | M4 | Survey Miner D1 |
| 22 | Code Splitting / Lazy Loading | Dynamic `import()` for Storyline, Sports, Digest, and Reader | M4 | Survey Miner D1 |
| 23 | Hero Autoplay Timer Management | Pause autoplay timer on view switch; resume on feed view | M4 | Survey Miner D1 |
| 24 | Scroll Listener Lifecycle | Scoped listener with `AbortController` cleanup | M4 | Survey Miner D1 |
| 25 | Modal Keyboard & Backdrop Cleanup | Centralized `Escape` key and backdrop event cleanup | M4 | Survey Miner D1 |
| 26 | Standalone Origin E2E Test | Automated verification of frontend running on independent port | M5 | Acceptance Criteria |
| 27 | 10 Sports Discipline Tabs Test | Automated verification of all 10 sports tabs and filter parity | M5 | Acceptance Criteria |
| 28 | Sports Digest & Hero Montage Test | Verification of AI digest cards and multi-image montage | M5 | Acceptance Criteria |
| 29 | Storyline & Citations Test | Verification of macro storyline view, dossier, and citations | M5 | Acceptance Criteria |
| 30 | Socket Live Updates Test | Verification of live socket event delivery and UI updates | M5 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Server-Level & Network Decoupling | Headless FastAPI, Dynamic CORS, Socket.IO CORS, Client Config | none | DONE (Verified: 165 decoupling tests, 489 full repo tests, clean Ruff/Mypy/Node-c, Forensic Audit CLEAN) |
| M2 | Client State & Communication Layer Isolation | Dedicated `socket.js`, isolated `api.js` | M1 | DONE (Verified: socket.js 512 LOC, api.js 554 LOC, 41 adversarial tests, 22 unit tests, Forensic Audit CLEAN) |
| M3 | Frontend Component Modularization | Decompose `UI.js` into 11 ES modules (<800 LOC each), barrel `UI.js` | M2 | IN_PROGRESS |
| M4 | Performance Optimization | Dead code elimination, dynamic imports, timer/scroll listener cleanup | M3 | PLANNED |
| M5 | E2E Integration, Visual & Regression Verification | Comprehensive automated test suite & adversarial validation | M4 | PLANNED |

## Interface Contracts
### Backend ↔ Frontend REST Contract
- `GET /`: In headless mode, returns `{"service": "News Collector & Summarizer API", "status": "ok", "version": "...", "endpoints": [...]}`
- `GET /api/news`: Standard news feed query with pagination, category, source, search
- `GET /api/stories`, `GET /api/stories/trending`: Story cluster queries
- `GET /api/macro-events`, `GET /api/macro-events/trending`: Storyline queries
- `GET /api/sources`, `GET /api/categories`: Taxonomy metadata
- `GET /api/status`: Scraper and service health telemetry

### Backend ↔ Frontend Socket.IO Contract
- Transports: `["websocket", "polling"]`
- Endpoint: `/socket.io/`
- Events emitted by backend:
  * `news_batch`: List of newly scraped articles
  * `stats_update`: Scraper status and article count updates
  * `trending_update`: Recalculated trending stories

### Client Module Dependency DAG
Level 0: `config.js`
Level 1: `utils/common.js` (pure helpers, formatting)
Level 2: `status.js`, `api.js`, `socket.js`, `sports-intelligence.js`
Level 3: `filters.js`, `cards.js`, `hero.js`, `reader.js`, `digest.js`, `evaluation.js`
Level 4: `sports.js`, `storyline.js`
Level 5: `UI.js` (barrel facade)
Level 6: `main.js` (app bootstrapper and dynamic view loader)
Strictly 0 circular dependencies.
