"""Wave 3 Live PostgreSQL Integration, Traceability, Conflict/Gap, Impact, Human Review & Negative RLS Isolation Tests."""

from __future__ import annotations

import io
from pathlib import Path
import uuid
import zipfile

from sqlalchemy import select, text

from app.api.v1.endpoints.organizations import bootstrap_default_context
from app.api.v1.endpoints.requirements_intelligence import (
    BusinessRuleReviewRequest,
    ConflictResolveRequest,
    RequirementReviewRequest,
    get_snapshot_business_rules_endpoint,
    get_snapshot_conflicts_and_gaps_endpoint,
    get_snapshot_impact_analysis_endpoint,
    get_snapshot_requirements_endpoint,
    get_snapshot_traceability_endpoint,
    resolve_conflict_endpoint,
    review_business_rule_endpoint,
    review_requirement_endpoint,
)
from app.core.security import verify_and_activate_tenant_context
from app.db.session import SessionLocal, tenant_db_session
from app.integrations.storage import TenantObjectStorage
from app.models.business_intelligence import (
    BusinessDomain,
    BusinessProcess,
    BusinessRule,
    Requirement,
    RequirementAcceptanceCriterion,
    RequirementTraceabilityLink,
)
from app.models.identity import Organization, OrganizationMembership, User
from app.services.agent_orchestrator import TechnicalIntelligenceOrchestrator
from app.services.ingestion_service import IngestionService
from app.services.technical_intelligence_service import TechnicalIntelligenceService


def _build_wave3_zip() -> bytes:
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
            """,
        )
        zf.writestr(
            "src/orders_service.py",
            """
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()

class OrderFulfillmentService:
    def evaluate_order_discount(self, order_total: float, customer_tier: str, user=Depends(lambda: True)):
        if order_total <= 0:
            raise ValueError("Order total must exceed zero")
        if order_total > 10000 and customer_tier == "GOLD":
            discount_amount = order_total * 0.075
        else:
            discount_amount = 0.0
        net_total = order_total - discount_amount
        order_status = "APPROVED"
        sql_read = "SELECT id, email FROM customers WHERE id = :cid"
        sql_write = "INSERT INTO customer_orders (id, customer_id, order_total, order_status) VALUES (:id, :cid, :tot, :st)"
        return net_total, order_status

@router.post("/api/v1/orders/submit")
def submit_order(user=Depends(lambda: True)):
    svc = OrderFulfillmentService()
    return svc.evaluate_order_discount(15000.0, "GOLD")

@router.post("/api/v1/orders/guest-checkout")
def guest_checkout():
    return {"status": "GUEST_ACCEPTED"}
""",
        )
        zf.writestr(
            "docs/billing_policy.md",
            f"""# Billing & Discount Policy
