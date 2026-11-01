"""Wave 3 — Deterministic Business Rule & Requirements Extraction Engine (Code, DB, API, Docs)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import re
from typing import Any


@dataclass
class ExtractedBusinessRuleCandidate:
    """Structured business rule candidate extracted from source code, DB schema, API spec, or documentation."""

    rule_code_prefix: str
    domain_code: str
    rule_category: str  # VALIDATION | CALCULATION | AUTHORIZATION | STATE_TRANSITION | INVARIANT | ROUTING
    title: str
    condition_expression: str
    action_consequence: str
    origin_type: str  # DETERMINISTIC_RULE | HYBRID_AI_STATIC | AI_INFERRED
    confidence_score: float
    source_kind: str  # CODE | DB | API | DOC
    relative_path: str | None = None
    start_line: int = 1
    end_line: int = 1
    excerpt_text: str = ""
    enclosing_symbol_qname: str | None = None
    enclosing_symbol_name: str | None = None
    subject_identifier: str | None = None
    numeric_thresholds: list[float] = field(default_factory=list)
    evidence_role: str = "PRIMARY_DEFINITION"
    rationale_note: str = "Extracted deterministically from source artifact."


@dataclass
class ExtractedRequirementCandidate:
    """Structured functional or non-functional requirement synthesized from discovered rules and technical contracts."""

    req_code_prefix: str
    domain_code: str
    req_type: str  # FUNCTIONAL | NON_FUNCTIONAL_SECURITY | NON_FUNCTIONAL_PERFORMANCE | DATA_CONSTRAINT | INTEGRATION_CONTRACT
    priority: str  # MUST | SHOULD | COULD
    title: str
    specification_statement: str
    origin_type: str
    confidence_score: float
    actors: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    given_clause: str = "Given an active application runtime context"
    when_clause: str = "When the operation is invoked"
    then_clause: str = "Then the system enforces the specified behavior"
    verification_method: str = "UNIT_TEST"
    is_implicit: bool = False
    source_rule_indices: list[int] = field(default_factory=list)
    related_symbol_qnames: list[str] = field(default_factory=list)
    related_table_names: list[str] = field(default_factory=list)
    related_endpoint_routes: list[str] = field(default_factory=list)
    relative_path: str | None = None
    start_line: int = 1
    end_line: int = 1
    excerpt_text: str = ""


DOMAIN_CATALOG: dict[str, tuple[str, str]] = {
    "ORDER_MANAGEMENT": (
        "Order & Fulfillment Management",
        "Customer orders, checkout validation, order status lifecycle, and fulfillment processing.",
    ),
    "BILLING_FINANCE": (
        "Billing, Pricing & Financial Calculations",
        "Pricing formulas, discounts, taxes, fees, invoicing, and payment settlement rules.",
    ),
    "IDENTITY_SECURITY": (
        "Identity, Access Control & Security",
        "Authentication, role-based authorization, tenant isolation, and PII protection controls.",
    ),
    "DATA_GOVERNANCE": (
        "Data Integrity & Schema Governance",
        "Relational schema invariants, foreign-key referential integrity, triggers, and audit trails.",
    ),
    "API_INTEGRATION": (
        "API Contracts & Service Integration",
        "External/internal REST and GraphQL service contracts, request schemas, and routing.",
    ),
    "OPERATIONS_INFRA": (
        "Platform Operations & Resilience",
        "Runtime health checks, container/infrastructure constraints, and operational reliability.",
    ),
    "CORE_DOMAIN": (
        "Core Application Business Logic",
        "General domain workflows, state transitions, and application invariants.",
    ),
}

_CALC_KEYWORDS = {
    "total",
    "subtotal",
    "amount",
    "price",
    "tax",
    "discount",
    "fee",
    "rate",
    "balance",
    "score",
    "limit",
    "quota",
    "interest",
    "commission",
    "charge",
    "cost",
    "net",
    "gross",
}

_STATE_KEYWORDS = {
    "status",
    "state",
    "stage",
    "phase",
    "lifecycle",
    "order_status",
    "approval_status",
    "review_status",
    "payment_status",
}

_AUTH_KEYWORDS = {
    "role",
    "permission",
    "auth",
    "token",
    "admin",
    "tenant",
    "preauthorize",
    "hasrole",
    "is_authenticated",
    "current_user",
    "scope",
}

_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def infer_domain_code(text_blob: str, relative_path: str | None = None) -> str:
    """Classify a rule or requirement into one of the canonical business domains."""
    lower = f"{relative_path or ''} {text_blob}".lower()
    if any(
        k in lower
        for k in ("tax", "discount", "invoice", "billing", "payment", "charge", "fee", "price")
    ):
        return "BILLING_FINANCE"
    if any(k in lower for k in ("order", "cart", "checkout", "fulfill", "shipment", "customer_orders")):
        return "ORDER_MANAGEMENT"
    if any(
        k in lower
        for k in ("auth", "role", "permission", "jwt", "token", "login", "preauthorize", "security", "pii")
    ):
        return "IDENTITY_SECURITY"
    if any(
        k in lower
        for k in ("foreign key", "primary key", "trigger", "procedure", "schema", "table", "constraint")
    ):
        return "DATA_GOVERNANCE"
    if any(k in lower for k in ("openapi", "graphql", "endpoint", "route", "/api/", "webhook")):
        return "API_INTEGRATION"
    if any(k in lower for k in ("docker", "kubernetes", "terraform", "healthcheck", "replica")):
        return "OPERATIONS_INFRA"
    return "CORE_DOMAIN"


def _extract_numbers(text: str) -> list[float]:
    vals: list[float] = []
    for m in _NUMBER_RE.finditer(text):
        try:
            v = float(m.group(0))
            if v not in (0.0, 1.0):
                vals.append(v)
        except ValueError:
            continue
    return vals


def _slice_lines(source_text: str, start_line: int, end_line: int) -> str:
    lines = source_text.splitlines()
    if not lines:
        return ""
    s = max(1, start_line)
    e = min(len(lines), max(s, end_line))
    return "\n".join(lines[s - 1 : e])[:1200]


def extract_business_rules_from_python(
    source_text: str,
    relative_path: str,
) -> list[ExtractedBusinessRuleCandidate]:
    """Deterministically extract validations, calculations, state transitions, and auth checks from Python AST."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return _extract_business_rules_regex_fallback(source_text, relative_path, "python")

    candidates: list[ExtractedBusinessRuleCandidate] = []

    class _RuleVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope_stack: list[str] = []

        @property
        def current_symbol(self) -> str | None:
            return ".".join(self.scope_stack) if self.scope_stack else None

        @property
        def current_short_symbol(self) -> str | None:
            return self.scope_stack[-1] if self.scope_stack else None

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope_stack.append(node.name)
            self.generic_visit(node)
            self.scope_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._inspect_function(node)
            self.scope_stack.append(node.name)
            self.generic_visit(node)
            self.scope_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._inspect_function(node)
            self.scope_stack.append(node.name)
            self.generic_visit(node)
            self.scope_stack.pop()

        def _inspect_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            # Check function signature/decorators for auth dependencies
            fn_src = _slice_lines(
                source_text,
                getattr(node, "lineno", 1),
                min(getattr(node, "end_lineno", getattr(node, "lineno", 1)), getattr(node, "lineno", 1) + 12),
            )
            if any(tok in fn_src.lower() for tok in ("depends(", "require_role", "permission", "current_user", "verify_token")):
                s_line = getattr(node, "lineno", 1)
                e_line = min(getattr(node, "end_lineno", s_line), s_line + 8)
                candidates.append(
                    ExtractedBusinessRuleCandidate(
                        rule_code_prefix="BR-AUTH",
                        domain_code="IDENTITY_SECURITY",
                        rule_category="AUTHORIZATION",
                        title=f"Access Control Gate on `{node.name}`",
                        condition_expression=f"WHEN `{node.name}` is invoked without satisfied security dependency",
                        action_consequence="DENY execution and enforce authentication/authorization guard.",
                        origin_type="DETERMINISTIC_RULE",
                        confidence_score=0.95,
                        source_kind="CODE",
                        relative_path=relative_path,
                        start_line=s_line,
                        end_line=e_line,
                        excerpt_text=_slice_lines(source_text, s_line, e_line),
                        enclosing_symbol_qname=f"{self.current_symbol}.{node.name}" if self.current_symbol else node.name,
                        enclosing_symbol_name=node.name,
                        subject_identifier=node.name.lower(),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Extracted from function security dependency/decorator in Python AST.",
                    )
                )

        def visit_If(self, node: ast.If) -> None:
            cond_str = ast.unparse(node.test) if hasattr(ast, "unparse") else "condition"
            s_line = getattr(node, "lineno", 1)
            e_line = getattr(node, "end_lineno", s_line)
            snippet = _slice_lines(source_text, s_line, e_line)
            sym_name = self.current_short_symbol or "module"

            # 1. Check if branch raises an exception -> VALIDATION or AUTHORIZATION rule
            raises = [n for n in node.body if isinstance(n, ast.Raise)]
            if raises:
                raise_str = ast.unparse(raises[0]) if hasattr(ast, "unparse") else "raise"
                is_auth = any(k in f"{cond_str} {raise_str}".lower() for k in _AUTH_KEYWORDS)
                category = "AUTHORIZATION" if is_auth else "VALIDATION"
                dom = "IDENTITY_SECURITY" if is_auth else infer_domain_code(f"{sym_name} {cond_str} {raise_str}", relative_path)
                candidates.append(
                    ExtractedBusinessRuleCandidate(
                        rule_code_prefix="BR-AUTH" if is_auth else "BR-VAL",
                        domain_code=dom,
                        rule_category=category,
                        title=f"{'Authorization' if is_auth else 'Validation'} Guard in `{sym_name}`: `{cond_str[:65]}`",
                        condition_expression=f"IF {cond_str}",
                        action_consequence=f"REJECT operation ({raise_str})",
                        origin_type="DETERMINISTIC_RULE",
                        confidence_score=0.96,
                        source_kind="CODE",
                        relative_path=relative_path,
                        start_line=s_line,
                        end_line=e_line,
                        excerpt_text=snippet,
                        enclosing_symbol_qname=self.current_symbol,
                        enclosing_symbol_name=self.current_short_symbol,
                        subject_identifier=sym_name.lower(),
                        numeric_thresholds=_extract_numbers(cond_str),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Extracted from conditional guard raising exception in Python AST.",
                    )
                )
            else:
                # 2. Check if branch performs calculation or state transition
                body_unparsed = "\n".join(
                    ast.unparse(stmt) for stmt in node.body if hasattr(ast, "unparse")
                )
                lower_body = body_unparsed.lower()
                if any(k in f"{cond_str.lower()} {lower_body}" for k in _CALC_KEYWORDS):
                    dom = infer_domain_code(f"{sym_name} {cond_str} {body_unparsed}", relative_path)
                    candidates.append(
                        ExtractedBusinessRuleCandidate(
                            rule_code_prefix="BR-CALC",
                            domain_code=dom,
                            rule_category="CALCULATION",
                            title=f"Conditional Calculation in `{sym_name}` when `{cond_str[:55]}`",
                            condition_expression=f"IF {cond_str}",
                            action_consequence=f"COMPUTE {body_unparsed.splitlines()[0][:140] if body_unparsed else 'derived value'}",
                            origin_type="DETERMINISTIC_RULE",
                            confidence_score=0.93,
                            source_kind="CODE",
                            relative_path=relative_path,
                            start_line=s_line,
                            end_line=e_line,
                            excerpt_text=snippet,
                            enclosing_symbol_qname=self.current_symbol,
                            enclosing_symbol_name=self.current_short_symbol,
                            subject_identifier=sym_name.lower(),
                            numeric_thresholds=_extract_numbers(f"{cond_str} {body_unparsed}"),
                            evidence_role="PRIMARY_DEFINITION",
                            rationale_note="Extracted from conditional calculation branch in Python AST.",
                        )
                    )
                elif any(k in lower_body for k in _STATE_KEYWORDS):
                    dom = infer_domain_code(f"{sym_name} {cond_str} {body_unparsed}", relative_path)
                    candidates.append(
                        ExtractedBusinessRuleCandidate(
                            rule_code_prefix="BR-STATE",
                            domain_code=dom,
                            rule_category="STATE_TRANSITION",
                            title=f"State Transition in `{sym_name}` when `{cond_str[:55]}`",
                            condition_expression=f"IF {cond_str}",
                            action_consequence=f"TRANSITION {body_unparsed.splitlines()[0][:140] if body_unparsed else 'state'}",
                            origin_type="DETERMINISTIC_RULE",
                            confidence_score=0.92,
                            source_kind="CODE",
                            relative_path=relative_path,
                            start_line=s_line,
                            end_line=e_line,
                            excerpt_text=snippet,
                            enclosing_symbol_qname=self.current_symbol,
                            enclosing_symbol_name=self.current_short_symbol,
                            subject_identifier=sym_name.lower(),
                            numeric_thresholds=_extract_numbers(f"{cond_str} {body_unparsed}"),
                            evidence_role="PRIMARY_DEFINITION",
                            rationale_note="Extracted from conditional state assignment in Python AST.",
                        )
                    )

            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            if not hasattr(ast, "unparse"):
                return
            targets_str = ", ".join(ast.unparse(t) for t in node.targets)
            val_str = ast.unparse(node.value)
            s_line = getattr(node, "lineno", 1)
            e_line = getattr(node, "end_lineno", s_line)
            sym_name = self.current_short_symbol or "module"

            if isinstance(node.value, ast.BinOp) and any(
                k in f"{targets_str} {val_str}".lower() for k in _CALC_KEYWORDS
            ):
                dom = infer_domain_code(f"{sym_name} {targets_str} {val_str}", relative_path)
                candidates.append(
                    ExtractedBusinessRuleCandidate(
                        rule_code_prefix="BR-CALC",
                        domain_code=dom,
                        rule_category="CALCULATION",
                        title=f"Formula Calculation for `{targets_str}` in `{sym_name}`",
                        condition_expression=f"WHEN computing `{targets_str}` in `{sym_name}`",
                        action_consequence=f"SET {targets_str} = {val_str}",
                        origin_type="DETERMINISTIC_RULE",
                        confidence_score=0.94,
                        source_kind="CODE",
                        relative_path=relative_path,
                        start_line=s_line,
                        end_line=e_line,
                        excerpt_text=_slice_lines(source_text, s_line, e_line),
                        enclosing_symbol_qname=self.current_symbol,
                        enclosing_symbol_name=self.current_short_symbol,
                        subject_identifier=targets_str.lower(),
                        numeric_thresholds=_extract_numbers(val_str),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Extracted from arithmetic business calculation assignment in Python AST.",
                    )
                )
            elif any(k in targets_str.lower() for k in _STATE_KEYWORDS) and isinstance(
                node.value, ast.Constant
            ):
                dom = infer_domain_code(f"{sym_name} {targets_str} {val_str}", relative_path)
                candidates.append(
                    ExtractedBusinessRuleCandidate(
                        rule_code_prefix="BR-STATE",
                        domain_code=dom,
                        rule_category="STATE_TRANSITION",
                        title=f"Lifecycle State Update `{targets_str} = {val_str}` in `{sym_name}`",
                        condition_expression=f"DURING `{sym_name}` execution",
                        action_consequence=f"TRANSITION `{targets_str}` to {val_str}",
                        origin_type="DETERMINISTIC_RULE",
                        confidence_score=0.90,
                        source_kind="CODE",
                        relative_path=relative_path,
                        start_line=s_line,
                        end_line=e_line,
                        excerpt_text=_slice_lines(source_text, s_line, e_line),
                        enclosing_symbol_qname=self.current_symbol,
                        enclosing_symbol_name=self.current_short_symbol,
                        subject_identifier=targets_str.lower(),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Extracted from explicit domain state assignment in Python AST.",
                    )
                )

    _RuleVisitor().visit(tree)
    return candidates


