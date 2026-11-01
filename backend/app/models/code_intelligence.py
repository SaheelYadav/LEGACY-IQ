"""Domain I (`analysis_runs`) & Domain D: Deterministic Code Intelligence models (8 Tables)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class AnalysisRun(Base, TenantScopedMixin):
    """I1. Versioned execution record for static parsing, embeddings, and AI passes (`TENANT_DIRECT`)."""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "run_number",
            name="uq_analysis_runs_app_num",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_analysis_runs_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_analysis_runs_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_analysis_runs_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_scope_id"],
            ["analysis_scopes.tenant_id", "analysis_scopes.id"],
            ondelete="RESTRICT",
            name="fk_analysis_runs_scope",
        ),
        ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_analysis_runs_user",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    run_mode: Mapped[str] = mapped_column(
        String(32), default="FULL_DISCOVERY", server_default="FULL_DISCOVERY", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="QUEUED", server_default="QUEUED", nullable=False
    )
    pipeline_versions_manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CodeModule(Base, TenantScopedMixin):
    """D1. Language package, namespace, directory, or module (`TENANT_DIRECT`)."""

    __tablename__ = "code_modules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "snapshot_id",
            "language",
            "qualified_name",
            name="uq_code_modules_snap_lang_qname",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_code_modules_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_code_modules_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_module_id"],
            ["code_modules.tenant_id", "code_modules.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_code_modules_parent",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    module_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_module_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class CodeFile(Base, TenantScopedMixin):
    """D2. Snapshot file bound to an immutable artifact_version_id (`TENANT_DIRECT`)."""

    __tablename__ = "code_files"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "snapshot_id",
            "relative_path",
            name="ux_code_files_snap_path",
        ),
        Index("ix_code_files_artifact_ver", "tenant_id", "artifact_version_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_code_files_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_code_files_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            ondelete="RESTRICT",
            name="fk_code_files_artifact_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "module_id"],
            ["code_modules.tenant_id", "code_modules.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_code_files_module",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_code_files_analysis_run",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    artifact_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    module_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False)
    loc_code: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    loc_comment: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    ast_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class CodeSymbol(Base, TenantScopedMixin):
    """D3. Deterministic AST symbol declaration (`TENANT_DIRECT`)."""

    __tablename__ = "code_symbols"
    __table_args__ = (
        Index("ix_code_symbols_snap_qname", "tenant_id", "snapshot_id", "qualified_name"),
        Index("ix_code_symbols_file_lines", "tenant_id", "code_file_id", "start_line", "end_line"),
        Index("ix_code_symbols_ast_hash", "tenant_id", "body_ast_hash"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_code_symbols_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_code_symbols_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "code_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            ondelete="CASCADE",
            name="fk_code_symbols_file",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_code_symbols_parent",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code_file_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parent_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    symbol_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    signature_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_column: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    end_column: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    cyclomatic_complexity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cognitive_complexity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_ast_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    modifiers_and_annotations: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class CodeImport(Base, TenantScopedMixin):
    """D4. Static import/require/use statement (`TENANT_DIRECT`)."""

    __tablename__ = "code_imports"
    __table_args__ = (
        Index("ix_code_imports_source", "tenant_id", "snapshot_id", "source_file_id"),
        Index("ix_code_imports_target", "tenant_id", "snapshot_id", "resolved_target_file_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_code_imports_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_code_imports_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            ondelete="CASCADE",
            name="fk_code_imports_source_file",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "resolved_target_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_code_imports_target_file",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_file_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    resolved_target_file_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    imported_module_expr: Mapped[str] = mapped_column(Text, nullable=False)
    imported_symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alias_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_external_package: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)


class CodeCallEdge(Base, TenantScopedMixin):
    """D5. Static call graph edge between symbols (`TENANT_DIRECT`)."""

    __tablename__ = "code_call_edges"
    __table_args__ = (
        Index("ix_call_edges_caller", "tenant_id", "snapshot_id", "caller_symbol_id"),
        Index("ix_call_edges_callee", "tenant_id", "snapshot_id", "callee_symbol_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_code_call_edges_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_code_call_edges_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "caller_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            ondelete="CASCADE",
            name="fk_code_call_edges_caller",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "callee_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_code_call_edges_callee",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    caller_symbol_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    callee_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    unresolved_callee_expr: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_certainty: Mapped[str] = mapped_column(String(32), nullable=False)
    call_site_line: Mapped[int] = mapped_column(Integer, nullable=False)
    call_site_column: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class CodeTypeHierarchy(Base, TenantScopedMixin):
    """D6. Class inheritance and interface realization edge (`TENANT_DIRECT`)."""

    __tablename__ = "code_type_hierarchies"
    __table_args__ = (
        Index("ix_type_hier_sub", "tenant_id", "snapshot_id", "sub_symbol_id"),
        Index("ix_type_hier_super", "tenant_id", "snapshot_id", "super_symbol_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_code_type_hier_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_code_type_hier_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sub_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            ondelete="CASCADE",
            name="fk_code_type_hier_sub",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "super_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_code_type_hier_super",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sub_symbol_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    super_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    unresolved_super_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    relation_kind: Mapped[str] = mapped_column(String(32), nullable=False)


class CodeSymbolReference(Base, TenantScopedMixin):
    """D7. Fine-grained read/write/instantiation/decorator reference (`TENANT_DIRECT`)."""

    __tablename__ = "code_symbol_references"
    __table_args__ = (
        Index("ix_sym_refs_target", "tenant_id", "snapshot_id", "referenced_symbol_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_code_sym_refs_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_code_sym_refs_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "referencing_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            ondelete="CASCADE",
            name="fk_code_sym_refs_file",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "enclosing_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_code_sym_refs_enclosing",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "referenced_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            ondelete="CASCADE",
            name="fk_code_sym_refs_target",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    referencing_file_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    enclosing_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    referenced_symbol_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reference_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    column_number: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

