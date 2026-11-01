"""Wave 5 Unit Tests: 76-Table Registry, Specialized Question Intent Classifier, Multi-Format Export Formatters (PDF, DOCX, XLSX, JSON), and API Route Registration."""

from __future__ import annotations

import json

from app.analysis.doc_intelligence import extract_documentation
from app.analysis.export_formatters import render_report_export
from app.main import app as fastapi_app
from app.models import Base
from app.services.reporting_qa_export_service import (
    REPORT_TYPE_CATALOG,
    classify_question_intent,
)


def test_wave5_76_canonical_models_registered() -> None:
    """Confirm all 76 canonical D3 tables (including the 11 Wave 5 Reporting, Q&A & Governance tables) are registered."""
    tables = set(Base.metadata.tables.keys())
    assert len(tables) == 76, f"Expected 76 tables, got {len(tables)}"
    expected_wave5 = {
        "qa_conversations",
        "qa_messages",
        "intelligence_reports",
        "intelligence_report_versions",
        "report_exports",
        "audit_logs",
        "approval_requests",
        "retention_policies",
        "deletion_requests",
        "tenant_subscriptions",
        "tenant_usage_quotas",
    }
    assert expected_wave5.issubset(tables)
    assert len(REPORT_TYPE_CATALOG) == 11


def test_question_intent_classification_all_specialized_queries() -> None:
    """Verify deterministic classification across all 12 specialized application intelligence query intents."""
    assert (
        classify_question_intent(
            "Explain the overall architecture of this application."
        )
        == "ARCHITECTURE_DISCOVERY"
    )
    assert (
        classify_question_intent(
            "What are the most important business rules?"
        )
        == "BUSINESS_RULE_EXPLANATION"
    )
    assert (
        classify_question_intent(
            "Which APIs depend on this database table?"
        )
        == "API_DB_DEPENDENCY"
    )
    assert (
        classify_question_intent(
            "What happens when a customer account is deactivated?"
        )
        == "BUSINESS_PROCESS"
    )
    assert (
        classify_question_intent(
            "Which requirements are not covered by tests?"
        )
        == "TEST_COVERAGE_GAPS"
    )
    assert (
        classify_question_intent("What are the biggest security risks?")
        == "SECURITY_RISK_INVESTIGATION"
    )
    assert (
        classify_question_intent(
            "Which components will be affected if this service changes?"
        )
        == "CHANGE_IMPACT_ANALYSIS"
    )
    assert (
        classify_question_intent("How can we modernize this application?")
        == "MODERNIZATION_PLANNING"
    )
    assert (
        classify_question_intent(
            "Show me the technical debt hotspots and cyclomatic complexity."
        )
        == "TECHNICAL_DEBT_INVESTIGATION"
    )
    assert (
        classify_question_intent(
            "Are there any contradictions or conflicts between documentation and code?"
        )
        == "CONFLICT_DETECTION"
    )
    assert (
        classify_question_intent(
            "List the functional requirements and actors."
        )
        == "REQUIREMENTS_TRACEABILITY"
    )


