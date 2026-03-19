"""
core/socket_manager.py
─────────────────────────────────────────────────────────────────
GRASP  Pure Fabrication — ไม่ map กับ domain object ใด ๆ
                          สร้างขึ้นเพื่อ low coupling โดยเฉพาะ
SOLID  S — จัดการ socket instance เท่านั้น
─────────────────────────────────────────────────────────────────
"""

import socketio

# Singleton — ทุก module import ตัวนี้ตัวเดียว
# ป้องกัน scraper_service กับ sockets/events ใช้คนละ instance
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


async def emit(event: str, data: dict, to: str | None = None) -> None:
    """Wrapper บาง ๆ ให้ scraper_service inject ได้โดยไม่รู้จัก socketio"""
    await sio.emit(event, data, to=to)