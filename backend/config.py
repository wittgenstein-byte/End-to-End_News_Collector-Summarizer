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
    # Explicit container/system environment variables take precedence over .env defaults
    val = os.environ.get(key)
    if val is not None and val.strip():
        return val.strip()
    if key in _env and _env[key].strip():
        return _env[key].strip()
    return default



# ── Tiered Model Defaults (KKU OpenSDK / OpenAI-compatible endpoint) ──
DEFAULT_TIER1_MODELS: list[str] = [
    "gemini-3.5-flash-lite",
    "nova-2-lite-v1",
    "llama-4-maverick",
    "nova-pro-v1",
]

DEFAULT_TIER2_MODELS: list[str] = [
    "gpt-5.6-luna",
    "mistral-medium-3",
    "llama-4-scout",
    "gpt-5.6-terra",
    "grok-4.5",
]

DEFAULT_TIER3_MODELS: list[str] = [
    "claude-sonnet-5",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "qwen3.7-plus",
    "qwen3.7-max",
    "mistral-small-2603",
    "mistral-large-2512",
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


def _parse_csv(value: str, default: list[str]) -> list[str]:
    """Parse comma-separated values into a stripped, non-empty list."""
    if not value or not value.strip():
        return list(default)
    parsed = [v.strip() for v in value.split(",") if v.strip()]
    return parsed or list(default)


# ── Settings ─────────────────────────────────────────────────────

class Settings:
    # ── Provider 1: KKU OpenSDK (Primary Campus Gateway) ──────────
    kku_api_key: str        = _get("LLM_API_KEY", _get("LLM_API"))
    kku_base_url: str       = _get("LLM_BASE_URL", "https://gen.ai.kku.ac.th/api/v1")
    kku_models: ClassVar[list[str]] = _parse_csv(
        _get("KKU_MODELS"),
        ["gemini-3.5-flash-lite", "nova-2-lite-v1", "llama-4-maverick", "nova-pro-v1", "gpt-5.6-luna", "mistral-medium-3"],
    )

    # ── Provider 2: Google Gemini Direct API (Cloud High-Availability) ──
    # Accepts GOOGLE_API_KEY, GEMINI_API_KEY, or legacy news_assistant key
    google_api_key: str     = _get("GOOGLE_API_KEY", _get("GEMINI_API_KEY", _get("news_assistant")))
    google_base_url: str    = _get("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    google_models: ClassVar[list[str]] = _parse_csv(
        _get("GOOGLE_MODELS"),
        ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"],
    )

    # ── Provider 3: Thai LLM (Typhoon / Sovereign Thai Model - Disabled by default) ──
    thai_llm_enabled: bool  = _get("THAI_LLM_ENABLED", "false").lower() == "true"
    thai_llm_api_key: str   = _get("THAI_LLM_API_KEY", _get("THAI_LLM"))
    thai_llm_base_url: str  = _get("THAI_LLM_BASE_URL", "https://api.opentyphoon.ai/v1")
    thai_llm_models: ClassVar[list[str]] = _parse_csv(
        _get("THAI_LLM_MODELS"),
        ["typhoon-v2.5-30b-a3b-instruct"],
    )

    # ── High Availability Engine Tuning ──────────────────────────
    llm_provider_order: ClassVar[list[str]] = _parse_csv(
        _get("LLM_PROVIDER_ORDER"),
        ["kku", "google", "thai_llm"],
    )
    llm_per_target_timeout: float      = float(_get("LLM_PER_TARGET_TIMEOUT", "10.0"))
    llm_overall_request_timeout: float = float(_get("LLM_OVERALL_REQUEST_TIMEOUT", "30.0"))
    llm_circuit_breaker_cooldown: float = float(_get("LLM_CIRCUIT_BREAKER_COOLDOWN", "45.0"))
    fallback_cache_ttl_seconds: int    = int(_get("FALLBACK_CACHE_TTL_SECONDS", "7200"))

    # ── Legacy / Backwards Compatibility Aliases ─────────────────
    llm_api_key: str        = _get("LLM_API_KEY", _get("LLM_API"))
    llm_base_url: str       = _get("LLM_BASE_URL", "https://gen.ai.kku.ac.th/api/v1")
    llm_model: str          = _get("LLM_MODEL",    "gemini-3.5-flash-lite")
    llm_temperature: float  = float(_get("LLM_TEMPERATURE", "0.3"))
    llm_cascade_models: ClassVar[list[str]] = _build_cascade_models(
        _get("LLM_MODEL", "gemini-3.5-flash-lite"),
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

    # Trending
    trending_window_hours: float                = float(_get("TRENDING_WINDOW_HOURS",                "48.0"))
    trending_cosine_threshold: float           = float(_get("TRENDING_COSINE_THRESHOLD",           "0.76"))
    trending_cohesion_threshold: float         = float(_get("TRENDING_COHESION_THRESHOLD",         "0.70"))
    trending_cluster_time_window_hours: float   = float(_get("TRENDING_CLUSTER_TIME_WINDOW_HOURS",   "36.0"))
    embedding_cache_max_size: int              = int(_get("EMBEDDING_CACHE_MAX_SIZE",              "2000"))
    trending_result_cache_ttl_seconds: int     = int(_get("TRENDING_RESULT_CACHE_TTL_SECONDS",     "600"))

    # Deterministic Trending Scoring Weights & Thresholds (Milestone 3)
    volume_weight: float                        = float(_get("TRENDING_VOLUME_WEIGHT",               "1.0"))
    velocity_weight: float                      = float(_get("TRENDING_VELOCITY_WEIGHT",             "1.5"))
    diversity_weight: float                     = float(_get("TRENDING_DIVERSITY_WEIGHT",            "1.2"))
    recency_half_life_hours: float              = float(_get("TRENDING_RECENCY_HALF_LIFE_HOURS",     "12.0"))
    novelty_weight: float                       = float(_get("TRENDING_NOVELTY_WEIGHT",              "0.8"))
    engagement_weight: float                    = float(_get("TRENDING_ENGAGEMENT_WEIGHT",           "0.6"))
    routine_penalty_factor: float               = float(_get("TRENDING_ROUTINE_PENALTY_FACTOR",      "0.25"))
    trending_recent_window_hours: float         = float(_get("TRENDING_RECENT_WINDOW_HOURS",        "24.0"))
    trending_baseline_window_hours: float       = float(_get("TRENDING_BASELINE_WINDOW_HOURS",      "72.0"))
    syndication_discount: float                 = float(_get("TRENDING_SYNDICATION_DISCOUNT",        "0.5"))

    # Storage (ใช้ pathlib เพื่อ cross-platform — ย้ายไปโฟลเดอร์ data/)
    DATA_DIR: Path          = BASE_DIR / "data"
    data_file: Path         = DATA_DIR / _get("DATA_FILE",  "news_data.json")
    sqlite_file: Path       = DATA_DIR / _get("SQLITE_FILE", "news_collector.db")
    stories_file: Path      = DATA_DIR / _get("STORIES_FILE", "stories_data.json")
    engagement_file: Path   = DATA_DIR / _get("ENGAGEMENT_FILE", "engagement_data.json")
    collected_md_dir: Path  = DATA_DIR / _get("COLLECTED_MD_DIR", "collected_md")
    db_type: str            = _get("DB_TYPE", "sqlite").lower().strip()
    sqlite_wal_mode: bool   = _get("SQLITE_WAL_MODE", "true").lower() in {"1", "true", "yes"}
    sqlite_cache_size_kb: int = int(_get("SQLITE_CACHE_SIZE_KB", "16000"))
    sqlite_mmap_size_bytes: int = int(_get("SQLITE_MMAP_SIZE_BYTES", "268435456"))

    # Tiered In-Memory Caching (L1 RAM Layer)
    news_cache_ttl_seconds: int     = int(_get("NEWS_CACHE_TTL_SECONDS", "30"))
    trending_cache_ttl_seconds: int = int(_get("TRENDING_CACHE_TTL_SECONDS", "60"))
    metadata_cache_ttl_seconds: int = int(_get("METADATA_CACHE_TTL_SECONDS", "60"))

    mongo_uri: str          = _get("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name: str      = _get("MONGO_DB_NAME", "news_collector")
    mongo_story_collection: str = _get("MONGO_STORY_COLLECTION", "stories")

    # Server
    host: str               = _get("HOST", "0.0.0.0")
    port: int               = int(_get("PORT", "5000"))
    playwright_service_url: str = _get("PLAYWRIGHT_SERVICE_URL", "http://playwright:8001/scrape")
    obscura_service_url: str    = _get("OBSCURA_SERVICE_URL", "")
    cors_origins: ClassVar[list[str]] = [x.strip() for x in _get("CORS_ORIGINS", "*").split(",") if x.strip()]

    # Frontend
    frontend_dir: Path      = BASE_DIR / "frontend"

    # Monitoring & Admin Auth
    monitoring_admin_key: str           = _get("MONITORING_ADMIN_KEY", "admin-dev-secret-2026")
    monitoring_session_ttl_seconds: int = int(_get("MONITORING_SESSION_TTL_SECONDS", "86400"))

    # Issue Explorer (เจาะประเด็น) — isolated feature, kill-switch via flag
    issue_explorer_enabled: bool     = _get("ISSUE_EXPLORER_ENABLED", "true").lower() in {"1", "true", "yes"}
    issue_max_matches: int           = int(_get("ISSUE_MAX_MATCHES", "2000"))
    issue_analysis_cap: int          = int(_get("ISSUE_ANALYSIS_CAP", "300"))
    issue_cluster_distance: float    = float(_get("ISSUE_CLUSTER_DISTANCE", "0.85"))
    issue_cache_ttl_seconds: int     = int(_get("ISSUE_CACHE_TTL_SECONDS", "120"))
    issue_rate_limit_per_min: int    = int(_get("ISSUE_RATE_LIMIT_PER_MIN", "30"))


# Singleton ใช้ได้ทั่วทั้ง app
settings = Settings()