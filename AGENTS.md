# AGENTS.md — News Collector & Summarizer

## Project Overview

- **Type**: Full-stack Python (FastAPI + Socket.IO) + Vanilla JS/CSS frontend
- **Language**: Python 3.10+ (backend), JavaScript ES Modules (frontend), Thai NLP (pythainlp)
- **Architecture**: SOLID + GRASP principles (see docstrings in each file)
- **Backend entry**: `python backend/main.py` (runs on port 5000)
- **Frontend**: Static files served by FastAPI at `/frontend/`

---

## Build / Run

```bash
# Install dependencies
pip install requests beautifulsoup4 playwright fastapi trafilatura uvicorn \
  socketio httpx openai pythainlp pydantic

# Install Playwright Chromium (required)
playwright install chromium

# Run server (auto-reload enabled)
python backend/main.py

# Open in browser
http://localhost:5000
```

### Environment

Copy `backend/.env.example` to `backend/.env`:
```
LLM_API=your_api_key_here
```

---

## Lint / Type Check

No formal linter config. Run manually if installed:

```bash
ruff check backend/
mypy backend/
```

---

## Test Commands

**No test suite found** (`pytest`, `unittest`). To run a test once added:

```bash
# Single test file / function / by name
pytest backend/tests/test_news_repo.py -v
pytest backend/tests/test_news_repo.py::TestFileNewsRepository::test_load_news -v
pytest -k "test_load_news" -v
```

Place tests in `backend/tests/` with `conftest.py` for fixtures.

---

## Code Style Guidelines

### Python

- **Indentation**: 4 spaces (no tabs)
- **Line length**: ~88-120 chars
- **Imports order**: `__future__` → stdlib → third-party → local/relative
- **Type hints**: Required on all function signatures
- **Literal types**: Use `Literal["politics", "economy", ...]` for enums
- **Protocol classes**: Use `Protocol` for dependency-injection ports
- **Private attrs**: Prefix with `_` (e.g., `self._repo`)
- **Docstrings**: Block-comment style with `──` borders; SOLID/GRASP notes at module top
- **Error handling**: 
  - IO/repo helpers: swallow at boundary (`except Exception: return default`)
  - Routers: raise `HTTPException`
- **Async**: Use `asyncio.to_thread()` for sync blocking calls. Never block the event loop.
- **Lazy imports**: Avoid top-level imports inside async functions when avoidable
- **Config**: Use `backend/config.py` `Settings` class. Never hardcode paths or secrets.
- **File paths**: Always use `pathlib.Path`, never string concatenation
- **`from __future__ import annotations`**: Use in every `.py` file for forward-ref compatibility

### JavaScript (Frontend)

- **Modules**: ES Modules (`import`/`export`), no CommonJS
- **State**: Module-level variables (no framework state management)
- **DOM**: All DOM work in `UI.js`. Business logic in `main.js`. API in `api.js`. Config in `config.js`.
- **Naming**: camelCase (variables/functions), UPPER_SNAKE (constants)
- **Callbacks**: Use `window.__<name>` pattern for HTML `onclick` attributes
- **Error handling**: `try/catch` with `UI.showGridError(e.message)` or `console.warn`

### CSS

- **Variables**: CSS custom properties for theming (`:root` in `app.css`)
- **Naming**: kebab-case class names
- **Units**: `rem` for typography/spacing, `px` for borders

---

## Architecture

### Backend Layers

```
routers/      → FastAPI endpoints (SOLID I: one concern per router)
services/     → Business logic (scraper, summarizer, classifier)
scrapers/     → Source-specific fetchers with @register_source decorator
repo/         → Data persistence (JSON files, NewsRepositoryPort protocol)
core/         → Shared utilities (browser, socket, constants, fetcher strategy)
schemas/      → Pydantic models (request/response/internal separated)
config.py     → Settings injection (singleton `settings` global)
```

### Data Flow

```
ScraperService.run_loop()
  → sources.py (per-source async fn)
    → helpers.py (HTML parse, image, URL)
      → core/browser.py or httpx (fetch)
  → repo/news_repo.py (save JSON)
  → emit via socket_manager → frontend WebSocket
```

---

## Adding New Components

### New News Source

1. Add scraper function to `backend/scrapers/sources.py`
2. Decorate with `@register_source("Name", "https://...", "#color")`

### New Category

1. Add keywords to `_RULES` dict in `backend/services/classifier_service.py`
2. Sync `CATEGORIES` array in `frontend/static/config.js`
3. Add to `VALID_CATEGORIES` in `backend/routers/news_router.py`

### One-off Jobs

```bash
# Re-classify all existing articles
python backend/reclassify_job.py
```

---

## File Patterns

| Pattern | Meaning |
|---|---|
| `backend/core/*.py` | Shared infrastructure |
| `backend/scrapers/sources.py` | Source scrapers (add here) |
| `backend/scrapers/helpers.py` | HTML parsing utilities |
| `backend/scrapers/registry.py` | Source registration |
| `backend/services/*.py` | Business logic |
| `backend/repo/news_repo.py` | Persistence layer |
| `backend/schemas/*.py` | Pydantic models |
| `backend/routers/*.py` | FastAPI route handlers |
| `frontend/static/*.js` | JS modules (main, api, UI, config) |
| `frontend/static/app.css` | All styles |
| `frontend/index.html` | Single HTML page |

---

## Common Pitfalls

- **Don't** call `settings` or repo at module-level outside `config.py` — use lazy imports
- **Don't** use `print()` for user-facing errors — log and return appropriate HTTP status
- **Do** use `pathlib.Path` for all file paths (cross-platform)