_GUARD_THROW_RE = re.compile(
    r"if\s*\((?P<cond>[^)]+)\)\s*\{?\s*(?:throw\s+new\s+(?P<exc>[A-Za-z0-9_]+)\s*\((?P<msg>[^)]*)\)|return\s+(?P<ret>[^;]+);)",
    re.MULTILINE | re.DOTALL,
)
_PREAUTH_RE = re.compile(
    r"@(?P<ann>PreAuthorize|Secured|RolesAllowed)\s*\(\s*\"(?P<expr>[^\"]+)\"\s*\)",
    re.MULTILINE,
)
_CALC_ASSIGN_RE = re.compile(
    r"(?P<lhs>[A-Za-z0-9_.$\->]*(?:total|amount|price|tax|discount|fee|rate|balance|limit)[A-Za-z0-9_]*)\s*=\s*(?P<rhs>[^;\n]+[*+\-/][^;\n]+)",
    re.IGNORECASE,
)


def _extract_business_rules_regex_fallback(
    source_text: str,
    relative_path: str,
    language: str,
) -> list[ExtractedBusinessRuleCandidate]:
    """Extract business rules from Java, JavaScript, TypeScript, PHP, or fallback source files."""
    candidates: list[ExtractedBusinessRuleCandidate] = []

    for m in _PREAUTH_RE.finditer(source_text):
        s_line = source_text[: m.start()].count("\n") + 1
        e_line = min(len(source_text.splitlines()), s_line + 4)
        expr = m.group("expr")
        candidates.append(
            ExtractedBusinessRuleCandidate(
                rule_code_prefix="BR-AUTH",
                domain_code="IDENTITY_SECURITY",
                rule_category="AUTHORIZATION",
                title=f"Method Security Policy `@{m.group('ann')}({expr})`",
                condition_expression=f"WHEN caller invokes annotated handler without `{expr}`",
                action_consequence="DENY invocation with HTTP 403 Forbidden.",
                origin_type="DETERMINISTIC_RULE",
                confidence_score=0.97,
                source_kind="CODE",
                relative_path=relative_path,
                start_line=s_line,
                end_line=e_line,
                excerpt_text=_slice_lines(source_text, s_line, e_line),
                subject_identifier=expr.lower(),
                evidence_role="PRIMARY_DEFINITION",
                rationale_note=f"Extracted from @{m.group('ann')} security annotation in {language} source.",
            )
        )

    for m in _GUARD_THROW_RE.finditer(source_text):
        s_line = source_text[: m.start()].count("\n") + 1
        e_line = source_text[: m.end()].count("\n") + 1
        cond = " ".join(m.group("cond").split())
        exc = m.group("exc") or "ValidationError"
        msg = (m.group("msg") or m.group("ret") or "").strip()
        dom = infer_domain_code(f"{cond} {exc} {msg}", relative_path)
        candidates.append(
            ExtractedBusinessRuleCandidate(
                rule_code_prefix="BR-VAL",
                domain_code=dom,
                rule_category="VALIDATION",
                title=f"Guard Clause `{cond[:60]}` in `{relative_path}`",
                condition_expression=f"IF ({cond})",
                action_consequence=f"THROW {exc}({msg})" if m.group("exc") else f"RETURN {msg}",
                origin_type="DETERMINISTIC_RULE",
                confidence_score=0.94,
                source_kind="CODE",
                relative_path=relative_path,
                start_line=s_line,
                end_line=e_line,
                excerpt_text=_slice_lines(source_text, s_line, e_line),
                subject_identifier=relative_path.lower(),
                numeric_thresholds=_extract_numbers(cond),
                evidence_role="PRIMARY_DEFINITION",
                rationale_note=f"Extracted from conditional guard clause in {language} source.",
            )
        )

    for m in _CALC_ASSIGN_RE.finditer(source_text):
        s_line = source_text[: m.start()].count("\n") + 1
        e_line = source_text[: m.end()].count("\n") + 1
        lhs = m.group("lhs").strip()
        rhs = m.group("rhs").strip()
        dom = infer_domain_code(f"{lhs} {rhs}", relative_path)
        candidates.append(
            ExtractedBusinessRuleCandidate(
                rule_code_prefix="BR-CALC",
                domain_code=dom,
                rule_category="CALCULATION",
                title=f"Business Calculation `{lhs} = {rhs[:55]}`",
                condition_expression=f"WHEN computing `{lhs}` in `{relative_path}`",
                action_consequence=f"SET {lhs} = {rhs}",
                origin_type="DETERMINISTIC_RULE",
                confidence_score=0.91,
                source_kind="CODE",
                relative_path=relative_path,
                start_line=s_line,
                end_line=e_line,
                excerpt_text=_slice_lines(source_text, s_line, e_line),
                subject_identifier=lhs.lower(),
                numeric_thresholds=_extract_numbers(rhs),
                evidence_role="PRIMARY_DEFINITION",
                rationale_note=f"Extracted from financial/metric calculation formula in {language} source.",
            )
        )

    return candidates


