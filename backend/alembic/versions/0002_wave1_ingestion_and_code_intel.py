"""Wave 1 Part 2: Source Ingestion (Domain C), Analysis Runs & Deterministic Code Intelligence (Domain D).

Revision ID: 0002_wave1_code_intel
Revises: 0001_wave1_identity
Create Date: 2026-11-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_wave1_code_intel"
down_revision: Union[str, None] = "0001_wave1_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 1. Domain C tables (8 tables)
    op.create_table(
        "source_connectors",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("endpoint_base_url", sa.Text(), nullable=True),
        sa.Column("encrypted_credentials_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_source_connectors_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_source_connectors"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_source_connectors_name"),
    )

    op.create_table(
        "repositories",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("remote_url", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(length=128), server_default="main", nullable=True),
        sa.Column("status", sa.String(length=32), server_default="REGISTERED", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_repositories_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_repositories_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "connector_id"],
            ["source_connectors.tenant_id", "source_connectors.id"],
            name="fk_repositories_connector",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_repositories"),
        sa.UniqueConstraint(
            "tenant_id", "application_id", "name", name="uq_repositories_app_name"
        ),
    )

    op.create_table(
        "repository_branches",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("head_commit_sha", sa.String(length=64), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_repo_branches_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            name="fk_repo_branches_repository",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_repository_branches"),
        sa.UniqueConstraint(
            "tenant_id", "repository_id", "branch_name", name="uq_repo_branches_name"
        ),
    )

    op.create_table(
        "repository_commits",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("author_email", sa.String(length=320), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commit_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_repo_commits_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            name="fk_repo_commits_repository",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_repository_commits"),
        sa.UniqueConstraint(
            "tenant_id", "repository_id", "commit_sha", name="uq_repo_commits_sha"
        ),
    )

    op.create_table(
        "repository_snapshots",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("commit_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_number", sa.Integer(), nullable=False),
        sa.Column("tree_or_archive_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("total_files_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_bytes_size", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("legal_hold_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="CREATING", nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_repo_snapshots_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["repository_branches.tenant_id", "repository_branches.id"],
            name="fk_repo_snapshots_branch",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "commit_id"],
            ["repository_commits.tenant_id", "repository_commits.id"],
            name="fk_repo_snapshots_commit",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            name="fk_repo_snapshots_repository",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_repository_snapshots"),
        sa.UniqueConstraint(
            "tenant_id",
            "repository_id",
            "snapshot_number",
            name="ux_snapshots_repo_num",
        ),
    )

    op.create_table(
        "artifacts",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_kind", sa.String(length=32), nullable=False),
        sa.Column("canonical_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_artifacts_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_artifacts_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            name="fk_artifacts_repository",
            match="SIMPLE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_artifacts"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "repository_id",
            "canonical_path",
            name="uq_artifacts_app_repo_path",
        ),
    )

    op.create_table(
        "artifact_versions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=True),
        sa.Column("encoding", sa.String(length=32), server_default="utf-8", nullable=False),
        sa.Column(
            "mime_type", sa.String(length=128), server_default="text/plain", nullable=False
        ),
        sa.Column("storage_object_uri", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_artifact_versions_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "artifact_id"],
            ["artifacts.tenant_id", "artifacts.id"],
            name="fk_artifact_versions_artifact",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_artifact_versions"),
        sa.UniqueConstraint(
            "tenant_id",
            "artifact_id",
            "content_sha256",
            name="uq_artifact_versions_sha256",
        ),
    )
    op.create_index(
        "ix_artifact_versions_sha256",
        "artifact_versions",
        ["tenant_id", "content_sha256"],
        unique=False,
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="QUEUED", nullable=False),
        sa.Column(
            "stats_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_ingestion_jobs_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "repository_id"],
            ["repositories.tenant_id", "repositories.id"],
            name="fk_ingestion_jobs_repository",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_ingestion_jobs_snapshot",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            name="fk_ingestion_jobs_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_ingestion_jobs"),
    )

    # 2. Domain I anchor table (`analysis_runs`)
    op.create_table(
        "analysis_runs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_scope_id", sa.Uuid(), nullable=False),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column(
            "run_mode",
            sa.String(length=32),
            server_default="FULL_DISCOVERY",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="QUEUED", nullable=False),
        sa.Column(
            "pipeline_versions_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_analysis_runs_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_scope_id"],
            ["analysis_scopes.tenant_id", "analysis_scopes.id"],
            name="fk_analysis_runs_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_analysis_runs_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_analysis_runs_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            name="fk_analysis_runs_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_analysis_runs"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "run_number",
            name="uq_analysis_runs_app_num",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_active_analysis_run_per_snapshot
        ON analysis_runs (tenant_id, snapshot_id)
        WHERE status IN ('QUEUED', 'RUNNING_STATIC', 'RUNNING_EMBEDDINGS', 'RUNNING_AI_AGENTS');
        """
    )

    # 3. Domain D tables (7 tables)
    op.create_table(
        "code_modules",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("module_kind", sa.String(length=32), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("parent_module_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_code_modules_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_module_id"],
            ["code_modules.tenant_id", "code_modules.id"],
            name="fk_code_modules_parent",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_code_modules_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_code_modules"),
        sa.UniqueConstraint(
            "tenant_id",
            "snapshot_id",
            "language",
            "qualified_name",
            name="uq_code_modules_snap_lang_qname",
        ),
    )

    op.create_table(
        "code_files",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_version_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=True),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("loc_code", sa.Integer(), server_default="0", nullable=False),
        sa.Column("loc_comment", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "ast_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_code_files_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_code_files_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            name="fk_code_files_artifact_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "module_id"],
            ["code_modules.tenant_id", "code_modules.id"],
            name="fk_code_files_module",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_code_files_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_code_files"),
        sa.UniqueConstraint(
            "tenant_id",
            "snapshot_id",
            "relative_path",
            name="ux_code_files_snap_path",
        ),
    )
    op.create_index(
        "ix_code_files_artifact_ver",
        "code_files",
        ["tenant_id", "artifact_version_id"],
        unique=False,
    )

    op.create_table(
        "code_symbols",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("code_file_id", sa.Uuid(), nullable=False),
        sa.Column("parent_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("symbol_kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("signature_text", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_column", sa.Integer(), server_default="0", nullable=False),
        sa.Column("end_column", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cyclomatic_complexity", sa.Integer(), nullable=True),
        sa.Column("cognitive_complexity", sa.Integer(), nullable=True),
        sa.Column("body_ast_hash", sa.CHAR(length=64), nullable=True),
        sa.Column(
            "modifiers_and_annotations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_code_symbols_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "code_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            name="fk_code_symbols_file",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_code_symbols_parent",
            match="SIMPLE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_code_symbols_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_code_symbols"),
    )
    op.create_index(
        "ix_code_symbols_snap_qname",
        "code_symbols",
        ["tenant_id", "snapshot_id", "qualified_name"],
        unique=False,
    )
    op.create_index(
        "ix_code_symbols_file_lines",
        "code_symbols",
        ["tenant_id", "code_file_id", "start_line", "end_line"],
        unique=False,
    )
    op.create_index(
        "ix_code_symbols_ast_hash",
        "code_symbols",
        ["tenant_id", "body_ast_hash"],
        unique=False,
    )
    op.execute(
        """
        CREATE INDEX ix_code_symbols_qname_trgm
        ON code_symbols USING gin (qualified_name gin_trgm_ops);
        """
    )

    op.create_table(
        "code_imports",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_target_file_id", sa.Uuid(), nullable=True),
        sa.Column("imported_module_expr", sa.Text(), nullable=False),
        sa.Column("imported_symbol_name", sa.String(length=255), nullable=True),
        sa.Column("alias_name", sa.String(length=255), nullable=True),
        sa.Column("is_external_package", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_code_imports_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "resolved_target_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            name="fk_code_imports_target_file",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_code_imports_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            name="fk_code_imports_source_file",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_code_imports"),
    )
    op.create_index(
        "ix_code_imports_source",
        "code_imports",
        ["tenant_id", "snapshot_id", "source_file_id"],
        unique=False,
    )
    op.create_index(
        "ix_code_imports_target",
        "code_imports",
        ["tenant_id", "snapshot_id", "resolved_target_file_id"],
        unique=False,
    )

    op.create_table(
        "code_call_edges",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("caller_symbol_id", sa.Uuid(), nullable=False),
        sa.Column("callee_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("unresolved_callee_expr", sa.Text(), nullable=True),
        sa.Column("resolution_certainty", sa.String(length=32), nullable=False),
        sa.Column("call_site_line", sa.Integer(), nullable=False),
        sa.Column("call_site_column", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_code_call_edges_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "callee_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_code_call_edges_callee",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "caller_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_code_call_edges_caller",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_code_call_edges_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_code_call_edges"),
    )
    op.create_index(
        "ix_call_edges_caller",
        "code_call_edges",
        ["tenant_id", "snapshot_id", "caller_symbol_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_edges_callee",
        "code_call_edges",
        ["tenant_id", "snapshot_id", "callee_symbol_id"],
        unique=False,
    )

    op.create_table(
        "code_type_hierarchies",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("sub_symbol_id", sa.Uuid(), nullable=False),
        sa.Column("super_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("unresolved_super_name", sa.Text(), nullable=True),
        sa.Column("relation_kind", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_code_type_hier_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_code_type_hier_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sub_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_code_type_hier_sub",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "super_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_code_type_hier_super",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_code_type_hierarchies"),
    )
    op.create_index(
        "ix_type_hier_sub",
        "code_type_hierarchies",
        ["tenant_id", "snapshot_id", "sub_symbol_id"],
        unique=False,
    )
    op.create_index(
        "ix_type_hier_super",
        "code_type_hierarchies",
        ["tenant_id", "snapshot_id", "super_symbol_id"],
        unique=False,
    )

    op.create_table(
        "code_symbol_references",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("referencing_file_id", sa.Uuid(), nullable=False),
        sa.Column("enclosing_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("referenced_symbol_id", sa.Uuid(), nullable=False),
        sa.Column("reference_kind", sa.String(length=32), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("column_number", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_code_sym_refs_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "enclosing_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_code_sym_refs_enclosing",
            match="SIMPLE",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "referenced_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_code_sym_refs_target",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "referencing_file_id"],
            ["code_files.tenant_id", "code_files.id"],
            name="fk_code_sym_refs_file",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_code_sym_refs_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_code_symbol_references"),
    )
    op.create_index(
        "ix_sym_refs_target",
        "code_symbol_references",
        ["tenant_id", "snapshot_id", "referenced_symbol_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sym_refs_target", table_name="code_symbol_references")
    op.drop_table("code_symbol_references")
    op.drop_index("ix_type_hier_super", table_name="code_type_hierarchies")
    op.drop_index("ix_type_hier_sub", table_name="code_type_hierarchies")
    op.drop_table("code_type_hierarchies")
    op.drop_index("ix_call_edges_callee", table_name="code_call_edges")
    op.drop_index("ix_call_edges_caller", table_name="code_call_edges")
    op.drop_table("code_call_edges")
    op.drop_index("ix_code_imports_target", table_name="code_imports")
    op.drop_index("ix_code_imports_source", table_name="code_imports")
    op.drop_table("code_imports")
    op.execute("DROP INDEX IF EXISTS ix_code_symbols_qname_trgm;")
    op.drop_index("ix_code_symbols_ast_hash", table_name="code_symbols")
    op.drop_index("ix_code_symbols_file_lines", table_name="code_symbols")
    op.drop_index("ix_code_symbols_snap_qname", table_name="code_symbols")
    op.drop_table("code_symbols")
    op.drop_index("ix_code_files_artifact_ver", table_name="code_files")
    op.drop_table("code_files")
    op.drop_table("code_modules")
    op.execute("DROP INDEX IF EXISTS ux_active_analysis_run_per_snapshot;")
    op.drop_table("analysis_runs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_artifact_versions_sha256", table_name="artifact_versions")
    op.drop_table("artifact_versions")
    op.drop_table("artifacts")
    op.drop_table("repository_snapshots")
    op.drop_table("repository_commits")
    op.drop_table("repository_branches")
    op.drop_table("repositories")
    op.drop_table("source_connectors")

