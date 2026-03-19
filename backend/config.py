"""
config.py
─────────────────────────────────────────────────────────────────
SOLID  S — จัดการ config อย่างเดียว
SOLID  D — ค่าต่าง ๆ inject เข้า service ผ่าน Settings object
GRASP  Information Expert — รู้จักทุก setting ของระบบ
─────────────────────────────────────────────────────────────────
"""

import os
from pathlib import Path


# ── Resolve base paths ───────────────────────────────────────────
_HERE = Path(__file__).resolve().parent          # backend/
BASE_DIR = _HERE.parent                          # project root
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
    except Exception:
        pass
    return result


_env = _load_env_file(ENV_PATH)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key) or _env.get(key, default)


# ── Settings ─────────────────────────────────────────────────────

class Settings:
    # LLM
    llm_api_key: str        = _get("LLM_API")
    llm_base_url: str       = _get("LLM_BASE_URL", "https://gen.ai.kku.ac.th/api/v1")
    llm_model: str          = _get("LLM_MODEL",    "gemini-3.1-flash-lite-preview")
    llm_temperature: float  = float(_get("LLM_TEMPERATURE", "0.3"))

    # Scraper
    interval_minutes: int           = int(_get("INTERVAL_MINUTES",         "15"))
    max_articles_per_source: int    = int(_get("MAX_ARTICLES_PER_SOURCE",  "10"))
    summary_sentences: int          = int(_get("SUMMARY_SENTENCES",        "3"))
    page_size: int                  = int(_get("PAGE_SIZE",                "20"))

    # Storage (ใช้ pathlib เพื่อ cross-platform — แก้ hardcode D:\... ออก)
    output_file: Path       = BASE_DIR / _get("OUTPUT_FILE",  "news_output.json")
    seen_file: Path         = BASE_DIR / _get("SEEN_FILE",    "seen_urls.json")
    collected_md_dir: Path  = BASE_DIR / _get("COLLECTED_MD_DIR", "collected_md")

    # Server
    host: str               = _get("HOST", "0.0.0.0")
    port: int               = int(_get("PORT", "5000"))

    # Frontend
    frontend_dir: Path      = BASE_DIR / "frontend"


# Singleton ใช้ได้ทั่วทั้ง app
settings = Settings()