"""
sockets/events.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ WebSocket events เท่านั้น
           ไม่มี business logic — ถามข้อมูลจาก repository
─────────────────────────────────────────────────────────────────
"""

from datetime import datetime

from backend.core.socket_manager import sio
from backend.repo.news_repo import get_news_repository


@sio.event
async def connect(sid: str, environ: dict) -> None:
    repo  = get_news_repository()
    news  = repo.load_news()
    await sio.emit(
        "init",
        {
            "total":   len(news),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        to=sid,
    )
    print(f"  🔌 client เชื่อมต่อแล้ว ({sid})")


@sio.event
async def disconnect(sid: str) -> None:
    print(f"  🔌 client ตัดการเชื่อมต่อ ({sid})")