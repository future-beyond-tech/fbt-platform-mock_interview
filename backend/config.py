"""
InterVu — centralised configuration.

All environment variables are declared here as typed fields on `settings`
(a pydantic-settings BaseSettings instance).  The helper functions below
are thin wrappers kept for backward-compatibility with existing callers in
main.py and providers.py — no other file needs to change.

Precedence (highest → lowest):
    process environment  >  project-root .env  >  backend/.env
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Paths ────────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)

# ── Provider → env-var name mapping (used by has_server_key / resolve_api_key) ──
SERVER_KEY_ENV_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


# ── Settings model ────────────────────────────────────────────────────────────
class Settings(BaseSettings):
    """All runtime configuration for InterVu.

    Field names map 1-to-1 to environment variable names (case-insensitive).
    """

    model_config = SettingsConfigDict(
        # Load both .env files; project root takes precedence over backend/.env
        env_file=[
            str(_BACKEND_DIR / ".env"),   # lower priority
            str(_PROJECT_ROOT / ".env"),  # higher priority
        ],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM provider API keys ──────────────────────────────────────────────
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Ollama ─────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    # ── App behaviour ──────────────────────────────────────────────────────
    default_provider: str = "ollama"
    session_store: str = "memory"          # "memory" | "sqlite"
    sqlite_db_path: str = "intervu.db"
    max_interview_sessions: int = 100

    # ── CORS ───────────────────────────────────────────────────────────────
    backend_cors_origins: str = ",".join(_DEFAULT_CORS_ORIGINS)

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return (v or "").strip()


# Singleton — import this wherever you need a config value.
settings = Settings()


# ── Backward-compatible helpers ───────────────────────────────────────────────
# These preserve the public API that main.py and providers.py already use,
# so those files require zero edits.

def get_cors_origins(
    *,
    env: Mapping[str, str] | None = None,           # kept for signature compat
    project_env_path: object = None,                # kept for signature compat
    backend_env_path: object = None,                # kept for signature compat
) -> list[str]:
    """Return the CORS origin list from settings."""
    raw = settings.backend_cors_origins
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def has_server_key(
    provider_id: str,
    *,
    env: Mapping[str, str] | None = None,           # kept for signature compat
    project_env_path: object = None,
    backend_env_path: object = None,
) -> bool:
    """Return True if a server-side API key is configured for *provider_id*."""
    field = SERVER_KEY_ENV_VARS.get(provider_id, "").lower().replace("_api_key", "_api_key")
    # Map e.g. "GEMINI_API_KEY" → settings.gemini_api_key
    attr = field.lower() if field else ""
    value: str = getattr(settings, attr, "") if attr else ""
    return bool(value.strip())


def get_config_value(
    name: str,
    default: str = "",
    *,
    env: Mapping[str, str] | None = None,           # kept for signature compat
    project_env_path: object = None,
    backend_env_path: object = None,
) -> str:
    """Retrieve a config value by env-var name.

    Tries settings first (covers all declared fields), then falls back
    to `default`.  This preserves the lookup behaviour that providers.py
    relies on for arbitrary key names like ``GEMINI_API_KEY``.
    """
    attr = name.lower()
    # Direct attribute match on settings (e.g. "GEMINI_API_KEY" → gemini_api_key)
    if hasattr(settings, attr):
        return str(getattr(settings, attr))

    # Fallback: check the live process environment (covers vars not declared
    # as fields, e.g. custom deployment vars).
    import os
    return os.environ.get(name, default)
