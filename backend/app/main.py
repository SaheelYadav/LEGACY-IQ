"""LegacyIQ FastAPI Application Entry Point (Waves 1–7 Production Hardened Platform)."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator, Callable
import uuid

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import mask_connection_url, settings
from app.core.logging import configure_logging, correlation_id_ctx
from app.core.security import rate_limiter
from app.db.session import engine

configure_logging(
    debug=settings.APP_DEBUG,
    log_format=settings.LOG_FORMAT,
    log_level=settings.LOG_LEVEL,
)
logger = logging.getLogger("legacyiq.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate configuration on startup without logging secrets, and dispose pools on shutdown."""
    settings.assert_production_ready()
    logger.info(
        "Starting %s v%s (env=%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
    )
    logger.info(
        "Database target: %s (configured=%s)",
        mask_connection_url(settings.DATABASE_URL),
        settings.is_database_configured,
    )
    logger.info(
        "Redis target: %s (configured=%s)",
        mask_connection_url(settings.REDIS_URL),
        settings.is_redis_configured,
    )
    logger.info(
        "Ollama target: %s (model=%s)",
        settings.OLLAMA_BASE_URL,
        settings.OLLAMA_MODEL,
    )
    yield
    logger.info("Shutting down %s and disposing database connection pool", settings.APP_NAME)
    engine.dispose()


def create_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    is_prod = settings.APP_ENV == "production" and not settings.APP_DEBUG
    application = FastAPI(
        title=settings.APP_NAME,
        description=(
            "AI-powered Legacy Application Discovery & Requirements Intelligence Platform "
            "(Waves 1–7 Enterprise Multi-Tenant SaaS)"
        ),
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    if settings.ALLOWED_HOSTS:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Tenant-Id",
            "X-User-Id",
            "X-Correlation-Id",
        ],
        expose_headers=["X-Correlation-Id", "X-RateLimit-Remaining"],
    )

    @application.middleware("http")
    async def security_and_correlation_middleware(
        request: Request, call_next: Callable[[Request], AsyncGenerator[Response, None]]
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        token_ctx = correlation_id_ctx.set(correlation_id)
        try:
            # Apply sliding-window rate limiting when enabled
            rate_remaining: int | None = None
            if settings.RATE_LIMIT_ENABLED and not request.url.path.startswith(
                f"{settings.API_V1_PREFIX}/health"
            ):
                client_host = request.client.host if request.client else "local"
                tenant_hdr = request.headers.get("X-Tenant-Id") or client_host
                path_lower = request.url.path.lower()
                is_expensive = any(
                    seg in path_lower
                    for seg in (
                        "/upload-zip",
                        "/analyze",
                        "/qa/",
                        "/reports/generate",
                        "/exports",
                        "/bootstrap",
                        "/auth/token",
                    )
                )
                bucket_type = "expensive" if is_expensive else "default"
                limit_val = (
                    settings.RATE_LIMIT_EXPENSIVE_PER_MINUTE
                    if is_expensive
                    else settings.RATE_LIMIT_DEFAULT_PER_MINUTE
                )
                allowed, rate_remaining = rate_limiter.check_rate_limit(
                    f"{tenant_hdr}:{bucket_type}", limit=limit_val
                )
                if not allowed:
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": "Rate limit exceeded. Please retry after 60 seconds.",
                            "correlation_id": correlation_id,
                        },
                        headers={
                            "X-Correlation-Id": correlation_id,
                            "Retry-After": "60",
                        },
                    )

            response: Response = await call_next(request)  # type: ignore[assignment]
            response.headers["X-Correlation-Id"] = correlation_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            if rate_remaining is not None:
                response.headers["X-RateLimit-Remaining"] = str(rate_remaining)
            return response
        finally:
            correlation_id_ctx.reset(token_ctx)

    @application.exception_handler(Exception)
    async def sanitized_unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None) or correlation_id_ctx.get()
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error. Reference the correlation_id for diagnostics.",
                "correlation_id": correlation_id,
            },
            headers={"X-Correlation-Id": correlation_id},
        )

    application.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
    return application


app = create_application()

