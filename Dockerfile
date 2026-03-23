# Stage 1: Build frontend assets
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/tailwind.config.js frontend/postcss.config.js* ./
COPY frontend/static/ ./static/
RUN npx tailwindcss -i static/tailwind-input.css -o static/app.css --minify

# Stage 2: Base image with Python
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Overwrite css with built css
COPY --from=frontend-builder /app/frontend/static/app.css ./frontend/static/app.css

# Environment variables (Defaults - can be overridden at runtime)
ENV PORT=5000
ENV HOST=0.0.0.0
ENV LLM_BASE_URL=https://gen.ai.kku.ac.th/api/v1
ENV LLM_MODEL=gemini-3.1-flash-lite-preview

# Expose the port
EXPOSE 5000

# Run the application with Gunicorn for production
# Using uvicorn.workers.UvicornWorker for ASGI support (FastAPI + Socket.IO)
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:5000", "backend.main:app_asgi", "--workers", "1", "--timeout", "120"]
