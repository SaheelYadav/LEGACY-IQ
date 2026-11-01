"""Wave 2 Unit Tests: Database, API, Infrastructure, Documentation Extractors, 54 Models & OpenAPI Routes."""

from __future__ import annotations

import io
import zipfile
import zlib

from sqlalchemy.orm import configure_mappers

from app.analysis.api_intelligence import (
    extract_api_endpoints_from_code,
    parse_graphql_schema,
    parse_openapi_or_swagger,
)
from app.analysis.database_intelligence import (
    extract_orm_and_sql_from_code,
    parse_sql_ddl,
)
from app.analysis.doc_intelligence import extract_documentation
from app.analysis.infra_intelligence import (
    parse_dockerfile,
    parse_terraform_hcl,
    parse_yaml_or_json_iac,
)
from app.db.base import Base
from app.main import app as fastapi_app
import app.models  # noqa: F401


def test_wave2_54_canonical_models_registered() -> None:
    configure_mappers()
    tables = set(Base.metadata.tables.keys())
    assert len(tables) == 54
    expected_wave2_tables = {
        # Domain E (9)
        "db_schemas",
        "db_tables",
        "db_columns",
        "db_foreign_keys",
        "api_services",
        "api_endpoints",
        "infra_resources",
        "doc_sections",
        "runtime_observations",
        # Domain F (7)
        "knowledge_entities",
        "knowledge_relationships",
        "findings",
        "evidence_anchors",
        "finding_evidence_links",
        "knowledge_conflicts",
        "review_history",
        # Domain I remaining (5)
        "agent_runs",
        "agent_task_dependencies",
        "prompt_templates",
        "model_invocations",
        "agent_execution_events",
    }
    assert expected_wave2_tables.issubset(tables)


def test_database_intelligence_sql_ddl_views_procs_triggers_and_orm() -> None:
    sql_script = """
    CREATE TABLE billing.customers (
        id UUID PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        ssn VARCHAR(16),
        created_at TIMESTAMPTZ NOT NULL
    );

    CREATE TABLE billing.invoices (
        id UUID NOT NULL,
        customer_id UUID NOT NULL,
        total_cents INTEGER NOT NULL,
        CONSTRAINT pk_invoices PRIMARY KEY (id),
        CONSTRAINT fk_invoices_customer FOREIGN KEY (customer_id) REFERENCES billing.customers (id)
    );

    CREATE INDEX ix_invoices_customer ON billing.invoices (customer_id);

    CREATE MATERIALIZED VIEW billing.customer_totals_mv AS
    SELECT customer_id, SUM(total_cents) AS lifetime_cents
    FROM billing.invoices
    GROUP BY customer_id;

    CREATE OR REPLACE FUNCTION billing.recalc_invoice_tax(inv_id UUID) RETURNS INTEGER AS $$
    BEGIN
        RETURN 0;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_audit_invoices
    AFTER INSERT OR UPDATE ON billing.invoices
    FOR EACH ROW EXECUTE FUNCTION billing.recalc_invoice_tax();
    """
    res = parse_sql_ddl(sql_script, "db/migrations/001_billing.sql")
    assert len(res.tables) == 3
    by_name = {t.table_name: t for t in res.tables}
    assert "customers" in by_name
    assert "invoices" in by_name
    assert "customer_totals_mv" in by_name
    assert by_name["customer_totals_mv"].table_kind == "MATERIALIZED_VIEW"

    cust_cols = {c.column_name: c for c in by_name["customers"].columns}
    assert cust_cols["id"].is_primary_key is True
    assert cust_cols["email"].is_pii_candidate is True
    assert cust_cols["ssn"].is_pii_candidate is True

    assert len(res.foreign_keys) == 1
    fk = res.foreign_keys[0]
    assert fk.source_table == "invoices"
    assert fk.target_table == "customers"
    assert fk.source_columns == ["customer_id"]
    assert fk.target_columns == ["id"]

    prog_kinds = {p.object_kind for p in res.programmable_objects}
    assert {"INDEX", "FUNCTION", "TRIGGER"}.issubset(prog_kinds)

    # Test ORM + embedded SQL extraction
    py_orm_code = """
from sqlalchemy import Column, ForeignKey, Integer, String
from app.db import Base

class OrderRecord(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_email: Mapped[str] = mapped_column(String, nullable=False)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"))

def fetch_active_orders(db):
    db.execute("SELECT id, customer_email FROM orders WHERE active = 1")
    db.execute("UPDATE invoices SET status = 'PAID' WHERE id = 10")
"""
    orm_res = extract_orm_and_sql_from_code(py_orm_code, "python", "billing.models")
    assert len(orm_res.tables) == 1
    assert orm_res.tables[0].table_name == "orders"
    assert len(orm_res.foreign_keys) == 1
    assert orm_res.foreign_keys[0].target_table == "invoices"
    edge_types = {(e.table_name, e.relationship_type) for e in orm_res.access_edges}
    assert ("orders", "MAPS_TO_TABLE") in edge_types
    assert ("orders", "READS_TABLE") in edge_types
    assert ("invoices", "WRITES_TABLE") in edge_types


