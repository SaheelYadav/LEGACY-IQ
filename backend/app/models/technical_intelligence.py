"""Domain E: Technical, Data, API, Infrastructure & Runtime Intelligence models (9 Tables)."""

from datetime import datetime
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class DbSchema(Base, TenantScopedMixin):
    """E1. Discovered relational/NoSQL database schemas (`TENANT_DIRECT`)."""

    __tablename__ = "db_schemas"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "snapshot_id",
            "schema_name",
            name="uq_db_schemas_snap_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_db_schemas_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_db_schemas_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_db_schemas_artifact_version",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_artifact_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    db_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    discovery_source: Mapped[str] = mapped_column(String(32), nullable=False)


class DbTable(Base, TenantScopedMixin):
    """E2. Discovered database tables, views, or collections within a `db_schema` (`TENANT_DIRECT`)."""

    __tablename__ = "db_tables"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "db_schema_id",
            "table_name",
            name="uq_db_tables_schema_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_db_tables_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "db_schema_id"],
            ["db_schemas.tenant_id", "db_schemas.id"],
            ondelete="CASCADE",
            name="fk_db_tables_schema",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "mapped_orm_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_db_tables_orm_symbol",
        ),
    )

    db_schema_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    mapped_orm_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_kind: Mapped[str] = mapped_column(
        String(32), default="TABLE", server_default="TABLE", nullable=False
    )
    comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class DbColumn(Base, TenantScopedMixin):
    """E3. Columns belonging to a discovered `db_table` (`TENANT_DIRECT`)."""

    __tablename__ = "db_columns"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "db_table_id",
            "column_name",
            name="uq_db_columns_table_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_db_columns_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "db_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            ondelete="CASCADE",
            name="fk_db_columns_table",
        ),
    )

    db_table_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    is_nullable: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    is_primary_key: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    is_pii_candidate: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )


class DbForeignKey(Base, TenantScopedMixin):
    """E4. Explicit DDL foreign keys or ORM/naming-inferred table relationships (`TENANT_DIRECT`)."""

    __tablename__ = "db_foreign_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_db_foreign_keys_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            ondelete="CASCADE",
            name="fk_db_foreign_keys_source_table",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            ondelete="CASCADE",
            name="fk_db_foreign_keys_target_table",
        ),
    )

    source_table_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    target_table_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    constraint_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_column_names: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    target_column_names: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    relation_origin: Mapped[str] = mapped_column(String(32), nullable=False)


class ApiService(Base, TenantScopedMixin):
    """E5. Discovered HTTP/REST, GraphQL, gRPC, SOAP, or message consumer service boundaries (`TENANT_DIRECT`)."""

    __tablename__ = "api_services"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "snapshot_id",
            "service_name",
            name="uq_api_services_snap_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_api_services_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_api_services_snapshot",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    base_path: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ApiEndpoint(Base, TenantScopedMixin):
    """E6. Individual API operations/routes discovered via OpenAPI specs or controller annotations (`TENANT_DIRECT`)."""

    __tablename__ = "api_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "api_service_id",
            "http_method",
            "route_pattern",
            name="uq_api_endpoints_svc_method_route",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_api_endpoints_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "api_service_id"],
            ["api_services.tenant_id", "api_services.id"],
            ondelete="CASCADE",
            name="fk_api_endpoints_service",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "handler_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_api_endpoints_handler_symbol",
        ),
    )

    api_service_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    handler_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    http_method: Mapped[str] = mapped_column(String(16), nullable=False)
    route_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    auth_required_inferred: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    request_schema_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    response_schema_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class InfraResource(Base, TenantScopedMixin):
    """E7. Infrastructure-as-Code resources parsed from Dockerfiles, Compose, K8s, Terraform, or CloudFormation (`TENANT_DIRECT`)."""

    __tablename__ = "infra_resources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_infra_resources_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_infra_resources_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            ondelete="CASCADE",
            name="fk_infra_resources_artifact_version",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_artifact_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    iac_tool: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    configuration_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class DocSection(Base, TenantScopedMixin):
    """E8. Hierarchical sections parsed from Markdown, HTML, PDF, DOCX, XLSX, or manuals (`TENANT_DIRECT`)."""

    __tablename__ = "doc_sections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_doc_sections_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            ondelete="CASCADE",
            name="fk_doc_sections_artifact_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_section_id"],
            ["doc_sections.tenant_id", "doc_sections.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_doc_sections_parent",
        ),
    )

    artifact_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parent_section_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    heading_level: Mapped[int] = mapped_column(Integer, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)


class RuntimeObservation(Base, TenantScopedMixin):
    """E9. Optional ingested OpenTelemetry trace summaries, endpoint latency/error rates, or log patterns (`TENANT_DIRECT`)."""

    __tablename__ = "runtime_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_runtime_observations_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_runtime_observations_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["application_environments.tenant_id", "application_environments.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_runtime_observations_environment",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "linked_endpoint_id"],
            ["api_endpoints.tenant_id", "api_endpoints.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_runtime_observations_endpoint",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "linked_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_runtime_observations_symbol",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    linked_endpoint_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    linked_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    observation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    metric_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    observed_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

