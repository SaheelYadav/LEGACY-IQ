"""Wave 2: Technical Intelligence (Domain E), Unified Knowledge Graph & Provenance (Domain F), and AI Orchestration (Domain I).

Revision ID: 0004_wave2_tech_intel
Revises: 0003_wave1_rls_vec
Create Date: 2026-11-01
"""

import hashlib
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_wave2_tech_intel"
down_revision: Union[str, None] = "0003_wave1_rls_vec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_DIRECT_WAVE2_TABLES: tuple[str, ...] = (
    # Domain E (9)
    "db_schemas",
    "db_tables",
    "db_columns",
    "db_foreign_keys",
    "api_services",
    "api_endpoints",
    "infra_resources",
    "doc_sections",
    "runtime_observations",
    # Domain I remaining (4 TENANT_DIRECT; prompt_templates is HYBRID_CATALOG)
    "agent_runs",
    "agent_task_dependencies",
    "model_invocations",
    "agent_execution_events",
    # Domain F (7)
    "knowledge_entities",
    "knowledge_relationships",
    "findings",
    "evidence_anchors",
    "finding_evidence_links",
    "knowledge_conflicts",
    "review_history",
)

ALL_WAVE2_TABLES: tuple[str, ...] = (
    "prompt_templates",
    *TENANT_DIRECT_WAVE2_TABLES,
)


