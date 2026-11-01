"""Wave 4: Domain H Testing, Risk, Technical Debt & Modernization Intelligence (5 Tables + RLS + RTM FK).

Revision ID: 0006_wave4_test_risk_mod
Revises: 0005_wave3_biz_reqs
Create Date: 2026-11-01
"""

from __future__ import annotations

import hashlib
import json
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0006_wave4_test_risk_mod"
down_revision = "0005_wave3_biz_reqs"
branch_labels = None
depends_on = None

WAVE4_DIRECT_TENANT_TABLES = [
    "test_suites",
    "test_cases",
    "test_coverage_links",
    "technical_debt_items",
    "modernization_recommendations",
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # H1. test_suites
    # ------------------------------------------------------------------
    op.create_table(
        "test_suites",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("suite_name", sa.String(length=255), nullable=False),
        sa.Column("test_framework", sa.String(length=32), nullable=False),
        sa.Column("suite_origin", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_test_suites"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_test_suites_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "suite_name",
            name="uq_test_suites_app_snap_name",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_test_suites_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_test_suites_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_test_suites_snapshot",
        ),
    )

    # ------------------------------------------------------------------
    # H2. test_cases
    # ------------------------------------------------------------------
    op.create_table(
        "test_cases",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_suite_id", sa.Uuid(), nullable=False),
        sa.Column("test_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("test_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("test_kind", sa.String(length=32), nullable=False),
        sa.Column("scenario_description", sa.Text(), nullable=False),
        sa.Column("generated_code_blueprint", sa.Text(), nullable=True),
        sa.Column(
            "last_observed_status",
            sa.String(length=32),
            server_default="UNKNOWN",
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_test_cases"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_test_cases_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "test_suite_id",
            "test_key",
            name="uq_test_cases_suite_key",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_test_cases_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_test_cases_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "test_suite_id"],
            ["test_suites.tenant_id", "test_suites.id"],
            ondelete="CASCADE",
            name="fk_test_cases_suite",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "test_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            ondelete="SET NULL",
            match="SIMPLE",
            name="fk_test_cases_symbol",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_test_cases_analysis_run",
        ),
    )

    # ------------------------------------------------------------------
    # H3. test_coverage_links
    # ------------------------------------------------------------------
    op.create_table(
        "test_coverage_links",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_case_id", sa.Uuid(), nullable=False),
        sa.Column("target_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("target_business_rule_id", sa.Uuid(), nullable=True),
        sa.Column("target_requirement_id", sa.Uuid(), nullable=True),
        sa.Column("coverage_source", sa.String(length=32), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            server_default="1.0000",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_test_coverage_links"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_test_coverage_links_tenant_id"),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_test_coverage_links_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_test_coverage_links_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "test_case_id"],
            ["test_cases.tenant_id", "test_cases.id"],
            ondelete="CASCADE",
            name="fk_test_coverage_links_test_case",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            ondelete="CASCADE",
            match="SIMPLE",
            name="fk_test_coverage_links_symbol",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_business_rule_id"],
            ["business_rules.tenant_id", "business_rules.id"],
            ondelete="CASCADE",
            match="SIMPLE",
            name="fk_test_coverage_links_business_rule",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_requirement_id"],
            ["requirements.tenant_id", "requirements.id"],
            ondelete="CASCADE",
            match="SIMPLE",
            name="fk_test_coverage_links_requirement",
        ),
    )
    op.create_index(
        "ix_test_cov_symbol",
        "test_coverage_links",
        ["tenant_id", "target_symbol_id"],
    )
    op.create_index(
        "ix_test_cov_req",
        "test_coverage_links",
        ["tenant_id", "target_requirement_id"],
    )
    op.create_index(
        "ix_test_cov_rule",
        "test_coverage_links",
        ["tenant_id", "target_business_rule_id"],
    )

    # ------------------------------------------------------------------
    # H4. technical_debt_items
    # ------------------------------------------------------------------
    op.create_table(
        "technical_debt_items",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("affected_entity_id", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("debt_category", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("estimated_remediation_hours", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_technical_debt_items"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_technical_debt_items_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_technical_debt_items_analysis_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "affected_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            ondelete="SET NULL",
            match="SIMPLE",
            name="fk_technical_debt_items_entity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["findings.tenant_id", "findings.id"],
            ondelete="SET NULL",
            match="SIMPLE",
            name="fk_technical_debt_items_finding",
        ),
    )
    op.create_index(
        "ix_tech_debt_snap_cat_sev",
        "technical_debt_items",
        ["tenant_id", "snapshot_id", "debt_category", "severity"],
    )

    # ------------------------------------------------------------------
    # H5. modernization_recommendations
    # ------------------------------------------------------------------
    op.create_table(
        "modernization_recommendations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("addressed_debt_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_pattern", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("current_state_summary", sa.Text(), nullable=False),
        sa.Column("target_state_architecture", sa.Text(), nullable=False),
        sa.Column("step_by_step_plan_markdown", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("effort_tshirt", sa.String(length=8), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            server_default="0.8500",
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.String(length=32),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_modernization_recommendations"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_modernization_recommendations_tenant_id"
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_modernization_recs_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_modernization_recs_analysis_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "addressed_debt_id"],
            ["technical_debt_items.tenant_id", "technical_debt_items.id"],
            ondelete="SET NULL",
            match="SIMPLE",
            name="fk_modernization_recs_debt",
        ),
    )
    op.create_index(
        "ix_mod_recs_snap_strategy_status",
        "modernization_recommendations",
        ["tenant_id", "snapshot_id", "strategy_pattern", "review_status"],
    )

    # ------------------------------------------------------------------
    # Wire composite FK from requirement_traceability_links -> test_cases
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_req_traceability_links_test_case",
        "requirement_traceability_links",
        "test_cases",
        ["tenant_id", "test_case_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
        match="SIMPLE",
    )

    # ------------------------------------------------------------------
    # Enable & Force Row-Level Security on all 5 Domain H tables (56 -> 61)
    # ------------------------------------------------------------------
    for tbl in WAVE4_DIRECT_TENANT_TABLES:
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
    # Seed Wave 4 global prompt templates
    # ------------------------------------------------------------------
    output_schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "title",
                            "statement_markdown",
                            "cited_anchor_id",
                        ],
                    },
                }
            },
        }
    )
    for t_key, agent_name in [
        ("test_intelligence_architect_v1", "test_intelligence_architect"),
        ("risk_security_auditor_v1", "risk_security_auditor"),
        ("technical_debt_analyzer_v1", "technical_debt_analyzer"),
        ("modernization_strategist_v1", "modernization_strategist"),
    ]:
        sys_txt = (
            f"You are the LegacyIQ {agent_name} agent. Every finding MUST cite a valid "
            f"`cited_anchor_id` from `available_anchors` and separate measured facts from estimates."
        )
        usr_txt = "Context:\n{{context_json}}\nReturn JSON matching AgentFindingsPayload."
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
    op.drop_constraint(
        "fk_req_traceability_links_test_case",
        "requirement_traceability_links",
        type_="foreignkey",
    )
    for tbl in reversed(WAVE4_DIRECT_TENANT_TABLES):
        op.drop_table(tbl)

