"""Health verification service coordinating PostgreSQL, Redis, and Ollama probes."""

from datetime import datetime, timezone

from app.core.config import settings
from app.db.redis import check_redis_health
from app.db.session import check_database_and_pgvector_health
from app.integrations.llm import OllamaProvider
from app.schemas.health import AppHealthResponse, ServiceHealthResponse


class HealthService:
    """Executes truthful connectivity probes against local infrastructure."""

    @staticmethod
    def get_app_health() -> AppHealthResponse:
        return AppHealthResponse(
            status="healthy",
            app_name=settings.APP_NAME,
            environment=settings.APP_ENV,
            version=settings.APP_VERSION,
            milestone="M0",
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def get_database_health() -> ServiceHealthResponse:
        result = check_database_and_pgvector_health()
        return ServiceHealthResponse(**result)

    @staticmethod
    def get_redis_health() -> ServiceHealthResponse:
        result = check_redis_health()
        return ServiceHealthResponse(**result)

    @staticmethod
    def get_ollama_health() -> ServiceHealthResponse:
        provider = OllamaProvider()
        result = provider.check_health()
        return ServiceHealthResponse(**result)

