"""LegacyIQ FastAPI Application Entry Point (Wave 1 Core Platform & Source Intelligence)."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator, Callable
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import mask_connection_url, settings
from app.core.logging import configure_logging

configure_logging(debug=settings.APP_DEBUG)
logger = logging.getLogger("legacyiq.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate configuration on startup without logging secrets."""
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
    logger.info("Shutting down %s", settings.APP_NAME)


def create_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.APP_NAME,
        description=(
            "AI-powered Legacy Application Discovery & Requirements Intelligence Platform "
            "(Wave 1 Core Platform, Database Foundation & Source Intelligence)"
        ),
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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
        expose_headers=["X-Correlation-Id"],
    )

    @application.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: Callable[[Request], AsyncGenerator[Response, None]]
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response: Response = await call_next(request)  # type: ignore[assignment]
        response.headers["X-Correlation-Id"] = correlation_id
        return response

    application.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
    return application


app = create_application()
