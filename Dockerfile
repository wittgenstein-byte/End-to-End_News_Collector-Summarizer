# Stage 1: Build frontend assets
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npx tailwindcss -i static/tailwind-input.css -o static/app.css --minify

# Stage 2: Base image with Python
FROM python:3.11-slim

# Set working directory
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only runtime files
COPY backend/ ./backend/
COPY frontend/index.html ./frontend/index.html
COPY frontend/static/ ./frontend/static/
RUN mkdir -p /app/data/collected_md

# Overwrite css with built css
COPY --from=frontend-builder /app/frontend/static/app.css ./frontend/static/app.css

# Environment variables (Defaults - can be overridden at runtime)
ENV PORT=5000
ENV HOST=0.0.0.0
ENV LLM_BASE_URL=https://gen.ai.kku.ac.th/api/v1
ENV LLM_MODEL=gemini-3.1-flash-lite-preview

# Expose the default port (runtime may override with PORT env)
EXPOSE 5000

# Run the application with Gunicorn for production
# Using uvicorn.workers.UvicornWorker for ASGI support (FastAPI + Socket.IO)
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-5000} backend.main:app_asgi --workers 1 --timeout 120"]
