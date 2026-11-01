"""Domain C: Source Connectors & Immutable Ingestion SQLAlchemy 2.0 models (8 Tables)."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantScopedMixin


class SourceConnector(Base, TenantScopedMixin, CreatedAtMixin):
    """C1. External source connector metadata and secret reference (`TENANT_DIRECT`)."""

    __tablename__ = "source_connectors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_source_connectors_name"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_source_connectors_tenant",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_credentials_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="ACTIVE", server_default="ACTIVE", nullable=False
    )


class Repository(Base, TenantScopedMixin, CreatedAtMixin):
    """C2. Source code repository or archive stream linked to an application (`TENANT_DIRECT`)."""

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "application_id", "name", name="uq_repositories_app_name"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_repositories_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_repositories_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "connector_id"],
            ["source_connectors.tenant_id", "source_connectors.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_repositories_connector",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    connector_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(
        String(128), default="main", server_default="main", nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="REGISTERED", server_default="REGISTERED", nullable=False
    )


class RepositoryBranch(Base, TenantScopedMixin):
    """C3. Discovered branch within a repository (`TENANT_DIRECT`)."""

    __tablename__ = "repository_branches"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "repository_id",
            "branch_name",
            name="uq_repo_branches_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_repo_branches_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            ondelete="CASCADE",
            name="fk_repo_branches_repository",
        ),
    )

    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    head_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )


class RepositoryCommit(Base, TenantScopedMixin):
    """C4. Immutable Git commit metadata (`TENANT_DIRECT`)."""

    __tablename__ = "repository_commits"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "repository_id",
            "commit_sha",
            name="uq_repo_commits_sha",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_repo_commits_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            ondelete="CASCADE",
            name="fk_repo_commits_repository",
        ),
    )

    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class RepositorySnapshot(Base, TenantScopedMixin):
    """C5. Immutable point-in-time repository or archive snapshot (`TENANT_DIRECT`)."""

    __tablename__ = "repository_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "repository_id",
            "snapshot_number",
            name="ux_snapshots_repo_num",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_repo_snapshots_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            ondelete="CASCADE",
            name="fk_repo_snapshots_repository",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["repository_branches.tenant_id", "repository_branches.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_repo_snapshots_branch",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "commit_id"],
            ["repository_commits.tenant_id", "repository_commits.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_repo_snapshots_commit",
        ),
    )

    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    commit_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    snapshot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tree_or_archive_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    total_files_count: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    total_bytes_size: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    legal_hold_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="CREATING", server_default="CREATING", nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    @property
    def snapshot_label(self) -> str:
        """Human-readable label for the immutable snapshot."""
        return f"snapshot-{self.snapshot_number}"


class Artifact(Base, TenantScopedMixin, CreatedAtMixin):
    """C6. Logical artifact identity across snapshots (`TENANT_DIRECT`)."""

    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "repository_id",
            "canonical_path",
            name="uq_artifacts_app_repo_path",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_artifacts_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_artifacts_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_artifacts_repository",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    repository_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    artifact_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_path: Mapped[str] = mapped_column(Text, nullable=False)


class ArtifactVersion(Base, TenantScopedMixin, CreatedAtMixin):
    """C7. Immutable content-addressed version of an artifact (`TENANT_DIRECT`)."""

    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "artifact_id",
            "content_sha256",
            name="uq_artifact_versions_sha256",
        ),
        Index("ix_artifact_versions_sha256", "tenant_id", "content_sha256"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_artifact_versions_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "artifact_id"],
            ["artifacts.tenant_id", "artifacts.id"],
            ondelete="CASCADE",
            name="fk_artifact_versions_artifact",
        ),
    )

    artifact_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoding: Mapped[str] = mapped_column(
        String(32), default="utf-8", server_default="utf-8", nullable=False
    )
    mime_type: Mapped[str] = mapped_column(
        String(128), default="text/plain", server_default="text/plain", nullable=False
    )
    storage_object_uri: Mapped[str] = mapped_column(Text, nullable=False)


class IngestionJob(Base, TenantScopedMixin):
    """C8. Background or synchronous repository/archive ingestion job (`TENANT_DIRECT`)."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_ingestion_jobs_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            ondelete="CASCADE",
            name="fk_ingestion_jobs_repository",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_ingestion_jobs_snapshot",
        ),
        ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_ingestion_jobs_user",
        ),
    )

    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="QUEUED", server_default="QUEUED", nullable=False
    )
    stats_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

