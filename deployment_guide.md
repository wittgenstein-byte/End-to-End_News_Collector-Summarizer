# Deployment Guide - News Collector & Summarizer

## Overview
This project runs as:

- FastAPI + Socket.IO backend
- Static frontend served by FastAPI
- A separate Playwright scraping service

For production deployment, `docker compose` is the recommended approach because the backend depends on the Playwright service for readiness and for scraping some sites reliably.

## Required Environment Variables

- `LLM_API`: API key for the summarizer
- `LLM_BASE_URL`: Optional, defaults to `https://gen.ai.kku.ac.th/api/v1`
- `LLM_MODEL`: Optional, defaults to `gemini-3.1-flash-lite-preview`
- `PLAYWRIGHT_SERVICE_URL`: URL of the Playwright scraping service

Important:

- For Docker Compose, use `http://playwright:8001/scrape`
- For local/manual run, use `http://localhost:8001/scrape`
- For Railway, use the internal Playwright service URL provided by Railway, ending with `/scrape`

## Option 1: Docker Compose Deployment (Recommended)

### 1. Prepare environment file
Create `backend/.env` from `backend/.env.example` and make sure it contains:

```env
LLM_API=your_api_key_here
PLAYWRIGHT_SERVICE_URL=http://playwright:8001/scrape
```

You may also add:

```env
LLM_BASE_URL=https://gen.ai.kku.ac.th/api/v1
LLM_MODEL=gemini-3.1-flash-lite-preview
PORT=5000
HOST=0.0.0.0
```

### 2. Build and start services
```bash
docker compose up -d --build
```

This starts:

- `app`: FastAPI + Socket.IO application on port `5000`
- `playwright`: internal Playwright service on port `8001`

### 3. Verify deployment
Open:

- `http://your-server-ip:5000/`
- `http://your-server-ip:5000/livez`
- `http://your-server-ip:5000/readyz`

`/readyz` should return HTTP `200` with `status: "ready"`.

### 4. Stop services
```bash
docker compose down
```

## Option 2: Manual Deployment

Use this only if you also run a Playwright service separately.

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment
Create `.env` at the project root or `backend/.env`:

```env
LLM_API=your_api_key_here
PLAYWRIGHT_SERVICE_URL=http://localhost:8001/scrape
```

### 3. Run the backend
Development mode:

```bash
python backend/main.py
```

Production mode:

```bash
gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5000 backend.main:app_asgi --workers 1 --timeout 120
```

### 4. Verify
Open:

- `http://localhost:5000/`
- `http://localhost:5000/livez`
- `http://localhost:5000/readyz`

If `/readyz` returns `503`, the Playwright service is not reachable or storage is not writable.

## Option 3: Railway Deployment

Railway deployment should use 2 separate services from the same repository:

- `news-backend`
- `playwright-service`

Do not use the Docker Compose hostname `http://playwright:8001/scrape` on Railway. That hostname only works inside Docker Compose.

### 1. Create the Playwright service
Create a Railway service that uses:

- Root directory: `playwright-service`
- Dockerfile: `playwright-service/Dockerfile`

Railway env for Playwright:

```env
PORT=${{PORT}}
```

Notes:

- Railway injects its own `PORT`
- The Dockerfile is now compatible with dynamic ports
- The public or internal service URL must be copied after deployment

### 2. Create the backend service
Create another Railway service that uses:

- Root directory: repository root
- Dockerfile: `Dockerfile`

Set these environment variables on the backend service:

```env
LLM_API=your_api_key_here
LLM_BASE_URL=https://gen.ai.kku.ac.th/api/v1
LLM_MODEL=gemini-3.1-flash-lite-preview
HOST=0.0.0.0
PORT=${{PORT}}
PLAYWRIGHT_SERVICE_URL=https://<your-playwright-service-domain>/scrape
```

If Railway provides a private internal domain for service-to-service traffic, prefer that internal URL for `PLAYWRIGHT_SERVICE_URL`.

### 3. Add persistent storage to backend
The backend writes runtime data to:

- `data/news_data.json`
- `data/collected_md/`

If you want data to survive redeploys or restarts, attach a Railway volume to the backend service and mount it so the app's `/app/data` directory persists.

### 4. Verify Railway deployment
After both services are up:

- Open the backend public URL
- Check `/livez`
- Check `/readyz`

Expected result:

- `/livez` returns HTTP `200`
- `/readyz` returns HTTP `200`
- `PLAYWRIGHT_SERVICE_URL` resolves to the deployed Playwright service

### 5. Railway env summary

Backend service:

```env
LLM_API=your_api_key_here
LLM_BASE_URL=https://gen.ai.kku.ac.th/api/v1
LLM_MODEL=gemini-3.1-flash-lite-preview
HOST=0.0.0.0
PORT=${{PORT}}
PLAYWRIGHT_SERVICE_URL=https://<your-playwright-service-domain>/scrape
INTERVAL_MINUTES=15
MAX_ARTICLES_PER_SOURCE=10
SUMMARY_SENTENCES=3
PAGE_SIZE=20
```

Playwright service:

```env
PORT=${{PORT}}
```

## Data Storage
Runtime data is stored under the `data/` directory:

- `data/news_data.json`
- `data/collected_md/`

With Docker Compose, persistent data is stored in the named volume `app-data`, mounted to `/app/data`.

## Usage After Deploy

- Open the web UI at `/`
- Read paginated news from `/api/news`
- Check source counts from `/api/sources`
- Check category counts from `/api/categories`
- Check service status from `/api/status`
- Summarize an article with `POST /api/collect-md`

Example:

```bash
curl "http://localhost:5000/api/news?page=1"
```

```bash
curl -X POST "http://localhost:5000/api/collect-md" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example.com/article\"}"
```

## Notes

- The frontend is served by the same FastAPI app, so no separate frontend server is required.
- Socket.IO is exposed through the same application server.
- The background scraper starts automatically with the backend lifespan.
- Default scrape interval is controlled by `INTERVAL_MINUTES` and defaults to `15`.
