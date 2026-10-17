"""
core/socket_manager.py
─────────────────────────────────────────────────────────────────
GRASP  Pure Fabrication — ไม่ map กับ domain object ใด ๆ
                          สร้างขึ้นเพื่อ low coupling โดยเฉพาะ
SOLID  S — จัดการ socket instance เท่านั้น
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from typing import Any

import socketio  # type: ignore[import-untyped]


def _is_origin_allowed(origin: str | None, environ: dict[str, Any] | None = None) -> bool:
    """Validate cross-origin requests dynamically against configured settings.

    Adheres to AGENTS.md by lazily importing settings inside the callable
    to avoid module-level config freeze and enable runtime test overrides.
    """
    if not origin:
        # Same-origin requests, direct backend calls, or CLI tools without Origin header
        return True

    from backend.config import settings

    # 1. Allow wildcard if configured
    if "*" in settings.cors_origins:
        return True

    # 2. Check explicit allowed origins list (with/without trailing slash)
    clean_origin = origin.rstrip("/")
    if origin in settings.cors_origins or clean_origin in settings.cors_origins:
        return True

    # 3. Check regular expression pattern match
    if settings.cors_origin_regex:
        try:
            if re.fullmatch(settings.cors_origin_regex, origin) or re.fullmatch(
                settings.cors_origin_regex, clean_origin
            ):
                return True
        except re.error:
            pass

    return False


is_origin_allowed = _is_origin_allowed

# Singleton — ทุก module import ตัวนี้ตัวเดียว
# ป้องกัน scraper_service กับ sockets/events ใช้คนละ instance
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_is_origin_allowed,
)


async def emit(event: str, data: dict, to: str | None = None) -> None:
    """Wrapper บาง ๆ ให้ scraper_service inject ได้โดยไม่รู้จัก socketio"""
    await sio.emit(event, data, to=to)