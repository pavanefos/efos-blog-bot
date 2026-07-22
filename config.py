"""Central configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# The user-editable .env lives in the automation root (parent of src/).
PROJECT_DIR = BASE_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


# Load from project root first (where the user keeps .env), then src/ as fallback.
_load_dotenv(PROJECT_DIR / ".env")
_load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _bool(name: str, default: bool = False) -> bool:
    return _get(name, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


def _parse_times(raw: str) -> list[str]:
    """Parse '9,11,13,15,17,19' into ['09:00','11:00','13:00','15:00','17:00','19:00']."""
    out: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            h, m = part.split(":", 1)
        else:
            h, m = part, "0"
        try:
            out.append(f"{int(h):02d}:{int(m):02d}")
        except ValueError:
            continue
    return out


@dataclass
class Config:
    # Laravel API
    laravel_api_url: str = field(default=_get("LARAVEL_API_URL", "https://www.efos.in").rstrip("/"))
    ai_blog_token: str = field(default=_get("AI_BLOG_TOKEN", ""))
    blog_ai_user_id: int = field(default=_int("BLOG_AI_USER_ID", 0))

    # AI provider
    openrouter_api_key: str = field(default=_get("OPENROUTER_API_KEY", ""))
    ai_model: str = field(default=_get("AI_MODEL", "gemini/gemini-2.5-flash"))
    ai_max_tokens: int = field(default=_int("AI_MAX_TOKENS", 1024))
    ai_fallback_models: str = field(default=_get("AI_FALLBACK_MODELS", "meta-llama/llama-3.1-8b-instruct"))
    gemini_api_key: str = field(default=_get("GEMINI_API_KEY", ""))

    # Image generation
    use_image_api: bool = field(default=_bool("USE_IMAGE_API", False))
    image_provider: str = field(default=_get("IMAGE_PROVIDER", "openrouter"))  # openrouter | chatgpt
    image_model: str = field(default=_get("IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0"))
    openai_api_key: str = field(default=_get("OPENAI_API_KEY", ""))  # for ChatGPT image API

    # Scheduling - fixed times each day (HH:MM,24h). Empty -> single time below.
    # Example: "9,11,13,15,17,19"  => 9am,11am,1pm,3pm,5pm,7pm
    schedule_times: list[str] = field(default_factory=lambda: _parse_times(_get("SCHEDULE_TIMES", "")))
    schedule_hour: int = field(default=_int("SCHEDULE_HOUR", 9))
    schedule_minute: int = field(default=_int("SCHEDULE_MINUTE", 0))
    blogs_per_day: int = field(default=_int("BLOGS_PER_DAY", 5))

    # Behaviour
    dedup_days: int = field(default=_int("DEDUP_DAYS", 30))
    dry_run: bool = field(default=_bool("DRY_RUN", False))

    # Paths (default to folders inside the package so they are stable no matter
    # where the script is launched from - cron, PHP, or directly).
    state_dir: Path = field(default=Path(_get("STATE_DIR", str(BASE_DIR / "state"))))
    log_dir: Path = field(default=Path(_get("LOG_DIR", str(BASE_DIR / "logs"))))

    def __post_init__(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def publish_url(self) -> str:
        return f"{self.laravel_api_url}/api/ai/publish-blog"


# Singleton config instance.
CFG = Config()
