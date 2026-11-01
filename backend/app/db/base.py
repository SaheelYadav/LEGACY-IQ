"""SQLAlchemy 2.0 Declarative Base and foundational multi-tenant mixins."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative Base class for all SQLAlchemy 2.0 models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAtMixin:
    """Standard created_at audit column for immutable or append-only tables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    """Standard created_at / updated_at audit columns."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """
    Composite primary key mixin (tenant_id, id) for all 64 TENANT_DIRECT tables.
    Prevents cross-tenant foreign key references at the PostgreSQL DDL level.
    """

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, nullable=False)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, nullable=False)
