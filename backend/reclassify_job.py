from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
import trafilatura

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import settings
from backend.core.constants import BROWSER_HEADERS
from backend.services.classifier_service import classify_article

async def process_article(client: httpx.AsyncClient, sem: asyncio.Semaphore, item: dict) -> bool:
    url = item.get("url", "")
    title = (item.get("title") or "").strip()
    summary = (item.get("summary") or "").strip()
    
    if not url or not url.startswith("http"):
        # Fallback to just summary if no valid URL
        cat, method = classify_article(title, summary, url=url)
        item["category"] = cat
        item["classification_method"] = method
        return True

    async with sem:
        try:
            resp = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=10)
            md = trafilatura.extract(resp.text)
            content_to_classify = md if md else summary
        except Exception:
            content_to_classify = summary

    cat, method = classify_article(title, content_to_classify, url=url)
    item["category"] = cat
    item["classification_method"] = method
    return True

async def amain():
    if not settings.data_file.exists():
        print(f"No file found at {settings.data_file}")
        return

    with open(settings.data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    news = data.get("articles", [])
    if not news:
        print("No articles found in data file")
        return

    print("=== Categories Before ===")
    before_counts = {}
    for item in news:
        c = item.get("category", "unknown")
        if isinstance(c, list): c = ", ".join(c)
        elif not isinstance(c, str): c = str(c)
        before_counts[c] = before_counts.get(c, 0) + 1
    for k, v in before_counts.items():
        print(f"{k}: {v}")

    print("\n[⏳] Fetching full text and Re-classifying... (This may take a minute)")
    sem = asyncio.Semaphore(5) # limit concurrency
    async with httpx.AsyncClient() as client:
        tasks = [process_article(client, sem, item) for item in news]
        await asyncio.gather(*tasks)

    print("\n=== Categories After ===")
    after_counts = {}
    for item in news:
        c = item.get("category", "unknown")
        if isinstance(c, list): c = ", ".join(c)
        elif not isinstance(c, str): c = str(c)
        after_counts[c] = after_counts.get(c, 0) + 1
    for k, v in after_counts.items():
        print(f"{k}: {v}")
    
    # Update data and save
    data["articles"] = news
    data["metadata"]["last_updated"] = datetime.now().isoformat()
    data["metadata"]["total_articles"] = len(news)
    
    with open(settings.data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Re-classified and saved {len(news)} articles successfully to {settings.data_file.name}")

def main():
    asyncio.run(amain())

if __name__ == '__main__':
    main()
