import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import asyncio
import httpx
import trafilatura
from config import settings
from services.classifier_service import classify_article
from core.constants import BROWSER_HEADERS

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
    if not settings.output_file.exists():
        print(f"No file found at {settings.output_file}")
        return

    with open(settings.output_file, 'r', encoding='utf-8') as f:
        news = json.load(f)

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
    
    with open(settings.output_file, 'w', encoding='utf-8') as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Re-classified and saved {len(news)} articles successfully to {settings.output_file.name}")

def main():
    asyncio.run(amain())

if __name__ == '__main__':
    main()
