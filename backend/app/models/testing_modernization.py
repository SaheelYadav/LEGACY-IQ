"""Domain H: Testing, Risk, Technical Debt & Modernization Intelligence models (5 Tables)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class TestSuite(Base, TenantScopedMixin):
    """H1. Catalogs existing test suites discovered in the repository or AI-generated characterization suites (`TENANT_DIRECT`)."""

    __test__ = False
    __tablename__ = "test_suites"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "suite_name",
            name="uq_test_suites_app_snap_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_test_suites_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_test_suites_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_test_suites_snapshot",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    suite_name: Mapped[str] = mapped_column(String(255), nullable=False)
    test_framework: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_origin: Mapped[str] = mapped_column(String(32), nullable=False)


class TestCase(Base, TenantScopedMixin):
    """H2. Individual discovered test methods or generated characterization/regression test blueprints (`TENANT_DIRECT`)."""

    __test__ = False
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "test_suite_id",
            "test_key",
            name="uq_test_cases_suite_key",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_test_cases_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_test_cases_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_suite_id"],
            ["test_suites.tenant_id", "test_suites.id"],
            ondelete="CASCADE",
            name="fk_test_cases_suite",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_test_cases_symbol",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_test_cases_analysis_run",
        ),
    )

    test_suite_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    test_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    test_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    test_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_description: Mapped[str] = mapped_column(Text, nullable=False)
    generated_code_blueprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_observed_status: Mapped[str] = mapped_column(
        String(32),
        default="UNKNOWN",
        server_default="UNKNOWN",
        nullable=False,
    )
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


class TestCoverageLink(Base, TenantScopedMixin):
    """H3. Maps `test_cases` to `code_symbols`, `business_rules`, and `requirements` (`TENANT_DIRECT`)."""

    __test__ = False
    __tablename__ = "test_coverage_links"
    __table_args__ = (
        Index("ix_test_cov_symbol", "tenant_id", "target_symbol_id"),
        Index("ix_test_cov_req", "tenant_id", "target_requirement_id"),
        Index("ix_test_cov_rule", "tenant_id", "target_business_rule_id"),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_test_coverage_links_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_test_coverage_links_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "test_case_id"],
            ["test_cases.tenant_id", "test_cases.id"],
            ondelete="CASCADE",
            name="fk_test_coverage_links_test_case",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_test_coverage_links_symbol",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_business_rule_id"],
            ["business_rules.tenant_id", "business_rules.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_test_coverage_links_business_rule",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_requirement_id"],
            ["requirements.tenant_id", "requirements.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_test_coverage_links_requirement",
        ),
    )

    test_case_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    target_symbol_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    target_business_rule_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    target_requirement_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    coverage_source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("1.0000"),
        server_default="1.0000",
        nullable=False,
    )


class TechnicalDebtItem(Base, TenantScopedMixin):
    """H4. Quantified structural, architectural, or maintainability debt items linked to `knowledge_entities` and `findings` (`TENANT_DIRECT`)."""

    __tablename__ = "technical_debt_items"
    __table_args__ = (
        Index(
            "ix_tech_debt_snap_cat_sev",
            "tenant_id",
            "snapshot_id",
            "debt_category",
            "severity",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "affected_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_technical_debt_items_entity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["findings.tenant_id", "findings.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_technical_debt_items_finding",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    affected_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    finding_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    debt_category: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    estimated_remediation_hours: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)


class ModernizationRecommendation(Base, TenantScopedMixin):
    """H5. Evidence-backed refactoring, decomposition, or migration blueprints addressing `technical_debt_items` (`TENANT_DIRECT`)."""

    __tablename__ = "modernization_recommendations"
    __table_args__ = (
        Index(
            "ix_mod_recs_snap_strategy_status",
            "tenant_id",
            "snapshot_id",
            "strategy_pattern",
            "review_status",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_modernization_recs_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_application",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_snapshot",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_analysis_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "addressed_debt_id"],
            ["technical_debt_items.tenant_id", "technical_debt_items.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_modernization_recs_debt",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    addressed_debt_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    strategy_pattern: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    current_state_summary: Mapped[str] = mapped_column(Text, nullable=False)
    target_state_architecture: Mapped[str] = mapped_column(Text, nullable=False)
    step_by_step_plan_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    effort_tshirt: Mapped[str] = mapped_column(String(8), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.8500"),
        server_default="0.8500",
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING_REVIEW",
        server_default="PENDING_REVIEW",
        nullable=False,
    )


__all__ = [
    "TestSuite",
    "TestCase",
    "TestCoverageLink",
    "TechnicalDebtItem",
    "ModernizationRecommendation",
]

