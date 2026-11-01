"""Wave 5 Live PostgreSQL Integration Tests: 76-Table & 72-RLS Verification, Unified Dashboard, Executive Insights, Semantic Q&A, 11 Report Types, Immutable Approved Versioning, Multi-Format Exports, Hash-Chained Audit Logs, and Tenant/Project Isolation."""

from __future__ import annotations

import io
from pathlib import Path
import uuid
import zipfile

import pytest
from sqlalchemy import select, text

from app.api.v1.endpoints.organizations import bootstrap_default_context
from app.core.security import SecurityViolationError
from app.db.session import SessionLocal, tenant_db_session
from app.integrations.storage import TenantObjectStorage
from app.models.identity import Organization, OrganizationMembership, User
from app.models.reporting_governance import (
    ApprovalRequest,
    AuditLog,
    IntelligenceReport,
    IntelligenceReportVersion,
    QaConversation,
    QaMessage,
    ReportExport,
)
from app.services.agent_orchestrator import TechnicalIntelligenceOrchestrator
from app.services.ingestion_service import IngestionService
from app.services.reporting_qa_export_service import (
    REPORT_TYPE_CATALOG,
    ReportingQaExportService,
)
from app.services.technical_intelligence_service import TechnicalIntelligenceService


def _build_wave5_sample_zip() -> bytes:
    """Create a realistic repository archive covering code, SQL DDL, OpenAPI, Dockerfile, docs, and tests."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "schema/001_accounts.sql",
            """
            CREATE TABLE customer_accounts (
                account_id UUID PRIMARY KEY,
                customer_email VARCHAR(255) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
                balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
            );
            """,
        )
        zf.writestr(
            "api/openapi.yaml",
            """
openapi: 3.0.3
info:
  title: Customer Account API
  version: 1.0.0
paths:
  /api/v1/accounts/{account_id}/deactivate:
    post:
      operationId: deactivateAccount
      summary: Deactivate customer account
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Deactivated
            """,
        )
        zf.writestr(
            "src/account_service.py",
            '''"""Customer account lifecycle and deactivation rules."""

import hashlib

def deactivate_customer_account(account_id: str, balance_cents: int, is_frozen: bool) -> dict:
    """
    Business Rule: A customer account can only be deactivated when balance_cents == 0.
    If balance_cents > 0, raise ValueError and block deactivation.
    """
    if is_frozen:
        raise ValueError("Frozen account requires compliance clearance before deactivation.")
    if balance_cents > 0:
        raise ValueError("Cannot deactivate customer_accounts row while balance_cents > 0.")
    audit_digest = hashlib.md5(account_id.encode("utf-8")).hexdigest()
    return {
        "table": "customer_accounts",
        "account_id": account_id,
        "new_status": "DEACTIVATED",
        "audit_digest": audit_digest,
    }
''',
        )
        zf.writestr(
            "tests/test_account_service.py",
            """
from src.account_service import deactivate_customer_account

def test_deactivate_zero_balance_account():
    res = deactivate_customer_account("acc-101", 0, False)
    assert res["new_status"] == "DEACTIVATED"
""",
        )
        zf.writestr(
            "docs/architecture.md",
            f"""# Customer Account Architecture
