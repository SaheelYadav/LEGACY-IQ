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

    # Database (PostgreSQL + pgvector)
    DATABASE_URL: str = (
        f"postgresql+psycopg://legacyiq_admin:{PLACEHOLDER_TOKEN}@localhost:5432/legacyiq"
    )
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_CONNECT_TIMEOUT_SECONDS: int = 3

    # Redis
    REDIS_URL: str = f"redis://:{PLACEHOLDER_TOKEN}@localhost:6380/0"
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 3.0

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

    # Security / CORS
    BACKEND_CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return list(json.loads(stripped))
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @property
    def is_database_configured(self) -> bool:
        """Return True only when DATABASE_URL is set without placeholder tokens."""
        return bool(self.DATABASE_URL) and PLACEHOLDER_TOKEN not in self.DATABASE_URL

    @property
    def is_redis_configured(self) -> bool:
        """Return True only when REDIS_URL is set without placeholder tokens."""
        return bool(self.REDIS_URL) and PLACEHOLDER_TOKEN not in self.REDIS_URL


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


settings = get_settings()

