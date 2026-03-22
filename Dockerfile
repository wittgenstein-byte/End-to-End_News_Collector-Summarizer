# Step 1: Base image with Python and Playwright dependencies
FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium only (to keep image size smaller)
RUN playwright install chromium

# Copy project files
COPY . .

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
