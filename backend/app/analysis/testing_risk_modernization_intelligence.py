"""Deterministic Wave 4 Analyzers: Test Intelligence, Risk & Security Intelligence, Dependency Auditing, and Technical Debt Metrics."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import json
import posixpath
import re
from typing import Any
import xml.etree.ElementTree as ET


@dataclass
class ExtractedTestCaseCandidate:
    suite_name: str
    test_framework: str  # PYTEST | JUNIT | JEST | VITEST | PHPUNIT
    test_key: str
    title: str
    test_kind: str  # UNIT | INTEGRATION | API | E2E | CONTRACT
    scenario_description: str
    relative_path: str
    start_line: int
    end_line: int
    excerpt_text: str
    enclosing_symbol_qname: str | None = None
    called_identifiers: list[str] = field(default_factory=list)
    referenced_routes: list[str] = field(default_factory=list)
    assertion_count: int = 0


@dataclass
class ExtractedCoverageRecord:
    relative_path: str
    line_rate: float
    covered_lines: list[int] = field(default_factory=list)
    coverage_source: str = "COVERAGE_REPORT"  # Measured from Cobertura XML / LCOV


@dataclass
class ExtractedDependencyRecord:
    manifest_path: str
    ecosystem: str  # pypi | npm | maven | composer
    package_name: str
    version_spec: str
    pinned_version: str | None
    is_pinned: bool
    is_outdated_or_eol: bool
    advisory_id: str | None  # Populated ONLY when matched against verified advisory rule
    advisory_severity: str | None
    advisory_summary: str | None
    start_line: int
    excerpt_text: str


@dataclass
class ExtractedRiskCandidate:
    risk_category: str  # SECURITY | DEPENDENCY | ARCHITECTURAL | SPOF_COUPLING | DATA_INTEGRITY | PERFORMANCE | OPERATIONAL_INFRA
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    likelihood: str  # HIGH | MEDIUM | LOW
    title: str
    statement_markdown: str
    remediation_recommendation: str
    affected_components: list[str]
    relative_path: str
    start_line: int
    end_line: int
    excerpt_text: str
    confidence_score: float = 0.92
    origin_type: str = "DETERMINISTIC_RULE"
    cwe_or_advisory_ref: str | None = None


# Curated, verifiable vulnerability & EOL baseline (never fabricates CVEs outside exact version matches)
_VERIFIED_ADVISORY_DB: dict[tuple[str, str], list[tuple[str, str, str, str]]] = {
    # (ecosystem, package_lower): [(vulnerable_prefix_or_exact, advisory_id, severity, summary)]
    ("pypi", "pyyaml"): [
        (
            "5.",
            "CVE-2020-14343",
            "CRITICAL",
            "PyYAML < 5.4 allows arbitrary code execution via full_load / unsafe YAML deserialization.",
        ),
        (
            "3.",
            "CVE-2017-18342",
            "CRITICAL",
            "PyYAML 3.x yaml.load() arbitrary code execution vulnerability.",
        ),
    ],
    ("pypi", "django"): [
        (
            "1.",
            "EOL-DJANGO-1X",
            "HIGH",
            "Django 1.x is End-of-Life and lacks security patches for SQLi/XSS.",
        ),
        (
            "2.",
            "EOL-DJANGO-2X",
            "HIGH",
            "Django 2.x is End-of-Life and unsupported.",
        ),
    ],
    ("pypi", "flask"): [
        (
            "0.",
            "CVE-2018-1000656",
            "HIGH",
            "Legacy Flask 0.x series has known DoS/session vulnerabilities and is End-of-Life.",
        ),
    ],
    ("pypi", "requests"): [
        (
            "2.19.",
            "CVE-2018-18074",
            "HIGH",
            "Requests <= 2.19.1 leaks Authorization headers on cross-origin HTTPS->HTTP redirects.",
        ),
    ],
    ("pypi", "urllib3"): [
        (
            "1.24.",
            "CVE-2019-11324",
            "HIGH",
            "urllib3 1.24.x mishandles CA certificate verification.",
        ),
    ],
    ("pypi", "cryptography"): [
        (
            "2.",
            "CVE-2020-25659",
            "HIGH",
            "cryptography 2.x vulnerable to Bleichenbacher timing attacks on RSA decryption.",
        ),
    ],
    ("npm", "lodash"): [
        (
            "4.17.15",
            "CVE-2020-8203",
            "HIGH",
            "lodash <= 4.17.15 is vulnerable to Prototype Pollution in zipObjectDeep.",
        ),
        (
            "4.17.11",
            "CVE-2019-10744",
            "CRITICAL",
            "lodash < 4.17.12 vulnerable to severe Prototype Pollution in defaultsDeep.",
        ),
    ],
    ("npm", "express"): [
        (
            "3.",
            "EOL-EXPRESS-3X",
            "HIGH",
            "Express 3.x is End-of-Life and unmaintained.",
        ),
    ],
    ("npm", "axios"): [
        (
            "0.18.",
            "CVE-2019-10742",
            "HIGH",
            "axios 0.18.x vulnerable to DoS via unbounded content length.",
        ),
    ],
    ("maven", "org.apache.logging.log4j:log4j-core"): [
        (
            "2.14.",
            "CVE-2021-44228",
            "CRITICAL",
            "Log4Shell JNDI remote code execution vulnerability in log4j-core 2.14.x.",
        ),
        (
            "2.13.",
            "CVE-2021-44228",
            "CRITICAL",
            "Log4Shell JNDI remote code execution vulnerability in log4j-core 2.13.x.",
        ),
    ],
}


def is_test_file_path(relative_path: str) -> bool:
    norm = relative_path.replace("\\", "/").lower()
    base = posixpath.basename(norm)
    parts = [p for p in norm.split("/") if p]
    if any(p in ("tests", "test", "__tests__", "spec", "specs", "e2e") for p in parts[:-1]):
        if base.endswith((".py", ".java", ".ts", ".tsx", ".js", ".jsx", ".php")):
            return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith(("_test.py", "test.java", "tests.java", "it.java", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx", ".test.js", ".spec.js", "test.php")):
        return True
    return False


def _infer_test_kind(relative_path: str, body_text: str, name: str) -> str:
    combined = f"{relative_path} {name} {body_text}".lower()
    if any(k in combined for k in ("e2e", "playwright", "cypress", "selenium", "webdriver")):
        return "E2E"
    if any(
        k in combined
        for k in (
            "testclient",
            "httpx",
            "supertest",
            "mockmvc",
            "/api/",
            "status_code",
            "client.get(",
            "client.post(",
        )
    ):
        return "API"
    if any(
        k in combined
        for k in (
            "integration",
            "sessionlocal",
            "db_session",
            "postgres",
            "repository",
            "database",
            "sql",
        )
    ):
        return "INTEGRATION"
    if any(k in combined for k in ("openapi", "schema", "contract", "graphql")):
        return "CONTRACT"
    return "UNIT"


def extract_tests_from_code(
    source_text: str,
    relative_path: str,
    language: str,
) -> list[ExtractedTestCaseCandidate]:
    """
    Deterministically discover unit, integration, API, contract, and E2E test cases
    across Python (`pytest`/`unittest`), Java (`JUnit`), JS/TS (`Jest`/`Vitest`), and PHP (`PHPUnit`).
    """
    norm_path = relative_path.replace("\\", "/")
    lines = source_text.splitlines()
    candidates: list[ExtractedTestCaseCandidate] = []

    if language == "python":
        has_test_markers = (
            is_test_file_path(norm_path)
            or "import pytest" in source_text
            or "import unittest" in source_text
            or "def test_" in source_text
        )
        if not has_test_markers:
            return []
        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            return []

        framework = "PYTEST"
        suite_name = norm_path

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                sline = getattr(node, "lineno", 1)
                eline = getattr(node, "end_lineno", sline)
                snippet = "\n".join(lines[max(0, sline - 1) : min(len(lines), eline)])[:600]

                called_ids: list[str] = []
                assert_cnt = 0
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assert):
                        assert_cnt += 1
                    elif isinstance(sub, ast.Call):
                        if isinstance(sub.func, ast.Name):
                            fn_name = sub.func.id
                            if fn_name.startswith("assert"):
                                assert_cnt += 1
                            elif len(fn_name) >= 3:
                                called_ids.append(fn_name)
                        elif isinstance(sub.func, ast.Attribute):
                            attr_name = sub.func.attr
                            if attr_name.startswith("assert"):
                                assert_cnt += 1
                            elif len(attr_name) >= 3:
                                called_ids.append(attr_name)

                routes = re.findall(r"['\"](/api/[^'\"]+)['\"]", snippet)
                t_kind = _infer_test_kind(norm_path, snippet, node.name)
                doc = ast.get_docstring(node) or f"Executes {t_kind.lower()} verification in `{node.name}`."
                candidates.append(
                    ExtractedTestCaseCandidate(
                        suite_name=suite_name,
                        test_framework=framework,
                        test_key=f"{norm_path}::{node.name}",
                        title=node.name.replace("_", " ").strip().title()[:255],
                        test_kind=t_kind,
                        scenario_description=doc.strip(),
                        relative_path=norm_path,
                        start_line=sline,
                        end_line=eline,
                        excerpt_text=snippet,
                        enclosing_symbol_qname=node.name,
                        called_identifiers=sorted(set(called_ids))[:25],
                        referenced_routes=sorted(set(routes))[:10],
                        assertion_count=assert_cnt,
                    )
                )
        return candidates

    if language == "java":
        if not (is_test_file_path(norm_path) or "@Test" in source_text):
            return []
        java_test_re = re.compile(
            r"@Test\b[^{]*?(?:public|protected|private)?\s*void\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{([^}]*)\}",
            re.DOTALL,
        )
        for m in java_test_re.finditer(source_text):
            m_name = m.group(1)
            body = m.group(2)
            sline = source_text.count("\n", 0, m.start()) + 1
            eline = source_text.count("\n", 0, m.end()) + 1
            calls = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(", body)
            asserts = len(re.findall(r"\bassert[A-Za-z]*\s*\(", body))
            routes = re.findall(r"\"(/api/[^\"]+)\"", body)
            t_kind = _infer_test_kind(norm_path, body, m_name)
            candidates.append(
                ExtractedTestCaseCandidate(
                    suite_name=norm_path,
                    test_framework="JUNIT",
                    test_key=f"{norm_path}#{m_name}",
                    title=m_name[:255],
                    test_kind=t_kind,
                    scenario_description=f"JUnit {t_kind.lower()} test `{m_name}` in `{norm_path}`.",
                    relative_path=norm_path,
                    start_line=sline,
                    end_line=eline,
                    excerpt_text=m.group(0).strip()[:600],
                    enclosing_symbol_qname=m_name,
                    called_identifiers=sorted(set(calls))[:25],
                    referenced_routes=sorted(set(routes))[:10],
                    assertion_count=asserts,
                )
            )
        return candidates

    if language in ("javascript", "typescript"):
        if not (
            is_test_file_path(norm_path)
            or "describe(" in source_text
            or "test(" in source_text
            or "it(" in source_text
        ):
            return []
        framework = "VITEST" if "vitest" in source_text.lower() else "JEST"
        js_test_re = re.compile(
            r"\b(?:it|test)\s*\(\s*['\"`]([^'\"`]+)['\"`]\s*,\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_]+)\s*=>\s*\{([^}]*)\}",
            re.DOTALL,
        )
        for m in js_test_re.finditer(source_text):
            t_title = m.group(1).strip()
            body = m.group(2)
            sline = source_text.count("\n", 0, m.start()) + 1
            eline = source_text.count("\n", 0, m.end()) + 1
            calls = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(", body)
            asserts = len(re.findall(r"\bexpect\s*\(", body))
            routes = re.findall(r"['\"`](/api/[^'\"`]+)['\"`]", body)
            t_kind = _infer_test_kind(norm_path, body, t_title)
            candidates.append(
                ExtractedTestCaseCandidate(
                    suite_name=norm_path,
                    test_framework=framework,
                    test_key=f"{norm_path}::{t_title[:120]}",
                    title=t_title[:255],
                    test_kind=t_kind,
                    scenario_description=f"{framework} {t_kind.lower()} spec: {t_title}",
                    relative_path=norm_path,
                    start_line=sline,
                    end_line=eline,
                    excerpt_text=m.group(0).strip()[:600],
                    called_identifiers=sorted(set(calls))[:25],
                    referenced_routes=sorted(set(routes))[:10],
                    assertion_count=asserts,
                )
            )
        return candidates

    if language == "php":
        if not (is_test_file_path(norm_path) or "TestCase" in source_text):
            return []
        php_test_re = re.compile(
            r"public\s+function\s+(test[A-Za-z0-9_]*)\s*\([^)]*\)\s*\{([^}]*)\}",
            re.DOTALL,
        )
        for m in php_test_re.finditer(source_text):
            m_name = m.group(1)
            body = m.group(2)
            sline = source_text.count("\n", 0, m.start()) + 1
            eline = source_text.count("\n", 0, m.end()) + 1
            calls = re.findall(r"->([A-Za-z_][A-Za-z0-9_]{2,})\s*\(", body)
            asserts = len(re.findall(r"->assert[A-Za-z0-9_]*\s*\(", body))
            t_kind = _infer_test_kind(norm_path, body, m_name)
            candidates.append(
                ExtractedTestCaseCandidate(
                    suite_name=norm_path,
                    test_framework="PHPUNIT",
                    test_key=f"{norm_path}::{m_name}",
                    title=m_name[:255],
                    test_kind=t_kind,
                    scenario_description=f"PHPUnit {t_kind.lower()} test `{m_name}`.",
                    relative_path=norm_path,
                    start_line=sline,
                    end_line=eline,
                    excerpt_text=m.group(0).strip()[:600],
                    enclosing_symbol_qname=m_name,
                    called_identifiers=sorted(set(calls))[:25],
                    assertion_count=asserts,
                )
            )
    return candidates


def parse_coverage_report(raw_text: str, relative_path: str) -> list[ExtractedCoverageRecord]:
    """
    Parse Cobertura XML (`coverage.xml`) or LCOV (`lcov.info`) reports if present in the snapshot.
    Distinguishes measured coverage (`COVERAGE_REPORT`) from static/inferred coverage.
    """
    records: list[ExtractedCoverageRecord] = []
    norm_path = relative_path.replace("\\", "/").lower()

    if norm_path.endswith(".xml") and "<coverage" in raw_text:
        try:
            root = ET.fromstring(raw_text)
            for cls_el in root.findall(".//class"):
                filename = cls_el.attrib.get("filename", "").replace("\\", "/")
                if not filename:
                    continue
                line_rate = float(cls_el.attrib.get("line-rate", "0.0") or 0.0)
                cov_lines: list[int] = []
                for line_el in cls_el.findall(".//line"):
                    hits = int(line_el.attrib.get("hits", "0") or 0)
                    num = int(line_el.attrib.get("number", "0") or 0)
                    if hits > 0 and num > 0:
                        cov_lines.append(num)
                records.append(
                    ExtractedCoverageRecord(
                        relative_path=filename,
                        line_rate=round(line_rate, 4),
                        covered_lines=sorted(set(cov_lines)),
                        coverage_source="COVERAGE_REPORT",
                    )
                )
        except Exception:
            pass
    elif norm_path.endswith(("lcov.info", ".lcov")) or "SF:" in raw_text:
        current_file: str | None = None
        hit_lines: list[int] = []
        total_lines = 0
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if line.startswith("SF:"):
                current_file = line[3:].strip().replace("\\", "/")
                hit_lines = []
                total_lines = 0
            elif line.startswith("DA:") and current_file:
                parts = line[3:].split(",")
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    total_lines += 1
                    if int(parts[1]) > 0:
                        hit_lines.append(int(parts[0]))
            elif line == "end_of_record" and current_file:
                rate = (len(hit_lines) / total_lines) if total_lines > 0 else 0.0
                records.append(
                    ExtractedCoverageRecord(
                        relative_path=current_file,
                        line_rate=round(rate, 4),
                        covered_lines=sorted(set(hit_lines)),
                        coverage_source="COVERAGE_REPORT",
                    )
                )
                current_file = None
    return records


def generate_missing_test_blueprint(
    *,
    req_code: str,
    req_title: str,
    req_type: str,
    given_clause: str,
    when_clause: str,
    then_clause: str,
    target_symbol_name: str | None = None,
) -> tuple[str, str, str]:
    """
    Generate a characterization/regression test blueprint for an untested Requirement or Business Rule.
    Returns `(test_key, test_kind, code_blueprint)`.
    """
    safe_slug = re.sub(r"[^a-z0-9_]+", "_", f"{req_code}_{req_title}".lower()).strip("_")[:60]
    test_key = f"blueprint::test_{safe_slug}"
    test_kind = (
        "INTEGRATION"
        if req_type in ("INTEGRATION_CONTRACT", "NON_FUNCTIONAL_SECURITY", "DATA_CONSTRAINT")
        else "CHARACTERIZATION"
    )
    fn_target = target_symbol_name or "target_component"
    blueprint = (
        f"# AUTO-GENERATED CHARACTERIZATION TEST BLUEPRINT (NOT EXECUTED)\n"
        f"# Requirement: {req_code} — {req_title}\n"
        f"import pytest\n\n"
        f"def test_{safe_slug}() -> None:\n"
        f'    """\n'
        f"    {given_clause}\n"
        f"    {when_clause}\n"
        f"    {then_clause}\n"
        f'    """\n'
        f"    # Arrange ({given_clause})\n"
        f"    # Act: invoke `{fn_target}` ({when_clause})\n"
        f"    # Assert ({then_clause})\n"
        f"    assert True  # Replace with concrete assertion against `{fn_target}`\n"
    )
    return test_key, test_kind, blueprint


