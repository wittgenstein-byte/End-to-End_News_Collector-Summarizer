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
uv sync
uv run playwright install chromium
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
uv run python backend/main.py
```

Production mode:

```bash
uv run gunicorn -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:5000 backend.main:app_asgi --workers 1 --timeout 120
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

---

## Option 4: AWS EC2 + S3 Deployment (Recommended: `c7i-flex.large`)

### 1. Architecture Overview
- **EC2 Instance (`c7i-flex.large`)**: 2 vCPU, 4GB RAM — เหมาะสำหรับรัน FastAPI, Playwright (Chromium) และ WangchanBERTa Transformer ในตัว พร้อมตั้ง Swap 4GB ป้องกัน OOM
- **AWS S3**: เก็บไฟล์ Model (`/models/`) และระบบสำรองข้อมูลอัตโนมัติ (`/backups/data/`)
- **IAM Role**: เชื่อมต่อ EC2 กับ S3 ได้อย่างปลอดภัยโดยไม่ต้องระบุ Credentials ในไฟล์ `.env`

### 2. AWS Setup
1. **S3 Bucket**: สร้าง Bucket เช่น `news-collector-storage-prod`
2. **Upload Models ขึ้น S3**:
   ```bash
   aws s3 sync ./backend/model s3://news-collector-storage-prod/models/
   ```
3. **IAM Role**: สร้าง Role ที่มีสิทธิ์อ่าน/เขียน S3 Bucket และ Attach เข้ากับ EC2 Instance

### 3. Server Setup (`c7i-flex.large`)
```bash
# 1. Setup Swap Memory 4GB (Safety Buffer สำหรับ WangchanBERTa + Chromium)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. Update และติดตั้ง Docker, Compose, AWS CLI, Nginx, Certbot
sudo apt-get update && sudo apt-get upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
sudo apt-get install -y docker-compose-plugin awscli nginx certbot python3-certbot-nginx

# 3. Clone repo & ดึง Model (รวม WangchanBERTa) จาก S3
git clone <YOUR_REPO_URL> /home/ubuntu/app
cd /home/ubuntu/app
mkdir -p backend/model
aws s3 sync s3://news-collector-storage-prod/models/ ./backend/model/

# 4. ตั้งค่า backend/.env
cp backend/.env.example backend/.env
# ปรับ LLM_API, LLM_BASE_URL, LLM_MODEL, PLAYWRIGHT_SERVICE_URL=http://playwright:8001/scrape

# 5. สตาร์ทเซอร์วิส
docker compose up -d --build
```

### 4. Nginx Reverse Proxy & SSL Configuration
Create `/etc/nginx/sites-available/news-collector`:
```nginx
server {
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```
Enable site and get SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/news-collector /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
sudo certbot --nginx -d yourdomain.com
```

### 5. Automated Data Backup to S3
Add daily cron job (`crontab -e`):
```cron
0 0 * * * aws s3 sync /home/ubuntu/app/data/ s3://news-collector-storage-prod/backups/data/ --delete
```

