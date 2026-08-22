"""
routers/collect_router.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ endpoint /api/collect-md เท่านั้น
SOLID  D — inject FetcherService + SummarizerService
GRASP  Controller — ประสาน fetcher → save file → summarizer
                   ไม่ implement logic เอง
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.core.fetcher_service import FetcherService, get_fetcher_service
from backend.schemas.news_schema import CollectRequest
from backend.services.summarizer_service import (
    SummarizerService,
    get_summarizer_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["collect"])


@router.post("/collect-md")
async def collect_md(
    req: CollectRequest,                                          # Pydantic validation
    fetcher:    FetcherService    = Depends(get_fetcher_service),
    summarizer: SummarizerService = Depends(get_summarizer_service),
) -> JSONResponse:

    # ── Step 1: ดึงเนื้อหา ──────────────────────────────────────
    md_content, fetch_method = await fetcher.fetch_markdown(req.url)

    if not md_content:
        raise HTTPException(
            status_code=422,
            detail="ดึงเนื้อหาไม่ได้จากทุกวิธี (เว็บอาจบล็อกรุนแรง หรือเนื้อหาไม่ใช่บทความ)",
        )

    # ── Step 2: บันทึก Markdown file ───────────────────────────
    save_dir = settings.collected_md_dir
    save_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r'[\\/*?:"<>|]', "", req.url.split("/")[-1]) or "article"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath  = save_dir / f"{timestamp}_{safe_name}.md"

    with filepath.open("w", encoding="utf-8") as f:
        f.write(f"# Source URL: {req.url}\n\n{md_content}")

    print(f"  💾 บันทึก Markdown: {filepath}")

    # ── Step 3: สรุปด้วย LLM (พร้อม cache & stampede deduplication) ─────────
    try:
        summary = await summarizer.summarize_async(md_content, url=req.url)
    except Exception as e:
        logger.exception("LLM Error during summarization:")
        raise HTTPException(status_code=500, detail=f"LLM สรุปล้มเหลว: {e}") from e

    return JSONResponse({
        "ok":           True,
        "path":         str(filepath),
        "fetch_method": fetch_method,
        "summary":      summary.model_dump(),
    })