"""Wave 4 Live PostgreSQL Integration Tests: Test Intelligence, Risk Register, Technical Debt, Modernization Assessment, 4-Phase Roadmap, Human Review & Negative RLS Isolation."""

from __future__ import annotations

import io
from pathlib import Path
import uuid
import zipfile

from sqlalchemy import select, text

from app.api.v1.endpoints.organizations import bootstrap_default_context
from app.api.v1.endpoints.testing_modernization import (
    ModernizationRecommendationReviewRequest,
    TestCaseReviewRequest,
    get_snapshot_coverage_and_gaps_endpoint,
    get_snapshot_modernization_assessment_endpoint,
    get_snapshot_modernization_roadmap_endpoint,
    get_snapshot_risk_register_endpoint,
    get_snapshot_technical_debt_endpoint,
    get_snapshot_test_intelligence_endpoint,
    review_modernization_recommendation_endpoint,
    review_test_case_endpoint,
    trigger_wave4_testing_modernization_analysis,
)
from app.core.security import verify_and_activate_tenant_context
from app.db.session import SessionLocal, tenant_db_session
from app.integrations.storage import TenantObjectStorage
from app.models.identity import Organization
from app.models.testing_modernization import (
    ModernizationRecommendation,
    TechnicalDebtItem,
    TestCase,
    TestCoverageLink,
    TestSuite,
)
from app.services.agent_orchestrator import TechnicalIntelligenceOrchestrator
from app.services.ingestion_service import IngestionService
from app.services.technical_intelligence_service import TechnicalIntelligenceService


