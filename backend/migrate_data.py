"""
Migration script to transform old JSON files to new unified schema
─────────────────────────────────────────────────────────────────
Usage: python backend/migrate_data.py
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List


def load_old_data(data_dir: Path) -> tuple[List[Dict], List[str], Dict[str, int]]:
    """Load data from old JSON files"""
    # Load articles
    news_file = data_dir / "news_output.json"
    articles = []
    if news_file.exists():
        with open(news_file, 'r', encoding='utf-8') as f:
            articles = json.load(f)

    # Load seen URLs
    seen_file = data_dir / "seen_urls.json"
    seen_urls = []
    if seen_file.exists():
        with open(seen_file, 'r', encoding='utf-8') as f:
            seen_urls = json.load(f)

    # Load site registry
    registry_file = data_dir / "site_registry.json"
    site_registry = {}
    if registry_file.exists():
        with open(registry_file, 'r', encoding='utf-8') as f:
            site_registry = json.load(f)

    return articles, seen_urls, site_registry


def load_markdown_content(data_dir: Path, articles: List[Dict]) -> Dict[str, str]:
    """Load markdown content from collected_md directory"""
    md_dir = data_dir / "collected_md"
    content_map = {}

    if not md_dir.exists():
        return content_map

    for md_file in md_dir.glob("*.md"):
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Try to match by filename (rough heuristic)
                filename = md_file.stem
                # Extract date and title from filename
                parts = filename.split('_', 2)
                if len(parts) >= 3:
                    date_str, time_str, title_slug = parts
                    # Store content keyed by title_slug for matching
                    content_map[title_slug.lower().replace('-', ' ')] = content
        except Exception as e:
            print(f"Error reading {md_file}: {e}")

    return content_map


def transform_articles(articles: List[Dict], content_map: Dict[str, str], site_registry: Dict[str, int]) -> List[Dict]:
    """Transform articles to new schema"""
    transformed = []

    for article in articles:
        # Generate UUID if not present
        article_id = str(uuid.uuid4())

        # Extract domain from URL for source matching
        url = article.get('url', '')
        domain = ''
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
            except:
                pass

        # Get content from markdown if available
        content = ''
        title = article.get('title', '').lower()
        # Try to find matching content
        for slug, md_content in content_map.items():
            if slug in title or title in slug:
                content = md_content
                break

        # If no markdown found, use summary as content
        if not content:
            content = article.get('summary', '')

        transformed_article = {
            "id": article_id,
            "title": article.get('title', ''),
            "summary": article.get('summary', ''),
            "content": content,
            "source": article.get('source', ''),
            "url": url,
            "image_url": article.get('image_url', ''),
            "fetched_at": article.get('fetched_at', ''),
            "category": article.get('category', ''),
            "classification_method": article.get('classification_method', ''),
            "tags": [],  # Can be populated later
            "read_count": 0
        }
        transformed.append(transformed_article)

    return transformed


def transform_sources(site_registry: Dict[str, int]) -> Dict[str, Dict]:
    """Transform site registry to sources"""
    sources = {}
    for domain, priority in site_registry.items():
        # Skip metadata keys (those with __)
        if '__' in domain:
            continue
        # Skip non-integer priorities (metadata)
        if not isinstance(priority, int):
            continue
        sources[domain] = {
            "name": domain.split('.')[0].title(),  # Simple name from domain
            "priority": priority,
            "last_scraped": None,
            "article_count": 0
        }
    return sources


def create_new_data(articles: List[Dict], seen_urls: List[str], sources: Dict[str, Dict]) -> Dict[str, Any]:
    """Create new JSON structure"""
    return {
        "metadata": {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "total_articles": len(articles),
            "total_sources": len(sources)
        },
        "sources": sources,
        "articles": articles,
        "seen_urls": seen_urls
    }


def main():
    """Main migration function"""
    # Setup paths
    root_dir = Path(__file__).parent.parent
    data_dir = root_dir / "data"
    new_file = data_dir / "news_data.json"

    print("Starting data migration...")

    # Load old data
    articles, seen_urls, site_registry = load_old_data(data_dir)
    print(f"Loaded {len(articles)} articles, {len(seen_urls)} seen URLs, {len(site_registry)} sources")

    # Load markdown content
    content_map = load_markdown_content(data_dir, articles)
    print(f"Loaded content for {len(content_map)} articles")

    # Transform data
    transformed_articles = transform_articles(articles, content_map, site_registry)
    transformed_sources = transform_sources(site_registry)

    # Create new structure
    new_data = create_new_data(transformed_articles, seen_urls, transformed_sources)

    # Write new file
    with open(new_file, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    print(f"Migration complete! New data saved to {new_file}")
    print(f"Total articles: {len(transformed_articles)}")
    print(f"Total sources: {len(transformed_sources)}")


if __name__ == "__main__":
    main()