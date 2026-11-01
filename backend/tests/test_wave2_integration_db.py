"""Wave 2 Live PostgreSQL Integration & Negative RLS Isolation Tests."""

from __future__ import annotations

import io
from pathlib import Path
import uuid
import zipfile
import zlib

from sqlalchemy import select, text

from app.api.v1.endpoints.organizations import bootstrap_default_context
from app.api.v1.endpoints.technical_intelligence import (
    FindingReviewRequest,
    get_snapshot_agent_orchestration,
    get_snapshot_api_intelligence,
    get_snapshot_database_intelligence,
    get_snapshot_documentation_intelligence,
    get_snapshot_findings,
    get_snapshot_infrastructure_intelligence,
    get_snapshot_knowledge_graph,
    review_finding_endpoint,
    traverse_snapshot_knowledge_graph,
)
from app.core.security import verify_and_activate_tenant_context
from app.db.session import SessionLocal, tenant_db_session
from app.integrations.storage import TenantObjectStorage
from app.models.agent_orchestration import AgentExecutionEvent, AgentRun
from app.models.identity import Organization, OrganizationMembership, User
from app.models.ingestion import Repository
from app.models.knowledge_graph import (
    EvidenceAnchor,
    Finding,
    KnowledgeEntity,
    KnowledgeRelationship,
    ReviewHistory,
)
from app.models.technical_intelligence import (
    ApiEndpoint,
    DbForeignKey,
    DbTable,
    DocSection,
    InfraResource,
)
from app.services.agent_orchestrator import (
    AgentFindingClaim,
    AgentFindingsPayload,
    TechnicalIntelligenceOrchestrator,
)
from app.services.ingestion_service import IngestionService


def _build_wave2_polyglot_zip() -> bytes:
    """Create a rich in-memory ZIP archive covering SQL, ORM, OpenAPI, GraphQL, Docker, K8s, Terraform, MD, HTML, DOCX, XLSX, and PDF."""
    buf = io.BytesIO()

    # Build embedded DOCX
    docx_io = io.BytesIO()
    with zipfile.ZipFile(docx_io, "w") as dz:
        dz.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Operations Runbook</w:t></w:r></w:p>
                <w:p><w:r><w:t>The OrderProcessor symbol writes to the customer_orders table and exposes /api/v1/orders.</w:t></w:r></w:p>
              </w:body>
            </w:document>""",
        )

    # Build embedded XLSX
    xlsx_io = io.BytesIO()
    with zipfile.ZipFile(xlsx_io, "w") as xz:
        xz.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Entity</t></si>
              <si><t>customer_orders</t></si>
            </sst>""",
        )
        xz.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheets><sheet name="Tables" sheetId="1"/></sheets>
            </workbook>""",
        )
        xz.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
              </sheetData>
            </worksheet>""",
        )

    # Build embedded PDF
    pdf_stream = zlib.compress(b"BT /F1 12 Tf (Architecture Manual for OrderProcessor) Tj ET")
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj\n<< /Length 55 >>\nstream\n"
        + pdf_stream
        + b"\nendstream\nendobj\n%%EOF"
    )

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "db/schema.sql",
            """
            CREATE TABLE public.customers (
                id UUID PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                ssn VARCHAR(16)
            );

            CREATE TABLE public.customer_orders (
                id UUID PRIMARY KEY,
                customer_id UUID NOT NULL,
                amount_cents INTEGER NOT NULL,
                CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES public.customers (id)
            );

            CREATE VIEW public.active_orders_view AS
            SELECT id, customer_id, amount_cents FROM public.customer_orders;
            """,
        )
        zf.writestr(
            "src/orders_service.py",
            '''"""Orders service with ORM, REST endpoints, and SQL queries."""

from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/v1/orders")


class OrderProcessor:
    """Processes customer orders and updates persistence."""

    def process(self, db, customer_id: str) -> dict:
        db.execute("SELECT id, email FROM customers WHERE id = :cid")
        db.execute("INSERT INTO customer_orders (id, customer_id, amount_cents) VALUES ('1', '2', 500)")
        return self.audit_order(customer_id)

    def audit_order(self, customer_id: str) -> dict:
        return {"customer_id": customer_id, "audited": True}


@router.get("/{order_id}")
def get_order_endpoint(order_id: str, current_user: str = Depends(lambda: "user")) -> dict:
    proc = OrderProcessor()
    return proc.audit_order(order_id)


@router.post("/webhook")
def public_order_webhook(payload: dict) -> dict:
    return {"received": True}
''',
        )
        zf.writestr(
            "specs/openapi.yaml",
            """
openapi: "3.0.2"
info:
  title: LegacyGatewayAPI
  version: "2.1"
paths:
  /api/v1/billing/charge:
    post:
      operationId: chargeCustomer
      security: []
      responses:
        "200":
          description: Charged
""",
        )
        zf.writestr(
            "specs/schema.graphql",
            """
type Query {
  customerOrders(customerId: ID!): [Order] @authenticated
}
""",
        )
        zf.writestr(
            "Dockerfile",
            """
FROM python:3.11-slim
WORKDIR /srv
EXPOSE 8000
USER appuser
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "src.orders_service:router"]
""",
        )
        zf.writestr(
            "docker-compose.yml",
            """
services:
  orders-api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - orders-db
  orders-db:
    image: postgres:17
""",
        )
        zf.writestr(
            "infra/main.tf",
            """
resource "aws_db_instance" "orders_rds" {
  engine = "postgres"
  instance_class = "db.t4g.medium"
}
""",
        )
        zf.writestr(
            "docs/architecture.md",
            "# Orders Architecture\nThe `OrderProcessor` service reads `customers` and writes to `customer_orders`.\n## Endpoints\nExposes `/api/v1/orders/{order_id}`.",
        )
        zf.writestr(
            "docs/overview.html",
            "<html><body><h1>System Guide</h1><p>Covers `OrderProcessor` and `customers`.</p></body></html>",
        )
        zf.writestr("docs/runbook.docx", docx_io.getvalue())
        zf.writestr("docs/catalog.xlsx", xlsx_io.getvalue())
        zf.writestr("docs/spec.pdf", pdf_bytes)

    return buf.getvalue()


