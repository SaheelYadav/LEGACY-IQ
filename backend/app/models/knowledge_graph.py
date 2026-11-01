"""Domain F: Unified Knowledge Graph, Findings & Evidence models (7 Tables)."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
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

from app.db.base import Base, CreatedAtMixin, TenantScopedMixin


class KnowledgeEntity(Base, TenantScopedMixin, CreatedAtMixin):
    """F1. Unified property-graph node bridging code, DB, API, infra, and architectural components (`TENANT_DIRECT`)."""

    __tablename__ = "knowledge_entities"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "analysis_run_id",
            "entity_type",
            "canonical_key",
            name="uq_knowledge_entities_run_type_key",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_knowledge_entities_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_knowledge_entities_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_knowledge_entities_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_knowledge_entities_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_knowledge_entities_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_knowledge_entities_symbol",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_db_table_id"],
            ["db_tables.tenant_id", "db_tables.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_knowledge_entities_db_table",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_api_endpoint_id"],
            ["api_endpoints.tenant_id", "api_endpoints.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_knowledge_entities_api_endpoint",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    source_db_table_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    source_api_endpoint_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    canonical_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("1.0000"),
        server_default="1.0000",
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        String(32), default="DRAFT_AI", server_default="DRAFT_AI", nullable=False
    )
    version_no: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    attributes_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class KnowledgeRelationship(Base, TenantScopedMixin):
    """F2. Unified directed property-graph edge connecting `knowledge_entities` (`TENANT_DIRECT`)."""

    __tablename__ = "knowledge_relationships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "analysis_run_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_knowledge_rels_run_src_tgt_type",
        ),
        Index(
            "ix_kr_source",
            "tenant_id",
            "snapshot_id",
            "source_entity_id",
            "relationship_type",
        ),
        Index(
            "ix_kr_target",
            "tenant_id",
            "snapshot_id",
            "target_entity_id",
            "relationship_type",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_knowledge_relationships_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_knowledge_rels_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_knowledge_rels_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_knowledge_rels_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_knowledge_rels_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            ondelete="CASCADE",
            name="fk_knowledge_rels_source_entity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            ondelete="CASCADE",
            name="fk_knowledge_rels_target_entity",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    target_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(48), nullable=False)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("1.0000"),
        server_default="1.0000",
        nullable=False,
    )
    edge_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0000"),
        server_default="1.0000",
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        default="DETERMINISTIC_FACT",
        server_default="DETERMINISTIC_FACT",
        nullable=False,
    )
    edge_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )


class Finding(Base, TenantScopedMixin, CreatedAtMixin):
    """F3. First-class analytical assertions surfaced by LegacyIQ requiring source evidence links (`TENANT_DIRECT`)."""

    __tablename__ = "findings"
    __table_args__ = (
        Index(
            "ix_findings_app_cat_status",
            "tenant_id",
            "application_id",
            "finding_category",
            "review_status",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_findings_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_findings_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_findings_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_findings_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_findings_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subject_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_findings_subject_entity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "producing_agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_findings_agent_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "superseded_by_finding_id"],
            ["findings.tenant_id", "findings.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_findings_superseded_by",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    subject_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    producing_agent_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    finding_category: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), default="INFO", server_default="INFO", nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    statement_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("1.0000"),
        server_default="1.0000",
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING_REVIEW",
        server_default="PENDING_REVIEW",
        nullable=False,
    )
    superseded_by_finding_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    version_no: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class EvidenceAnchor(Base, TenantScopedMixin, CreatedAtMixin):
    """F4. Immutable cryptographic pointer to an exact span inside an `artifact_version` (`TENANT_DIRECT`)."""

    __tablename__ = "evidence_anchors"
    __table_args__ = (
        UniqueConstraint(
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
        CheckConstraint(
            "end_line >= start_line",
            name="ck_evidence_anchors_line_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_evidence_anchors_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "artifact_version_id"],
            ["artifact_versions.tenant_id", "artifact_versions.id"],
            ondelete="CASCADE",
            name="fk_evidence_anchors_artifact_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_evidence_anchors_snapshot",
        ),
    )

    artifact_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    locator_type: Mapped[str] = mapped_column(
        String(32), default="LINE_RANGE", server_default="LINE_RANGE", nullable=False
    )
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_column: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    end_column: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    ast_or_json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    excerpt_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class FindingEvidenceLink(Base, TenantScopedMixin):
    """F5. Associates `evidence_anchors` with findings, knowledge_entities, knowledge_relationships, etc. (`TENANT_DIRECT`)."""

    __tablename__ = "finding_evidence_links"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(finding_id, knowledge_entity_id, knowledge_relationship_id, business_rule_id, requirement_id) >= 1",
            name="ck_finding_evidence_links_has_target",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_finding_evidence_links_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evidence_anchor_id"],
            ["evidence_anchors.tenant_id", "evidence_anchors.id"],
            ondelete="CASCADE",
            name="fk_finding_evidence_links_anchor",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["findings.tenant_id", "findings.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_finding_evidence_links_finding",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_finding_evidence_links_entity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_relationship_id"],
            ["knowledge_relationships.tenant_id", "knowledge_relationships.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_finding_evidence_links_relationship",
        ),
    )

    evidence_anchor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    finding_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    knowledge_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    knowledge_relationship_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    business_rule_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    requirement_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    evidence_role: Mapped[str] = mapped_column(String(32), nullable=False)
    relevance_weight: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("1.0000"),
        server_default="1.0000",
        nullable=False,
    )
    rationale_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class KnowledgeConflict(Base, TenantScopedMixin):
    """F6. Explicit record of contradictions discovered between code and docs, static vs runtime, or AI interpretations (`TENANT_DIRECT`)."""

    __tablename__ = "knowledge_conflicts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_knowledge_conflicts_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_knowledge_conflicts_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_knowledge_conflicts_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "primary_evidence_anchor_id"],
            ["evidence_anchors.tenant_id", "evidence_anchors.id"],
            ondelete="CASCADE",
            name="fk_knowledge_conflicts_primary_anchor",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "conflicting_evidence_anchor_id"],
            ["evidence_anchors.tenant_id", "evidence_anchors.id"],
            ondelete="CASCADE",
            name="fk_knowledge_conflicts_conflicting_anchor",
        ),
        ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_knowledge_conflicts_resolver",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(48), nullable=False)
    primary_entity_or_finding_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    conflicting_entity_or_finding_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    primary_evidence_anchor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    conflicting_evidence_anchor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="OPEN", server_default="OPEN", nullable=False
    )
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReviewHistory(Base, TenantScopedMixin):
    """F7. Append-only immutable audit log of human review state transitions (`TENANT_DIRECT`)."""

    __tablename__ = "review_history"
    __table_args__ = (
        Index(
            "ix_review_history_target",
            "tenant_id",
            "target_object_type",
            "target_object_id",
            "reviewed_at",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_review_history_tenant",
        ),
        ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_review_history_reviewer",
        ),
    )

    target_object_type: Mapped[str] = mapped_column(String(48), nullable=False)
    target_object_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reviewer_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    updated_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