def test_api_intelligence_openapi_graphql_and_controllers() -> None:
    openapi_yaml = """
openapi: "3.0.3"
info:
  title: LegacyOrderService
  version: "1.0.0"
servers:
  - url: /api/v1
paths:
  /orders:
    get:
      operationId: listOrders
      security:
        - bearerAuth: []
      responses:
        "200":
          description: OK
    post:
      operationId: createOrder
      security: []
      requestBody:
        required: true
      responses:
        "201":
          description: Created
"""
    oa_res = parse_openapi_or_swagger(openapi_yaml, "specs/openapi.yaml")
    assert len(oa_res.endpoints) == 2
    by_method = {e.http_method: e for e in oa_res.endpoints}
    assert by_method["GET"].auth_required_inferred is True
    assert by_method["POST"].auth_required_inferred is False

    gql_sdl = """
type Query {
  orderById(id: ID!): Order @authenticated
}
type Mutation {
  cancelOrder(id: ID!): Boolean
}
"""
    gql_res = parse_graphql_schema(gql_sdl, "schema.graphql")
    assert len(gql_res.endpoints) == 2
    routes = {e.route_pattern: e for e in gql_res.endpoints}
    assert routes["Query.orderById"].auth_required_inferred is True
    assert routes["Mutation.cancelOrder"].auth_required_inferred is False

    java_ctrl = """
@RequestMapping("/api/v2/payments")
public class PaymentController {
    @PostMapping("/charge")
    @PreAuthorize("hasRole('BILLING_ADMIN')")
    public PaymentReceipt chargeCard(ChargeRequest req) {
        return null;
    }
}
"""
    java_res = extract_api_endpoints_from_code(
        java_ctrl, "java", "com.acme.PaymentController", "PaymentController.java"
    )
    assert len(java_res.endpoints) == 1
    assert java_res.endpoints[0].http_method == "POST"
    assert java_res.endpoints[0].route_pattern == "/api/v2/payments/charge"
    assert java_res.endpoints[0].auth_required_inferred is True


def test_infrastructure_intelligence_docker_compose_k8s_terraform_and_cfn() -> None:
    dockerfile = """
FROM python:3.11-slim
WORKDIR /app
ENV APP_ENV=production
EXPOSE 8080
USER appuser
HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1
CMD ["uvicorn", "app.main:app"]
"""
    df_res = parse_dockerfile(dockerfile, "backend/Dockerfile")
    assert len(df_res.resources) == 1
    attrs = df_res.resources[0].configuration_attributes
    assert attrs["base_images"] == ["python:3.11-slim"]
    assert attrs["has_healthcheck"] is True
    assert attrs["runs_as_non_root"] is True

    compose_and_k8s = """
services:
  api:
    image: acme/legacy-api:1.2
    ports:
      - "8000:8000"
    depends_on:
      - db
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: legacy-worker
  namespace: prod
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: worker
          image: acme/worker:1.0
"""
    iac_res = parse_yaml_or_json_iac(compose_and_k8s, "deploy/stack.yaml")
    tools = {r.iac_tool for r in iac_res.resources}
    assert "DOCKER_COMPOSE" in tools
    assert "KUBERNETES" in tools

    tf_hcl = """
resource "aws_db_instance" "primary_pg" {
  engine = "postgres"
  instance_class = "db.m6i.large"
  master_password = "super_secret_password_123"
}
"""
    tf_res = parse_terraform_hcl(tf_hcl, "infra/main.tf")
    assert len(tf_res.resources) == 1
    assert tf_res.resources[0].resource_type == "aws_db_instance"
    assert tf_res.resources[0].configuration_attributes["master_password"] == "[REDACTED]"


