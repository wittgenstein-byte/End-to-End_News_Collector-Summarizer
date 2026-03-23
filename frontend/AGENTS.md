# AGENTS.md — Frontend (frontend/)

## Project Overview

- **Stack**: Vanilla JavaScript ES Modules + Tailwind CSS 3.4 + PostCSS
- **Build**: No bundler (pure CSS output via Tailwind CLI/PostCSS)
- **Serving**: FastAPI serves static files from `frontend/static/` at `/frontend/`
- **Entry**: `frontend/index.html` loads `main.js` as ES module

---

## Build / Run

```bash
# Install dependencies (from repo root)
cd frontend
npm install

# Build CSS (Tailwind → app.css)
npx tailwindcss -i ./static/tailwind-input.css -o ./static/app.css --watch

# Or build once (no watch)
npx tailwindcss -i ./static/tailwind-input.css -o ./static/app.css --minify
```

### Development Workflow

```bash
# Terminal 1: Build CSS with watch
npx tailwindcss -i ./static/tailwind-input.css -o ./static/app.css --watch

# Terminal 2: Run backend (from repo root)
python backend/main.py

# Open http://localhost:5000
```

---

## Test Commands

**No test suite found.** `npm test` currently errors out.

To add tests, install a framework and place files in `frontend/tests/`:

```bash
# Example with Vitest
npm install -D vitest

# Run single test file
npx vitest run tests/api.test.js

# Run single test
npx vitest run tests/api.test.js --testNamePattern="fetchNews"
```

---

## Lint / Type Check

**No linter configured** (no ESLint, Prettier, or TypeScript).

Run manually if installed:
```bash
# ESLint (if present)
npx eslint static/

# Prettier (if present)
npx prettier --check static/
```

---

## Code Style Guidelines

### JavaScript

- **Modules**: ES Modules only (`import`/`export`). Never CommonJS (`require`).
- **State**: Module-level variables only. No framework state management.
- **Naming**:
  - Variables/functions: `camelCase`
  - Constants: `UPPER_SNAKE_CASE`
  - CSS classes: `kebab-case`
- **DOM work**: All DOM manipulation in `UI.js`. Never touch DOM from `main.js` or `api.js`.
- **Business logic**: In `main.js` (orchestrator). Never fetch from `main.js`.
- **API layer**: In `api.js`. Never touch DOM or state from `api.js`.
- **Config**: In `config.js`. Centralize all constants here.
- **Exposing callbacks**: Use `window.__<name>` pattern for HTML `onclick` attributes.
  ```js
  // In main.js
  window.__loadPage = loadPage;
  window.__summarize = handleSummarize;
  ```
- **Error handling**: Always use `try/catch`. On failure, call `UI.showGridError(e.message)` or `console.warn`.
- **JSDoc comments**: Use for functions with complex parameters. Keep simple functions self-documenting.
- **Module structure**:
  ```
  static/
  ├── main.js    — Orchestrator (connects api.js ↔ ui.js)
  ├── api.js     — HTTP + WebSocket layer
  ├── UI.js      — DOM rendering and manipulation
  ├── config.js  — Constants and configuration
  ├── app.css    — Compiled Tailwind CSS (do not edit)
  └── tailwind-input.css — Tailwind source (edit this instead)
  ```

### CSS / Tailwind

- **Primary file**: Edit `tailwind-input.css`, not `app.css`. Run build to generate `app.css`.
- **Custom classes**: Use Tailwind utility classes. Only add custom CSS for animations/keyframes in `tailwind-input.css`.
- **Colors**: Use custom theme colors defined in `tailwind.config.js`:
  - `primary`, `surface`, `on-surface`, `error`, `outline`, `outline-variant`
- **Fonts**: Use Tailwind's `font-headline` (Newsreader serif) and `font-body` (Manrope sans).
- **Custom animations**: Add to `tailwind.config.js` `animation`/`keyframes` section.
- **Custom keyframes**: In `tailwind-input.css` for one-off animations, or in config for reusable ones.

### HTML

- **Language**: Set `lang="th"` for Thai content.
- **Scripts**: Use `type="module"` for main script.
- **Event handlers**: Call `window.__<name>` functions, not inline anonymous functions.
- **Responsive**: Use Tailwind responsive prefixes (`sm:`, `md:`, `lg:`, `xl:`).
- **Accessibility**: Use semantic HTML, `aria-*` attributes where needed.

---

## Adding a New Feature

### New API Endpoint

1. Add function to `static/api.js`:
   ```js
   export async function fetchNewEndpoint(param) {
     const res = await fetch(`${API_BASE}/api/new-endpoint`);
     if (!res.ok) throw new Error(`HTTP ${res.status}`);
     return res.json();
   }
   ```

2. Import and use in `static/main.js`

### New UI Component

1. Add rendering function to `static/UI.js`:
   ```js
   export function renderNewComponent(data) {
     const el = document.getElementById("container");
     el.innerHTML = /* HTML template */;
   }
   ```

2. Call from `static/main.js` when data is ready

### New Category

1. Add to `CATEGORIES` array in `static/config.js`
2. Sync with backend: Add keywords to `_RULES` in `backend/services/classifier_service.py`
3. Add to `VALID_CATEGORIES` in `backend/routers/news_router.py`

### New News Source

1. Add filter button to `index.html` `#source-filters` div
2. Add source color to `SOURCE_COLORS` in `config.js`
3. Update backend scraper in `backend/scrapers/sources.py` with `@register_source` decorator

---

## Common Pitfalls

- **Don't** edit `app.css` directly — it will be overwritten on next Tailwind build
- **Don't** add DOM manipulation to `api.js` — keep layers separated
- **Don't** use `onclick="someFn()"` — use `window.__someFn` pattern
- **Do** always escape user content with `UI.esc()` before inserting into HTML
- **Do** use Tailwind responsive prefixes for mobile-first design
- **Do** handle errors gracefully with `try/catch` and user feedback

---

## File Reference

| File | Purpose |
|------|---------|
| `static/main.js` | App controller, orchestrates API ↔ UI |
| `static/api.js` | HTTP client, WebSocket setup |
| `static/UI.js` | All DOM rendering functions |
| `static/config.js` | Constants, API_BASE, CATEGORIES, SOURCE_COLORS |
| `static/app.css` | Compiled Tailwind (generated, do not edit) |
| `static/tailwind-input.css` | Tailwind source file (edit this) |
| `tailwind.config.js` | Tailwind theme config (colors, fonts, animations) |
| `index.html` | Single HTML page with modal, toast, pagination slots |
