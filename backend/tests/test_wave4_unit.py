"""Wave 4 Unit Tests: 65 Canonical Models, Polyglot Test & Coverage Analyzers, CWE/CVE Security & Dependency Risk Analyzers, and OpenAPI Routes."""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers

from app.analysis.testing_risk_modernization_intelligence import (
    extract_code_security_and_performance_risks,
    extract_tests_from_code,
    generate_missing_test_blueprint,
    is_test_file_path,
    parse_coverage_report,
    parse_dependency_manifests,
)
from app.db.base import Base
from app.main import app as fastapi_app
import app.models  # noqa: F401


def test_wave4_65_canonical_models_registered() -> None:
    configure_mappers()
    tables = set(Base.metadata.tables.keys())
    assert len(tables) >= 65
    expected_wave4_tables = {
        "test_suites",
        "test_cases",
        "test_coverage_links",
        "technical_debt_items",
        "modernization_recommendations",
    }
    assert expected_wave4_tables.issubset(tables)


def test_polyglot_test_discovery_pytest_junit_jest_and_coverage_reports() -> None:
    assert is_test_file_path("tests/test_billing.py") is True
    assert is_test_file_path("src/services/billing.py") is False

    py_test_code = '''
import pytest

class TestOrderFulfillment:
    def test_evaluate_order_discount_gold_tier(self, client):
        resp = client.post("/api/v1/orders/submit", json={"order_total": 15000})
        res = evaluate_order_discount(15000.0, "GOLD")
        assert resp.status_code == 200
        assert res[0] < 15000.0
'''
    py_tests = extract_tests_from_code(
        py_test_code, "tests/test_order_fulfillment.py", "python"
    )
    assert len(py_tests) == 1
    assert py_tests[0].test_framework == "PYTEST"
    assert py_tests[0].test_kind == "API"
    assert "evaluate_order_discount" in py_tests[0].called_identifiers
    assert "/api/v1/orders/submit" in py_tests[0].referenced_routes
    assert py_tests[0].assertion_count >= 2

    java_test_code = '''
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class PaymentServiceTest {
    @Test
    public void shouldCalculateSettlementFee() {
        double fee = calculateSettlementFee(1000.0);
        assertEquals(25.0, fee);
    }
}
'''
    java_tests = extract_tests_from_code(
        java_test_code, "src/test/java/PaymentServiceTest.java", "java"
    )
    assert len(java_tests) == 1
    assert java_tests[0].test_framework == "JUNIT"
    assert "calculateSettlementFee" in java_tests[0].called_identifiers

    ts_test_code = '''
import { describe, it, expect } from "vitest";

describe("CheckoutService", () => {
    it("rejects negative order totals", async () => {
        const result = validateOrderTotal(-50);
        expect(result.valid).toBe(false);
    });
});
'''
    ts_tests = extract_tests_from_code(
        ts_test_code, "src/__tests__/checkout.spec.ts", "typescript"
    )
    assert len(ts_tests) == 1
    assert ts_tests[0].test_framework in ("VITEST", "JEST")
    assert "validateOrderTotal" in ts_tests[0].called_identifiers

    cobertura_xml = '''<?xml version="1.0" ?>
<coverage line-rate="0.85">
  <packages>
    <package name="src">
      <classes>
        <class filename="src/orders_service.py" line-rate="0.85">
          <lines>
            <line number="10" hits="3"/>
            <line number="11" hits="3"/>
            <line number="12" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
'''
    cov_records = parse_coverage_report(cobertura_xml, "coverage.xml")
    assert len(cov_records) == 1
    assert cov_records[0].relative_path == "src/orders_service.py"
    assert cov_records[0].line_rate == 0.85
    assert 10 in cov_records[0].covered_lines
    assert cov_records[0].coverage_source == "COVERAGE_REPORT"

    lcov_text = """TN:
SF:src/billing.py
DA:1,2
DA:2,2
DA:3,0
end_of_record
"""
    lcov_records = parse_coverage_report(lcov_text, "lcov.info")
    assert len(lcov_records) == 1
    assert lcov_records[0].relative_path == "src/billing.py"
    assert round(lcov_records[0].line_rate, 2) == 0.67

    test_key, test_kind, blueprint = generate_missing_test_blueprint(
        req_code="REQ-FIN-001",
        req_title="Positive Order Total Enforcement",
        req_type="FUNCTIONAL",
        given_clause="Given an order submission request",
        when_clause="When order_total <= 0",
        then_clause="Then raise ValueError",
        target_symbol_name="evaluate_order_discount",
    )
    assert test_key.startswith("blueprint::test_req_fin_001")
    assert test_kind == "CHARACTERIZATION"
    assert "def test_req_fin_001" in blueprint
    assert "evaluate_order_discount" in blueprint


def test_security_performance_and_dependency_risk_analyzers_no_fabricated_cves() -> None:
    vuln_py = '''
import subprocess
import yaml

API_SECRET = "sk_live_9876543210abcdef123456"

def unsafe_lookup(db_conn, user_input, items):
    query = f"SELECT * FROM accounts WHERE username = '{user_input}'"
    db_conn.execute(query)
    cfg = yaml.load(user_input)
    subprocess.run(user_input, shell=True)
    for item in items:
        db_conn.execute("SELECT * FROM audit_logs WHERE item_id = :id")
'''
    risks = extract_code_security_and_performance_risks(
        vuln_py, "src/legacy_auth.py", "python"
    )
    cwe_refs = {r.cwe_or_advisory_ref for r in risks if r.cwe_or_advisory_ref}
    assert "CWE-798" in cwe_refs
    assert "CWE-89" in cwe_refs
    assert "CWE-78/CWE-502" in cwe_refs
    assert any(r.risk_category == "PERFORMANCE" for r in risks)

    req_txt = """
pyyaml==5.3.1
fastapi==0.115.0
custom-internal-lib>=1.2.0
"""
    deps = parse_dependency_manifests(req_txt, "requirements.txt")
    by_pkg = {d.package_name: d for d in deps}
    assert by_pkg["pyyaml"].advisory_id == "CVE-2020-14343"
    assert by_pkg["pyyaml"].advisory_severity == "CRITICAL"
    # FastAPI 0.115.0 and unpinned internal packages MUST NOT have fabricated CVEs
    assert by_pkg["fastapi"].advisory_id is None
    assert by_pkg["custom-internal-lib"].advisory_id is None
    assert by_pkg["custom-internal-lib"].is_pinned is False


def test_wave4_api_routes_registered() -> None:
    fastapi_app.openapi_schema = None
    route_paths = set(fastapi_app.openapi()["paths"].keys())
    expected_paths = {
        "/api/v1/snapshots/{snapshot_id}/testing-modernization/analyze",
        "/api/v1/snapshots/{snapshot_id}/test-intelligence",
        "/api/v1/snapshots/{snapshot_id}/coverage-and-gaps",
        "/api/v1/snapshots/{snapshot_id}/risk-register",
        "/api/v1/snapshots/{snapshot_id}/technical-debt",
        "/api/v1/snapshots/{snapshot_id}/modernization-assessment",
        "/api/v1/snapshots/{snapshot_id}/modernization-roadmap",
        "/api/v1/modernization-recommendations/{recommendation_id}/review",
        "/api/v1/test-cases/{test_case_id}/review",
    }
    assert expected_paths.issubset(route_paths)