def _build_wave4_zip() -> bytes:
    run_nonce = uuid.uuid4().hex[:8]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "db/schema.sql",
            """
            CREATE TABLE public.customers (
                id UUID PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                ssn VARCHAR(32)
            );

            CREATE TABLE public.customer_orders (
                id UUID PRIMARY KEY,
                customer_id UUID NOT NULL,
                order_total NUMERIC(12, 2) NOT NULL,
                order_status VARCHAR(32) DEFAULT 'PENDING',
                CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id)
                    REFERENCES public.customers(id) ON DELETE RESTRICT
            );

            CREATE TABLE public.legacy_audit_dump (
                event_name VARCHAR(128),
                payload TEXT
            );
            """,
        )
        zf.writestr(
            "src/orders_service.py",
            f'''
from fastapi import APIRouter, Depends

router = APIRouter()

STRIPE_API_SECRET = "sk_live_legacy_{run_nonce}_9988776655"

class OrderFulfillmentService:
    def evaluate_order_discount(self, db_conn, order_total: float, customer_tier: str, items: list):
        if order_total <= 0:
            raise ValueError("Order total must exceed zero")
        if order_total > 10000 and customer_tier == "GOLD":
            discount_amount = order_total * 0.075
        else:
            discount_amount = 0.0
        net_total = order_total - discount_amount
        order_status = "APPROVED"
        raw_sql = f"SELECT id, email FROM customers WHERE tier = '{{customer_tier}}'"
        db_conn.execute(raw_sql)
        for item in items:
            db_conn.execute("INSERT INTO customer_orders (id, customer_id, order_total, order_status) VALUES (:id, :cid, :tot, :st)")
        return net_total, order_status

    def calculate_late_penalty(self, overdue_days: int, invoice_amount: float) -> float:
        if overdue_days > 30:
            return invoice_amount * 0.05
        return 0.0

@router.post("/api/v1/orders/submit")
def submit_order(user=Depends(lambda: True)):
    return {{"status": "SUBMITTED"}}

@router.post("/api/v1/orders/guest-checkout")
def guest_checkout():
    return {{"status": "GUEST_ACCEPTED"}}
''',
        )
        zf.writestr(
            "tests/test_orders.py",
            """
import pytest

def test_evaluate_order_discount_gold_tier(client):
    resp = client.post("/api/v1/orders/submit", json={"order_total": 15000})
    res = evaluate_order_discount(None, 15000.0, "GOLD", [])
    assert resp.status_code == 200
    assert res[0] == 13875.0
""",
        )
        zf.writestr(
            "coverage.xml",
            """<?xml version="1.0" ?>
<coverage line-rate="0.72">
  <packages>
    <package name="src">
      <classes>
        <class filename="src/orders_service.py" line-rate="0.72">
          <lines>
            <line number="8" hits="4"/>
            <line number="9" hits="4"/>
            <line number="10" hits="4"/>
            <line number="11" hits="2"/>
            <line number="22" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        )
        zf.writestr(
            "requirements.txt",
            """
pyyaml==5.3.1
fastapi==0.115.0
internal-billing-sdk>=2.0.0
""",
        )
        zf.writestr(
            "Dockerfile",
            """
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "src.orders_service:router"]
""",
        )
    return buf.getvalue()


def test_postgres_65_tables_and_61_rls_policies_active() -> None:
    with SessionLocal() as db:
        tables = set(
            db.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        assert len(tables) >= 65

        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev in {"0006_wave4_test_risk_mod", "0007_wave5_qa_reports_export"}

        rls_rows = db.execute(
            text(
                """
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND relname NOT IN (
                      'alembic_version',
                      'users',
                      'permissions',
                      'role_permissions',
                      'embedding_model_versions'
                  )
                """
            )
        ).fetchall()
        assert len(rls_rows) >= 61
        for relname, rowsec, forcerowsec in rls_rows:
            assert rowsec is True, f"RLS not enabled on {relname}"
            assert forcerowsec is True, f"FORCE RLS not enabled on {relname}"


def test_wave4_end_to_end_testing_risk_debt_modernization_roadmap_review_and_rls(
    tmp_path: Path,
) -> None:
    with SessionLocal() as boot_db:
        boot_info = bootstrap_default_context(db=boot_db)

    tenant_a_id = uuid.UUID(str(boot_info.tenant_id))
    user_a_id = uuid.UUID(str(boot_info.user_id))
    repo_a_id = uuid.UUID(str(boot_info.default_repository_id))

    storage = TenantObjectStorage(vault_root=tmp_path / "vault_wave4")
    orchestrator = TechnicalIntelligenceOrchestrator(allow_live_ollama=False)
    tech_service = TechnicalIntelligenceService(
        storage=storage, orchestrator=orchestrator
    )
    ingestion_service = IngestionService(
        storage=storage, tech_intel_service=tech_service
    )

    zip_bytes = _build_wave4_zip()

    with tenant_db_session(tenant_a_id) as db:
        ctx_a = verify_and_activate_tenant_context(
            db, tenant_id=tenant_a_id, user_id=user_a_id
        )
        ingest_summary = ingestion_service.ingest_zip_archive(
            db,
            tenant_id=tenant_a_id,
            repository_id=repo_a_id,
            zip_bytes=zip_bytes,
            snapshot_label=f"wave4-e2e-{uuid.uuid4().hex[:6]}",
            triggered_by_user_id=user_a_id,
            run_analysis_and_indexing=True,
        )
        snapshot_id = ingest_summary.snapshot_id

        # 1. Verify Test Intelligence (Discovered vs. Blueprint Tests & Coverage Links)
        test_intel = get_snapshot_test_intelligence_endpoint(
            snapshot_id=snapshot_id,
            suite_origin=None,
            test_kind=None,
            ctx_pair=(db, ctx_a),
        )
        assert test_intel["summary"]["discovered_test_cases"] >= 1
        assert test_intel["summary"]["recommended_test_blueprints"] >= 1
        assert len(test_intel["test_suites"]) >= 2
        assert len(test_intel["test_cases"]) >= 2

        origins = {s["suite_origin"] for s in test_intel["test_suites"]}
        assert "EXISTING_IN_REPO" in origins
        assert "AI_GENERATED_BLUEPRINT" in origins

        # 2. Verify Coverage & Gaps (Discovered vs. Estimated Coverage Separation)
        cov_gaps = get_snapshot_coverage_and_gaps_endpoint(
            snapshot_id=snapshot_id,
            ctx_pair=(db, ctx_a),
        )
        cov_metrics = cov_gaps["coverage_metrics"]
        assert cov_metrics["total_requirements"] >= 1
        assert cov_metrics["measured_coverage_report_links"] >= 1
        assert cov_metrics["inferred_blueprint_links"] >= 1
        assert "untested_requirements" in cov_gaps
        assert "untested_critical_components" in cov_gaps

        # 3. Verify Risk Register (Security, Dependency CVE, Performance, Data Integrity, Infra)
        risk_res = get_snapshot_risk_register_endpoint(
            snapshot_id=snapshot_id,
            severity=None,
            risk_category=None,
            ctx_pair=(db, ctx_a),
        )
        assert len(risk_res["risk_findings"]) >= 4
        risk_titles = " ".join(r["title"] for r in risk_res["risk_findings"])
        assert "CVE-2020-14343" in risk_titles
        assert "fastapi" not in risk_titles.lower()  # Never fabricate CVEs for clean packages

        for rf in risk_res["risk_findings"]:
            assert rf["is_confirmed_fact"] is False
            assert rf["likelihood"] in ("HIGH", "MEDIUM", "LOW")
            assert len(rf["evidence"]) >= 1
            assert len(rf["evidence"][0]["snippet_sha256"]) == 64

        # 4. Verify Technical Debt (Measured Metrics vs. Heuristic Effort Estimates)
        debt_res = get_snapshot_technical_debt_endpoint(
            snapshot_id=snapshot_id,
            debt_category=None,
            severity=None,
            ctx_pair=(db, ctx_a),
        )
        assert len(debt_res["technical_debt_items"]) >= 2
        assert (
            debt_res["measured_vs_estimated_summary"]["measured_metrics"]["metric_nature"]
            == "MEASURED"
        )
        assert (
            debt_res["measured_vs_estimated_summary"]["heuristic_estimates"]["metric_nature"]
            == "HEURISTIC_ESTIMATE"
        )
        for item in debt_res["technical_debt_items"]:
            assert item["effort_nature"] == "HEURISTIC_ESTIMATE"
            assert item["is_effort_estimated"] is True

        # 5. Verify Multi-Dimensional Modernization Assessment
        assess_res = get_snapshot_modernization_assessment_endpoint(
            snapshot_id=snapshot_id,
            ctx_pair=(db, ctx_a),
        )
        assert assess_res["microservices_recommended"] is False
        assert len(assess_res["dimensions"]) == 5
        arch_dim = next(
            d for d in assess_res["dimensions"] if d["dimension"] == "ARCHITECTURE_POSTURE"
        )
        assert arch_dim["recommended_posture"] == "MODULAR_MONOLITH"

        # 6. Verify 4-Phase Modernization Roadmap & Recommendations
        roadmap_res = get_snapshot_modernization_roadmap_endpoint(
            snapshot_id=snapshot_id,
            ctx_pair=(db, ctx_a),
        )
        assert len(roadmap_res["recommendations"]) >= 3
        assert len(roadmap_res["roadmap_phases"]) == 4
        for phase in roadmap_res["roadmap_phases"]:
            assert phase["effort_nature"] == "HEURISTIC_ESTIMATE"

        # 7. Verify Human Review Workflows on ModernizationRecommendation & TestCase
        first_rec_id = uuid.UUID(roadmap_res["recommendations"][0]["id"])
        rec_edit = review_modernization_recommendation_endpoint(
            recommendation_id=first_rec_id,
            payload=ModernizationRecommendationReviewRequest(
                new_status="MODIFIED_BY_HUMAN",
                updated_title="Phase 1 Priority Security & CVE Remediation",
                updated_effort_tshirt="M",
                review_comment="Scoped effort to medium sprint capacity.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert rec_edit["review_status"] == "MODIFIED_BY_HUMAN"
        assert rec_edit["is_confirmed_fact"] is False

        rec_approve = review_modernization_recommendation_endpoint(
            recommendation_id=first_rec_id,
            payload=ModernizationRecommendationReviewRequest(
                new_status="APPROVED",
                review_comment="Approved by Architecture Review Board.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert rec_approve["review_status"] == "APPROVED"
        assert rec_approve["is_confirmed_fact"] is True

        first_tc_id = uuid.UUID(test_intel["test_cases"][0]["id"])
        tc_approve = review_test_case_endpoint(
            test_case_id=first_tc_id,
            payload=TestCaseReviewRequest(
                new_status="APPROVED",
                review_comment="Verified test scenario against requirement.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert tc_approve["review_status"] == "APPROVED"
        assert tc_approve["is_confirmed_fact"] is True

        # 8. Verify Idempotent Re-Analysis Trigger Endpoint
        re_run = trigger_wave4_testing_modernization_analysis(
            snapshot_id=snapshot_id,
            ctx_pair=(db, ctx_a),
        )
        assert re_run["discovered_test_cases_count"] >= 1
        assert re_run["modernization_recommendations_count"] >= 3

    # 9. Verify Negative Tenant Isolation (RLS) across all 5 Wave 4 Domain H tables
    tenant_b_id = uuid.uuid4()
    with SessionLocal() as admin_db:
        admin_db.add(
            Organization(
                id=tenant_b_id,
                slug=f"wave4-isolated-{tenant_b_id.hex[:8]}",
                display_name="Wave 4 Isolated Tenant B",
            )
        )
        admin_db.commit()

    with tenant_db_session(tenant_b_id) as db_b:
        for model_cls in (
            TestSuite,
            TestCase,
            TestCoverageLink,
            TechnicalDebtItem,
            ModernizationRecommendation,
        ):
            leaked = db_b.execute(select(model_cls)).scalars().all()
            assert leaked == [], f"RLS leak detected on {model_cls.__tablename__}"

