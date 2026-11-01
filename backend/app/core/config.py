"""Application settings and environment validation using Pydantic v2."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent

PLACEHOLDER_TOKEN = "REPLACE_WITH_PASSWORD"
DEV_DEFAULT_SECRET_KEY = "dev-only-insecure-secret-key-change-in-production-32bytes"


def mask_connection_url(url: str) -> str:
    """Mask password in a connection URL so secrets are never logged."""
    if not url:
        return "<empty>"
    try:
        parts = urlsplit(url)
        if parts.password:
            user = parts.username or ""
            host = parts.hostname or "localhost"
            port = f":{parts.port}" if parts.port else ""
            auth = f"{user}:***" if user else ":***"
            netloc = f"{auth}@{host}{port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "<redacted-url>"
    return url


class Settings(BaseSettings):
    """Centralized configuration for LegacyIQ backend."""

    model_config = SettingsConfigDict(
        env_file=(
            str(ROOT_DIR / ".env"),
            str(ROOT_DIR / ".env.local"),
            str(BACKEND_DIR / ".env"),
            str(BACKEND_DIR / ".env.local"),
        ),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "LegacyIQ"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_DEBUG: bool = True
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    LOG_FORMAT: Literal["text", "json"] = "text"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Cryptographic Signing & Authentication
    APP_SECRET_KEY: str = DEV_DEFAULT_SECRET_KEY
    AUTH_TOKEN_EXPIRE_MINUTES: int = 60
    AUTH_ENFORCE_BEARER_TOKEN: bool = False

    # Database (PostgreSQL + pgvector)
    DATABASE_URL: str = (
        f"postgresql+psycopg://legacyiq_admin:{PLACEHOLDER_TOKEN}@localhost:5432/legacyiq"
    )
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_CONNECT_TIMEOUT_SECONDS: int = 3
    DB_STATEMENT_TIMEOUT_MS: int = 30000

    # Redis
    REDIS_URL: str = f"redis://:{PLACEHOLDER_TOKEN}@localhost:6380/0"
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 3.0

    # Storage & Archive Limits
    STORAGE_VAULT_ROOT: str = str(BACKEND_DIR / "storage_vault")
    MAX_ARCHIVE_COMPRESSED_MB: int = 50
    MAX_ARCHIVE_UNCOMPRESSED_MB: int = 150
    MAX_ARCHIVE_FILE_COUNT: int = 2500

    # Ollama Local Inference
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:3b"
    OLLAMA_TIMEOUT_SECONDS: float = 5.0

    # Local Embeddings
    EMBEDDING_PROVIDER: str = "sentence_transformers"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_DEVICE: str = "cpu"

    # AI Provider Routing
    AI_DEFAULT_PROVIDER: str = "ollama"
    AI_FALLBACK_PROVIDER: str = "openrouter"

    # Optional Future Cloud Providers
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "cohere/north-mini-code:free"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = ""

    # Security / CORS / Trusted Hosts / Rate Limiting
    BACKEND_CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    ALLOWED_HOSTS: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "*.legacyiq.internal"]
    )
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = 120
    RATE_LIMIT_EXPENSIVE_PER_MINUTE: int = 20

    @field_validator("BACKEND_CORS_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_string_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return list(json.loads(stripped))
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def is_database_configured(self) -> bool:
        """Return True only when DATABASE_URL is set without placeholder tokens."""
        return bool(self.DATABASE_URL) and PLACEHOLDER_TOKEN not in self.DATABASE_URL

    @property
    def is_redis_configured(self) -> bool:
        """Return True only when REDIS_URL is set without placeholder tokens."""
        return bool(self.REDIS_URL) and PLACEHOLDER_TOKEN not in self.REDIS_URL

    @property
    def is_secret_key_production_safe(self) -> bool:
        """Return True only when APP_SECRET_KEY is not the dev placeholder and is >= 32 chars."""
        return (
            bool(self.APP_SECRET_KEY)
            and self.APP_SECRET_KEY != DEV_DEFAULT_SECRET_KEY
            and PLACEHOLDER_TOKEN not in self.APP_SECRET_KEY
            and len(self.APP_SECRET_KEY) >= 32
        )

    def validate_production_readiness(self) -> list[str]:
        """
        Validate mandatory production configuration invariants.
        Returns a list of human-readable configuration errors (empty when valid).
        Raises RuntimeError when called via `assert_production_ready()` in `APP_ENV == 'production'`.
        """
        errors: list[str] = []
        if self.APP_ENV == "production":
            if self.APP_DEBUG:
                errors.append("APP_DEBUG must be false when APP_ENV='production'.")
            if not self.is_database_configured:
                errors.append(
                    "DATABASE_URL is missing or contains placeholder token REPLACE_WITH_PASSWORD."
                )
            if not self.is_redis_configured:
                errors.append(
                    "REDIS_URL is missing or contains placeholder token REPLACE_WITH_PASSWORD."
                )
            if not self.is_secret_key_production_safe:
                errors.append(
                    "APP_SECRET_KEY must be set to a unique secret of at least 32 characters in production."
                )
            if not self.BACKEND_CORS_ORIGINS or "*" in self.BACKEND_CORS_ORIGINS:
                errors.append(
                    "BACKEND_CORS_ORIGINS must specify explicit allowed origins (wildcard '*' is forbidden in production)."
                )
            if not self.ALLOWED_HOSTS or "*" in self.ALLOWED_HOSTS:
                errors.append(
                    "ALLOWED_HOSTS must specify explicit allowed hostnames (wildcard '*' is forbidden in production)."
                )
        return errors

    def assert_production_ready(self) -> None:
        """Fail fast at startup if APP_ENV=='production' and mandatory settings are unsafe."""
        errors = self.validate_production_readiness()
        if errors:
            joined = "; ".join(errors)
            raise RuntimeError(f"Production configuration validation failed: {joined}")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


settings = get_settings()