def upgrade() -> None:
    # =========================================================================
    # 1. Domain E: Technical, Data, API, Infrastructure & Runtime Intelligence (9 tables)
    # =========================================================================
    op.create_table(
        "db_schemas",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_version_id", sa.Uuid(), nullable=True),
        sa.Column("db_engine", sa.String(length=32), nullable=False),
        sa.Column("schema_name", sa.String(length=128), nullable=False),
        sa.Column("discovery_source", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_db_schemas_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_db_schemas_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            name="fk_db_schemas_artifact_version",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_db_schemas"),
        sa.UniqueConstraint(
            "tenant_id", "snapshot_id", "schema_name", name="uq_db_schemas_snap_name"
        ),
    )

    op.create_table(
        "db_tables",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("db_schema_id", sa.Uuid(), nullable=False),
        sa.Column("mapped_orm_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("table_kind", sa.String(length=32), server_default="TABLE", nullable=False),
        sa.Column("comment_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_db_tables_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "db_schema_id"],
            ["db_schemas.tenant_id", "db_schemas.id"],
            name="fk_db_tables_schema",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mapped_orm_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_db_tables_orm_symbol",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_db_tables"),
        sa.UniqueConstraint(
            "tenant_id", "db_schema_id", "table_name", name="uq_db_tables_schema_name"
        ),
    )

    op.create_table(
        "db_columns",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("db_table_id", sa.Uuid(), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
        sa.Column("data_type", sa.String(length=128), nullable=False),
        sa.Column("is_nullable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_primary_key", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_pii_candidate", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_db_columns_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "db_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            name="fk_db_columns_table",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_db_columns"),
        sa.UniqueConstraint(
            "tenant_id", "db_table_id", "column_name", name="uq_db_columns_table_name"
        ),
    )

    op.create_table(
        "db_foreign_keys",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_table_id", sa.Uuid(), nullable=False),
        sa.Column("target_table_id", sa.Uuid(), nullable=False),
        sa.Column("constraint_name", sa.String(length=255), nullable=True),
        sa.Column(
            "source_column_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "target_column_names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("relation_origin", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_db_foreign_keys_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            name="fk_db_foreign_keys_source_table",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            name="fk_db_foreign_keys_target_table",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_db_foreign_keys"),
    )

    op.create_table(
        "api_services",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("base_path", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_api_services_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_api_services_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_api_services"),
        sa.UniqueConstraint(
            "tenant_id", "snapshot_id", "service_name", name="uq_api_services_snap_name"
        ),
    )

    op.create_table(
        "api_endpoints",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("api_service_id", sa.Uuid(), nullable=False),
        sa.Column("handler_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("http_method", sa.String(length=16), nullable=False),
        sa.Column("route_pattern", sa.Text(), nullable=False),
        sa.Column("auth_required_inferred", sa.Boolean(), nullable=True),
        sa.Column(
            "request_schema_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "response_schema_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_api_endpoints_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "api_service_id"],
            ["api_services.tenant_id", "api_services.id"],
            name="fk_api_endpoints_service",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "handler_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_api_endpoints_handler_symbol",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_api_endpoints"),
        sa.UniqueConstraint(
            "tenant_id",
            "api_service_id",
            "http_method",
            "route_pattern",
            name="uq_api_endpoints_svc_method_route",
        ),
    )

    op.create_table(
        "infra_resources",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_version_id", sa.Uuid(), nullable=False),
        sa.Column("iac_tool", sa.String(length=32), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("resource_name", sa.String(length=255), nullable=False),
        sa.Column(
            "configuration_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_infra_resources_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_infra_resources_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            name="fk_infra_resources_artifact_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_infra_resources"),
    )

    op.create_table(
        "doc_sections",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_version_id", sa.Uuid(), nullable=False),
        sa.Column("parent_section_id", sa.Uuid(), nullable=True),
        sa.Column("heading_path", sa.Text(), nullable=False),
        sa.Column("heading_level", sa.Integer(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_doc_sections_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            name="fk_doc_sections_artifact_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_section_id"],
            ["doc_sections.tenant_id", "doc_sections.id"],
            name="fk_doc_sections_parent",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_doc_sections"),
    )

    op.create_table(
        "runtime_observations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=True),
        sa.Column("linked_endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("linked_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("observation_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "metric_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("observed_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_runtime_observations_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_runtime_observations_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["application_environments.tenant_id", "application_environments.id"],
            name="fk_runtime_observations_environment",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "linked_endpoint_id"],
            ["api_endpoints.tenant_id", "api_endpoints.id"],
            name="fk_runtime_observations_endpoint",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "linked_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_runtime_observations_symbol",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_runtime_observations"),
    )

    # =========================================================================
    # 2. Domain I: AI Orchestration & Telemetry (5 remaining tables)
    # =========================================================================
    op.create_table(
        "agent_runs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("parent_agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "input_context_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "output_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_agent_runs_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_agent_runs_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_runs_parent",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_agent_runs"),
    )

    op.create_table(
        "agent_task_dependencies",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("upstream_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("downstream_agent_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "dependency_kind",
            sa.String(length=32),
            server_default="DATA_PREREQUISITE",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_agent_task_deps_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_agent_task_deps_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "upstream_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_task_deps_upstream",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "downstream_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_task_deps_downstream",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_agent_task_dependencies"),
        sa.UniqueConstraint(
            "tenant_id",
            "upstream_agent_run_id",
            "downstream_agent_run_id",
            name="uq_agent_task_deps_up_down",
        ),
    )

    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("template_key", sa.String(length=96), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("target_agent_name", sa.String(length=64), nullable=False),
        sa.Column("template_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("system_prompt_text", sa.Text(), nullable=False),
        sa.Column("user_prompt_template", sa.Text(), nullable=False),
        sa.Column(
            "output_json_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_prompt_templates_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_templates"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_prompt_templates_tenant_key_ver
        ON prompt_templates (
            COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid),
            template_key,
            version_number
        );
        """
    )

    op.create_table(
        "model_invocations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_template_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("model_identifier", sa.String(length=128), nullable=False),
        sa.Column(
            "is_fallback_invocation", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("rendered_prompt_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("storage_payload_uri", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "invoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_model_invocations_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_model_invocations_agent_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"],
            ["prompt_templates.id"],
            name="fk_model_invocations_prompt_template",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_model_invocations"),
    )
    op.create_index("ix_model_inv_agent", "model_invocations", ["tenant_id", "agent_run_id"])
    op.create_index("ix_model_inv_time", "model_invocations", ["tenant_id", "invoked_at"])

    # Trigger guard enforcing that model_invocations can only reference global (tenant_id IS NULL)
    # or same-tenant prompt_templates
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_prompt_template_tenant_match()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            tmpl_tenant UUID;
        BEGIN
            SELECT tenant_id INTO tmpl_tenant FROM prompt_templates WHERE id = NEW.prompt_template_id;
            IF tmpl_tenant IS NOT NULL AND tmpl_tenant <> NEW.tenant_id THEN
                RAISE EXCEPTION 'Cross-tenant prompt_template reference forbidden (template tenant %, invocation tenant %)',
                    tmpl_tenant, NEW.tenant_id;
            END IF;
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_model_invocations_prompt_tenant_guard
        BEFORE INSERT OR UPDATE ON model_invocations
        FOR EACH ROW EXECUTE FUNCTION enforce_prompt_template_tenant_match();
        """
    )

    op.create_table(
        "agent_execution_events",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column(
            "event_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_agent_exec_events_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_exec_events_agent_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_agent_execution_events"),
        sa.UniqueConstraint(
            "tenant_id", "agent_run_id", "sequence_no", name="uq_agent_exec_events_run_seq"
        ),
    )

    # =========================================================================
    # 3. Domain F: Unified Knowledge Graph, Findings & Evidence (7 tables)
    # =========================================================================
    op.create_table(
        "knowledge_entities",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("source_db_table_id", sa.Uuid(), nullable=True),
        sa.Column("source_api_endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.String(length=48), nullable=False),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary_description", sa.Text(), nullable=True),
        sa.Column("origin_type", sa.String(length=32), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            server_default="1.0000",
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.String(length=32),
            server_default="DRAFT_AI",
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "attributes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_knowledge_entities_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_knowledge_entities_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_knowledge_entities_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_knowledge_entities_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_knowledge_entities_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            name="fk_knowledge_entities_symbol",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_db_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            name="fk_knowledge_entities_db_table",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_api_endpoint_id"],
            ["api_endpoints.tenant_id", "api_endpoints.id"],
            name="fk_knowledge_entities_api_endpoint",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_knowledge_entities"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "analysis_run_id",
            "entity_type",
            "canonical_key",
            name="uq_knowledge_entities_run_type_key",
        ),
    )

    op.create_table(
        "knowledge_relationships",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_entity_id", sa.Uuid(), nullable=False),
        sa.Column("target_entity_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=48), nullable=False),
        sa.Column("origin_type", sa.String(length=32), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            server_default="1.0000",
            nullable=False,
        ),
        sa.Column(
            "edge_weight",
            sa.Numeric(precision=8, scale=4),
            server_default="1.0000",
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.String(length=32),
            server_default="DETERMINISTIC_FACT",
            nullable=False,
        ),
        sa.Column(
            "edge_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_knowledge_relationships_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_knowledge_rels_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_knowledge_rels_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_knowledge_rels_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_knowledge_rels_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            name="fk_knowledge_rels_source_entity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            name="fk_knowledge_rels_target_entity",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_knowledge_relationships"),
        sa.UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_knowledge_rels_run_src_tgt_type",
        ),
    )
    op.create_index(
        "ix_kr_source",
        "knowledge_relationships",
        ["tenant_id", "snapshot_id", "source_entity_id", "relationship_type"],
    )
    op.create_index(
        "ix_kr_target",
        "knowledge_relationships",
        ["tenant_id", "snapshot_id", "target_entity_id", "relationship_type"],
    )

    op.create_table(
        "findings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=True),
        sa.Column("producing_agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("finding_category", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="INFO", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("statement_markdown", sa.Text(), nullable=False),
        sa.Column("origin_type", sa.String(length=32), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            server_default="1.0000",
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.String(length=32),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
        sa.Column("superseded_by_finding_id", sa.Uuid(), nullable=True),
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_findings_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_findings_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_findings_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_findings_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_findings_analysis_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "subject_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            name="fk_findings_subject_entity",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "producing_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_findings_agent_run",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "superseded_by_finding_id"],
            ["findings.tenant_id", "findings.id"],
            name="fk_findings_superseded_by",
            ondelete="SET NULL",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_findings"),
    )
    op.create_index(
        "ix_findings_app_cat_status",
        "findings",
        ["tenant_id", "application_id", "finding_category", "review_status"],
    )

    op.create_table(
        "evidence_anchors",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_version_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column(
            "locator_type",
            sa.String(length=32),
            server_default="LINE_RANGE",
            nullable=False,
        ),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_column", sa.Integer(), server_default="0", nullable=False),
        sa.Column("end_column", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ast_or_json_path", sa.Text(), nullable=True),
        sa.Column("snippet_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("excerpt_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_line >= start_line",
            name="ck_evidence_anchors_line_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_evidence_anchors_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            name="fk_evidence_anchors_artifact_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_evidence_anchors_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_evidence_anchors"),
        sa.UniqueConstraint(
            "tenant_id",
            "artifact_version_id",
            "locator_type",
            "start_line",
            "end_line",
            "start_column",
            "end_column",
            "snippet_sha256",
            name="uq_evidence_anchors_ver_span_hash",
        ),
    )

    op.create_table(
        "finding_evidence_links",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_anchor_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("knowledge_entity_id", sa.Uuid(), nullable=True),
        sa.Column("knowledge_relationship_id", sa.Uuid(), nullable=True),
        sa.Column("business_rule_id", sa.Uuid(), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_role", sa.String(length=32), nullable=False),
        sa.Column(
            "relevance_weight",
            sa.Numeric(precision=5, scale=4),
            server_default="1.0000",
            nullable=False,
        ),
        sa.Column("rationale_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(finding_id, knowledge_entity_id, knowledge_relationship_id, business_rule_id, requirement_id) >= 1",
            name="ck_finding_evidence_links_has_target",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_finding_evidence_links_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evidence_anchor_id"],
            ["evidence_anchors.tenant_id", "evidence_anchors.id"],
            name="fk_finding_evidence_links_anchor",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["findings.tenant_id", "findings.id"],
            name="fk_finding_evidence_links_finding",
            ondelete="CASCADE",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            name="fk_finding_evidence_links_entity",
            ondelete="CASCADE",
            match="SIMPLE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_relationship_id"],
            ["knowledge_relationships.tenant_id", "knowledge_relationships.id"],
            name="fk_finding_evidence_links_relationship",
            ondelete="CASCADE",
            match="SIMPLE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_finding_evidence_links"),
    )

    op.create_table(
        "knowledge_conflicts",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("conflict_type", sa.String(length=48), nullable=False),
        sa.Column("primary_entity_or_finding_id", sa.Uuid(), nullable=False),
        sa.Column("conflicting_entity_or_finding_id", sa.Uuid(), nullable=False),
        sa.Column("primary_evidence_anchor_id", sa.Uuid(), nullable=False),
        sa.Column("conflicting_evidence_anchor_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="OPEN", nullable=False),
        sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_knowledge_conflicts_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_knowledge_conflicts_application",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            name="fk_knowledge_conflicts_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "primary_evidence_anchor_id"],
            ["evidence_anchors.tenant_id", "evidence_anchors.id"],
            name="fk_knowledge_conflicts_primary_anchor",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conflicting_evidence_anchor_id"],
            ["evidence_anchors.tenant_id", "evidence_anchors.id"],
            name="fk_knowledge_conflicts_conflicting_anchor",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.id"],
            name="fk_knowledge_conflicts_resolver",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_knowledge_conflicts"),
    )

    op.create_table(
        "review_history",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_object_type", sa.String(length=48), nullable=False),
        sa.Column("target_object_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column(
            "previous_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "updated_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_review_history_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name="fk_review_history_reviewer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_review_history"),
    )
    op.create_index(
        "ix_review_history_target",
        "review_history",
        ["tenant_id", "target_object_type", "target_object_id", "reviewed_at"],
    )

    # =========================================================================
    # 4. Grant DML privileges on all 21 Wave 2 tables to `legacyiq_app`
    # =========================================================================
    for tbl in ALL_WAVE2_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO legacyiq_app;")

    # =========================================================================
    # 5. Enable & Force Row-Level Security on all 21 Wave 2 tables
    # =========================================================================
    op.execute(
        """
        ALTER TABLE prompt_templates ENABLE ROW LEVEL SECURITY;
        ALTER TABLE prompt_templates FORCE ROW LEVEL SECURITY;
        CREATE POLICY prompt_templates_select_policy ON prompt_templates
            FOR SELECT
            TO legacyiq_app
            USING (tenant_id IS NULL OR tenant_id = app_current_tenant_id());
        CREATE POLICY prompt_templates_write_policy ON prompt_templates
            FOR ALL
            TO legacyiq_app
            USING (tenant_id = app_current_tenant_id())
            WITH CHECK (tenant_id = app_current_tenant_id());
        """
    )

    for tbl in TENANT_DIRECT_WAVE2_TABLES:
        op.execute(
            f"""
            ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;
            CREATE POLICY tenant_isolation_policy ON {tbl}
                AS PERMISSIVE
                FOR ALL
                TO legacyiq_app
                USING (tenant_id = app_current_tenant_id())
                WITH CHECK (tenant_id = app_current_tenant_id());
            """
        )

    # =========================================================================
    # 6. Seed Default System Prompt Templates for Wave 2 Technical Intelligence Agents
    # =========================================================================
    default_prompts = [
        (
            "00000000-0000-7000-8000-000000000401",
            "repo_cartographer_v1",
            1,
            "repo_cartographer",
            "You are the LegacyIQ Repository Cartographer Agent. Analyze static module, symbol, and call-graph telemetry. Every architectural finding MUST cite an exact file path and line range from the provided evidence anchors.",
            "Analyze the following modules, centrality metrics, and strongly connected components:\n{{context_json}}\nReturn JSON matching the FindingsPayload schema.",
        ),
        (
            "00000000-0000-7000-8000-000000000402",
            "db_analyst_v1",
            1,
            "db_analyst",
            "You are the LegacyIQ Database Intelligence Analyst Agent. Inspect discovered SQL schemas, tables, columns, foreign keys, and ORM mappings. Flag missing foreign-key constraints, PII exposure candidates, and tightly coupled shared tables with exact source line citations.",
            "Analyze the following database schemas, tables, and code-to-table access edges:\n{{context_json}}\nReturn JSON matching the FindingsPayload schema.",
        ),
        (
            "00000000-0000-7000-8000-000000000403",
            "api_inspector_v1",
            1,
            "api_inspector",
            "You are the LegacyIQ API Intelligence Inspector Agent. Inspect REST, OpenAPI, and GraphQL endpoints, handler symbols, and authentication metadata. Identify unauthenticated state-mutating endpoints or contract mismatches with exact source line citations.",
            "Analyze the following API services and endpoints:\n{{context_json}}\nReturn JSON matching the FindingsPayload schema.",
        ),
        (
            "00000000-0000-7000-8000-000000000404",
            "infra_auditor_v1",
            1,
            "infra_auditor",
            "You are the LegacyIQ Infrastructure Intelligence Auditor Agent. Inspect Docker, Docker Compose, Kubernetes, Terraform, and CloudFormation resources. Identify privileged containers, unpinned base images, or missing healthchecks with exact source line citations.",
            "Analyze the following infrastructure resources:\n{{context_json}}\nReturn JSON matching the FindingsPayload schema.",
        ),
        (
            "00000000-0000-7000-8000-000000000405",
            "doc_linker_v1",
            1,
            "doc_linker",
            "You are the LegacyIQ Documentation Linker Agent. Cross-reference technical documentation sections against actual code symbols, database tables, and API endpoints. Flag documentation drift or undocumented critical components with exact source line citations.",
            "Analyze the following documentation sections and code entities:\n{{context_json}}\nReturn JSON matching the FindingsPayload schema.",
        ),
    ]

    output_schema = json.dumps(
        {
            "type": "object",
            "required": ["findings"],
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "finding_category",
                            "severity",
                            "title",
                            "statement_markdown",
                            "confidence_score",
                            "cited_anchor_id",
                        ],
                    },
                }
            },
        }
    )

    for pid, tkey, ver, agent_name, sys_txt, usr_txt in default_prompts:
        sha = hashlib.sha256(f"{sys_txt}\n{usr_txt}".encode("utf-8")).hexdigest()
        op.execute(
            sa.text(
                """
                INSERT INTO prompt_templates (
                    id, tenant_id, template_key, version_number, target_agent_name,
                    template_sha256, system_prompt_text, user_prompt_template, output_json_schema
                ) VALUES (
                    CAST(:id AS uuid), NULL, :tkey, :ver, :agent_name,
                    :sha, :sys_txt, :usr_txt, CAST(:schema_json AS jsonb)
                ) ON CONFLICT DO NOTHING;
                """
            ).bindparams(
                id=pid,
                tkey=tkey,
                ver=ver,
                agent_name=agent_name,
                sha=sha,
                sys_txt=sys_txt,
                usr_txt=usr_txt,
                schema_json=output_schema,
            )
        )


def downgrade() -> None:
    for tbl in reversed(TENANT_DIRECT_WAVE2_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP POLICY IF EXISTS prompt_templates_write_policy ON prompt_templates;")
    op.execute("DROP POLICY IF EXISTS prompt_templates_select_policy ON prompt_templates;")
    op.execute("ALTER TABLE prompt_templates DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_review_history_target", table_name="review_history")
    op.drop_table("review_history")
    op.drop_table("knowledge_conflicts")
    op.drop_table("finding_evidence_links")
    op.drop_table("evidence_anchors")
    op.drop_index("ix_findings_app_cat_status", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_kr_target", table_name="knowledge_relationships")
    op.drop_index("ix_kr_source", table_name="knowledge_relationships")
    op.drop_table("knowledge_relationships")
    op.drop_table("knowledge_entities")

    op.drop_table("agent_execution_events")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_model_invocations_prompt_tenant_guard ON model_invocations;"
    )
    op.execute("DROP FUNCTION IF EXISTS enforce_prompt_template_tenant_match();")
    op.drop_index("ix_model_inv_time", table_name="model_invocations")
    op.drop_index("ix_model_inv_agent", table_name="model_invocations")
    op.drop_table("model_invocations")
    op.execute("DROP INDEX IF EXISTS uq_prompt_templates_tenant_key_ver;")
    op.drop_table("prompt_templates")
    op.drop_table("agent_task_dependencies")
    op.drop_table("agent_runs")

    op.drop_table("runtime_observations")
    op.drop_table("doc_sections")
    op.drop_table("infra_resources")
    op.drop_table("api_endpoints")
    op.drop_table("api_services")
    op.drop_table("db_foreign_keys")
    op.drop_table("db_columns")
    op.drop_table("db_tables")
    op.drop_table("db_schemas")

