# Original User Request

## Follow-up — 2026-08-22T15:58:30Z

This is a single self-contained fix; keep it small and focused.

Refactor the News Collector and Summarizer web application into a secure Progressive Web App (PWA) architecture featuring a Snippet Preview sub-view, copyright-safe local asset caching (strictly avoiding unauthorized caching/copying of third-party images), on-demand AI summarization, and clean external link launching.

Working directory: c:\Users\narawit\dev\End-to-End_News_Collector-Summarizer
Integrity mode: development

## Requirements

### R1. PWA Standalone & Service Worker
- Implement PWA standalone web application capabilities with Web App Manifest (`frontend/manifest.webmanifest`), icons, install prompt banner/button, and an offline status indicator.
- Service Worker (`frontend/sw.js`) pre-caches the application shell and UI assets. Network-first with cache-fallback for API responses. FastAPI backend serves `/sw.js` and `/manifest.webmanifest` with appropriate headers and root scope.

### R2. Copyright-Safe Image & Local Placeholder Architecture
- Strictly avoid caching, storing, or server-side copying/proxying of third-party copyrighted news photos in the Cache API or backend.
- Provide local categorized SVG placeholder images (e.g. politics, technology, economy, world, default) in `frontend/static/icons/` for offline display and missing thumbnails.

### R3. Snippet Preview Sub-View Navigation
- Implement Single Page App (SPA) hash routing (`#/`, `#/preview/{id}`, `#/history`) allowing seamless navigation between news feed and full-page article preview with scroll restoration and smooth back navigation.
- Preview screen displays thumbnail/placeholder, title, metadata, short 2-3 line excerpt, and action triggers.

### R4. On-Demand AI Summarization & Reading State Management
- "สรุปเนื้อหาด้วย AI" button triggers on-demand AI synthesis (takeaways, sentiment, keywords) and caches results in client storage (IndexedDB/LocalStorage).
- Auto-record viewed articles to local reading history and support bookmarking for offline reading.

### R5. Clean & Secure External Link Launching
- Prominent "อ่านข่าวฉบับเต็ม" button opens the original news source in a new browser window/tab using `target="_blank" rel="noopener noreferrer"` with automated tracking parameters (e.g. `utm_*`, `fbclid`, `gclid`) stripped for user privacy.

## Verification Resources
- Python lint & type checks: `uv run ruff check backend/` and `uv run mypy backend/`
- Backend test suite: `uv run pytest backend/tests/ -v`

## Acceptance Criteria

### PWA & Offline Functionality
- [ ] Application registers service worker and can be installed as a standalone PWA.
- [ ] Core app shell and previously fetched news feed load seamlessly when network is offline.
- [ ] Third-party images are not stored in Cache API; category SVG placeholders render when offline.

### Navigation & UX
- [ ] Clicking an article opens the Preview sub-view (`#/preview/...`) and back button restores feed position.
- [ ] Snippet preview displays 2-3 line excerpt, metadata, and all action buttons.

### AI & External Links
- [ ] On-demand AI summary executes on user click and caches result locally.
- [ ] External link opener strips tracking query parameters and launches with secure opener attributes (`rel="noopener noreferrer"`).

## Follow-up — 2026-10-09T09:58:44Z

Refactor the News Collector & Summarizer's trending pipeline into a two-layer architecture: a persistent **Story Identification** layer that answers "do these articles report the same real-world event?" and a separate **Trending** layer that ranks those stories by "which identified events are gaining coverage right now in the system's news feed?". Today a single 36–48h clustering pass in `backend/services/trending_service.py` does both jobs, so long-running stories (trials, floods, negotiations) get split once they pass 48h, and velocity / resurgence cannot be measured. Purpose: production feature of the existing app.

Working directory: c:\Users\narawit\dev\End-to-End_News_Collector-Summarizer
Integrity mode: development

Project conventions are in `AGENTS.md` at the repo root (Python 3.10+, FastAPI, `uv`, `from __future__ import annotations`, `pathlib`, type hints, `settings` from `backend/config.py`, Protocol-based repository ports, tests in `backend/tests/`). Follow them. The repo also has a graphify knowledge graph in `graphify-out/` (use `graphify query "<question>"` for codebase questions; run `graphify update .` after code changes).

Reference material:
- Story identification vs. topic modeling, online story assignment: arXiv story identification literature
- Event context / timeline of event development, precision/recall/F-measure for event clustering: https://www.mdpi.com/2076-3417/13/9/5510
- Hot-news topic dimensions (volume, diversity, velocity): https://link.springer.com/article/10.1007/s44163-026-01657-7

## Requirements

### R1. Story Identification layer (persistent, online)
Each incoming article is assigned to an existing story or starts a new one, as articles arrive (online/incremental — not a full re-cluster of all news on each request). The user has specified these design constraints:
- Semantic similarity from an embedding of the title combined with the summary or first substantive paragraph is the primary signal.
- Named entities (people, organizations, places) extracted from the article are a supporting/confirmation signal.
- Publication time (fall back to fetch time if absent) is used for temporal consistency. A short time window may be used to find *candidate* stories, but must NOT cap a story's lifetime: a story that keeps receiving related articles must remain the same story across multiple days.
- `category` may narrow the search or act as a soft signal but must NOT be a hard barrier — the same event filed under different categories must be mergeable.
- When an article does not confidently match an existing story, it starts a new story instead of being force-merged.
- No Jaccard / token-overlap of article text as a similarity measure (entity agreement as a confirmation signal is allowed).
- Stories persist across server restarts on both storage backends the app already supports (local JSON and MongoDB), and each article can be traced to its story id. Existing article data must remain readable; existing articles must be back-fillable into stories via a one-off job.
- Stories carry their own lifecycle state (e.g. active vs. dormant) that is separate from membership.

