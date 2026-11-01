"""SQLAlchemy 2.0 engine, session management, RLS transaction contexts, and PostgreSQL/pgvector health checks."""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def build_engine() -> Engine:
    """Create a SQLAlchemy 2.0 engine with safe timeouts and connection pooling."""
    connect_args: dict[str, Any] = {
        "connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
    }
    if settings.DB_STATEMENT_TIMEOUT_MS > 0:
        connect_args["options"] = f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}"
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
        pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
        connect_args=connect_args,
    )


engine: Engine = build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def activate_tenant_rls(db: Session, tenant_id: uuid.UUID | str | None) -> None:
    """
    Activate PostgreSQL non-superuser application role (`legacyiq_app`) and bind
    `app.current_tenant_id` for the current transaction (`SET LOCAL` / `is_local=true`).
    Because both settings are transaction-local, they automatically reset on COMMIT or
    ROLLBACK, preventing pooled connection state bleed across requests.
    """
    db.execute(text("SET LOCAL ROLE legacyiq_app"))
    tid_str = str(uuid.UUID(str(tenant_id))) if tenant_id is not None else ""
    db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": tid_str},
    )


def activate_unscoped_rls_role(db: Session) -> None:
    """
    Switch to `legacyiq_app` with an empty `app.current_tenant_id` for the current
    transaction. Used for verifying fail-closed RLS behavior when tenant context is missing.
    """
    db.execute(text("SET LOCAL ROLE legacyiq_app"))
    db.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))


@contextmanager
def tenant_db_session(tenant_id: uuid.UUID | str) -> Generator[Session, None, None]:
    """
    Transactional context manager that opens a database session, activates
    `legacyiq_app` RLS scoping for `tenant_id`, commits on clean exit, and rolls back on error.
    """
    db = SessionLocal()
    try:
        activate_tenant_rls(db, tenant_id)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_and_pgvector_health() -> dict[str, Any]:
    """
    Perform a truthful PostgreSQL and pgvector extension readiness probe.
    Never returns healthy if credentials are missing or connection fails.
    """
    if not settings.is_database_configured:
        return {
            "status": "unconfigured",
            "service": "postgresql",
            "latency_ms": None,
            "details": {
                "host": "localhost:5432",
                "database": "legacyiq",
                "embedding_dimension_target": settings.EMBEDDING_DIMENSION,
            },
            "error": (
                "DATABASE_URL contains placeholder credentials (REPLACE_WITH_PASSWORD). "
                "Please configure actual credentials in backend/.env."
            ),
        }

    start = time.perf_counter()
    try:
        probe_engine = build_engine()
        with probe_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

            installed_row = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()

            available_row = conn.execute(
                text(
                    "SELECT default_version FROM pg_available_extensions WHERE name = 'vector'"
                )
            ).fetchone()

        probe_engine.dispose()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        return {
            "status": "healthy",
            "service": "postgresql",
            "latency_ms": latency_ms,
            "details": {
                "database": "legacyiq",
                "pgvector_installed": installed_row is not None,
                "pgvector_installed_version": installed_row[0] if installed_row else None,
                "pgvector_available": available_row is not None,
                "pgvector_available_version": available_row[0] if available_row else None,
                "embedding_dimension_target": settings.EMBEDDING_DIMENSION,
            },
            "error": None,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "unhealthy",
            "service": "postgresql",
            "latency_ms": latency_ms,
            "details": {"database": "legacyiq"},
            "error": f"{type(exc).__name__}: {str(exc)}",
        }
