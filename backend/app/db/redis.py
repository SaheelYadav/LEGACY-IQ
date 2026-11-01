"""Redis connection management and truthful PING health check."""

import time
from typing import Any

import redis

from app.core.config import settings


def get_redis_client() -> redis.Redis:
    """Create a Redis client configured with strict connection timeouts."""
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
    )


def check_redis_health() -> dict[str, Any]:
    """
    Perform a truthful Redis connectivity check using PING.
    Never returns healthy if credentials are missing or connection fails.
    """
    if not settings.is_redis_configured:
        return {
            "status": "unconfigured",
            "service": "redis",
            "latency_ms": None,
            "details": {
                "host": "localhost:6380",
            },
            "error": (
                "REDIS_URL contains placeholder credentials (REPLACE_WITH_PASSWORD). "
                "Please configure actual credentials in backend/.env."
            ),
        }

    start = time.perf_counter()
    client: redis.Redis | None = None
    try:
        client = get_redis_client()
        pong = bool(client.ping())
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if not pong:
            return {
                "status": "unhealthy",
                "service": "redis",
                "latency_ms": latency_ms,
                "details": {"ping_response": False},
                "error": "Redis PING did not return True.",
            }
        return {
            "status": "healthy",
            "service": "redis",
            "latency_ms": latency_ms,
            "details": {
                "ping": "PONG",
                "host": "localhost:6380",
            },
            "error": None,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "unhealthy",
            "service": "redis",
            "latency_ms": latency_ms,
            "details": {"host": "localhost:6380"},
            "error": f"{type(exc).__name__}: {str(exc)}",
        }
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