def test_export_formatters_pdf_docx_xlsx_and_json_roundtrip() -> None:
    """Verify PDF, DOCX, XLSX, and JSON export generators produce valid binaries and round-trip cleanly."""
    sample_report = {
        "id": "00000000-0000-0000-0000-000000000501",
        "report_type": "COMPLETE_INTELLIGENCE",
        "title": "Complete Application Intelligence Report — BillingCore (v1.0)",
        "version_no": 1,
        "lifecycle_status": "APPROVED",
        "is_immutable": True,
        "content_sha256": "abc1234567890def" * 4,
        "generated_at": "2026-11-01T12:00:00+00:00",
        "branding": {
            "organization_name": "Acme Enterprise Corp",
            "project_name": "Billing Modernization",
            "project_key": "BILL",
            "application_name": "BillingCore",
            "repository_name": "billing-core-repo",
            "snapshot_label": "v1.0",
        },
        "executive_summary_markdown": "BillingCore contains 14 symbols, 2 SQL tables, and 3 REST endpoints.",
        "scope_and_methodology_markdown": "Zero-execution AST + SQL DDL + OpenAPI static discovery.",
        "sections": [
            {
                "section_key": "DISCOVERY",
                "title": "Application Discovery & Inventory",
                "metric_basis": "MEASURED",
                "review_posture": "CONFIRMED_FACT",
                "content_markdown": "Measured 14 symbols and 2 database tables.",
            }
        ],
        "evidence_references": [
            {
                "ref_id": "EV-01",
                "category": "BUSINESS_RULE",
                "title": "Invoice Limit Rule",
                "relative_path": "src/billing/service.py",
                "start_line": 10,
                "end_line": 24,
                "snippet_sha256": "1122334455667788" * 4,
                "excerpt_text": "if amount > 10000: raise ValueError('Limit exceeded')",
            }
        ],
        "risks_and_limitations_markdown": "All effort hours are heuristic engineering estimates.",
        "recommendations": [
            {
                "roadmap_phase": 1,
                "strategy_pattern": "STRANGLER_FIG",
                "title": "Harden Security & Add Regression Tests",
                "target_state_architecture": "Modular Monolith with FastAPI",
                "effort_tshirt": "M",
                "estimated_effort_range": "2-4 person-weeks",
                "confidence_score": 0.91,
                "review_status": "APPROVED",
            }
        ],
        "metrics_summary": {
            "measured": {"total_files": 5, "code_symbols_count": 14},
            "heuristic_estimates": {"health_score": 84.5},
            "inferred": {"business_rules_count": 3},
        },
    }

    # 1. PDF (%PDF-1.4 FlateDecode stream) + Roundtrip via Wave 2 extract_documentation
    pdf_bytes, pdf_mime, pdf_ext = render_report_export("PDF", sample_report)
    assert pdf_mime == "application/pdf"
    assert pdf_ext == "pdf"
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    extracted_pdf = extract_documentation(pdf_bytes, "pdf", "report.pdf")
    assert "BillingCore" in extracted_pdf.normalized_full_text
    assert "src/billing/service.py" in extracted_pdf.normalized_full_text

    # 2. DOCX (ECMA-376 OpenXML) + Roundtrip via Wave 2 extract_documentation
    docx_bytes, docx_mime, docx_ext = render_report_export(
        "DOCX", sample_report
    )
    assert docx_ext == "docx"
    assert "wordprocessingml" in docx_mime
    assert docx_bytes[:4] == b"PK\x03\x04"
    extracted_docx = extract_documentation(docx_bytes, "docx", "report.docx")
    assert "BillingCore" in extracted_docx.normalized_full_text
    assert "src/billing/service.py" in extracted_docx.normalized_full_text

    # 3. XLSX (ECMA-376 OpenXML 4-sheet workbook) + Roundtrip via Wave 2 extract_documentation
    xlsx_bytes, xlsx_mime, xlsx_ext = render_report_export(
        "XLSX", sample_report
    )
    assert xlsx_ext == "xlsx"
    assert "spreadsheetml" in xlsx_mime
    assert xlsx_bytes[:4] == b"PK\x03\x04"
    extracted_xlsx = extract_documentation(xlsx_bytes, "xlsx", "report.xlsx")
    assert "Summary" in extracted_xlsx.normalized_full_text
    assert "src/billing/service.py" in extracted_xlsx.normalized_full_text

    # 4. JSON
    json_bytes, json_mime, json_ext = render_report_export(
        "JSON", sample_report
    )
    assert json_ext == "json"
    assert json_mime == "application/json"
    parsed_json = json.loads(json_bytes.decode("utf-8"))
    assert parsed_json["is_immutable"] is True
    assert parsed_json["report_type"] == "COMPLETE_INTELLIGENCE"


def test_wave5_api_routes_registered() -> None:
    """Confirm all 16 Wave 5 FastAPI endpoints are registered on the application router."""
    fastapi_app.openapi_schema = None
    routes = set(fastapi_app.openapi()["paths"].keys())
    expected_paths = {
        "/api/v1/snapshots/{snapshot_id}/intelligence-dashboard",
        "/api/v1/snapshots/{snapshot_id}/executive-insights",
        "/api/v1/qa/conversations",
        "/api/v1/qa/conversations/{conversation_id}",
        "/api/v1/qa/conversations/{conversation_id}/ask",
        "/api/v1/snapshots/{snapshot_id}/qa/ask",
        "/api/v1/snapshots/{snapshot_id}/reports/generate",
        "/api/v1/snapshots/{snapshot_id}/reports",
        "/api/v1/reports/{report_id}",
        "/api/v1/reports/{report_id}/versions",
        "/api/v1/reports/{report_id}/lifecycle",
        "/api/v1/reports/{report_id}/exports",
        "/api/v1/snapshots/{snapshot_id}/exports",
        "/api/v1/exports/{export_id}/download",
        "/api/v1/organizations/{tenant_id}/audit-logs",
    }
    assert expected_paths.issubset(routes)
