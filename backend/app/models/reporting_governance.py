"""Domain I/J/K Wave 5 Models: Semantic Q&A Conversations, Structured Intelligence Reports, Versioning, Controlled Exports, Audit Ledger & SaaS Governance (11 Tables)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class QaConversation(Base, TenantScopedMixin):
    """I7. Project- and snapshot-scoped conversational Semantic Q&A session (`TENANT_DIRECT`)."""

    __tablename__ = "qa_conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_project",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_qa_conversations_snapshot",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_qa_conversations_user",
        ),
        Index(
            "ix_qa_conversations_project_snap",
            "tenant_id",
            "project_id",
            "snapshot_id",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class QaMessage(Base, TenantScopedMixin):
    """I8. Individual USER or ASSISTANT message in a `QaConversation` with evidence citations and fact-vs-inference separation (`TENANT_DIRECT`)."""

    __tablename__ = "qa_messages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "conversation_id",
            "sequence_no",
            name="uq_qa_messages_conv_seq",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_qa_messages_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_qa_messages_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["qa_conversations.tenant_id", "qa_conversations.id"],
            ondelete="CASCADE",
            name="fk_qa_messages_conversation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_qa_messages_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="SET NULL",
            name="fk_qa_messages_agent_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "model_invocation_id"],
            ["model_invocations.tenant_id", "model_invocations.id"],
            ondelete="SET NULL",
            name="fk_qa_messages_model_invocation",
        ),
        Index("ix_qa_messages_conv", "tenant_id", "conversation_id", "sequence_no"),
    )

    conversation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # USER | ASSISTANT
    question_intent: Mapped[str] = mapped_column(
        String(64), nullable=False, default="GENERAL_CODE_QA"
    )
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    direct_facts_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    inferred_explanations_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    citations_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    insufficient_evidence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.9000")
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    model_invocation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IntelligenceReport(Base, TenantScopedMixin):
    """K7. Master structured intelligence report header per project and snapshot (`TENANT_DIRECT`)."""

    __tablename__ = "intelligence_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_project",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_intel_reports_snapshot",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_reports_creator",
        ),
        ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_reports_approver",
        ),
        Index(
            "ix_intel_reports_snap_type",
            "tenant_id",
            "snapshot_id",
            "report_type",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="GENERATED",
        server_default="GENERATED",
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IntelligenceReportVersion(Base, TenantScopedMixin):
    """K8. Versioned report snapshot (`DRAFT`, `GENERATED`, `SUBMITTED_FOR_REVIEW`, `APPROVED`, `REJECTED`, `ARCHIVED`). Approved versions are immutable (`TENANT_DIRECT`)."""

    __tablename__ = "intelligence_report_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "report_id",
            "version_no",
            name="uq_intel_report_versions_report_ver",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_intel_report_versions_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "report_id"],
            ["intelligence_reports.tenant_id", "intelligence_reports.id"],
            ondelete="CASCADE",
            name="fk_intel_report_versions_report",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_intel_report_versions_snapshot",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_report_versions_creator",
        ),
        ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_intel_report_versions_reviewer",
        ),
        Index(
            "ix_intel_report_versions_report",
            "tenant_id",
            "report_id",
            "version_no",
        ),
    )

    report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="GENERATED",
        server_default="GENERATED",
    )
    is_immutable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    executive_summary_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    scope_and_methodology_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    sections_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    evidence_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    risks_and_limitations_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    metrics_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditLog(Base, TenantScopedMixin):
    """K1. Tamper-evident, append-only compliance & export governance ledger (`TENANT_DIRECT`)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_audit_logs_tenant",
        ),
        ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_audit_logs_actor_user",
        ),
        Index("ix_audit_logs_tenant_time", "tenant_id", "occurred_at"),
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="USER"
    )
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_resource_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_audit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_diff: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReportExport(Base, TenantScopedMixin):
    """K9. Controlled multi-format report export artifact (`PDF`, `DOCX`, `XLSX`, `JSON`) with tenant storage URI and audit linkage (`TENANT_DIRECT`)."""

    __tablename__ = "report_exports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_report_exports_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_report_exports_project",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "report_id"],
            ["intelligence_reports.tenant_id", "intelligence_reports.id"],
            ondelete="CASCADE",
            name="fk_report_exports_report",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "report_version_id"],
            ["intelligence_report_versions.tenant_id", "intelligence_report_versions.id"],
            ondelete="CASCADE",
            name="fk_report_exports_report_version",
        ),
        ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_report_exports_user",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "audit_log_id"],
            ["audit_logs.tenant_id", "audit_logs.id"],
            ondelete="SET NULL",
            name="fk_report_exports_audit_log",
        ),
        Index("ix_report_exports_report", "tenant_id", "report_id", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    export_format: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # PDF | DOCX | XLSX | JSON
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="COMPLETED"
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_object_uri: Mapped[str] = mapped_column(Text, nullable=False)
    branding_config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    requested_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    audit_log_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    download_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApprovalRequest(Base, TenantScopedMixin):
    """K2. Formal governance sign-off workflows for report approvals, baseline requirements, or data purge (`TENANT_DIRECT`)."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_approval_requests_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_approval_requests_project",
        ),
        ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_approval_requests_requester",
        ),
        ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_approval_requests_decider",
        ),
    )

    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    request_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", server_default="PENDING"
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RetentionPolicy(Base, TenantScopedMixin):
    """K3. Tenant-configurable data lifecycle rules per artifact category (`TENANT_DIRECT`)."""

    __tablename__ = "retention_policies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "artifact_category",
            name="uq_retention_policies_tenant_category",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_retention_policies_tenant",
        ),
    )

    artifact_category: Mapped[str] = mapped_column(String(48), nullable=False)
    retain_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    max_snapshots_per_repo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_purge_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DeletionRequest(Base, TenantScopedMixin):
    """K4. Verifiable data erasure and crypto-shredding workflow records (`TENANT_DIRECT`)."""

    __tablename__ = "deletion_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_deletion_requests_tenant",
        ),
        ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_deletion_requests_requester",
        ),
    )

    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    deletion_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    target_scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="REQUESTED", server_default="REQUESTED"
    )
    completion_certificate_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TenantSubscription(Base, TenantScopedMixin):
    """K5. Commercial plan entitlements, LOC limits, and cloud AI provider opt-in gates (`TENANT_DIRECT`)."""

    __tablename__ = "tenant_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_tenant_subscriptions_tenant",
        ),
    )

    plan_code: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        default="LOCAL_COMMUNITY",
        server_default="LOCAL_COMMUNITY",
    )
    billing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    max_repositories_allowed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )
    max_loc_allowed: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=5000000, server_default="5000000"
    )
    allow_cloud_llm_providers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TenantUsageQuota(Base, TenantScopedMixin):
    """K6. Monthly metered resource consumption per tenant (`TENANT_DIRECT`)."""

    __tablename__ = "tenant_usage_quotas"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "billing_month",
            name="uq_tenant_usage_quotas_month",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_tenant_usage_quotas_tenant",
        ),
    )

    billing_month: Mapped[date] = mapped_column(Date, nullable=False)
    repositories_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    analyzed_loc_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    vector_chunks_stored: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    local_llm_tokens_used: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    cloud_llm_tokens_used: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    object_storage_bytes_used: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
