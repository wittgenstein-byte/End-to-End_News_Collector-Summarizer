# syntax=docker/dockerfile:1.7

# Stage 1: Build frontend assets
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx tailwindcss -i static/tailwind-input.css -o static/app.css --minify


# Stage 2: Production Python runtime
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Python & uv build optimizations + 2-vCPU thread & glibc memory tuning for AWS EC2
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    MALLOC_TRIM_THRESHOLD_=65536

# Copy project dependencies and install CPU-only PyTorch + packages
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Copy runtime files (heavy model weights are excluded via .dockerignore and mounted at runtime)
COPY backend/ ./backend/
COPY frontend/index.html frontend/monitoring.html frontend/issues.html frontend/manifest.webmanifest frontend/sw.js ./frontend/
COPY frontend/static/ ./frontend/static/
COPY --from=frontend-builder /app/frontend/static/app.css ./frontend/static/app.css

RUN mkdir -p /app/data/collected_md

# Runtime defaults (overridden by .env / docker-compose environment)
ENV PORT=5000 \
    HOST=0.0.0.0 \
    DB_TYPE=sqlite

EXPOSE 5000

# Run with Gunicorn + UvicornWorker (1 worker to keep Socket.IO & in-memory L1 cache unified)
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-5000} backend.main:app_asgi --workers 1 --timeout 120 --graceful-timeout 30 --keep-alive 5"]