The `deactivate_customer_account` service updates `customer_accounts` and enforces zero-balance deactivation rules.
Run Marker: {uuid.uuid4().hex}
""",
        )
    return buf.getvalue()


def test_postgres_76_tables_and_72_rls_policies_active() -> None:
    """Verify PostgreSQL 17 has all 76 canonical tables, Alembic revision 0007_wave5_qa_reports_export, and 72 RLS-forced tables."""
    with SessionLocal() as db:
        table_count = db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name != 'alembic_version'"
            )
        ).scalar_one()
        assert table_count == 76, f"Expected 76 tables, found {table_count}"

        rev = db.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert rev == "0007_wave5_qa_reports_export"

        rls_count = db.execute(
            text(
                "SELECT count(*) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                "AND c.relrowsecurity = true AND c.relforcerowsecurity = true"
            )
        ).scalar_one()
        assert rls_count == 72, f"Expected 72 RLS-forced tables, found {rls_count}"


def test_wave5_end_to_end_dashboard_qa_reports_versioning_exports_audit_and_rls(
    tmp_path: Path,
) -> None:
    """
    End-to-end live PostgreSQL test for Wave 5:
    1. Unified Application Intelligence Dashboard & Executive Insights
    2. Semantic Q&A Assistant (specialized intents, source citations, anti-hallucination guard, conversation isolation)
    3. 11-Type Report Generation Engine, Lifecycle Transitions & Strict Immutability on APPROVED versions
    4. Controlled Exports (PDF, DOCX, XLSX, JSON), Safe Download & Hash-Chained AuditLog
    5. Negative Cross-Tenant RLS Isolation & Cross-Project RBAC Denial
    """
    with SessionLocal() as boot_db:
        boot_info = bootstrap_default_context(db=boot_db)

    tenant_a = uuid.UUID(str(boot_info.tenant_id))
    user_a1 = uuid.UUID(str(boot_info.user_id))
    repo_a_id = uuid.UUID(str(boot_info.default_repository_id))
    user_a2_no_project_access = uuid.uuid4()

    storage = TenantObjectStorage(vault_root=tmp_path / "vault_wave5")
    orchestrator = TechnicalIntelligenceOrchestrator(allow_live_ollama=False)
    tech_service = TechnicalIntelligenceService(
        storage=storage, orchestrator=orchestrator
    )
    ingestion_service = IngestionService(
        storage=storage, tech_intel_service=tech_service
    )
    wave5_svc = ReportingQaExportService(
        storage=storage, orchestrator=orchestrator
    )

    with tenant_db_session(tenant_a) as db:
        # Create a second user who has NO project membership on the target project
        db.add(
            User(
                id=user_a2_no_project_access,
                email=f"outsider-{user_a2_no_project_access.hex[:8]}@legacyiq.local",
                full_name="Unassigned Tenant Member",
            )
        )
        db.flush()

        ingest_summary = ingestion_service.ingest_zip_archive(
            db,
            tenant_id=tenant_a,
            repository_id=repo_a_id,
            zip_bytes=_build_wave5_sample_zip(),
            snapshot_label=f"wave5-e2e-{uuid.uuid4().hex[:6]}",
            triggered_by_user_id=user_a1,
            run_analysis_and_indexing=True,
        )
        snapshot_id = ingest_summary.snapshot_id

        # --------------------------------------------------------------
        # 1. Unified Application Intelligence Dashboard & Executive Insights
        # --------------------------------------------------------------
        dash = wave5_svc.get_application_intelligence_dashboard(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            snapshot_id=snapshot_id,
        )
        assert dash["snapshot_overview"]["snapshot_id"] == str(snapshot_id)
        assert dash["snapshot_overview"]["metric_basis"] == "MEASURED"
        assert dash["technical_inventory"]["code_symbols_count"] >= 1
        assert dash["technical_inventory"]["db_tables_count"] >= 1
        assert dash["technical_inventory"]["api_endpoints_count"] >= 1
        assert dash["business_and_requirements"]["business_rules_count"] >= 1
        assert dash["business_and_requirements"]["requirements_count"] >= 1
        assert dash["testing_and_coverage"]["discovered_test_cases_count"] >= 1
        assert "MEASURED" in dash["metric_basis_legend"]
        assert "HEURISTIC_ESTIMATE" in dash["metric_basis_legend"]
        assert "INFERRED" in dash["metric_basis_legend"]

        exec_ins = wave5_svc.get_executive_insights(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            snapshot_id=snapshot_id,
        )
        assert 0 <= exec_ins["overall_application_health"]["health_score"] <= 100
        assert exec_ins["overall_application_health"]["health_grade"] in {
            "A",
            "B",
            "C",
            "D",
        }
        assert exec_ins["architecture_complexity"]["metric_basis"] == "MEASURED"
        assert (
            exec_ins["estimated_modernization_effort"]["metric_basis"]
            == "HEURISTIC_ESTIMATE"
        )

        # --------------------------------------------------------------
        # 2. Semantic Q&A Assistant & Specialized Intelligence Queries
        # --------------------------------------------------------------
        q_arch = wave5_svc.ask_question(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            snapshot_id=snapshot_id,
            question="Explain the overall architecture of this application.",
        )
        conv_id = uuid.UUID(q_arch["conversation_id"])
        assert q_arch["question_intent"] == "ARCHITECTURE_DISCOVERY"
        assert q_arch["assistant_message"]["insufficient_evidence"] is False
        assert len(q_arch["assistant_message"]["direct_facts"]) >= 1
        assert len(q_arch["assistant_message"]["citations"]) >= 1
        first_cit = q_arch["assistant_message"]["citations"][0]
        assert first_cit["relative_path"]
        assert first_cit["start_line"] >= 1
        assert len(first_cit["snippet_sha256"]) == 64

        # Follow-up specialized query in the same conversation: Business Process / Deactivation
        q_deact = wave5_svc.ask_question(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            conversation_id=conv_id,
            question="What happens when a customer account is deactivated?",
        )
        assert q_deact["question_intent"] == "BUSINESS_PROCESS"
        assert q_deact["assistant_message"]["insufficient_evidence"] is False
        assert len(q_deact["assistant_message"]["citations"]) >= 1

        # API-DB dependency query
        q_apidb = wave5_svc.ask_question(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            conversation_id=conv_id,
            question="Which APIs depend on this database table?",
        )
        assert q_apidb["question_intent"] == "API_DB_DEPENDENCY"
        assert len(q_apidb["assistant_message"]["direct_facts"]) >= 1

        # Insufficient evidence anti-hallucination guard test
        q_missing = wave5_svc.ask_question(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            conversation_id=conv_id,
            question="How does the xyzzynonexistentquantumwarpdrive999fluxcapacitor operate?",
        )
        assert q_missing["assistant_message"]["insufficient_evidence"] is True
        assert q_missing["assistant_message"]["citations"] == []
        assert (
            "Insufficient Evidence"
            in q_missing["assistant_message"]["content_markdown"]
        )

        conv_detail = wave5_svc.get_conversation(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            conversation_id=conv_id,
        )
        assert len(conv_detail["messages"]) == 8  # 4 USER + 4 ASSISTANT turns

        # --------------------------------------------------------------
        # 3. 11 Report Types + Lifecycle + Strict Immutability on APPROVED
        # --------------------------------------------------------------
        generated_reports: dict[str, dict] = {}
        for rtype in REPORT_TYPE_CATALOG:
            rep_data = wave5_svc.generate_report(
                db,
                tenant_id=tenant_a,
                user_id=user_a1,
                snapshot_id=snapshot_id,
                report_type=rtype,
            )
            assert rep_data["report_type"] == rtype
            assert rep_data["version_no"] == 1
            assert rep_data["is_immutable"] is False
            assert len(rep_data["sections"]) >= 1
            assert len(rep_data["evidence_references"]) >= 1
            generated_reports[rtype] = rep_data

        complete_rep_id = uuid.UUID(
            generated_reports["COMPLETE_INTELLIGENCE"]["id"]
        )

        # Submit for review -> Approve
        sub_rep = wave5_svc.transition_report_lifecycle(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            report_id=complete_rep_id,
            target_status="SUBMITTED_FOR_REVIEW",
            review_comment="Ready for architecture board sign-off.",
        )
        assert sub_rep["lifecycle_status"] == "SUBMITTED_FOR_REVIEW"
        assert sub_rep["is_immutable"] is False

        app_rep = wave5_svc.transition_report_lifecycle(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            report_id=complete_rep_id,
            target_status="APPROVED",
            review_comment="Approved v1 baseline report.",
        )
        assert app_rep["version_no"] == 1
        assert app_rep["lifecycle_status"] == "APPROVED"
        assert app_rep["is_immutable"] is True
        v1_hash = app_rep["content_sha256"]
        v1_summary = app_rep["executive_summary_markdown"]

        # CRITICAL RULE: Editing an APPROVED report MUST NOT overwrite v1; it must create v2!
        v2_rep = wave5_svc.transition_report_lifecycle(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            report_id=complete_rep_id,
            target_status="DRAFT",
            review_comment="Creating v2 draft with updated executive notes.",
            updated_executive_summary_markdown="Updated v2 Executive Summary with post-audit notes.",
        )
        assert v2_rep["current_version_no"] == 2
        assert v2_rep["version_no"] == 2
        assert v2_rep["lifecycle_status"] == "DRAFT"
        assert v2_rep["is_immutable"] is False
        assert (
            v2_rep["executive_summary_markdown"]
            == "Updated v2 Executive Summary with post-audit notes."
        )

        # Fetch historical v1 and prove it remained strictly immutable!
        v1_fetched = wave5_svc.get_report(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            report_id=complete_rep_id,
            version_no=1,
        )
        assert v1_fetched["version_no"] == 1
        assert v1_fetched["lifecycle_status"] == "APPROVED"
        assert v1_fetched["is_immutable"] is True
        assert v1_fetched["content_sha256"] == v1_hash
        assert v1_fetched["executive_summary_markdown"] == v1_summary

        # --------------------------------------------------------------
        # 4. Export Governance (PDF, DOCX, XLSX, JSON), Download & Audit Chain
        # --------------------------------------------------------------
        for fmt in ("PDF", "DOCX", "XLSX", "JSON"):
            exp_meta = wave5_svc.export_report(
                db,
                tenant_id=tenant_a,
                user_id=user_a1,
                report_id=complete_rep_id,
                export_format=fmt,
                version_no=1,
            )
            assert exp_meta["export_format"] == fmt
            assert exp_meta["file_size_bytes"] > 0
            raw_bytes, fname, mime = wave5_svc.download_export(
                db,
                tenant_id=tenant_a,
                user_id=user_a1,
                export_id=uuid.UUID(exp_meta["id"]),
            )
            assert len(raw_bytes) == exp_meta["file_size_bytes"]
            assert fname.endswith(fmt.lower())
            assert mime

        exp_list = wave5_svc.list_exports(
            db,
            tenant_id=tenant_a,
            user_id=user_a1,
            snapshot_id=snapshot_id,
        )
        assert len(exp_list["exports"]) == 4
        assert all(e["download_count"] == 1 for e in exp_list["exports"])
        assert len(exp_list["audit_logs"]) >= 15

        # --------------------------------------------------------------
        # 5. Cross-Project RBAC Denial within Tenant A
        # --------------------------------------------------------------
        with pytest.raises(SecurityViolationError):
            wave5_svc.get_application_intelligence_dashboard(
                db,
                tenant_id=tenant_a,
                user_id=user_a2_no_project_access,
                snapshot_id=snapshot_id,
            )
        with pytest.raises(SecurityViolationError):
            wave5_svc.get_report(
                db,
                tenant_id=tenant_a,
                user_id=user_a2_no_project_access,
                report_id=complete_rep_id,
            )

    # --------------------------------------------------------------
    # 6. Negative Cross-Tenant RLS Isolation across all Wave 5 tables
    # --------------------------------------------------------------
    tenant_b = uuid.uuid4()
    with SessionLocal() as admin_db:
        admin_db.add(
            Organization(
                id=tenant_b,
                slug=f"wave5-isolated-{tenant_b.hex[:8]}",
                display_name="Wave 5 Isolated Tenant B",
            )
        )
        admin_db.commit()

    with tenant_db_session(tenant_b) as db_b:
        for model_cls in (
            QaConversation,
            QaMessage,
            IntelligenceReport,
            IntelligenceReportVersion,
            ReportExport,
            AuditLog,
            ApprovalRequest,
        ):
            leaked = db_b.execute(select(model_cls)).scalars().all()
            assert (
                leaked == []
            ), f"RLS leak detected on {model_cls.__tablename__}"
