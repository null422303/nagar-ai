import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # nagarai/

# Load .env if present (keys are read from env — never hardcoded in the repo)
_env = Path(os.getenv("NAGARAI_ENV", str(BASE_DIR / ".env")))
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


class Settings:
    # Multiple DashScope keys — comma-separated in DASHSCOPE_API_KEYS.
    # Falls back to the single DASHSCOPE_API_KEY for backwards compatibility.
    DASHSCOPE_API_KEYS: list = [k.strip() for k in os.getenv("DASHSCOPE_API_KEYS", "").split(",") if k.strip()] or \
        ([os.getenv("DASHSCOPE_API_KEY", "")] if os.getenv("DASHSCOPE_API_KEY") else [])
    DASHSCOPE_API_KEY: str = DASHSCOPE_API_KEYS[0] if DASHSCOPE_API_KEYS else ""
    DASHSCOPE_BASE_URL: str = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    MODEL_TEXT = os.getenv("MODEL_TEXT", "qwen3.7-flash")
    MODEL_EMBED = os.getenv("MODEL_EMBED", "qwen3.7-text-embedding")
    MODEL_VISION = os.getenv("MODEL_VISION", "qwen-vl-max")
    MODEL_ASR = os.getenv("MODEL_ASR", "mistralai/voxtral-small-24b-2507")

    # Google reCAPTCHA v2 — optional. If keys are empty, the captcha is skipped
    # (demo mode); when set, complaint submissions must pass verification.
    RECAPTCHA_SITE_KEY: str = os.getenv("RECAPTCHA_SITE_KEY", "")
    RECAPTCHA_SECRET_KEY: str = os.getenv("RECAPTCHA_SECRET_KEY", "")

    DB_PATH = Path(os.getenv("NAGARAI_DB", str(BASE_DIR / "data" / "nagarai.db")))
    MEDIA_DIR = Path(os.getenv("NAGARAI_MEDIA", str(BASE_DIR / "data" / "media")))
    CACHE_CSV = Path(os.getenv("NAGARAI_CACHE", str(BASE_DIR / "data" / "api_cache.csv")))

    # Dedup weights + thresholds (tuned via harness)
    W_TEXT = 0.55
    W_GEO = 0.30
    W_VISION = 0.15
    GEO_MERGE_M = 60.0      # gaussian sigma for geo similarity
    GEO_FENCE_M = 500.0     # hard cap: beyond this distance, only text/vision can merge
    TAU_MERGE = 0.62
    TAU_HINT = 0.50

    # Priority formula
    SCHOOL_HOSPITAL_RADIUS_M = 100.0
    PROXIMITY_BONUS = 1.5

    CATEGORIES = ["pothole", "garbage", "broken_streetlight", "waterlogging", "other"]

    # Chennai anchor (Anna Nagar) for demo default
    CITY = os.getenv("NAGARAI_CITY", "chennai")
    CITY_CENTER = (13.0827, 80.2707)

    CORS_ORIGINS = ["*"]


settings = Settings()
settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