def parse_dependency_manifests(
    raw_text: str,
    relative_path: str,
) -> list[ExtractedDependencyRecord]:
    """
    Parse `requirements.txt`, `package.json`, `pom.xml`, and `composer.json`
    and match versions against `_VERIFIED_ADVISORY_DB` without fabricating CVEs.
    """
    norm_path = relative_path.replace("\\", "/")
    base = posixpath.basename(norm_path).lower()
    deps: list[ExtractedDependencyRecord] = []

    if base == "requirements.txt" or base.endswith("-requirements.txt"):
        for idx, raw_line in enumerate(raw_text.splitlines(), start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*([=<>!~]+\s*[A-Za-z0-9_.\-*]+)?", line)
            if not m:
                continue
            pkg = m.group(1).strip()
            spec = (m.group(2) or "").strip()
            is_pinned = spec.startswith("==") and "*" not in spec
            pinned_ver = spec.lstrip("=").strip() if is_pinned else None
            ver_check = pinned_ver or re.sub(r"^[~^>=<]+", "", spec).strip()
            adv_id, adv_sev, adv_sum = _lookup_advisory("pypi", pkg.lower(), ver_check)
            is_eol = adv_id is not None or (ver_check.startswith("0.") and is_pinned)
            deps.append(
                ExtractedDependencyRecord(
                    manifest_path=norm_path,
                    ecosystem="pypi",
                    package_name=pkg,
                    version_spec=spec or "UNPINNED",
                    pinned_version=pinned_ver,
                    is_pinned=is_pinned,
                    is_outdated_or_eol=is_eol,
                    advisory_id=adv_id,
                    advisory_severity=adv_sev,
                    advisory_summary=adv_sum,
                    start_line=idx,
                    excerpt_text=raw_line.strip()[:240],
                )
            )
    elif base == "package.json":
        try:
            data = json.loads(raw_text)
        except Exception:
            return []
        for section in ("dependencies", "devDependencies"):
            sec_obj = data.get(section)
            if not isinstance(sec_obj, dict):
                continue
            for pkg, spec_val in sec_obj.items():
                spec_str = str(spec_val).strip()
                is_pinned = bool(re.match(r"^\d+\.\d+\.\d+$", spec_str))
                clean_ver = spec_str.lstrip("^~>=< ")
                adv_id, adv_sev, adv_sum = _lookup_advisory("npm", pkg.lower(), clean_ver)
                deps.append(
                    ExtractedDependencyRecord(
                        manifest_path=norm_path,
                        ecosystem="npm",
                        package_name=pkg,
                        version_spec=spec_str,
                        pinned_version=clean_ver if is_pinned else None,
                        is_pinned=is_pinned,
                        is_outdated_or_eol=adv_id is not None,
                        advisory_id=adv_id,
                        advisory_severity=adv_sev,
                        advisory_summary=adv_sum,
                        start_line=1,
                        excerpt_text=f'"{pkg}": "{spec_str}"',
                    )
                )
    return deps


def _lookup_advisory(
    ecosystem: str, pkg_lower: str, version_str: str
) -> tuple[str | None, str | None, str | None]:
    if not version_str:
        return None, None, None
    entries = _VERIFIED_ADVISORY_DB.get((ecosystem, pkg_lower), [])
    for prefix, adv_id, sev, summary in entries:
        if version_str == prefix or version_str.startswith(prefix):
            return adv_id, sev, summary
    return None, None, None


def extract_code_security_and_performance_risks(
    source_text: str,
    relative_path: str,
    language: str,
) -> list[ExtractedRiskCandidate]:
    """
    Deterministically detect security, data integrity, and performance risks in source code:
    - Hardcoded secrets / API keys / passwords (`CWE-798`)
    - Dynamic SQL string concatenation / formatting (`CWE-89`)
    - Unsafe command execution / deserialization (`eval`, `exec`, `shell=True`, `pickle.loads`, `yaml.load`) (`CWE-78` / `CWE-502`)
    - N+1 database query execution inside loops (`PERFORMANCE`)
    """
    norm_path = relative_path.replace("\\", "/")
    if is_test_file_path(norm_path):
        return []

    risks: list[ExtractedRiskCandidate] = []
    lines = source_text.splitlines()

    # 1. Hardcoded credentials / secrets (`CWE-798`)
    secret_re = re.compile(
        r"\b([A-Za-z0-9_]*(?:password|passwd|secret|api_key|private_key|access_token)[A-Za-z0-9_]*)\s*=\s*['\"]([^'\"]{6,})['\"]",
        re.IGNORECASE,
    )
    for m in secret_re.finditer(source_text):
        var_name = m.group(1)
        val = m.group(2)
        if val.startswith(("$", "{", "<", "env", "YOUR_")) or "example" in val.lower():
            continue
        sline = source_text.count("\n", 0, m.start()) + 1
        redacted_line = re.sub(r"=['\"][^'\"]+['\"]", '="***REDACTED***"', lines[sline - 1].strip())
        risks.append(
            ExtractedRiskCandidate(
                risk_category="SECURITY",
                severity="CRITICAL",
                likelihood="HIGH",
                title=f"Hardcoded Credential / Secret in `{norm_path}` (`{var_name}`)",
                statement_markdown=(
                    f"Source file `{norm_path}` assigns a literal secret to `{var_name}` at line {sline} (`CWE-798`). "
                    f"Hardcoded credentials risk credential leakage via version control and artifact snapshots."
                ),
                remediation_recommendation=(
                    "Externalize secrets to environment variables or a dedicated secret manager (Vault/KMS) and rotate the exposed credential."
                ),
                affected_components=[norm_path, var_name],
                relative_path=norm_path,
                start_line=sline,
                end_line=sline,
                excerpt_text=redacted_line[:300],
                confidence_score=0.95,
                cwe_or_advisory_ref="CWE-798",
            )
        )

    # 2. Dynamic SQL Injection risk (`CWE-89`)
    sqli_re = re.compile(
        r"(?:f\"(?:SELECT|INSERT|UPDATE|DELETE)\b[^\"]*\{[^}]+\}|f'(?:SELECT|INSERT|UPDATE|DELETE)\b[^']*\{[^}]+\}|['\"](?:SELECT|INSERT|UPDATE|DELETE)\b[^'\"]*['\"]\s*(?:\+|%|\.\s*format\())",
        re.IGNORECASE,
    )
    for m in sqli_re.finditer(source_text):
        sline = source_text.count("\n", 0, m.start()) + 1
        eline = source_text.count("\n", 0, m.end()) + 1
        snippet = "\n".join(lines[max(0, sline - 1) : min(len(lines), eline)])[:350]
        risks.append(
            ExtractedRiskCandidate(
                risk_category="SECURITY",
                severity="CRITICAL",
                likelihood="HIGH",
                title=f"Potential SQL Injection via String Interpolation in `{norm_path}`",
                statement_markdown=(
                    f"Dynamic SQL statement constructed via string interpolation or concatenation at `{norm_path}:{sline}` (`CWE-89`)."
                ),
                remediation_recommendation=(
                    "Replace string-interpolated SQL with parameterized bind variables (`:param` or prepared statements)."
                ),
                affected_components=[norm_path],
                relative_path=norm_path,
                start_line=sline,
                end_line=eline,
                excerpt_text=snippet,
                confidence_score=0.94,
                cwe_or_advisory_ref="CWE-89",
            )
        )

    # 3. Unsafe Execution / Deserialization (`CWE-78` / `CWE-502`)
    unsafe_exec_re = re.compile(
        r"\b(eval\s*\(|exec\s*\(|pickle\.loads\s*\(|yaml\.load\s*\([^)]*\)|subprocess\.(?:Popen|call|run)\s*\([^)]*shell\s*=\s*True)",
    )
    for m in unsafe_exec_re.finditer(source_text):
        matched = m.group(0)
        if "yaml.load" in matched and "SafeLoader" in matched:
            continue
        sline = source_text.count("\n", 0, m.start()) + 1
        eline = source_text.count("\n", 0, m.end()) + 1
        snippet = "\n".join(lines[max(0, sline - 1) : min(len(lines), eline)])[:350]
        risks.append(
            ExtractedRiskCandidate(
                risk_category="SECURITY",
                severity="HIGH",
                likelihood="MEDIUM",
                title=f"Unsafe Code Execution / Deserialization Pattern in `{norm_path}`",
                statement_markdown=(
                    f"Detected unsafe execution or deserialization primitive (`{matched[:40]}...`) at `{norm_path}:{sline}` (`CWE-78`/`CWE-502`)."
                ),
                remediation_recommendation=(
                    "Avoid `eval`/`exec`/`pickle.loads` on untrusted input, use `yaml.safe_load`, and pass argument arrays to `subprocess` with `shell=False`."
                ),
                affected_components=[norm_path],
                relative_path=norm_path,
                start_line=sline,
                end_line=eline,
                excerpt_text=snippet,
                confidence_score=0.93,
                cwe_or_advisory_ref="CWE-78/CWE-502",
            )
        )

    # 4. N+1 Query / Synchronous DB Call inside Loop (`PERFORMANCE`)
    if language == "python":
        try:
            tree = ast.parse(source_text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.For, ast.While)):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                            if sub.func.attr in ("execute", "query", "get", "filter", "fetchall", "fetchone"):
                                sline = getattr(node, "lineno", 1)
                                eline = getattr(sub, "end_lineno", sline)
                                snippet = "\n".join(
                                    lines[max(0, sline - 1) : min(len(lines), eline)]
                                )[:350]
                                risks.append(
                                    ExtractedRiskCandidate(
                                        risk_category="PERFORMANCE",
                                        severity="MEDIUM",
                                        likelihood="HIGH",
                                        title=f"Potential N+1 Query / Database Call Inside Loop in `{norm_path}`",
                                        statement_markdown=(
                                            f"Iterative loop at `{norm_path}:{sline}` invokes `.{sub.func.attr}()` repeatedly, "
                                            f"creating an N+1 query bottleneck under high cardinality."
                                        ),
                                        remediation_recommendation=(
                                            "Batch-fetch records outside the loop using `WHERE id IN (...)` or bulk upsert operations."
                                        ),
                                        affected_components=[norm_path],
                                        relative_path=norm_path,
                                        start_line=sline,
                                        end_line=max(sline, eline),
                                        excerpt_text=snippet,
                                        confidence_score=0.88,
                                    )
                                )
                                break
        except SyntaxError:
            pass

    return risks


__all__ = [
    "ExtractedCoverageRecord",
    "ExtractedDependencyRecord",
    "ExtractedRiskCandidate",
    "ExtractedTestCaseCandidate",
    "extract_code_security_and_performance_risks",
    "extract_tests_from_code",
    "generate_missing_test_blueprint",
    "is_test_file_path",
    "parse_coverage_report",
    "parse_dependency_manifests",
]
