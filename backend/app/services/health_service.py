"""Health verification service coordinating PostgreSQL, Redis, and Ollama probes."""

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.redis import check_redis_health
from app.db.session import check_database_and_pgvector_health
from app.integrations.llm import OllamaProvider
from app.integrations.storage import TenantObjectStorage
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

    @staticmethod
    def get_storage_health() -> ServiceHealthResponse:
        storage = TenantObjectStorage()
        result = storage.get_storage_metrics()
        return ServiceHealthResponse(**result)

    @staticmethod
    def get_readiness_summary() -> dict[str, Any]:
        """
        Composite production readiness probe evaluating PostgreSQL + pgvector,
        Redis, Storage Vault, Ollama inference (with deterministic fallback),
        and production configuration validation.
        """
        db_h = HealthService.get_database_health()
        redis_h = HealthService.get_redis_health()
        storage_h = HealthService.get_storage_health()
        ollama_h = HealthService.get_ollama_health()
        config_errors = settings.validate_production_readiness()

        core_ready = (
            db_h.status == "healthy"
            and redis_h.status == "healthy"
            and storage_h.status == "healthy"
            and len(config_errors) == 0
        )
        return {
            "status": "ready" if core_ready else "degraded",
            "app_name": settings.APP_NAME,
            "environment": settings.APP_ENV,
            "version": settings.APP_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "database": db_h.model_dump(),
                "redis": redis_h.model_dump(),
                "storage": storage_h.model_dump(),
                "ollama": {
                    **ollama_h.model_dump(),
                    "deterministic_fallback_enabled": True,
                },
            },
            "configuration_errors": config_errors,
        }


