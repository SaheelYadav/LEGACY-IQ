"""Domain A: Identity and Multi-Tenancy SQLAlchemy 2.0 models (8 Tables)."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TenantScopedMixin, TimestampMixin


class Organization(Base, TimestampMixin):
    """A1. Root tenant entity (`TENANT_ROOT`)."""

    __tablename__ = "organizations"
    __table_args__ = (
        Index("ix_organizations_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="FREE", server_default="FREE", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="ACTIVE", server_default="ACTIVE", nullable=False
    )
    kms_key_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    legal_hold_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class User(Base, CreatedAtMixin):
    """A2. Global user identity (`GLOBAL_SYSTEM`)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_provider", "external_subject_id", name="uq_users_provider_subject"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_provider: Mapped[str] = mapped_column(
        String(32), default="LOCAL", server_default="LOCAL", nullable=False
    )
    external_subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="user",
    )


class Role(Base):
    """A6. RBAC Role definition (`HYBRID_CATALOG` — tenant_id NULL for system roles)."""

    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_system_role: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )


class Permission(Base):
    """A7. Global fine-grained permission catalog (`GLOBAL_SYSTEM`)."""

    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, nullable=False)
    code: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    """A8. Role-to-permission join (`GLOBAL_SYSTEM`)."""

    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    permission_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    role: Mapped["Role"] = relationship(back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship()


class OrganizationMembership(Base, TenantScopedMixin):
    """A3. Binds a global user to a tenant organization with a role (`TENANT_DIRECT`)."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="ux_org_members_tenant_user"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_org_memberships_tenant",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_org_memberships_user",
        ),
        ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            ondelete="RESTRICT",
            name="fk_org_memberships_role",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="ACTIVE", server_default="ACTIVE", nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")
    role: Mapped["Role"] = relationship()


class Team(Base, TenantScopedMixin, CreatedAtMixin):
    """A4. Tenant-scoped engineering or consulting team (`TENANT_DIRECT`)."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_teams_tenant",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class TeamMembership(Base, TenantScopedMixin):
    """A5. Join between teams and organization_memberships (`TENANT_DIRECT`)."""

    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "team_id",
            "org_membership_id",
            name="uq_team_memberships_member",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_team_memberships_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["teams.tenant_id", "teams.id"],
            ondelete="CASCADE",
            name="fk_team_memberships_team",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "org_membership_id"],
            ["organization_memberships.tenant_id", "organization_memberships.id"],
            ondelete="CASCADE",
            name="fk_team_memberships_org_member",
        ),
    )

    team_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    org_membership_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

