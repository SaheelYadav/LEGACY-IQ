"""Domain B: Workspace, Project & Application Management SQLAlchemy 2.0 models (6 Tables)."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TenantScopedMixin


class Workspace(Base, TenantScopedMixin, CreatedAtMixin):
    """B1. Logical business unit or client engagement boundary (`TENANT_DIRECT`)."""

    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_workspaces_tenant_slug"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_workspaces_tenant",
        ),
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    projects: Mapped[list["Project"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        overlaps="workspace",
    )


class Project(Base, TenantScopedMixin, CreatedAtMixin):
    """B2. Discovery or modernization initiative grouping applications (`TENANT_DIRECT`)."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_id", "key", name="ux_projects_workspace_key"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_projects_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id"],
            ["workspaces.tenant_id", "workspaces.id"],
            ondelete="CASCADE",
            name="fk_projects_workspace",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default="ACTIVE", server_default="ACTIVE", nullable=False
    )
    legal_hold_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(
        back_populates="projects",
        foreign_keys="[Project.tenant_id, Project.workspace_id]",
        overlaps="projects",
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        overlaps="project",
    )


class ProjectMembership(Base, TenantScopedMixin):
    """B3. Project-level RBAC access assignment (`TENANT_DIRECT`)."""

    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "org_membership_id",
            name="uq_project_memberships_member",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_project_memberships_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_project_memberships_project",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "org_membership_id"],
            ["organization_memberships.tenant_id", "organization_memberships.id"],
            ondelete="CASCADE",
            name="fk_project_memberships_org_member",
        ),
        ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            ondelete="RESTRICT",
            name="fk_project_memberships_role",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    org_membership_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class Application(Base, TenantScopedMixin, CreatedAtMixin):
    """B4. Bounded legacy software application under analysis (`TENANT_DIRECT`)."""

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "code", name="ux_applications_proj_code"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_applications_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_applications_project",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    architecture_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criticality_tier: Mapped[str] = mapped_column(
        String(32), default="TIER_2", server_default="TIER_2", nullable=False
    )
    primary_languages: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )

    project: Mapped["Project"] = relationship(
        back_populates="applications",
        foreign_keys="[Application.tenant_id, Application.project_id]",
        overlaps="applications",
    )


class ApplicationEnvironment(Base, TenantScopedMixin):
    """B5. Deployment environment for an application (`TENANT_DIRECT`)."""

    __tablename__ = "application_environments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "env_name",
            name="uq_app_environments_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_app_environments_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_app_environments_application",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    env_name: Mapped[str] = mapped_column(String(64), nullable=False)
    env_type: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class AnalysisScope(Base, TenantScopedMixin):
    """B6. File glob filters, parser toggles, and size thresholds (`TENANT_DIRECT`)."""

    __tablename__ = "analysis_scopes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "name",
            name="uq_analysis_scopes_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_analysis_scopes_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_analysis_scopes_application",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    include_globs: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: ["**/*"],
        server_default='["**/*"]',
        nullable=False,
    )
    exclude_globs: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: ["**/node_modules/**", "**/vendor/**", "**/.git/**", "**/__pycache__/**"],
        server_default='["**/node_modules/**","**/vendor/**","**/.git/**","**/__pycache__/**"]',
        nullable=False,
    )
    language_parsers_enabled: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: ["python", "java", "javascript", "typescript", "php"],
        server_default='["python","java","javascript","typescript","php"]',
        nullable=False,
    )
    max_file_size_bytes: Mapped[int] = mapped_column(
        Integer, default=5242880, server_default="5242880", nullable=False
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

