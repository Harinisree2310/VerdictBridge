"""
VerdictBridge – Application Configuration
All settings are loaded from environment variables / .env file.
"""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ────────────────────────────────────────────────────────────────────
    app_name: str = "VerdictBridge"
    debug: bool = False
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_32_CHAR_MIN"
    access_token_expire_minutes: int = 480  # 8 hours for government shift

    # ── Database ───────────────────────────────────────────────────────────────
    # Defaults to SQLite for zero-install local development.
    # Switch to postgresql://user:pass@localhost:5432/verdictbridge for production.
    database_url: str = "sqlite:///./verdictbridge.db"

    # ── Redis / Celery ─────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── File storage ───────────────────────────────────────────────────────────
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 50

    # ── OCR ────────────────────────────────────────────────────────────────────
    tesseract_cmd: str = "tesseract"
    ocr_language: str = "eng+kan"          # English + Kannada for Karnataka courts
    ocr_fallback_min_chars: int = 150      # chars below which OCR is triggered

    # ── LLM – Claude (primary) ─────────────────────────────────────────────────
    anthropic_api_key: str = ""
    claude_model: str = "claude-3-5-sonnet-20241022"
    claude_max_tokens: int = 4096

    # ── LLM – Gemini (fallback / PDF-native) ──────────────────────────────────
    google_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"

    # ── LLM – OpenAI (tertiary fallback) ──────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # ── PII masking ────────────────────────────────────────────────────────────
    pii_masking_enabled: bool = True

    # ── Deadline alerts ────────────────────────────────────────────────────────
    deadline_red_alert_days: int = 14      # raise red alert within N days
    default_appeal_days: int = 90          # Karnataka HC default appeal window

    @field_validator("anthropic_api_key", "google_api_key", "openai_api_key", mode="before")
    @classmethod
    def _strip_quotes(cls, v: str) -> str:
        """Strip surrounding single/double quotes that some .env editors add."""
        if isinstance(v, str):
            return v.strip().strip('"').strip("'")
        return v

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins.
    # Defaults cover all common local dev ports.
    # Override in production: CORS_ORIGINS=https://verdictbridge.gov.in
    cors_origins: str = (
        "http://localhost:3000,"
        "http://localhost:3001,"
        "http://localhost:5173,"
        "http://localhost:5174,"
        "http://localhost:5175,"
        "http://localhost:8080,"
        "http://127.0.0.1:3000,"
        "http://127.0.0.1:5173,"
        "http://127.0.0.1:5174,"
        "http://127.0.0.1:8080"
    )

    # ── Audit log ──────────────────────────────────────────────────────────────
    audit_chain_enabled: bool = True       # SHA-256 chained tamper-evident log

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins string into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """
    Clear the lru_cache and reload Settings from .env.
    Call this after changing .env values at runtime so the new
    API keys / config are picked up without a server restart.
    """
    get_settings.cache_clear()
    return get_settings()
