"""Application configuration.

Settings are read from environment variables (and a local ``.env`` file).
Provider API keys are intentionally optional so the platform boots in
development without them — feature availability is reported at runtime via
``settings.provider_status()`` and the ``/health`` endpoint.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load env from both the repo root and backend/ so a single root `.env` works
# regardless of where the process is started. Later files override earlier ones,
# so a backend/.env (if present) takes precedence over the root .env.
_BACKEND_DIR = Path(__file__).resolve().parents[2]   # .../backend
_REPO_ROOT = _BACKEND_DIR.parent                     # repo root
_ENV_FILES = (str(_REPO_ROOT / ".env"), str(_BACKEND_DIR / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # ── Infra ──────────────────────────────────────────────────
    # SQLite works out of the box for local dev (no Postgres needed).
    # Override with a real DATABASE_URL in .env for staging/production.
    database_url: str = "sqlite+aiosqlite:///./vai.db"
    redis_url: str = "redis://localhost:6379/0"

    # ── LiveKit ────────────────────────────────────────────────
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # ── Deepgram (STT) ─────────────────────────────────────────
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"

    # ── OpenAI (LLM) ───────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"
    openai_base_url: str = "https://api.openai.com/v1"

    # ── Cartesia (English TTS) ─────────────────────────────────
    cartesia_api_key: str = ""
    cartesia_model: str = "sonic-2"
    cartesia_version: str = "2024-11-13"

    # ── Sarvam (Indian-language TTS) ───────────────────────────
    sarvam_api_key: str = ""
    sarvam_model: str = "bulbul:v2"

    # ── Audio ──────────────────────────────────────────────────
    audio_sample_rate: int = 24000

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def provider_status(self) -> dict[str, bool]:
        """Which external providers are configured (have credentials)."""
        return {
            "livekit": bool(self.livekit_api_key and self.livekit_api_secret and self.livekit_url),
            "deepgram": bool(self.deepgram_api_key),
            "openai": bool(self.openai_api_key),
            "cartesia": bool(self.cartesia_api_key),
            "sarvam": bool(self.sarvam_api_key),
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
