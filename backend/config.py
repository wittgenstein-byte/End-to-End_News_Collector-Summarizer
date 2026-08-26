"""
config.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ config อย่างเดียว
SOLID  D — ค่าต่าง ๆ inject เข้า service ผ่าน Settings object
GRASP  Information Expert — รู้จักทุก setting ของระบบ
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

# ── Resolve base paths ───────────────────────────────────────────
_HERE = Path(__file__).resolve().parent          # backend/
BASE_DIR = _HERE.parent                          # project root
# ตรวจสอบ .env ใน root ก่อน ถ้าไม่มีค่อยดูใน backend/
ENV_PATH = BASE_DIR / ".env"
if not ENV_PATH.exists():
    ENV_PATH = _HERE / ".env"


def _load_env_file(path: Path) -> dict[str, str]:
    """อ่าน .env แบบ minimal (ไม่ต้องพึ่ง python-dotenv)"""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return result


_env = _load_env_file(ENV_PATH)


def _get(key: str, default: str = "") -> str:
    # Prioritize .env file values over container ENV defaults
    if key in _env and _env[key].strip():
        return _env[key].strip()
    return os.environ.get(key) or default



# ── Tiered Model Defaults (KKU OpenSDK / OpenAI-compatible endpoint) ──
# จัดลำดับโดยนำโมเดลที่เปิดให้บริการจริงและตอบสนองเร็วที่สุดขึ้นก่อน เพื่อความเร็วสูงสุด
DEFAULT_TIER1_MODELS: list[str] = [
    "qwen3-next-80b-a3b-instruct",
    "qwen3-coder-flash",
    "mistral-small-2603",
    "qwen3-coder",
    "nova-2-lite-v1",
    "llama-4-maverick",
]

DEFAULT_TIER2_MODELS: list[str] = [
    "llama-4-scout",
    "mistral-medium-3",
    "nova-pro-v1",
    "qwen3-235b-a22b-2507",
    "grok-4.3",
    "deepseek-chat-v3.1",
]

DEFAULT_TIER3_MODELS: list[str] = [
    "deepseek-v3.2-exp",
    "deepseek-v3.2",
    "grok-4.5",
    "mistral-large-2512",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gpt-5.4-mini",
    "claude-haiku-4.5",
]


def _build_cascade_models(primary_model: str, custom_cascade_env: str) -> list[str]:
    """สร้างลำดับ Model Cascade โดยเริ่มจาก Primary Model และเติมโมเดล Tier ต่างๆ โดยไม่ซ้ำ"""
    if custom_cascade_env.strip():
        models = [m.strip() for m in custom_cascade_env.split(",") if m.strip()]
    else:
        models = [primary_model] + DEFAULT_TIER1_MODELS + DEFAULT_TIER2_MODELS + DEFAULT_TIER3_MODELS

    # Deduplicate while preserving order, ensuring primary model is first
    seen: set[str] = set()
    result: list[str] = []
    if primary_model:
        result.append(primary_model)
        seen.add(primary_model)

    for m in models:
        if m not in seen:
            seen.add(m)
            result.append(m)

    return result


# ── Settings ─────────────────────────────────────────────────────

class Settings:
    # LLM
    llm_api_key: str        = _get("LLM_API_KEY", _get("LLM_API"))
    llm_base_url: str       = _get("LLM_BASE_URL", "https://gen.ai.kku.ac.th/api/v1")
    llm_model: str          = _get("LLM_MODEL",    "qwen3-next-80b-a3b-instruct")
    llm_temperature: float  = float(_get("LLM_TEMPERATURE", "0.3"))
    llm_cascade_models: ClassVar[list[str]] = _build_cascade_models(
        _get("LLM_MODEL", "qwen3-next-80b-a3b-instruct"),
        _get("LLM_CASCADE_MODELS", _get("LLM_FALLBACK_MODELS", "")),
    )

    # Caching
    summary_cache_ttl_seconds: int = int(_get("SUMMARY_CACHE_TTL_SECONDS", "86400"))
    summary_cache_max_size: int    = int(_get("SUMMARY_CACHE_MAX_SIZE", "1000"))

    # Scraper
    interval_minutes: int           = int(_get("INTERVAL_MINUTES",         "15"))
    max_articles_per_source: int    = int(_get("MAX_ARTICLES_PER_SOURCE",  "10"))
    summary_sentences: int          = int(_get("SUMMARY_SENTENCES",        "3"))
    page_size: int                  = int(_get("PAGE_SIZE",                "20"))

    # Storage (ใช้ pathlib เพื่อ cross-platform — ย้ายไปโฟลเดอร์ data/)
    DATA_DIR: Path          = BASE_DIR / "data"
    data_file: Path         = DATA_DIR / _get("DATA_FILE",  "news_data.json")
    engagement_file: Path   = DATA_DIR / _get("ENGAGEMENT_FILE", "engagement_data.json")
    collected_md_dir: Path  = DATA_DIR / _get("COLLECTED_MD_DIR", "collected_md")

    # Server
    host: str               = _get("HOST", "0.0.0.0")
    port: int               = int(_get("PORT", "5000"))
    playwright_service_url: str = _get("PLAYWRIGHT_SERVICE_URL", "http://playwright:8001/scrape")
    obscura_service_url: str    = _get("OBSCURA_SERVICE_URL", "ws://localhost:9222")
    cors_origins: ClassVar[list[str]] = [x.strip() for x in _get("CORS_ORIGINS", "*").split(",") if x.strip()]

    # Frontend
    frontend_dir: Path      = BASE_DIR / "frontend"


# Singleton ใช้ได้ทั่วทั้ง app
settings = Settings()