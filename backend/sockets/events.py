"""
sockets/events.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ WebSocket events เท่านั้น
           ไม่มี business logic — ถามข้อมูลจาก repository
─────────────────────────────────────────────────────────────────
CHANGELOG (security patch):
  - tab_id ownership is now tracked per-sid. Every handler that touches an
    existing tab (navigate/back/forward/refresh/close) checks that the
    calling sid is the one that opened it. Previously any connected
    client could pass any tab_id and read/drive another user's browsing
    session (cross-user data leak).
  - disconnect() now closes and releases every tab the disconnecting sid
    owned, instead of leaving orphaned contexts alive in BrowserService.
─────────────────────────────────────────────────────────────────
"""

from collections.abc import Coroutine
from datetime import datetime
from typing import Any

from backend.core.socket_manager import sio
from backend.repo.news_repo import get_news_repository
from backend.services.browser_service import browser_service

# tab_id -> sid that opened it. Lets every other handler verify the caller
# actually owns the tab before touching it.
_tab_owners: dict[str, str] = {}


def _owns_tab(sid: str, tab_id: str) -> bool:
    return _tab_owners.get(tab_id) == sid


async def _deny_unauthorized(sid: str, tab_id: str) -> None:
    await sio.emit(
        "browser_snapshot",
        {"tab_id": tab_id, "error": "Unauthorized: tab does not belong to this session"},
        to=sid,
    )


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
    owned_tabs = [tab_id for tab_id, owner in _tab_owners.items() if owner == sid]
    for tab_id in owned_tabs:
        try:
            await browser_service.close_tab(tab_id)
        except Exception:
            pass
        _tab_owners.pop(tab_id, None)
    print(f"  🔌 client ตัดการเชื่อมต่อ ({sid})")


@sio.event
async def browser_open_tab(sid: str, data: dict) -> None:
    tab_id = data.get("tab_id")
    if not tab_id:
        return
    try:
        await browser_service.open_tab(tab_id)
    except Exception as e:
        print(f"  ❌ browser_open_tab error for {tab_id}: {e!r}", flush=True)
        await sio.emit(
            "browser_snapshot",
            {"tab_id": tab_id, "error": f"Failed to open tab: {e!s}"},
            to=sid,
        )
        return
    _tab_owners[tab_id] = sid
    await sio.emit("browser_tab_opened", {"tab_id": tab_id}, to=sid)


@sio.event
async def browser_close_tab(sid: str, data: dict) -> None:
    tab_id = data.get("tab_id")
    if not tab_id:
        return
    if not _owns_tab(sid, tab_id):
        await _deny_unauthorized(sid, tab_id)
        return
    await browser_service.close_tab(tab_id)
    _tab_owners.pop(tab_id, None)


async def _run_browser_op(
    sid: str, tab_id: str | None, coro: Coroutine[Any, Any, dict]
) -> None:
    """Run a browser op and always reply — never leave the client's spinner hanging."""
    if not tab_id:
        return
    await sio.emit("browser_loading", {"tab_id": tab_id}, to=sid)
    try:
        result = await coro
    except Exception as e:
        result = {"error": f"Browser error: {e!s}"}
    result["tab_id"] = tab_id
    await sio.emit("browser_snapshot", result, to=sid)


@sio.event
async def browser_open_and_navigate(sid: str, data: dict) -> None:
    """เปิด tab ใหม่และนำทางไปยัง URL ในคำสั่งเดียว—ป้องกัน race condition"""
    tab_id = data.get("tab_id")
    url = data.get("url")
    if not (tab_id and url):
        return
    await sio.emit("browser_loading", {"tab_id": tab_id}, to=sid)
    try:
        await browser_service.open_tab(tab_id)
        _tab_owners[tab_id] = sid
    except Exception as e:
        print(f"  ❌ Error opening tab {tab_id}: {e}")
        try:
            # Retry once
            await browser_service.open_tab(tab_id)
            _tab_owners[tab_id] = sid
        except Exception as retry_e:
            await sio.emit(
                "browser_snapshot",
                {"tab_id": tab_id, "error": f"Failed to open tab: {retry_e!s}"},
                to=sid,
            )
            return
    result = await browser_service.navigate(tab_id, url)
    result["tab_id"] = tab_id
    await sio.emit("browser_snapshot", result, to=sid)


@sio.event
async def browser_navigate(sid: str, data: dict) -> None:
    tab_id = data.get("tab_id")
    url = data.get("url")
    if not (tab_id and url):
        return
    if not _owns_tab(sid, tab_id):
        await _deny_unauthorized(sid, tab_id)
        return
    await _run_browser_op(sid, tab_id, browser_service.navigate(tab_id, url))


@sio.event
async def browser_go_back(sid: str, data: dict) -> None:
    tab_id = data.get("tab_id")
    if not tab_id:
        return
    if not _owns_tab(sid, tab_id):
        await _deny_unauthorized(sid, tab_id)
        return
    await _run_browser_op(sid, tab_id, browser_service.go_back(tab_id))


@sio.event
async def browser_go_forward(sid: str, data: dict) -> None:
    tab_id = data.get("tab_id")
    if not tab_id:
        return
    if not _owns_tab(sid, tab_id):
        await _deny_unauthorized(sid, tab_id)
        return
    await _run_browser_op(sid, tab_id, browser_service.go_forward(tab_id))


@sio.event
async def browser_refresh(sid: str, data: dict) -> None:
    tab_id = data.get("tab_id")
    if not tab_id:
        return
    if not _owns_tab(sid, tab_id):
        await _deny_unauthorized(sid, tab_id)
        return
    await _run_browser_op(sid, tab_id, browser_service.refresh(tab_id))