def test_documentation_intelligence_md_html_docx_xlsx_and_pdf() -> None:
    # 1. Markdown
    md_bytes = b"# Architecture Overview\nThe `OrderRecord` model writes to `billing_invoices`.\n## API Layer\nExposes `/api/v1/orders`."
    md_res = extract_documentation(md_bytes, "markdown", "docs/architecture.md")
    assert len(md_res.sections) == 2
    assert "OrderRecord" in md_res.sections[0].mentioned_identifiers

    # 2. HTML
    html_bytes = b"<html><body><h1>Billing Service</h1><p>Calls `PaymentController`.</p><h2>Database</h2><p>Uses `customers`.</p></body></html>"
    html_res = extract_documentation(html_bytes, "html", "docs/guide.html")
    assert len(html_res.sections) == 2
    assert html_res.sections[1].heading_path == "Billing Service > Database"

    # 3. DOCX (synthesized in-memory OpenXML zip)
    docx_buf = io.BytesIO()
    with zipfile.ZipFile(docx_buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Legacy Runbook</w:t></w:r></w:p>
                <w:p><w:r><w:t>Inspect OrderService and billing_customers table.</w:t></w:r></w:p>
              </w:body>
            </w:document>""",
        )
    docx_res = extract_documentation(docx_buf.getvalue(), "docx", "docs/runbook.docx")
    assert len(docx_res.sections) >= 1
    assert "OrderService" in docx_res.sections[0].mentioned_identifiers

    # 4. XLSX (synthesized in-memory OpenXML workbook)
    xlsx_buf = io.BytesIO()
    with zipfile.ZipFile(xlsx_buf, "w") as zf:
        zf.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>TableName</t></si>
              <si><t>billing_invoices</t></si>
            </sst>""",
        )
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheets><sheet name="DataCatalog" sheetId="1"/></sheets>
            </workbook>""",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
              </sheetData>
            </worksheet>""",
        )
    xlsx_res = extract_documentation(xlsx_buf.getvalue(), "xlsx", "docs/catalog.xlsx")
    assert any("billing_invoices" in s.content_markdown for s in xlsx_res.sections)

    # 5. PDF (compressed stream with Tj operator)
    compressed_stream = zlib.compress(b"BT /F1 12 Tf (Legacy OrderService Specification) Tj ET")
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Length 50 >>\nstream\n" + compressed_stream + b"\nendstream\nendobj\n%%EOF"
    pdf_res = extract_documentation(pdf_bytes, "pdf", "docs/spec.pdf")
    assert any("OrderService" in s.content_markdown for s in pdf_res.sections)


def test_wave2_api_routes_registered() -> None:
    paths = set(fastapi_app.openapi()["paths"].keys())
    expected_wave2_paths = {
        "/api/v1/snapshots/{snapshot_id}/analyze-wave2",
        "/api/v1/snapshots/{snapshot_id}/database",
        "/api/v1/snapshots/{snapshot_id}/apis",
        "/api/v1/snapshots/{snapshot_id}/infrastructure",
        "/api/v1/snapshots/{snapshot_id}/documentation",
        "/api/v1/snapshots/{snapshot_id}/graph",
        "/api/v1/snapshots/{snapshot_id}/graph/traverse",
        "/api/v1/snapshots/{snapshot_id}/findings",
        "/api/v1/findings/{finding_id}/review",
        "/api/v1/snapshots/{snapshot_id}/agents",
    }
    assert expected_wave2_paths.issubset(paths)

