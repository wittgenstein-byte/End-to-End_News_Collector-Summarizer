# AGENTS.md — News Collector & Summarizer

## Project Overview

- **Type**: Full-stack Python (FastAPI + Socket.IO) + Vanilla JS/CSS frontend
- **Language**: Python (backend), JavaScript ES Modules (frontend), Thai NLP (pythainlp)
- **Python version**: 3.10+
- **Architecture**: SOLID + GRASP principles (see docstrings in each file)
- **Backend entry**: `python backend/main.py`
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

Copy `backend/.env.example` to `backend/.env` and set at minimum:
```
LLM_API=your_api_key_here
```

### One-off Jobs

```bash
# Re-classify all existing articles with updated rules
python backend/reclassify_job.py
```

---

## Lint / Type Check

No formal linter config found (no ruff, flake8, pyright). Run manually if installed:

```bash
# Ruff (if present)
ruff check backend/

# MyPy (if present)
mypy backend/
```

### Code Formatting Conventions (follow existing style)

- **Indentation**: 4 spaces (no tabs)
- **Line length**: ~88 chars (Black default), but manually wrapped at ~120 for readability
- **Imports order** (per file):
  1. `__future__` annotations
  2. stdlib
  3. third-party (`httpx`, `bs4`, `fastapi`, `pydantic`, etc.)
  4. local/relative (`.config`, `..repo`, etc.)
- **Blank lines**: 2 between top-level defs, 1 inside functions
- **Docstrings**: Block comment style with `──` borders and SOLID/GRASP notes at top of every module

---

## Test Commands

**No test suite found** (`pytest`, `unittest`). To run a single test once added:

```bash
# Single test file
pytest tests/test_news_repo.py -v

# Single test function
pytest tests/test_news_repo.py::TestFileNewsRepository::test_load_news -v

# Single test by name
pytest -k "test_load_news" -v
```

When adding tests, place them in `backend/tests/` with `conftest.py` for fixtures.

---

## Code Style Guidelines

### Python

- **Type hints**: Required on all function signatures (return type `-> None`, etc.)
- **Literal types**: Use `Literal["politics", "economy", ...]` for enums (see `schemas/news_schema.py`)
- **Protocol classes**: Use `Protocol` for dependency-injection ports (e.g., `NewsRepositoryPort`)
- **Private attrs**: Prefix with `_` (e.g., `self._repo`, `self._emit`)
- **Docstrings**: Every class and public method. Block-comment style with header border.
- **Error handling**: Swallow at boundary (e.g., `except Exception: return default`) in IO/repo helpers; raise `HTTPException` in routers.
- **Async**: Use `asyncio.to_thread()` for sync blocking calls (Playwright, LLM). Never block the event loop.
- **Imports**: Never import at module top-level inside async functions if avoidable (lazy import pattern used in `scraper_service.py`).
- **Config**: Use `backend/config.py` `Settings` class. Never hardcode paths or secrets.
- **Strategy pattern**: Use for extensible fetchers/parsers (see `core/fetcher_service.py`).
- **File paths**: Always use `pathlib.Path`, never string concatenation.

### JavaScript (Frontend)

- **Modules**: ES Modules (`import`/`export`), no CommonJS
- **State**: Module-level variables (no framework state management)
- **DOM**: All DOM work in `UI.js`. Business logic in `main.js`. API in `api.js`. Config in `config.js`.
- **Naming**: camelCase for variables/functions, UPPER_SNAKE for constants
- **Exposing callbacks**: Use `window.__<name>` pattern for HTML `onclick` attributes
- **Error handling**: `try/catch` with `UI.showGridError(e.message)` or `console.warn`

### CSS

- **Variables**: CSS custom properties for theming (see `:root` in `app.css`)
- **Naming**: kebab-case class names
- **Units**: `rem` for typography/spacing, `px` for borders and fine-grained sizing

---

## Architecture Notes

### Backend Layers

```
routers/       → FastAPI endpoints (SOLID I: one concern per router)
services/      → Business logic (scraper, summarizer, classifier)
scrapers/      → Source-specific fetchers with @register_source decorator
repo/          → Data persistence (JSON files, NewsRepositoryPort protocol)
core/          → Shared utilities (browser, socket, constants, fetcher strategy)
schemas/       → Pydantic models (request/response/internal separated)
config.py      → Settings injection (no singletons except `settings` global)
```

### Adding a New News Source

1. Add scraper function to `backend/scrapers/sources.py`
2. Decorate with `@register_source("Name", "https://...", "#color")`
3. No other files need changing (SOLID O)

### Adding a New Category

1. Add keywords to `_RULES` dict in `backend/services/classifier_service.py`
2. Sync the `CATEGORIES` array in `frontend/static/config.js`
3. Add to `VALID_CATEGORIES` in `backend/routers/news_router.py`

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

## File Patterns

| Pattern | Meaning |
|---|---|
| `backend/core/*.py` | Shared infrastructure |
| `backend/scrapers/sources.py` | Source scrapers (add new ones here) |
| `backend/scrapers/helpers.py` | HTML parsing utilities |
| `backend/scrapers/registry.py` | Source registration |
| `backend/services/*.py` | Business logic services |
| `backend/repo/news_repo.py` | Persistence layer |
| `backend/schemas/*.py` | Pydantic models |
| `backend/routers/*.py` | FastAPI route handlers |
| `frontend/static/*.js` | JS modules (main, api, UI, config) |
| `frontend/static/app.css` | All styles |
| `frontend/index.html` | Single HTML page |

---

## Common Pitfalls

- **Don't** call `settings` or repo in module-level scope outside `config.py` — use lazy imports inside functions to avoid circular imports
- **Don't** use `print()` for user-facing errors — log and return appropriate HTTP status
- **Do** use `from __future__ import annotations` in every `.py` file for forward-ref compatibility
- **Do** use `pathlib.Path` for all file paths (cross-platform)
