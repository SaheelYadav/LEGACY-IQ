"""Wave 3 Unit Tests: 60 Canonical Models, Deterministic Business Rule Extractors (Python, Java/TS, Docs) & OpenAPI Routes."""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers

from app.analysis.business_rule_intelligence import (
    extract_business_rules_from_code,
    extract_business_rules_from_doc_section,
    infer_domain_code,
)
from app.db.base import Base
from app.main import app as fastapi_app
import app.models  # noqa: F401


def test_wave3_60_canonical_models_registered() -> None:
    configure_mappers()
    tables = set(Base.metadata.tables.keys())
    assert len(tables) >= 60
    expected_wave3_tables = {
        "business_domains",
        "business_processes",
        "business_rules",
        "requirements",
        "requirement_acceptance_criteria",
        "requirement_traceability_links",
    }
    assert expected_wave3_tables.issubset(tables)


def test_python_business_rule_extractor_validations_calculations_auth_and_state() -> None:
    py_source = '''
from fastapi import Depends, HTTPException

class OrderBillingService:
    def process_order(self, order_total: float, customer_tier: str, user=Depends(get_current_user)):
        if order_total <= 0:
            raise ValueError("Order total must be positive")
        if order_total > 10000 and customer_tier == "GOLD":
            discount_amount = order_total * 0.075
        else:
            discount_amount = 0.0
        tax_amount = (order_total - discount_amount) * 0.18
        final_total = order_total - discount_amount + tax_amount
        order_status = "APPROVED"
        return final_total, order_status
'''
    rules = extract_business_rules_from_code(
        py_source, "src/services/order_billing.py", "python"
    )
    categories = {r.rule_category for r in rules}
    assert "AUTHORIZATION" in categories
    assert "VALIDATION" in categories
    assert "CALCULATION" in categories
    assert "STATE_TRANSITION" in categories

    calc_rules = [r for r in rules if r.rule_category == "CALCULATION"]
    assert any(10000.0 in r.numeric_thresholds for r in calc_rules)
    assert infer_domain_code("discount_amount tax_amount", "order_billing.py") == "BILLING_FINANCE"


def test_polyglot_java_and_typescript_business_rule_extractor() -> None:
    java_source = '''
public class PaymentController {
    @PreAuthorize("hasRole('FINANCE_ADMIN')")
    public void approveSettlement(double invoiceAmount) {
        if (invoiceAmount > 50000) {
            throw new IllegalArgumentException("Exceeds settlement limit");
        }
        double settlementFee = invoiceAmount * 0.025;
    }
}
'''
    rules = extract_business_rules_from_code(
        java_source, "src/main/java/PaymentController.java", "java"
    )
    categories = {r.rule_category for r in rules}
    assert "AUTHORIZATION" in categories
    assert "VALIDATION" in categories
    assert "CALCULATION" in categories


def test_documentation_business_rule_extractor() -> None:
    doc_text = """
    Orders exceeding 5000 USD must receive manager approval and a 10% discount rate.
    All customer billing endpoints shall enforce JWT authentication.
    """
    doc_rules = extract_business_rules_from_doc_section(
        section_title="Billing Policy",
        text_content=doc_text,
        relative_path="docs/billing-policy.md",
    )
    assert len(doc_rules) >= 2
    assert any(5000.0 in r.numeric_thresholds for r in doc_rules)
    assert any(r.rule_category in ("CALCULATION", "VALIDATION", "AUTHORIZATION") for r in doc_rules)


def test_wave3_api_routes_registered() -> None:
    fastapi_app.openapi_schema = None
    route_paths = set(fastapi_app.openapi()["paths"].keys())
    expected_paths = {
        "/api/v1/snapshots/{snapshot_id}/requirements-intelligence/analyze",
        "/api/v1/snapshots/{snapshot_id}/business-rules",
        "/api/v1/business-rules/{rule_id}/review",
        "/api/v1/snapshots/{snapshot_id}/requirements",
        "/api/v1/requirements/{requirement_id}/review",
        "/api/v1/snapshots/{snapshot_id}/traceability",
        "/api/v1/snapshots/{snapshot_id}/conflicts-and-gaps",
        "/api/v1/conflicts/{conflict_id}/resolve",
        "/api/v1/snapshots/{snapshot_id}/impact-analysis",
    }
    assert expected_paths.issubset(route_paths)