Orders exceeding 5000 USD must receive a 12.5% discount rate and manager approval.
The `OrderFulfillmentService` reads `customers` and writes to `customer_orders`.
Run-ID: {uuid.uuid4().hex[:8]}
""",
        )
    return buf.getvalue()


def test_postgres_60_tables_and_56_rls_policies_active() -> None:
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
        assert len(tables) >= 60

        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev in {
            "0005_wave3_biz_reqs",
            "0006_wave4_test_risk_mod",
            "0007_wave5_qa_reports_export",
        }

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
        assert len(rls_rows) >= 56
        for relname, rowsec, forcerowsec in rls_rows:
            assert rowsec is True, f"RLS not enabled on {relname}"
            assert forcerowsec is True, f"FORCE RLS not enabled on {relname}"


def test_wave3_end_to_end_business_rules_requirements_traceability_conflicts_impact_review_and_rls(
    tmp_path: Path,
) -> None:
    with SessionLocal() as boot_db:
        boot_info = bootstrap_default_context(db=boot_db)

    tenant_a_id = uuid.UUID(str(boot_info.tenant_id))
    user_a_id = uuid.UUID(str(boot_info.user_id))
    repo_a_id = uuid.UUID(str(boot_info.default_repository_id))

    storage = TenantObjectStorage(vault_root=tmp_path / "vault_wave3")
    orchestrator = TechnicalIntelligenceOrchestrator(allow_live_ollama=False)
    tech_service = TechnicalIntelligenceService(
        storage=storage, orchestrator=orchestrator
    )
    ingestion_service = IngestionService(
        storage=storage, tech_intel_service=tech_service
    )

    zip_bytes = _build_wave3_zip()

    with tenant_db_session(tenant_a_id) as db:
        ctx_a = verify_and_activate_tenant_context(
            db, tenant_id=tenant_a_id, user_id=user_a_id
        )
        ingest_summary = ingestion_service.ingest_zip_archive(
            db,
            tenant_id=tenant_a_id,
            repository_id=repo_a_id,
            zip_bytes=zip_bytes,
            snapshot_label=f"wave3-e2e-{uuid.uuid4().hex[:6]}",
            triggered_by_user_id=user_a_id,
            run_analysis_and_indexing=True,
        )
        snapshot_id = ingest_summary.snapshot_id

        # 1. Verify Business Rules Discovery
        rules_res = get_snapshot_business_rules_endpoint(
            snapshot_id=snapshot_id,
            category=None,
            domain_code=None,
            review_status=None,
            ctx_pair=(db, ctx_a),
        )
        assert len(rules_res["domains"]) >= 2
        assert len(rules_res["processes"]) >= 1
        assert len(rules_res["business_rules"]) >= 6

        categories = {r["rule_category"] for r in rules_res["business_rules"]}
        assert {"VALIDATION", "CALCULATION", "AUTHORIZATION", "INVARIANT"}.issubset(
            categories
        )
        for r in rules_res["business_rules"]:
            assert r["is_confirmed_fact"] is False
            assert len(r["evidence"]) >= 1
            assert len(r["evidence"][0]["snippet_sha256"]) == 64

        # 2. Verify Requirements Intelligence & Given/When/Then Acceptance Criteria
        reqs_res = get_snapshot_requirements_endpoint(
            snapshot_id=snapshot_id,
            req_type=None,
            priority=None,
            review_status=None,
            ctx_pair=(db, ctx_a),
        )
        assert len(reqs_res["requirements"]) >= 6
        req_types = {r["req_type"] for r in reqs_res["requirements"]}
        assert "FUNCTIONAL" in req_types
        assert "NON_FUNCTIONAL_SECURITY" in req_types
        assert "DATA_CONSTRAINT" in req_types
        for rq in reqs_res["requirements"]:
            assert rq["is_confirmed_fact"] is False
            assert len(rq["acceptance_criteria"]) >= 1
            assert len(rq["actors"]) >= 1
            assert len(rq["evidence"]) >= 1

        # 3. Verify Human Review Workflows (Edit -> Request Review -> Approve & Reject)
        first_rule_id = uuid.UUID(rules_res["business_rules"][0]["id"])
        rule_edit_res = review_business_rule_endpoint(
            rule_id=first_rule_id,
            payload=BusinessRuleReviewRequest(
                new_status="MODIFIED_BY_HUMAN",
                updated_title="Curated Order Total Positive Validation Rule",
                updated_condition_expression="IF order_total <= 0",
                updated_action_consequence="RAISE ValueError and reject checkout",
                review_comment="Refined wording during domain review.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert rule_edit_res["review_status"] == "MODIFIED_BY_HUMAN"
        assert rule_edit_res["is_confirmed_fact"] is False
        assert rule_edit_res["version_no"] == 2

        rule_req_rev = review_business_rule_endpoint(
            rule_id=first_rule_id,
            payload=BusinessRuleReviewRequest(
                new_status="PENDING_REVIEW",
                review_comment="Requesting lead architect sign-off.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert rule_req_rev["review_status"] == "PENDING_REVIEW"
        assert rule_req_rev["version_no"] == 3

        rule_approve_res = review_business_rule_endpoint(
            rule_id=first_rule_id,
            payload=BusinessRuleReviewRequest(
                new_status="APPROVED",
                review_comment="Approved as confirmed business rule.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert rule_approve_res["review_status"] == "APPROVED"
        assert rule_approve_res["is_confirmed_fact"] is True
        assert rule_approve_res["version_no"] == 4
        assert len(rule_approve_res["review_history"]) == 3

        first_req_id = uuid.UUID(reqs_res["requirements"][0]["id"])
        req_edit_res = review_requirement_endpoint(
            requirement_id=first_req_id,
            payload=RequirementReviewRequest(
                new_status="MODIFIED_BY_HUMAN",
                updated_title="Mandatory Positive Order Total Requirement",
                updated_priority="MUST",
                review_comment="Updated priority and title.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert req_edit_res["review_status"] == "MODIFIED_BY_HUMAN"
        assert req_edit_res["version_no"] == 2

        req_approve_res = review_requirement_endpoint(
            requirement_id=first_req_id,
            payload=RequirementReviewRequest(
                new_status="APPROVED",
                review_comment="Confirmed requirement against code and DDL.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert req_approve_res["review_status"] == "APPROVED"
        assert req_approve_res["is_confirmed_fact"] is True
        assert req_approve_res["version_no"] == 3
        assert len(req_approve_res["review_history"]) == 2

        # 4. Verify Forward & Backward Traceability Matrix
        trace_res = get_snapshot_traceability_endpoint(
            snapshot_id=snapshot_id, ctx_pair=(db, ctx_a)
        )
        assert len(trace_res["forward_traceability"]) >= 6
        assert len(trace_res["backward_traceability"]) >= 2
        first_fwd = trace_res["forward_traceability"][0]
        assert len(first_fwd["business_rules"]) >= 1
        assert len(first_fwd["evidence"]) >= 1

        # 5. Verify Conflict & Gap Detection + Conflict Resolution
        conflicts_res = get_snapshot_conflicts_and_gaps_endpoint(
            snapshot_id=snapshot_id, ctx_pair=(db, ctx_a)
        )
        assert len(conflicts_res["conflicts"]) >= 1
        conflict_types = {c["conflict_type"] for c in conflicts_res["conflicts"]}
        assert "CODE_VS_DOC" in conflict_types or "REQUIREMENT_CONTRADICTION" in conflict_types
        first_conflict = conflicts_res["conflicts"][0]
        assert first_conflict["primary_evidence"] is not None
        assert first_conflict["conflicting_evidence"] is not None

        resolved_conf = resolve_conflict_endpoint(
            conflict_id=uuid.UUID(first_conflict["id"]),
            payload=ConflictResolveRequest(
                new_status="RESOLVED_KEEP_PRIMARY",
                resolution_notes="Code threshold (10000 USD / 7.5%) is authoritative over outdated doc.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert resolved_conf["status"] == "RESOLVED_KEEP_PRIMARY"

        # 6. Verify Multi-Hop Impact Analysis
        impact_res = get_snapshot_impact_analysis_endpoint(
            snapshot_id=snapshot_id,
            target_id=first_req_id,
            ctx_pair=(db, ctx_a),
        )
        assert impact_res["target"]["id"] == str(first_req_id)
        assert impact_res["blast_radius_risk"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        total_affected = (
            len(impact_res["affected_apis"])
            + len(impact_res["affected_database_tables"])
            + len(impact_res["affected_code_components"])
            + len(impact_res["affected_business_rules"])
        )
        assert total_affected >= 1

    # 7. Verify Negative Tenant Isolation (RLS) across all 6 Wave 3 tables
    tenant_b_id = uuid.uuid4()
    with SessionLocal() as admin_db:
        admin_db.add(
            Organization(
                id=tenant_b_id,
                slug=f"wave3-isolated-{tenant_b_id.hex[:8]}",
                display_name="Wave 3 Isolated Tenant B",
            )
        )
        admin_db.commit()

    with tenant_db_session(tenant_b_id) as db_b:
        for model_cls in (
            BusinessDomain,
            BusinessProcess,
            BusinessRule,
            Requirement,
            RequirementAcceptanceCriterion,
            RequirementTraceabilityLink,
        ):
            leaked = db_b.execute(select(model_cls)).scalars().all()
            assert leaked == [], f"RLS leak detected on {model_cls.__tablename__}"

