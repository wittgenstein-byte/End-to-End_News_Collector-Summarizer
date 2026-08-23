# Project: In-App Browser & Personalization
# Scope: Full Project

## Architecture
- `docker-compose.yml`: Add `obscura` service.
- `backend/config.py`: Add `obscura_service_url`.
- `backend/sockets/` & `backend/services/`: Browser service managing Playwright CDP sessions.
- `frontend/static/`: Add personalization, cache, browser tabs UI, cookie banner.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Docker & Config | Update docker-compose.yml, add config to backend/config.py | none | PLANNED |
| 2 | Backend Browser Service | Add `browser_service.py` using CDP, wire to WebSockets | M1 | PLANNED |
| 3 | Frontend Personalization & PDPA | localStorage caching, cookie banner, settings UI | none | PLANNED |
| 4 | Frontend Browser UI | Tabs, URL bar, rendering DOM snapshots | M2, M3 | PLANNED |

## Interface Contracts
### Browser Service ↔ Frontend (WebSocket)
- `browser_navigate`: Request to navigate a tab.
- `browser_snapshot`: Push DOM snapshot from backend to frontend.
