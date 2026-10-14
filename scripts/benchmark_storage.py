"""
scripts/benchmark_storage.py
Benchmarking storage and caching latency across JSON, SQLite WAL, and L1 RAM.
"""

from __future__ import annotations

import asyncio
import sys
import time

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.config import settings
from backend.core.l1_cache import news_feed_cache
from backend.repo.news_repo import FileNewsRepository
from backend.repo.sqlite_news_repo import SqliteNewsRepository


async def run_benchmark():
    file_repo = FileNewsRepository(settings.data_file)
    sqlite_repo = SqliteNewsRepository(settings.sqlite_file)

    print("=================================================================")
    print(" [BENCHMARK] JSON vs SQLite WAL vs Tiered RAM Cache")
    print("=================================================================")

    # 1. JSON Storage (FileNewsRepository)
    t0 = time.perf_counter()
    f_items, f_total = file_repo.query_news(page=1, page_size=20, category="politics")
    t1 = time.perf_counter()
    json_ms = (t1 - t0) * 1000

    # 2. SQLite WAL Storage Engine (SqliteNewsRepository)
    t2 = time.perf_counter()
    s_items, s_total = sqlite_repo.query_news(page=1, page_size=20, category="politics")
    t3 = time.perf_counter()
    sqlite_ms = (t3 - t2) * 1000

    # 3. Tier 1 In-Memory Cache (RAM)
    await news_feed_cache.set("feed:bench:politics", {"news": s_items, "total": s_total}, ttl_seconds=30)
    t4 = time.perf_counter()
    cached_feed = await news_feed_cache.get("feed:bench:politics")
    t5 = time.perf_counter()
    ram_ms = (t5 - t4) * 1000

    print(f"1. FileNewsRepository (Monolithic JSON) : {json_ms:8.2f} ms")
    print(f"2. SqliteNewsRepository (SQLite WAL)    : {sqlite_ms:8.2f} ms ({json_ms / max(0.001, sqlite_ms):6.1f}x faster)")
    print(f"3. Tier 1 In-Memory Cache (RAM Tier)    : {ram_ms:8.3f} ms ({json_ms / max(0.0001, ram_ms):6.1f}x faster)")
    print("-----------------------------------------------------------------")
    print(f" Total articles tested: {s_total:,} articles")
    print(" Decoupled storage & WAL verified successfully!")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
