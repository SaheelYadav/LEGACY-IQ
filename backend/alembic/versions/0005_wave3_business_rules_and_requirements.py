"""Wave 3: Domain G Business Logic & Requirements Intelligence (6 Tables + RLS + Evidence FKs).

Revision ID: 0005_wave3_biz_reqs
Revises: 0004_wave2_tech_intel
Create Date: 2026-11-01
"""

from __future__ import annotations

import hashlib
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_wave3_biz_reqs"
down_revision = "0004_wave2_tech_intel"
branch_labels = None
depends_on = None

WAVE3_DIRECT_TENANT_TABLES = [
    "business_domains",
    "business_processes",
    "business_rules",
    "requirements",
    "requirement_acceptance_criteria",
    "requirement_traceability_links",
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # G1. business_domains
    # ------------------------------------------------------------------
    op.create_table(
        "business_domains",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_business_domains"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_business_domains_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "code",
            name="uq_business_domains_app_code",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_business_domains_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_business_domains_application",
        ),
    )

    # ------------------------------------------------------------------
    # G2. business_processes
    # ------------------------------------------------------------------
    op.create_table(
        "business_processes",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("business_domain_id", sa.Uuid(), nullable=True),
        sa.Column("entry_entity_id", sa.Uuid(), nullable=True),
        sa.Column("process_key", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("workflow_summary", sa.Text(), nullable=False),
        sa.Column(
            "ordered_step_entity_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_business_processes"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_business_processes_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "process_key",
            name="uq_business_processes_app_key",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_business_processes_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_business_processes_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_domain_id"],
            ["business_domains.tenant_id", "business_domains.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_processes_domain",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "entry_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_processes_entry_entity",
        ),
    )

    # ------------------------------------------------------------------
    # G3. business_rules
    # ------------------------------------------------------------------
    op.create_table(
        "business_rules",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("business_domain_id", sa.Uuid(), nullable=True),
        sa.Column("knowledge_entity_id", sa.Uuid(), nullable=True),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("rule_category", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("condition_expression", sa.Text(), nullable=False),
        sa.Column("action_consequence", sa.Text(), nullable=False),
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
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_business_rules"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_business_rules_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "rule_code",
            name="uq_business_rules_app_snap_code",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_business_rules_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_business_rules_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_business_rules_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_business_rules_analysis_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_domain_id"],
            ["business_domains.tenant_id", "business_domains.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_rules_domain",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_business_rules_knowledge_entity",
        ),
    )
    op.create_index(
        "ix_business_rules_snap_cat",
        "business_rules",
        ["tenant_id", "snapshot_id", "rule_category"],
    )

    # ------------------------------------------------------------------
    # G4. requirements
    # ------------------------------------------------------------------
    op.create_table(
        "requirements",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("business_domain_id", sa.Uuid(), nullable=True),
        sa.Column("knowledge_entity_id", sa.Uuid(), nullable=True),
        sa.Column("req_code", sa.String(length=64), nullable=False),
        sa.Column("req_type", sa.String(length=48), nullable=False),
        sa.Column(
            "priority",
            sa.String(length=16),
            server_default="MUST",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("specification_statement", sa.Text(), nullable=False),
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
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_requirements"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_requirements_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "snapshot_id",
            "req_code",
            name="uq_requirements_app_snap_code",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_requirements_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            ondelete="CASCADE",
            name="fk_requirements_application",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["repository_snapshots.tenant_id", "repository_snapshots.id"],
            ondelete="CASCADE",
            name="fk_requirements_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_requirements_analysis_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_domain_id"],
            ["business_domains.tenant_id", "business_domains.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_requirements_domain",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="SET NULL",
            name="fk_requirements_knowledge_entity",
        ),
    )
    op.create_index(
        "ix_requirements_snap_type",
        "requirements",
        ["tenant_id", "snapshot_id", "req_type"],
    )

    # ------------------------------------------------------------------
    # G5. requirement_acceptance_criteria
    # ------------------------------------------------------------------
    op.create_table(
        "requirement_acceptance_criteria",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_order", sa.Integer(), nullable=False),
        sa.Column("given_clause", sa.Text(), nullable=False),
        sa.Column("when_clause", sa.Text(), nullable=False),
        sa.Column("then_clause", sa.Text(), nullable=False),
        sa.Column(
            "verification_method",
            sa.String(length=32),
            server_default="UNIT_TEST",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "id", name="pk_requirement_acceptance_criteria"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_req_acceptance_criteria_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "requirement_id",
            "criterion_order",
            name="uq_req_acceptance_criteria_req_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_req_acceptance_criteria_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requirement_id"],
            ["requirements.tenant_id", "requirements.id"],
            ondelete="CASCADE",
            name="fk_req_acceptance_criteria_requirement",
        ),
    )

    # ------------------------------------------------------------------
    # G6. requirement_traceability_links
    # ------------------------------------------------------------------
    op.create_table(
        "requirement_traceability_links",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("business_rule_id", sa.Uuid(), nullable=True),
        sa.Column("knowledge_entity_id", sa.Uuid(), nullable=True),
        sa.Column("code_symbol_id", sa.Uuid(), nullable=True),
        sa.Column("test_case_id", sa.Uuid(), nullable=True),
        sa.Column("link_type", sa.String(length=48), nullable=False),
        sa.Column("origin_type", sa.String(length=32), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=5, scale=4),
            server_default="1.0000",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "id", name="pk_requirement_traceability_links"
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_req_traceability_links_tenant_id"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_req_traceability_links_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requirement_id"],
            ["requirements.tenant_id", "requirements.id"],
            ondelete="CASCADE",
            name="fk_req_traceability_links_requirement",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_rule_id"],
            ["business_rules.tenant_id", "business_rules.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_req_traceability_links_business_rule",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_entity_id"],
            ["knowledge_entities.tenant_id", "knowledge_entities.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_req_traceability_links_knowledge_entity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "code_symbol_id"],
            ["code_symbols.tenant_id", "code_symbols.id"],
            match="SIMPLE",
            ondelete="CASCADE",
            name="fk_req_traceability_links_code_symbol",
        ),
    )
    op.create_index(
        "ix_rtm_req",
        "requirement_traceability_links",
        ["tenant_id", "requirement_id"],
    )
    op.create_index(
        "ix_rtm_rule",
        "requirement_traceability_links",
        ["tenant_id", "business_rule_id"],
    )
    op.create_index(
        "ix_rtm_symbol",
        "requirement_traceability_links",
        ["tenant_id", "code_symbol_id"],
    )
    op.create_index(
        "ix_rtm_entity",
        "requirement_traceability_links",
        ["tenant_id", "knowledge_entity_id"],
    )

    # ------------------------------------------------------------------
    # Link finding_evidence_links -> business_rules & requirements
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_finding_evidence_links_business_rule",
        "finding_evidence_links",
        "business_rules",
        ["tenant_id", "business_rule_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_finding_evidence_links_requirement",
        "finding_evidence_links",
        "requirements",
        ["tenant_id", "requirement_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
        match="SIMPLE",
    )

    # ------------------------------------------------------------------
    # Enable & Force Row-Level Security on all 6 Domain G tables (50 -> 56)
    # ------------------------------------------------------------------
    for tbl in WAVE3_DIRECT_TENANT_TABLES:
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
    # Seed Wave 3 global prompt templates
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
        ("business_rule_miner_v1", "business_rule_miner"),
        ("requirements_synthesizer_v1", "requirements_synthesizer"),
    ]:
        sys_txt = (
            f"You are the LegacyIQ {agent_name} agent. Every finding MUST cite a valid "
            f"`cited_anchor_id` from `available_anchors`."
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
        "fk_finding_evidence_links_requirement",
        "finding_evidence_links",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_finding_evidence_links_business_rule",
        "finding_evidence_links",
        type_="foreignkey",
    )
    for tbl in reversed(WAVE3_DIRECT_TENANT_TABLES):
        op.drop_table(tbl)
