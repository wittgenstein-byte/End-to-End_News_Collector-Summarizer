"""
services/scraper_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — orchestrate scraping loop เท่านั้น
           ไม่รู้ว่าข้อมูลเก็บที่ไหน (repository inject มา)
           ไม่รู้วิธีส่ง event (socket inject มา)
SOLID  D — รับ repository + socket emitter ผ่าน constructor
GRASP  Controller — รับ event "ถึงเวลา scrape" แล้วประสาน
                   SOURCES, repository, socket โดยไม่ทำเอง
GRASP  Low Coupling — ไม่ import socketio / files โดยตรง
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Awaitable

from repo.news_repo import NewsRepositoryPort


# Type alias สำหรับฟังก์ชัน emit WebSocket
EmitFn = Callable[[str, dict], Awaitable[None]]


class ScraperService:
    """
    Background loop ที่ดึงข่าวจากทุก source แบบ round-robin
    ทุก INTERVAL_MINUTES นาที แล้ว emit event ผ่าน socket
    """

    def __init__(
        self,
        repo: NewsRepositoryPort,
        emit_fn: EmitFn,
        interval_minutes: int = 15,
    ) -> None:
        self._repo     = repo
        self._emit     = emit_fn
        self._interval = interval_minutes

    async def run_loop(self) -> None:
        """เรียกใน lifespan — รันจนกว่า task ถูก cancel"""
        from scrapers import SOURCES   # import ในนี้เพื่อ lazy load

        seen = self._repo.load_seen()

        while True:
            print(f"\n[{datetime.now():%H:%M:%S}] 🔄 กำลังดึงข่าว...")
            all_news  = self._repo.load_news()
            new_batch = await self._scrape_all(SOURCES, seen)

            if new_batch:
                all_news.extend(new_batch)
                self._repo.save_news(all_news)
                self._repo.save_seen(seen)
                print(f"  💾 {len(new_batch)} บทความใหม่ (รวม {len(all_news)})")
                await self._emit(
                    "new_articles",
                    {
                        "count":    len(new_batch),
                        "total":    len(all_news),
                        "articles": new_batch,
                        "updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
            else:
                print("  — ไม่มีข่าวใหม่")

            try:
                await asyncio.sleep(self._interval * 60)
            except asyncio.CancelledError:
                print("\n👋 scraper task halted")
                break

    # ── Private ───────────────────────────────────────────────────

    @staticmethod
    async def _scrape_all(sources, seen: set[str]) -> list[dict]:
        """ดึงข่าวจากทุก source — filter URL ซ้ำออก"""
        new_batch: list[dict] = []
        for source in sources:
            try:
                articles = await source.scrape_fn()
                fresh = [
                    a for a in articles
                    if a.get("url") and a["url"] not in seen
                ]
                for a in fresh:
                    seen.add(a["url"])
                new_batch.extend(fresh)
                print(f"  ✅ {source.name}: {len(fresh)} ใหม่")
            except Exception as e:
                print(f"  ❌ {source.name}: {e}")
        return new_batch