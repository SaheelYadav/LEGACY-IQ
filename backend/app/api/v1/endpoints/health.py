"""Health check endpoints for LegacyIQ backend and external infrastructure."""

from fastapi import APIRouter, Response, status

from app.schemas.health import AppHealthResponse, ServiceHealthResponse
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    response_model=AppHealthResponse,
    summary="Check core backend application status",
)
def check_app_health() -> AppHealthResponse:
    """Return basic backend status and environment readiness."""
    return HealthService.get_app_health()


@router.get(
    "/database",
    response_model=ServiceHealthResponse,
    summary="Check PostgreSQL and pgvector connectivity",
)
def check_database_health(response: Response) -> ServiceHealthResponse:
    """
    Verify actual PostgreSQL connectivity and pgvector readiness.
    Returns HTTP 503 when credentials are unconfigured or connection fails.
    """
    result = HealthService.get_database_health()
    if result.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/redis",
    response_model=ServiceHealthResponse,
    summary="Check Redis connectivity",
)
def check_redis_health_endpoint(response: Response) -> ServiceHealthResponse:
    """
    Verify actual Redis connectivity via PING.
    Returns HTTP 503 when credentials are unconfigured or connection fails.
    """
    result = HealthService.get_redis_health()
    if result.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/ollama",
    response_model=ServiceHealthResponse,
    summary="Check local Ollama API reachability",
)
def check_ollama_health_endpoint(response: Response) -> ServiceHealthResponse:
    """
    Verify actual reachability of the local Ollama API and model readiness.
    Returns HTTP 503 when Ollama is unreachable.
    """
    result = HealthService.get_ollama_health()
    if result.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/storage",
    response_model=ServiceHealthResponse,
    summary="Check object storage vault and disk space readiness",
)
def check_storage_health_endpoint(response: Response) -> ServiceHealthResponse:
    """Verify tenant-isolated storage vault accessibility and disk capacity."""
    result = HealthService.get_storage_health()
    if result.status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/readiness",
    summary="Composite production readiness probe (Database, Redis, Storage, Ollama, Config)",
)
def check_production_readiness_endpoint(response: Response) -> dict[str, object]:
    """Return composite readiness status across all critical dependencies."""
    summary = HealthService.get_readiness_summary()
    if summary["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return summary