### R2. Trending layer (ranking over stories, deterministic)
A separate component ranks story clusters (not individual articles) using deterministic, statistics-based scoring — no LLM in the scoring path. Signals to include: recent volume and velocity/burst (rate of new articles vs. the preceding period); number of distinct outlets reporting, with reduced credit for duplicate / syndicated copies of the same original; recency of the story's latest coverage; novelty relative to other tracked stories; and reader engagement from the existing engagement repository. Weights must be configurable via `Settings`. Only stories that are currently active/eligible are ranked. Routine/recurring reports (e.g. lottery results, weather forecasts) must not be inflated into top trending stories. The response must expose the per-signal score breakdown so ranking is explainable.

User-suggested starting points (non-binding; tune against the evaluation set): story stays active if it received a new article within ~72h, otherwise dormant; centroid updated incrementally (e.g. EMA); two-band assignment — high similarity merges directly, borderline similarity merges only with entity agreement, below that starts a new story; article schema change limited to adding an optional `story_id`; embed title + first paragraph / existing brief summary rather than full text.

### R3. Story presentation via LLM (naming & summarizing only)
For top-ranked stories, the LLM generates a story headline and a synthesized summary / timeline of key developments from a representative subset of the story's articles, with citations back to the source articles. The LLM never decides membership or trending rank. Generated metadata should be cached so it isn't regenerated unnecessarily. Real LLM API calls are permitted (key in `backend/.env` as `LLM_API`), but the app and all tests must still work when the LLM is unavailable (graceful fallback).

### R4. API + Frontend
Expose stories and trending stories through the FastAPI backend (story list, story detail with all member articles in chronological order, trending stories with score breakdown). Existing trending consumers must keep working (backward compatible, or updated in the same change). Update the vanilla-JS frontend so users can see trending stories with headline, summary, timeline of developments, source list with links, and the score breakdown. The UI must state the limitation that "trending" reflects how widely and frequently the collected outlets are covering a story, not verified public interest (beyond the engagement signal).

### R5. Evaluation harness
Build a labeled evaluation set from real articles already in the system (>=100 articles, containing multiple multi-article stories including at least some that span >48h and/or cross categories), where ground truth says which articles report the same event. Labels must be reviewed by an agent independent from the one that implemented the clustering. Provide a reproducible evaluation script that reports pairwise precision/recall/F1 and B-cubed precision/recall/F1, plus counts of false merges and false splits, for both the new Story layer and the current `SemanticClusterer` baseline on the same set. Provide a trending sanity report for the top-N stories (distinct-source count per story, flagging any top story whose coverage is a single origin).

## Acceptance Criteria

### Story Identification
- [ ] Evaluation script runs with one command (documented) and writes a results file.
- [ ] New Story layer achieves B-cubed precision >= 0.85 and B-cubed F1 >= 0.75 on the labeled set, and B-cubed F1 strictly higher than the current `SemanticClusterer` baseline on the same set.
- [ ] Automated test: articles about one event spread over >= 5 days (each new article within the candidate window of the previous) end up in a single story.
- [ ] Automated test: two articles about the same event with different `category` values are merged; two unrelated articles in the same category with similar wording are not.
- [ ] Automated test: an article with no confident match creates a new story (no forced merge).
- [ ] Automated test: stories survive a repository reload (restart) on the JSON backend; MongoDB repository has tests (mocked or `mongomock`) covering the same contract.
- [ ] Back-fill job runs on the existing `backend/data` news and assigns every article a story id.

### Trending
- [ ] Automated test: scoring is deterministic — identical input produces identical ranking and scores across runs, with no LLM call in the scoring path.
- [ ] Automated test: a story covered by 3 distinct outlets outranks an otherwise-equivalent story with 3 articles from one outlet.
- [ ] Automated test: a story with a recent burst outranks an otherwise-equivalent story with the same total volume spread evenly over older time.
- [ ] Automated test: dormant stories are not ranked; a dormant story that receives new articles becomes eligible again under the same story id.
- [ ] Trending sanity report generated on real data; top-5 stories each show their distinct-source count.

### LLM presentation & API/UI
- [ ] Automated test: with the LLM unavailable, story and trending endpoints still return 200 with fallback headline/summary.
- [ ] At least one recorded run with the real LLM produces a Thai headline + summary with citations for a real top story (output saved in the repo's evaluation output).
- [ ] API tests (FastAPI `TestClient`) cover story list, story detail (chronological members), and trending-stories endpoints, including score breakdown fields.
- [ ] Frontend: server starts with `uv run python backend/main.py`, and an independent agent verifies via browser screenshot that the trending-stories view shows headline, summary, timeline, source links, score breakdown, and the coverage-vs-interest disclaimer.

### Code quality
- [ ] `uv run pytest backend/tests` passes (all pre-existing tests still pass, or are updated with justification where behavior intentionally changed).
- [ ] `uv run ruff check backend/` and `uv run mypy backend/` report no new errors compared with the pre-change baseline.
- [ ] `graphify update .` run after code changes.
- [ ] A short design doc in the repo explains the two layers, data model, thresholds/weights and how they were tuned, evaluation results, and known limitations.

## Follow-up — 2026-10-09T10:45:19Z

pause ก่อน