def test_postgres_54_tables_and_50_rls_policies_active() -> None:
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
        assert len(tables) >= 54

        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev in {
            "0004_wave2_tech_intel",
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
        assert len(rls_rows) >= 50
        for relname, rowsec, forcerowsec in rls_rows:
            assert rowsec is True, f"RLS not enabled on {relname}"
            assert forcerowsec is True, f"FORCE RLS not enabled on {relname}"


def test_wave2_end_to_end_pipeline_graph_agents_and_rls_isolation(tmp_path: Path) -> None:
    with SessionLocal() as boot_db:
        boot_info = bootstrap_default_context(db=boot_db)

    tenant_a_id = uuid.UUID(str(boot_info.tenant_id))
    user_a_id = uuid.UUID(str(boot_info.user_id))
    repo_a_id = uuid.UUID(str(boot_info.default_repository_id))

    storage = TenantObjectStorage(vault_root=tmp_path / "vault_wave2")
    orchestrator = TechnicalIntelligenceOrchestrator(allow_live_ollama=False)
    from app.services.technical_intelligence_service import TechnicalIntelligenceService

    tech_service = TechnicalIntelligenceService(storage=storage, orchestrator=orchestrator)
    ingestion_service = IngestionService(storage=storage, tech_intel_service=tech_service)

    zip_bytes = _build_wave2_polyglot_zip()

    with tenant_db_session(tenant_a_id) as db:
        ctx_a = verify_and_activate_tenant_context(
            db, user_id=user_a_id, tenant_id=tenant_a_id
        )
        outcome = ingestion_service.ingest_zip_archive(
            db,
            tenant_id=tenant_a_id,
            repository_id=repo_a_id,
            zip_bytes=zip_bytes,
            snapshot_label=f"wave2-e2e-{uuid.uuid4().hex[:6]}",
            triggered_by_user_id=user_a_id,
            run_analysis_and_indexing=True,
        )
        snapshot_id = outcome.snapshot_id
        analysis_run_id = outcome.analysis_run_id
        assert analysis_run_id is not None

        # 1. Verify Database Intelligence endpoint
        db_intel = get_snapshot_database_intelligence(
            snapshot_id=snapshot_id, ctx_pair=(db, ctx_a)
        )
        table_names = {t["table_name"] for t in db_intel["tables"]}
        assert {"customers", "customer_orders", "active_orders_view"}.issubset(table_names)
        assert len(db_intel["foreign_keys"]) >= 1
        assert db_intel["foreign_keys"][0]["source_table_name"] == "customer_orders"
        assert db_intel["foreign_keys"][0]["target_table_name"] == "customers"

        # 2. Verify API Intelligence endpoint (OpenAPI + GraphQL + FastAPI routes)
        api_intel = get_snapshot_api_intelligence(
            snapshot_id=snapshot_id, ctx_pair=(db, ctx_a)
        )
        protocols = {s["protocol"] for s in api_intel["services"]}
        assert {"REST", "GRAPHQL"}.issubset(protocols)
        routes = {ep["route_pattern"] for ep in api_intel["endpoints"]}
        assert "/api/v1/orders/{order_id}" in routes
        assert "/api/v1/billing/charge" in routes
        assert "Query.customerOrders" in routes

        # 3. Verify Infrastructure Intelligence endpoint (Dockerfile, Compose, Terraform)
        infra_intel = get_snapshot_infrastructure_intelligence(
            snapshot_id=snapshot_id, ctx_pair=(db, ctx_a)
        )
        iac_tools = {r["iac_tool"] for r in infra_intel["resources"]}
        assert {"DOCKERFILE", "DOCKER_COMPOSE", "TERRAFORM"}.issubset(iac_tools)

        # 4. Verify Documentation Intelligence endpoint (MD, HTML, DOCX, XLSX, PDF)
        doc_intel = get_snapshot_documentation_intelligence(
            snapshot_id=snapshot_id, ctx_pair=(db, ctx_a)
        )
        doc_paths = {s["canonical_path"] for s in doc_intel["sections"]}
        assert {
            "docs/architecture.md",
            "docs/overview.html",
            "docs/runbook.docx",
            "docs/catalog.xlsx",
            "docs/spec.pdf",
        }.issubset(doc_paths)

        # 5. Verify Unified Knowledge Graph & Cycle-Safe Recursive CTE Traversal
        graph_res = get_snapshot_knowledge_graph(
            snapshot_id=snapshot_id,
            entity_type=None,
            relationship_type=None,
            ctx_pair=(db, ctx_a),
        )
        ent_types = set(graph_res["entity_counts_by_type"].keys())
        assert {
            "MODULE",
            "SYMBOL",
            "DB_TABLE",
            "API_ENDPOINT",
            "SERVICE",
            "INFRA_RESOURCE",
        }.issubset(ent_types)

        rel_types = set(graph_res["relationship_counts_by_type"].keys())
        assert "CONTAINS" in rel_types
        assert "REFERENCES_TABLE_FK" in rel_types
        assert "EXPOSES_API" in rel_types
        assert "READS_TABLE" in rel_types or "WRITES_TABLE" in rel_types

        # Pick OrderProcessor symbol entity and traverse outgoing edges
        order_proc_ent = next(
            e for e in graph_res["entities"] if e["title"] == "OrderProcessor"
        )
        traversal = traverse_snapshot_knowledge_graph(
            snapshot_id=snapshot_id,
            root_entity_id=uuid.UUID(order_proc_ent["id"]),
            max_hops=3,
            direction="BOTH",
            relationship_type=None,
            ctx_pair=(db, ctx_a),
        )
        assert len(traversal["nodes"]) >= 2
        assert len(traversal["edges"]) >= 1

        # 6. Verify Evidence-Backed Findings & Human Review Workflow
        findings_res = get_snapshot_findings(
            snapshot_id=snapshot_id,
            category=None,
            review_status=None,
            ctx_pair=(db, ctx_a),
        )
        assert len(findings_res["findings"]) >= 3
        for f in findings_res["findings"]:
            assert len(f["evidence"]) >= 1
            assert len(f["evidence"][0]["snippet_sha256"]) == 64

        first_finding_id = uuid.UUID(findings_res["findings"][0]["id"])
        rev_out = review_finding_endpoint(
            finding_id=first_finding_id,
            payload=FindingReviewRequest(
                new_status="APPROVED",
                review_comment="Verified against SQL DDL and controller evidence anchor.",
            ),
            ctx_pair=(db, ctx_a),
        )
        assert rev_out["review_status"] == "APPROVED"
        assert rev_out["version_no"] == 2
        assert len(rev_out["review_history"]) >= 1

        # 7. Verify AI Agent Orchestration & Hallucination Rejection Gate
        agents_res = get_snapshot_agent_orchestration(
            snapshot_id=snapshot_id, ctx_pair=(db, ctx_a)
        )
        agent_names = {ar["agent_name"] for ar in agents_res["agent_runs"]}
        assert {
            "central_orchestrator",
            "repo_cartographer",
            "db_analyst",
            "api_inspector",
            "infra_auditor",
            "doc_linker",
        }.issubset(agent_names)
        assert len(agents_res["task_dependencies"]) >= 6
        assert len(agents_res["model_invocations"]) >= 5

        # Explicitly test hallucination rejection when an agent cites a bogus anchor UUID
        dummy_ar = db.execute(
            select(AgentRun)
            .where(
                AgentRun.tenant_id == tenant_a_id,
                AgentRun.analysis_run_id == analysis_run_id,
                AgentRun.agent_name == "repo_cartographer",
            )
            .limit(1)
        ).scalar_one()
        bogus_payload = AgentFindingsPayload(
            findings=[
                AgentFindingClaim(
                    finding_category="ARCHITECTURE",
                    severity="HIGH",
                    title="Hallucinated Unanchored Claim",
                    statement_markdown="This claim cites a non-existent evidence anchor UUID.",
                    confidence_score=0.95,
                    cited_anchor_id=str(uuid.uuid4()),
                )
            ]
        )
        acc, rej, _ = orchestrator.validate_and_persist_agent_claims(
            db,
            tenant_id=tenant_a_id,
            application_id=uuid.UUID(str(boot_info.default_repository_id)),
            snapshot_id=snapshot_id,
            analysis_run_id=analysis_run_id,
            agent_run=dummy_ar,
            payload=bogus_payload,
            valid_anchor_ids=set(),
            valid_entity_ids=set(),
            seq_start=900,
        )
        assert acc == 0
        assert rej == 1
        rejected_ev = db.execute(
            select(AgentExecutionEvent).where(
                AgentExecutionEvent.tenant_id == tenant_a_id,
                AgentExecutionEvent.agent_run_id == dummy_ar.id,
                AgentExecutionEvent.event_type == "HALLUCINATION_REJECTED",
            )
        ).scalar_one_or_none()
        assert rejected_ev is not None

    # 8. Negative Cross-Tenant RLS Isolation Test across Wave 2 tables
    tenant_b_id = uuid.uuid4()
    with SessionLocal() as admin_db:
        admin_db.add(
            Organization(
                id=tenant_b_id,
                slug=f"wave2-isolated-{uuid.uuid4().hex[:8]}",
                display_name="Wave 2 Isolated Tenant B",
            )
        )
        admin_db.commit()

    with tenant_db_session(tenant_b_id) as db_b:
        assert db_b.execute(select(DbTable)).scalars().all() == []
        assert db_b.execute(select(DbForeignKey)).scalars().all() == []
        assert db_b.execute(select(ApiEndpoint)).scalars().all() == []
        assert db_b.execute(select(InfraResource)).scalars().all() == []
        assert db_b.execute(select(DocSection)).scalars().all() == []
        assert db_b.execute(select(KnowledgeEntity)).scalars().all() == []
        assert db_b.execute(select(KnowledgeRelationship)).scalars().all() == []
        assert db_b.execute(select(Finding)).scalars().all() == []
        assert db_b.execute(select(EvidenceAnchor)).scalars().all() == []
        assert db_b.execute(select(ReviewHistory)).scalars().all() == []
        assert db_b.execute(select(AgentRun)).scalars().all() == []
