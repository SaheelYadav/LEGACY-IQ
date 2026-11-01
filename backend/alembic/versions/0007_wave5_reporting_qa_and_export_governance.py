"""Wave 5: Semantic Q&A Conversations, Structured Intelligence Reports, Versioning, Controlled Exports, Audit Ledger & SaaS Governance (11 Tables + RLS).

Revision ID: 0007_wave5_qa_reports_export
Revises: 0006_wave4_test_risk_mod
Create Date: 2026-11-01
"""

from __future__ import annotations

import hashlib
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_wave5_qa_reports_export"
down_revision = "0006_wave4_test_risk_mod"
branch_labels = None
depends_on = None

WAVE5_DIRECT_TENANT_TABLES = [
    "qa_conversations",
    "qa_messages",
    "intelligence_reports",
    "intelligence_report_versions",
    "audit_logs",
    "report_exports",
    "approval_requests",
    "retention_policies",
    "deletion_requests",
    "tenant_subscriptions",
    "tenant_usage_quotas",
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # I7. qa_conversations
    # ------------------------------------------------------------------
    op.create_table(
        "qa_conversations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "conversation_status",
            sa.String(length=32),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_qa_conversations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_qa_conversations_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_project",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_qa_conversations_user",
        ),
    )
    op.create_index(
        "ix_qa_conversations_project_snap",
        "qa_conversations",
        ["tenant_id", "project_id", "snapshot_id"],
    )

    # ------------------------------------------------------------------
    # I8. qa_messages
    # ------------------------------------------------------------------
    op.create_table(
        "qa_messages",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "question_intent",
            sa.String(length=64),
            server_default="GENERAL_CODE_QA",
            nullable=False,
        ),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column(
            "direct_facts_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "inferred_explanations_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "citations_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "insufficient_evidence",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            server_default="0.9000",
            nullable=False,
        ),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("model_invocation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_qa_messages"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_qa_messages_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "sequence_no",
            name="uq_qa_messages_conv_seq",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_qa_messages_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_qa_messages_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["qa_conversations.tenant_id", "qa_conversations.id"],
            ondelete="CASCADE",
            name="fk_qa_messages_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_qa_messages_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="SET NULL",
            match="SIMPLE",
            name="fk_qa_messages_agent_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "model_invocation_id"],
            ["model_invocations.tenant_id", "model_invocations.id"],
            ondelete="SET NULL",
            match="SIMPLE",
            name="fk_qa_messages_model_invocation",
        ),
    )
    op.create_index(
        "ix_qa_messages_conv",
        "qa_messages",
        ["tenant_id", "conversation_id", "sequence_no"],
    )

    # ------------------------------------------------------------------
    # K7. intelligence_reports
    # ------------------------------------------------------------------
    op.create_table(
        "intelligence_reports",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "current_version_no",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "lifecycle_status",
            sa.String(length=32),
            server_default="GENERATED",
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_intelligence_reports"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_intelligence_reports_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_project",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_reports_creator",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_reports_approver",
        ),
    )
    op.create_index(
        "ix_intel_reports_snap_type",
        "intelligence_reports",
        ["tenant_id", "snapshot_id", "report_type"],
    )

    # ------------------------------------------------------------------
    # K8. intelligence_report_versions
    # ------------------------------------------------------------------
    op.create_table(
        "intelligence_report_versions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.String(length=32),
            server_default="GENERATED",
            nullable=False,
        ),
        sa.Column(
            "is_immutable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("executive_summary_markdown", sa.Text(), nullable=False),
        sa.Column("scope_and_methodology_markdown", sa.Text(), nullable=False),
        sa.Column(
            "sections_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence_refs_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("risks_and_limitations_markdown", sa.Text(), nullable=False),
        sa.Column(
            "recommendations_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "tenant_id", "id", name="pk_intelligence_report_versions"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_intelligence_report_versions_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "report_id",
            "version_no",
            name="uq_intel_report_versions_report_ver",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_intel_report_versions_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_id"],
            ["intelligence_reports.tenant_id", "intelligence_reports.id"],
            ondelete="CASCADE",
            name="fk_intel_report_versions_report",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_intel_report_versions_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_report_versions_creator",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_report_versions_reviewer",
        ),
    )
    op.create_index(
        "ix_intel_report_versions_report",
        "intelligence_report_versions",
        ["tenant_id", "report_id", "version_no"],
    )

    # ------------------------------------------------------------------
    # K1. audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "actor_type",
            sa.String(length=32),
            server_default="USER",
            nullable=False,
        ),
        sa.Column("action_code", sa.String(length=64), nullable=False),
        sa.Column("target_resource_type", sa.String(length=64), nullable=False),
        sa.Column("target_resource_id", sa.Uuid(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("prev_audit_hash", sa.String(length=64), nullable=True),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "metadata_diff",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_audit_logs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_audit_logs_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_audit_logs_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_audit_logs_actor_user",
        ),
    )
    op.create_index(
        "ix_audit_logs_tenant_time",
        "audit_logs",
        ["tenant_id", "occurred_at"],
    )

    # ------------------------------------------------------------------
    # K9. report_exports
    # ------------------------------------------------------------------
    op.create_table(
        "report_exports",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("report_version_id", sa.Uuid(), nullable=False),
        sa.Column("export_format", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="COMPLETED",
            nullable=False,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_object_uri", sa.Text(), nullable=False),
        sa.Column(
            "branding_config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("audit_log_id", sa.Uuid(), nullable=True),
        sa.Column(
            "download_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_report_exports"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_report_exports_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_report_exports_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_report_exports_project",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_id"],
            ["intelligence_reports.tenant_id", "intelligence_reports.id"],
            ondelete="CASCADE",
            name="fk_report_exports_report",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "report_version_id"],
            ["intelligence_report_versions.tenant_id", "intelligence_report_versions.id"],
            ondelete="CASCADE",
            name="fk_report_exports_report_version",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_report_exports_user",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "audit_log_id"],
            ["audit_logs.tenant_id", "audit_logs.id"],
            ondelete="SET NULL",
            match="SIMPLE",
            name="fk_report_exports_audit_log",
        ),
    )
    op.create_index(
        "ix_report_exports_report",
        "report_exports",
        ["tenant_id", "report_id", "created_at"],
    )

    # ------------------------------------------------------------------
    # K2. approval_requests
    # ------------------------------------------------------------------
    op.create_table(
        "approval_requests",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("request_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_approval_requests"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_approval_requests_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_approval_requests_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            match="SIMPLE",
            name="fk_approval_requests_project",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_approval_requests_requester",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_approval_requests_decider",
        ),
    )

    # ------------------------------------------------------------------
    # K3. retention_policies
    # ------------------------------------------------------------------
    op.create_table(
        "retention_policies",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artifact_category", sa.String(length=48), nullable=False),
        sa.Column("retain_days", sa.Integer(), server_default="365", nullable=False),
        sa.Column("max_snapshots_per_repo", sa.Integer(), nullable=True),
        sa.Column(
            "auto_purge_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_retention_policies"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_retention_policies_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "artifact_category",
            name="uq_retention_policies_tenant_category",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_retention_policies_tenant",
        ),
    )

    # ------------------------------------------------------------------
    # K4. deletion_requests
    # ------------------------------------------------------------------
    op.create_table(
        "deletion_requests",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("deletion_scope", sa.String(length=32), nullable=False),
        sa.Column("target_scope_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="REQUESTED",
            nullable=False,
        ),
        sa.Column("completion_certificate_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_deletion_requests"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_deletion_requests_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_deletion_requests_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_deletion_requests_requester",
        ),
    )

    # ------------------------------------------------------------------
    # K5. tenant_subscriptions
    # ------------------------------------------------------------------
    op.create_table(
        "tenant_subscriptions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "plan_code",
            sa.String(length=48),
            server_default="LOCAL_COMMUNITY",
            nullable=False,
        ),
        sa.Column(
            "billing_status",
            sa.String(length=32),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "max_repositories_allowed",
            sa.Integer(),
            server_default="10",
            nullable=False,
        ),
        sa.Column(
            "max_loc_allowed",
            sa.BigInteger(),
            server_default="5000000",
            nullable=False,
        ),
        sa.Column(
            "allow_cloud_llm_providers",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "current_period_start",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_tenant_subscriptions"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_subscriptions_tenant_id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_tenant_subscriptions_tenant",
        ),
    )

    # ------------------------------------------------------------------
    # K6. tenant_usage_quotas
    # ------------------------------------------------------------------
    op.create_table(
        "tenant_usage_quotas",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("billing_month", sa.Date(), nullable=False),
        sa.Column("repositories_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "analyzed_loc_count", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "vector_chunks_stored", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "local_llm_tokens_used", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "cloud_llm_tokens_used", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "object_storage_bytes_used",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_tenant_usage_quotas"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_usage_quotas_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "billing_month", name="uq_tenant_usage_quotas_month"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_tenant_usage_quotas_tenant",
        ),
    )

    # ------------------------------------------------------------------
    # Enable & Force Row-Level Security on all 11 Wave 5 tables (61 -> 72)
    # ------------------------------------------------------------------
    for tbl in WAVE5_DIRECT_TENANT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO legacyiq_app")
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tbl}_tenant_isolation ON {tbl}
                FOR ALL
                TO legacyiq_app
                USING (tenant_id = app_current_tenant_id())
                WITH CHECK (tenant_id = app_current_tenant_id())
            """
        )

    # ------------------------------------------------------------------
    # Seed Wave 5 global prompt templates
    # ------------------------------------------------------------------
    output_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "direct_facts": {"type": "array"},
                "inferred_explanations": {"type": "array"},
                "cited_anchor_ids": {"type": "array"},
            },
        }
    )
    for t_key, agent_name in [
        ("semantic_qa_assistant_v1", "semantic_qa_assistant"),
        ("report_synthesizer_v1", "report_synthesizer"),
    ]:
        sys_txt = (
            f"You are the LegacyIQ {agent_name} agent. Answer strictly from retrieved "
            f"code chunks, evidence anchors, graph relationships, business rules, and requirements. "
            f"Separate directly observed facts from inferred explanations and never fabricate citations."
        )
        usr_txt = "Context:\n{{context_json}}\nQuestion:\n{{question}}\nReturn grounded analysis."
        sha = hashlib.sha256(f"{sys_txt}\n{usr_txt}".encode("utf-8")).hexdigest()
        op.execute(
            sa.text(
                """
                INSERT INTO prompt_templates (
                    id, tenant_id, template_key, version_number,
                    target_agent_name, template_sha256,
                    system_prompt_text, user_prompt_template, output_json_schema
                )
                SELECT
                    :id, NULL, :tkey, 1,
                    :agent, :sha,
                    :sys_txt, :usr_txt, CAST(:schema_json AS jsonb)
                WHERE NOT EXISTS (
                    SELECT 1 FROM prompt_templates
                    WHERE tenant_id IS NULL AND template_key = :tkey
                )
                """
            ).bindparams(
                id=uuid.uuid4(),
                tkey=t_key,
                agent=agent_name,
                sha=sha,
                sys_txt=sys_txt,
                usr_txt=usr_txt,
                schema_json=output_schema,
            )
        )


def downgrade() -> None:
    for tbl in reversed(WAVE5_DIRECT_TENANT_TABLES):
        op.drop_table(tbl)
