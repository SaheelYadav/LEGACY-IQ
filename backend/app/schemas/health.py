"""Pydantic v2 schemas for application and infrastructure health checks."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AppHealthResponse(BaseModel):
    """Response model for GET /api/v1/health."""

    status: Literal["healthy"] = "healthy"
    app_name: str
    environment: str
    version: str
    milestone: str = "M0"
    timestamp: datetime


class ServiceHealthResponse(BaseModel):
    """Response model for infrastructure dependency health checks."""

    status: Literal["healthy", "unhealthy", "unconfigured"]
    service: str
    latency_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

