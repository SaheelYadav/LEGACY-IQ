"""Domain G: Business Logic & Requirements Intelligence ORM Models (6 Canonical Tables)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
     ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class BusinessDomain(Base, TenantScopedMixin):
    """G1. High-level bounded contexts / functional business areas within an application (`TENANT_DIRECT`)."""

    __tablename__ = "business_domains"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "code",
            name="uq_business_domains_app_code",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_business_domains_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_business_domains_application",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class BusinessProcess(Base, TenantScopedMixin):
    """G2. End-to-end business workflows reconstructed from API entrypoints, batch jobs, and call chains (`TENANT_DIRECT`)."""

    __tablename__ = "business_processes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "process_key",
            name="uq_business_processes_app_key",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_business_processes_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_business_processes_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "business_domain_id"],
            ["business_domains.tenant_id", "business_domains.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_processes_domain",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "entry_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_processes_entry_entity",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    business_domain_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    entry_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    process_key: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow_summary: Mapped[str] = mapped_column(Text, nullable=False)
    ordered_step_entity_ids: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
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


class BusinessRule(Base, TenantScopedMixin):
    """G3. Explicit domain invariants, calculations, branching conditions, and state transitions (`TENANT_DIRECT`)."""

    __tablename__ = "business_rules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "rule_code",
            name="uq_business_rules_app_snap_code",
        ),
        Index(
            "ix_business_rules_snap_cat",
            "tenant_id",
            "snapshot_id",
            "rule_category",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_business_rules_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_business_rules_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_business_rules_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_business_rules_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "business_domain_id"],
            ["business_domains.tenant_id", "business_domains.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_rules_domain",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_rules_knowledge_entity",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    business_domain_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    knowledge_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    condition_expression: Mapped[str] = mapped_column(Text, nullable=False)
    action_consequence: Mapped[str] = mapped_column(Text, nullable=False)
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
    version_no: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class Requirement(Base, TenantScopedMixin):
    """G4. Reconstructed Functional and Non-Functional Requirements synthesized from rules, APIs, DB constraints, and docs (`TENANT_DIRECT`)."""

    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "req_code",
            name="uq_requirements_app_snap_code",
        ),
        Index(
            "ix_requirements_snap_type",
            "tenant_id",
            "snapshot_id",
            "req_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_requirements_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_requirements_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_requirements_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_requirements_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "business_domain_id"],
            ["business_domains.tenant_id", "business_domains.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_requirements_domain",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_requirements_knowledge_entity",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    business_domain_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    knowledge_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    req_code: Mapped[str] = mapped_column(String(64), nullable=False)
    req_type: Mapped[str] = mapped_column(String(48), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(16), default="MUST", server_default="MUST", nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    specification_statement: Mapped[str] = mapped_column(Text, nullable=False)
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
    version_no: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class RequirementAcceptanceCriterion(Base, TenantScopedMixin):
    """G5. Testable Given/When/Then acceptance criteria decomposing a `requirement` (`TENANT_DIRECT`)."""

    __tablename__ = "requirement_acceptance_criteria"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "requirement_id",
            "criterion_order",
            name="uq_req_acceptance_criteria_req_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_req_acceptance_criteria_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requirement_id"],
            ["requirements.tenant_id", "requirements.id"],
            ondelete="CASCADE",
            name="fk_req_acceptance_criteria_requirement",
        ),
    )

    requirement_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    criterion_order: Mapped[int] = mapped_column(Integer, nullable=False)
    given_clause: Mapped[str] = mapped_column(Text, nullable=False)
    when_clause: Mapped[str] = mapped_column(Text, nullable=False)
    then_clause: Mapped[str] = mapped_column(Text, nullable=False)
    verification_method: Mapped[str] = mapped_column(
        String(32),
        default="UNIT_TEST",
        server_default="UNIT_TEST",
        nullable=False,
    )


class RequirementTraceabilityLink(Base, TenantScopedMixin):
    """G6. Explicit forward/backward Requirements Traceability Matrix (RTM) links (`TENANT_DIRECT`)."""

    __tablename__ = "requirement_traceability_links"
    __table_args__ = (
        Index("ix_rtm_req", "tenant_id", "requirement_id"),
        Index("ix_rtm_rule", "tenant_id", "business_rule_id"),
        Index("ix_rtm_symbol", "tenant_id", "code_symbol_id"),
        Index("ix_rtm_entity", "tenant_id", "knowledge_entity_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_req_traceability_links_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requirement_id"],
            ["requirements.tenant_id", "requirements.id"],
            ondelete="CASCADE",
            name="fk_req_traceability_links_requirement",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "business_rule_id"],
            ["business_rules.tenant_id", "business_rules.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_req_traceability_links_business_rule",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_req_traceability_links_knowledge_entity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "code_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_req_traceability_links_code_symbol",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_case_id"],
            ["test_cases.tenant_id", "test_cases.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_req_traceability_links_test_case",
        ),
    )

    requirement_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    business_rule_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    knowledge_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    code_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    test_case_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    link_type: Mapped[str] = mapped_column(String(48), nullable=False)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("1.0000"),
        server_default="1.0000",
        nullable=False,
    )


__all__ = [
    "BusinessDomain",
    "BusinessProcess",
    "BusinessRule",
    "Requirement",
    "RequirementAcceptanceCriterion",
    "RequirementTraceabilityLink",
]