def extract_business_rules_from_code(
    source_text: str,
    relative_path: str,
    language: str,
) -> list[ExtractedBusinessRuleCandidate]:
    """Entry point for extracting business rules from any supported source code language."""
    if language == "python":
        py_rules = extract_business_rules_from_python(source_text, relative_path)
        if py_rules:
            return py_rules
    return _extract_business_rules_regex_fallback(source_text, relative_path, language)


_DOC_NORMATIVE_RE = re.compile(
    r"(?P<sent>[^.\n]*(?:\bmust\b|\bshall\b|\brequired\b|\bnever\b|\bmaximum\b|\bminimum\b|\blimit\b|\bthreshold\b|\bdiscount\b|\bapproval\b|\bwrites to\b|\breads\b|\bexposes\b)[^.\n]*\.?)",
    re.IGNORECASE,
)


def extract_business_rules_from_doc_section(
    *,
    section_title: str,
    text_content: str,
    relative_path: str,
    start_line: int = 1,
    end_line: int = 1,
) -> list[ExtractedBusinessRuleCandidate]:
    """Extract documented business rules and normative constraints from documentation sections."""
    candidates: list[ExtractedBusinessRuleCandidate] = []
    seen_titles: set[str] = set()

    for m in _DOC_NORMATIVE_RE.finditer(text_content):
        sentence = " ".join(m.group("sent").strip().split())
        if len(sentence) < 18:
            continue
        title = f"Documented Rule ({section_title}): {sentence[:72]}"
        if title in seen_titles:
            continue
        seen_titles.add(title)

        lower = sentence.lower()
        if any(k in lower for k in ("discount", "tax", "total", "price", "fee", "%", "rate")):
            cat = "CALCULATION"
            prefix = "BR-DOC-CALC"
        elif any(k in lower for k in ("auth", "role", "permission", "admin", "token", "security")):
            cat = "AUTHORIZATION"
            prefix = "BR-DOC-AUTH"
        elif any(k in lower for k in ("must", "shall", "required", "minimum", "maximum", "limit", "threshold")):
            cat = "VALIDATION"
            prefix = "BR-DOC-VAL"
        else:
            cat = "INVARIANT"
            prefix = "BR-DOC-INV"

        dom = infer_domain_code(f"{section_title} {sentence}", relative_path)
        candidates.append(
            ExtractedBusinessRuleCandidate(
                rule_code_prefix=prefix,
                domain_code=dom,
                rule_category=cat,
                title=title[:250],
                condition_expression=f"DOCUMENTED IN `{section_title}` ({relative_path})",
                action_consequence=sentence,
                origin_type="DETERMINISTIC_RULE",
                confidence_score=0.88,
                source_kind="DOC",
                relative_path=relative_path,
                start_line=start_line,
                end_line=max(start_line, end_line),
                excerpt_text=sentence[:1000],
                subject_identifier=section_title.lower(),
                numeric_thresholds=_extract_numbers(sentence),
                evidence_role="DOC_CLAIM",
                rationale_note=f"Extracted from normative documentation statement in `{relative_path}`.",
            )
        )

    return candidates


__all__ = [
    "DOMAIN_CATALOG",
    "ExtractedBusinessRuleCandidate",
    "ExtractedRequirementCandidate",
    "extract_business_rules_from_code",
    "extract_business_rules_from_doc_section",
    "infer_domain_code",
]

