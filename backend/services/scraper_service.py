"""
services/scraper_service.py
─────────────────────────────────────────────────────────────────
SOLID  S — orchestrate scraping loop & telemetry เท่านั้น
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
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from backend.repo.news_repo import NewsRepositoryPort

# Type alias สำหรับฟังก์ชัน emit WebSocket
EmitFn = Callable[[str, dict], Awaitable[None]]

_scraper_instance: ScraperService | None = None


class ScraperService:
    """
    Background loop ที่ดึงข่าวจากทุก source แบบ round-robin
    ทุก INTERVAL_MINUTES นาที แล้ว emit event ผ่าน socket
    พร้อมจัดเก็บ telemetry และ metrics สำหรับ monitoring dashboard
    """

    def __init__(
        self,
        repo: NewsRepositoryPort,
        emit_fn: EmitFn,
        interval_minutes: int = 15,
    ) -> None:
        self._repo = repo
        self._emit = emit_fn
        self._interval = interval_minutes

        # Telemetry & Monitoring state
        self._is_scraping: bool = False
        self._last_cycle_started_at: str | None = None
        self._last_cycle_finished_at: str | None = None
        self._total_cycles_completed: int = 0
        self._sources_status: dict[str, dict[str, Any]] = {}
        self._logs: list[dict[str, Any]] = []
        self._wake_event: asyncio.Event = asyncio.Event()

        global _scraper_instance
        _scraper_instance = self

    # ── Public Telemetry & Control APIs ───────────────────────────

    @property
    def is_scraping(self) -> bool:
        return self._is_scraping

    def get_metrics(self) -> dict[str, Any]:
        """Return runtime status of scraper and all sources."""
        from backend.scrapers import SOURCES

        # Ensure all registered sources have an entry in _sources_status
        sources_list: list[dict[str, Any]] = []
        for s in SOURCES:
            status = self._sources_status.get(
                s.name,
                {
                    "name": s.name,
                    "url": s.url,
                    "color": s.color,
                    "status": "idle",
                    "last_scraped_at": None,
                    "last_fresh_count": 0,
                    "last_duration_ms": 0,
                    "last_error": None,
                    "total_collected": 0,
                },
            )
            sources_list.append(status)

        return {
            "is_scraping": self._is_scraping,
            "interval_minutes": self._interval,
            "total_cycles_completed": self._total_cycles_completed,
            "last_cycle_started_at": self._last_cycle_started_at,
            "last_cycle_finished_at": self._last_cycle_finished_at,
            "sources": sources_list,
            "recent_logs": self._logs[-50:],
        }

    def trigger_scrape(self) -> bool:
        """
        Trigger an immediate scrape cycle if not currently scraping.
        Returns True if trigger signal was scheduled, False if already scraping.
        """
        if self._is_scraping:
            return False
        self._wake_event.set()
        return True

    async def test_single_source(self, source_name: str) -> dict[str, Any]:
        """Test fetch for a single specific source without mutating persistent seen list."""
        from backend.scrapers import SOURCES

        target = next((s for s in SOURCES if s.name.lower() == source_name.strip().lower()), None)
        if not target:
            return {
                "source": source_name,
                "success": False,
                "error": f"Source '{source_name}' not found in registry",
                "articles_count": 0,
                "duration_ms": 0,
            }

        start = time.perf_counter()
        try:
            articles = await target.scrape_fn()
            duration_ms = int((time.perf_counter() - start) * 1000)
            sample = [
                {"title": a.get("title", ""), "url": a.get("url", "")}
                for a in articles[:3]
            ]
            return {
                "source": target.name,
                "success": True,
                "articles_count": len(articles),
                "duration_ms": duration_ms,
                "sample": sample,
                "error": None,
            }
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return {
                "source": target.name,
                "success": False,
                "articles_count": 0,
                "duration_ms": duration_ms,
                "sample": [],
                "error": str(exc),
            }

    def log_event(self, level: str, message: str, source: str | None = None) -> None:
        """Add event to ring buffer and emit to WebSocket listeners."""
        entry = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "level": level.upper(),
            "source": source or "system",
            "message": message,
        }
        self._logs.append(entry)
        if len(self._logs) > 100:
            self._logs.pop(0)

        # Emit in background non-blocking
        try:
            loop = asyncio.get_running_loop()

            async def _bg_emit() -> None:
                await self._emit("monitoring_log", entry)

            loop.create_task(_bg_emit())
        except RuntimeError:
            pass

    # ── Background Loop ───────────────────────────────────────────

    async def run_loop(self) -> None:
        """เรียกใน lifespan — รันจนกว่า task ถูก cancel"""
        from backend.scrapers import SOURCES  # import ในนี้เพื่อ lazy load

        seen = await asyncio.to_thread(self._repo.load_seen)
        self.log_event("INFO", "Background Scraper Service started")

        while True:
            self._is_scraping = True
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            self._last_cycle_started_at = now_iso
            print(f"\n[{datetime.now(timezone.utc):%H:%M:%S}] 🔄 กำลังดึงข่าว...")
            self.log_event("INFO", "Starting news collection cycle", "scraper")

            from backend.repo.news_repo import FileNewsRepository

            is_file_repo = isinstance(self._repo, FileNewsRepository)
            all_news = await asyncio.to_thread(self._repo.load_news) if is_file_repo else []

            def _on_source_result(src, status_dict):
                self._sources_status[src.name] = {
                    "name": src.name,
                    "url": src.url,
                    "color": src.color,
                    **status_dict,
                }
                lvl = "ERROR" if status_dict.get("status") == "error" else "INFO"
                msg = f"{src.name}: {status_dict.get('last_fresh_count', 0)} new ({status_dict.get('status')})"
                if status_dict.get("last_error"):
                    msg += f" - {status_dict.get('last_error')}"
                self.log_event(lvl, msg, src.name)

            new_batch = await self._scrape_all(
                SOURCES,
                seen,
                status_callback=_on_source_result,
            )

            if new_batch:
                if is_file_repo:
                    all_news.extend(new_batch)
                    await asyncio.to_thread(self._repo.save_news, all_news)
                    await asyncio.to_thread(self._repo.save_seen, seen)
                    total_count = len(all_news)
                else:
                    new_urls = {a["url"] for a in new_batch if a.get("url")}
                    await asyncio.to_thread(self._repo.save_news, new_batch)
                    await asyncio.to_thread(self._repo.save_seen, new_urls)
                    counts = await asyncio.to_thread(self._repo.get_category_counts)
                    total_count = counts.get("all", len(seen))

                # Reconcile unassigned articles into persistent stories (Single-Authority)
                try:
                    from backend.services.story_service import get_story_service
                    story_service = get_story_service()
                    assigned_tuples = await asyncio.to_thread(
                        story_service.assign_articles_batch, new_batch
                    )
                    url_to_story_id = {
                        str(a.get("url") or ""): story.story_id
                        for (story, is_new), a in zip(assigned_tuples, new_batch)
                        if a.get("url")
                    }
                    if hasattr(self._repo, "update_story_ids_batch"):
                        await asyncio.to_thread(
                            self._repo.update_story_ids_batch, url_to_story_id
                        )
                except Exception as rec_exc:
                    self.log_event("WARN", f"Story reconciliation error: {rec_exc}", "scraper")

                # Invalidate L1 feed and trending caches so clients see new articles immediately
                from backend.core.l1_cache import invalidate_feed_caches
                await invalidate_feed_caches()

                print(f"  💾 {len(new_batch)} บทความใหม่ (รวม {total_count})")
                self.log_event("SUCCESS", f"Collected {len(new_batch)} new articles (Total: {total_count})", "scraper")
                await self._emit(
                    "new_articles",
                    {
                        "count": len(new_batch),
                        "total": total_count,
                        "articles": new_batch,
                        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
            else:
                print("  — ไม่มีข่าวใหม่")
                self.log_event("INFO", "Cycle completed: No new articles found", "scraper")

            self._last_cycle_finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            self._total_cycles_completed += 1
            self._is_scraping = False

            # Wait for interval or wake event
            self._wake_event.clear()
            try:
                await asyncio.wait_for(
                    self._wake_event.wait(),
                    timeout=self._interval * 60,
                )
                self.log_event("INFO", "Scraper awakened manually via trigger", "scraper")
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                print("\n👋 scraper task halted")
                self.log_event("WARN", "Scraper task cancelled", "system")
                break

    # ── Private ───────────────────────────────────────────────────

    @staticmethod
    async def _scrape_all(
        sources,
        seen: set[str],
        status_callback: Callable[[Any, dict[str, Any]], None] | None = None,
    ) -> list[dict]:
        """ดึงข่าวจากทุก source — filter URL ซ้ำออก (รักษา signature เดิมสำหรับ test suite)"""
        new_batch: list[dict] = []
        for source in sources:
            t0 = time.perf_counter()
            err_msg: str | None = None
            fresh: list[dict] = []
            articles: list[dict] = []
            status_str = "idle"

            try:
                articles = await source.scrape_fn()
                fresh = [
                    a for a in articles
                    if a.get("url") and a["url"] not in seen
                ]
                for a in fresh:
                    seen.add(a["url"])
                new_batch.extend(fresh)

                if fresh:
                    print(f"  ✅ {source.name}: {len(fresh)} ใหม่")
                    status_str = "success"
                elif articles:
                    print(f"  ✅ {source.name}: 0 ใหม่ (URL ซ้ำ {len(articles)} รายการ)")
                    status_str = "not_modified"
                else:
                    print(f"  — {source.name}: 0 ใหม่ (304 Not Modified / ไม่มีบทความใหม่)")
                    status_str = "not_modified"
            except Exception as e:
                err_msg = str(e)
                status_str = "error"
                print(f"  ❌ {source.name}: {e}")

            duration_ms = int((time.perf_counter() - t0) * 1000)

            if status_callback:
                status_callback(
                    source,
                    {
                        "status": status_str,
                        "last_scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "last_fresh_count": len(fresh),
                        "last_duration_ms": duration_ms,
                        "last_error": err_msg,
                    },
                )

        return new_batch


def get_scraper_service() -> ScraperService:
    """Access or lazily initialize singleton scraper service instance."""
    global _scraper_instance
    if _scraper_instance is None:
        from backend.config import settings
        from backend.core.socket_manager import emit
        from backend.repo.news_repo import get_news_repository

        _scraper_instance = ScraperService(
            repo=get_news_repository(),
            emit_fn=emit,
            interval_minutes=settings.interval_minutes,
        )
    return _scraper_instance