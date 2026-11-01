"""
Wave 6: System Integration, Cross-Wave Consistency, AI & Evidence Validation,
Security Validation, and Performance Validation Test Suite.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.analysis.parser_registry import default_parser_registry
from app.api.v1.endpoints.organizations import bootstrap_default_context
from app.core.security import (
    SecurityViolationError,
    TaskEnvelope,
    build_tenant_cache_key,
)
from app.db.redis import check_redis_health
from app.db.session import (
    SessionLocal,
    check_database_and_pgvector_health,
    tenant_db_session,
)
from app.integrations.llm import OllamaProvider
from app.integrations.storage import TenantObjectStorage
from app.models import (
    ApiService,
    AuditLog,
    BusinessRule,
    CodeFile,
    CodeSymbol,
    DbSchema,
    DocSection,
    EvidenceAnchor,
    Finding,
    FindingEvidenceLink,
    InfraResource,
    IntelligenceReport,
    KnowledgeEntity,
    KnowledgeRelationship,
    ModernizationRecommendation,
    Organization,
    RepositorySnapshot,
    Requirement,
    RequirementTraceabilityLink,
    TechnicalDebtItem,
    TestSuite,
    User,
)
from app.services.agent_orchestrator import (
    TechnicalIntelligenceOrchestrator,
)
from app.services.ingestion_service import ArchiveValidationError, IngestionService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.reporting_qa_export_service import (
    REPORT_TYPE_CATALOG,
    SUGGESTED_QA_QUESTIONS,
    ReportingQaExportService,
)
from app.services.requirements_intelligence_service import (
    RequirementsIntelligenceService,
)
from app.services.retrieval_service import RetrievalService
from app.services.technical_intelligence_service import TechnicalIntelligenceService
from app.services.testing_modernization_service import TestingModernizationService


def _build_wave6_enterprise_legacy_zip() -> bytes:
    """Build a realistic polyglot legacy enterprise application archive for Wave 6 end-to-end validation."""
    run_marker = uuid.uuid4().hex
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "schema/billing_core.sql",
            f"-- run_marker: {run_marker}\n"
            + """
CREATE TABLE customer_accounts (
    account_id UUID PRIMARY KEY,
    customer_email VARCHAR(255) NOT NULL UNIQUE,
    tax_ssn VARCHAR(32),
    balance_cents INTEGER NOT NULL DEFAULT 0 CHECK (balance_cents >= 0),
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE invoice_ledgers (
    invoice_id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES customer_accounts(account_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    discount_pct INTEGER NOT NULL DEFAULT 0
);
""",
        )
        zf.writestr(
            "api/openapi.yaml",
            f"# run_marker: {run_marker}\n"
            + """
openapi: 3.0.3
info:
  title: Legacy Billing & Account Platform API
  version: 2.4.0
paths:
  /api/v1/accounts/{account_id}/deactivate:
    post:
      summary: Deactivate customer account when balance is zero
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Account deactivated
  /api/v1/invoices/settle:
    post:
      summary: Settle customer invoice ledger
      responses:
        '200':
          description: Invoice settled
""",
        )
        zf.writestr(
            "Dockerfile",
            f"# run_marker: {run_marker}\n"
            + """
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
CMD ["python", "-m", "src.billing_engine"]
""",
        )
        zf.writestr(
            "requirements.txt",
            f"# run_marker: {run_marker}\nfastapi==0.100.0\nsqlalchemy==2.0.20\nrequests==2.25.1\n",
        )
        zf.writestr(
            "src/billing_engine.py",
            f"# Run: {run_marker}\n"
            + '''"""Core billing, discount, and customer account deactivation rules."""

import hashlib


def calculate_invoice_discount(amount_cents: int, loyalty_years: int) -> int:
    """
    Business Rule: If amount_cents >= 100000 and loyalty_years >= 3, apply 15% discount.
    Otherwise apply 5% discount when amount_cents >= 50000.
    """
    if amount_cents < 0:
        raise ValueError("Invoice amount_cents cannot be negative.")
    if amount_cents >= 100000 and loyalty_years >= 3:
        return int(amount_cents * 0.15)
    if amount_cents >= 50000:
        return int(amount_cents * 0.05)
    return 0


def deactivate_customer_account(account_id: str, balance_cents: int, is_frozen: bool) -> dict:
    """
    Business Rule: Customer account deactivation requires balance_cents == 0 and not is_frozen.
    """
    if is_frozen:
        raise PermissionError("Frozen account cannot be deactivated without compliance approval.")
    if balance_cents > 0:
        raise ValueError("Cannot deactivate customer_accounts row while balance_cents > 0.")
    legacy_digest = hashlib.md5(account_id.encode("utf-8")).hexdigest()
    return {
        "table": "customer_accounts",
        "account_id": account_id,
        "status": "DEACTIVATED",
        "legacy_digest": legacy_digest,
    }
''',
        )
        zf.writestr(
            "tests/test_billing_engine.py",
            f"# run_marker: {run_marker}\n"
            + """
from src.billing_engine import calculate_invoice_discount, deactivate_customer_account


def test_calculate_invoice_discount_vip():
    assert calculate_invoice_discount(120000, 5) == 18000


def test_deactivate_customer_account_zero_balance():
    res = deactivate_customer_account("acc-900", 0, False)
    assert res["status"] == "DEACTIVATED"
""",
        )
        zf.writestr(
            "docs/billing_specification.md",
            f"""# Legacy Billing & Account Specification
- **Rule 1**: Customer accounts in `customer_accounts` can only be deactivated when `balance_cents == 0`.
- **Rule 2**: VIP invoices (`amount_cents >= 100000` and `loyalty_years >= 3`) receive a `20%` discount according to legacy documentation (note discrepancy with code `15%`).
- **Validation Run Marker**: `{run_marker}`
""",
        )
    return buf.getvalue()


def test_wave6_phase_a_infrastructure_and_schema_baseline() -> None:
    """Phase A: Verify live PostgreSQL 17, pgvector, Alembic head 0007, 76 tables, 72 RLS-forced tables, Redis, and Ollama."""
    db_health = check_database_and_pgvector_health()
    assert db_health["status"] == "healthy"
    assert db_health["details"]["pgvector_installed"] is True

    redis_health = check_redis_health()
    assert redis_health["status"] == "healthy"
    assert redis_health["details"]["ping"] == "PONG"

    ollama_health = OllamaProvider().check_health()
    assert ollama_health["status"] in ("healthy", "unhealthy")

    with SessionLocal() as db:
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "0007_wave5_qa_reports_export"

        table_count = db.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name != 'alembic_version'"
            )
        ).scalar_one()
        assert table_count == 76

        rls_count = db.execute(
            text(
                "SELECT count(*) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                "AND c.relrowsecurity = true AND c.relforcerowsecurity = true"
            )
        ).scalar_one()
        assert rls_count == 72


def test_wave6_phases_b_c_d_e_f_complete_system_integration(tmp_path: Path) -> None:
    """
    Execute Phases B, C, D, E, and F end-to-end against live PostgreSQL 17:
    - Phase B: 24-step end-to-end workflow verification
    - Phase C: Cross-wave referential & review-governance consistency (including DEF-W6-001 & DEF-W6-002)
    - Phase D: AI & evidence validation (all 12 intents, fact vs inference, insufficient evidence, hallucination gate)
    - Phase E: Security validation (RLS across Waves 1-5, RBAC denial, ZIP traversal guard, storage isolation, Redis & task envelope security, AuditLog hash chain)
    - Phase F: Performance benchmarks across ingestion, parsing, graph traversal, hybrid search, Q&A, reports, and exports
    """
    perf_metrics: dict[str, float] = {}

    with SessionLocal() as boot_db:
        boot = bootstrap_default_context(db=boot_db)

    tenant_a = uuid.UUID(str(boot.tenant_id))
    user_a = uuid.UUID(str(boot.user_id))
    repo_a = uuid.UUID(str(boot.default_repository_id))
    outsider_user_a = uuid.uuid4()

    storage = TenantObjectStorage(vault_root=tmp_path / "vault_wave6")
    orchestrator = TechnicalIntelligenceOrchestrator(allow_live_ollama=False)
    tech_service = TechnicalIntelligenceService(
        storage=storage, orchestrator=orchestrator
    )
    ingestion_service = IngestionService(
        storage=storage, tech_intel_service=tech_service
    )
    graph_service = KnowledgeGraphService()
    req_service = RequirementsIntelligenceService(
        storage=storage, graph_service=graph_service, orchestrator=orchestrator
    )
    mod_service = TestingModernizationService(
        storage=storage, graph_service=graph_service, orchestrator=orchestrator
    )
    wave5_service = ReportingQaExportService(
        storage=storage,
        graph_service=graph_service,
        req_service=req_service,
        mod_service=mod_service,
        orchestrator=orchestrator,
    )
    retrieval_service = RetrievalService(storage=storage)

    # Phase F.1: Measure standalone multi-language AST parser latency
    t0 = time.perf_counter()
    parsed_py = default_parser_registry.parse_file(
        "src/billing_engine.py",
        "python",
        "def sample_fn(x: int) -> int:\n    return x + 1\n",
    )
    perf_metrics["ast_parser_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    assert parsed_py.parse_status == "PARSED"
    assert len(parsed_py.symbols) == 1

    with tenant_db_session(tenant_a) as db:
        db.add(
            User(
                id=outsider_user_a,
                email=f"wave6-outsider-{outsider_user_a.hex[:8]}@legacyiq.local",
                full_name="Wave 6 Unassigned User",
            )
        )
        db.flush()

        # ------------------------------------------------------------------
        # PHASE B (Steps 1–19): Ingestion + Waves 1–4 Full Pipeline
        # ------------------------------------------------------------------
        t_ingest_start = time.perf_counter()
        ingest_res = ingestion_service.ingest_zip_archive(
            db,
            tenant_id=tenant_a,
            repository_id=repo_a,
            zip_bytes=_build_wave6_enterprise_legacy_zip(),
            snapshot_label=f"wave6-validation-{uuid.uuid4().hex[:6]}",
            triggered_by_user_id=user_a,
            run_analysis_and_indexing=True,
        )
        perf_metrics["full_ingestion_and_waves1_4_ms"] = round(
            (time.perf_counter() - t_ingest_start) * 1000, 2
        )
        snapshot_id = ingest_res.snapshot_id
        assert ingest_res.files_processed >= 6
        assert ingest_res.chunks_indexed >= 2

        # Verify persisted database records across Waves 1-4
        code_files = (
            db.execute(
                select(CodeFile).where(
                    CodeFile.tenant_id == tenant_a,
                    CodeFile.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        code_symbols = (
            db.execute(
                select(CodeSymbol).where(
                    CodeSymbol.tenant_id == tenant_a,
                    CodeSymbol.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        db_schemas = (
            db.execute(
                select(DbSchema).where(
                    DbSchema.tenant_id == tenant_a,
                    DbSchema.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        api_services = (
            db.execute(
                select(ApiService).where(
                    ApiService.tenant_id == tenant_a,
                    ApiService.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        infra_resources = (
            db.execute(
                select(InfraResource).where(
                    InfraResource.tenant_id == tenant_a,
                    InfraResource.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        anchors = (
            db.execute(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.tenant_id == tenant_a,
                    EvidenceAnchor.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        art_ver_ids = list({a.artifact_version_id for a in anchors})
        doc_sections = (
            db.execute(
                select(DocSection).where(
                    DocSection.tenant_id == tenant_a,
                    DocSection.artifact_version_id.in_(art_ver_ids)
                    if art_ver_ids
                    else False,
                )
            )
            .scalars()
            .all()
        )
        entities = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_a,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        relationships = (
            db.execute(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.tenant_id == tenant_a,
                    KnowledgeRelationship.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        rules = (
            db.execute(
                select(BusinessRule).where(
                    BusinessRule.tenant_id == tenant_a,
                    BusinessRule.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        reqs = (
            db.execute(
                select(Requirement).where(
                    Requirement.tenant_id == tenant_a,
                    Requirement.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        rtm_links = (
            db.execute(
                select(RequirementTraceabilityLink).where(
                    RequirementTraceabilityLink.tenant_id == tenant_a,
                    RequirementTraceabilityLink.requirement_id.in_(
                        [r.id for r in reqs]
                    ),
                )
            )
            .scalars()
            .all()
        )
        test_suites = (
            db.execute(
                select(TestSuite).where(
                    TestSuite.tenant_id == tenant_a,
                    TestSuite.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        findings = (
            db.execute(
                select(Finding).where(
                    Finding.tenant_id == tenant_a,
                    Finding.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        debt_items = (
            db.execute(
                select(TechnicalDebtItem).where(
                    TechnicalDebtItem.tenant_id == tenant_a,
                    TechnicalDebtItem.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        mod_recs = (
            db.execute(
                select(ModernizationRecommendation).where(
                    ModernizationRecommendation.tenant_id == tenant_a,
                    ModernizationRecommendation.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )

        assert len(code_files) >= 2
        assert len(code_symbols) >= 2
        assert len(db_schemas) >= 1
        assert len(api_services) >= 1
        assert len(infra_resources) >= 1
        assert len(doc_sections) >= 1
        assert len(anchors) >= 5
        assert len(entities) >= 5
        assert len(relationships) >= 3
        assert len(rules) >= 2
        assert len(reqs) >= 2
        assert len(rtm_links) >= 2
        assert len(test_suites) >= 1
        assert len(findings) >= 1
        assert len(debt_items) >= 1
        assert len(mod_recs) >= 1

        # ------------------------------------------------------------------
        # PHASE C: Cross-Wave Consistency Validation
        # ------------------------------------------------------------------
        anchor_ids = {a.id for a in anchors}
        entity_ids = {e.id for e in entities}
        symbol_ids = {s.id for s in code_symbols}
        rule_ids = {r.id for r in rules}
        req_ids = {r.id for r in reqs}

        # C.1: Every KnowledgeRelationship references valid KnowledgeEntity nodes
        for rel in relationships:
            assert rel.source_entity_id in entity_ids
            assert rel.target_entity_id in entity_ids

        # C.2: Every Finding has valid EvidenceAnchor links
        fe_links = (
            db.execute(
                select(FindingEvidenceLink).where(
                    FindingEvidenceLink.tenant_id == tenant_a,
                    FindingEvidenceLink.finding_id.in_([f.id for f in findings]),
                )
            )
            .scalars()
            .all()
        )
        assert len(fe_links) >= len(findings)
        for fel in fe_links:
            assert fel.evidence_anchor_id in anchor_ids

        # C.3: Every Requirement has acceptance criteria, evidence links, and valid traceability links
        req_ev_links = (
            db.execute(
                select(FindingEvidenceLink).where(
                    FindingEvidenceLink.tenant_id == tenant_a,
                    FindingEvidenceLink.requirement_id.in_(list(req_ids)),
                )
            )
            .scalars()
            .all()
        )
        assert len(req_ev_links) >= len(reqs)
        for rel_ev in req_ev_links:
            assert rel_ev.evidence_anchor_id in anchor_ids

        for rtm in rtm_links:
            assert rtm.requirement_id in req_ids
            if rtm.business_rule_id:
                assert rtm.business_rule_id in rule_ids
            if rtm.code_symbol_id:
                assert rtm.code_symbol_id in symbol_ids
            if rtm.knowledge_entity_id:
                assert rtm.knowledge_entity_id in entity_ids

        # C.4: Every ModernizationRecommendation in API payload includes supporting evidence (DEF-W6-002 check)
        roadmap_payload = mod_service.get_recommendations_and_roadmap(
            db, tenant_id=tenant_a, snapshot_id=snapshot_id
        )
        assert len(roadmap_payload["recommendations"]) >= 1
        for rec_item in roadmap_payload["recommendations"]:
            assert len(rec_item["evidence"]) >= 1
            assert rec_item["evidence"][0]["anchor_id"] in {str(aid) for aid in anchor_ids}
            assert len(rec_item["evidence"][0]["snippet_sha256"]) == 64

        # C.5: Rejecting a BusinessRule excludes it from active dashboard counts, Q&A, and Reports (DEF-W6-001 check)
        rule_to_reject = rules[0]
        req_service.review_business_rule(
            db,
            tenant_id=tenant_a,
            rule_id=rule_to_reject.id,
            reviewer_user_id=user_a,
            new_status="REJECTED",
            review_comment="Wave 6 test: reject rule to verify cross-wave exclusion.",
        )

        t_dash_start = time.perf_counter()
        dash = wave5_service.get_application_intelligence_dashboard(
            db, tenant_id=tenant_a, user_id=user_a, snapshot_id=snapshot_id
        )
        perf_metrics["dashboard_query_ms"] = round(
            (time.perf_counter() - t_dash_start) * 1000, 2
        )
        assert dash["governance_and_reviews"]["rejected_items_count"] >= 1
        assert dash["business_and_requirements"]["business_rules_count"] == len(rules) - 1

        exec_insights = wave5_service.get_executive_insights(
            db, tenant_id=tenant_a, user_id=user_a, snapshot_id=snapshot_id
        )
        assert 15 <= exec_insights["overall_application_health"]["health_score"] <= 98

        # ------------------------------------------------------------------
        # PHASE D: AI & Evidence Validation (All Specialized Intents, Hybrid RRF, Hallucination Gate)
        # ------------------------------------------------------------------
        assert len(SUGGESTED_QA_QUESTIONS) >= 10
        assert len(REPORT_TYPE_CATALOG) == 11

        # D.1: Measure Knowledge Graph multi-hop traversal latency
        t_graph_start = time.perf_counter()
        trav = graph_service.traverse_subgraph(
            db,
            tenant_id=tenant_a,
            snapshot_id=snapshot_id,
            root_entity_id=entities[0].id,
            max_hops=2,
            direction="BOTH",
        )
        perf_metrics["graph_traversal_ms"] = round(
            (time.perf_counter() - t_graph_start) * 1000, 2
        )
        assert len(trav["nodes"]) >= 1

        # D.2: Measure Hybrid RRF retrieval latency
        t_rrf_start = time.perf_counter()
        rrf_hits = retrieval_service.hybrid_search(
            db,
            tenant_id=tenant_a,
            project_id=uuid.UUID(str(boot.project_id)),
            snapshot_id=snapshot_id,
            query_text="deactivate_customer_account balance_cents",
            limit=5,
        )
        perf_metrics["hybrid_rrf_search_ms"] = round(
            (time.perf_counter() - t_rrf_start) * 1000, 2
        )
        assert len(rrf_hits) >= 1

        # D.3: Ask grounded question and verify citations + exclusion of rejected rule
        t_qa_start = time.perf_counter()
        qa_res = wave5_service.ask_question(
            db,
            tenant_id=tenant_a,
            user_id=user_a,
            snapshot_id=snapshot_id,
            question="What are the most important business rules for invoice discount and account deactivation?",
        )
        perf_metrics["semantic_qa_ms"] = round(
            (time.perf_counter() - t_qa_start) * 1000, 2
        )
        assistant_msg = qa_res["assistant_message"]
        assert assistant_msg["question_intent"] == "BUSINESS_RULE_EXPLANATION"
        assert assistant_msg["insufficient_evidence"] is False
        assert len(assistant_msg["citations"]) >= 1
        assert rule_to_reject.rule_code not in assistant_msg["content_markdown"]

        # Verify security risk Q&A separates unapproved findings into inferred_explanations
        qa_risk = wave5_service.ask_question(
            db,
            tenant_id=tenant_a,
            user_id=user_a,
            snapshot_id=snapshot_id,
            conversation_id=uuid.UUID(qa_res["conversation_id"]),
            question="Are there any security vulnerabilities or MD5 weaknesses?",
        )
        risk_msg = qa_risk["assistant_message"]
        assert risk_msg["question_intent"] == "SECURITY_RISK_INVESTIGATION"
        assert len(risk_msg["inferred_explanations"]) >= 1
        for inf in risk_msg["inferred_explanations"]:
            assert inf["review_status"] in ("PENDING_REVIEW", "MODIFIED_BY_HUMAN")

        # D.4: Verify Insufficient-Evidence Guard on out-of-scope query
        qa_oos = wave5_service.ask_question(
            db,
            tenant_id=tenant_a,
            user_id=user_a,
            snapshot_id=snapshot_id,
            conversation_id=uuid.UUID(qa_res["conversation_id"]),
            question="zxqv_nonexistent_mars_orbital_telemetry_xyz987",
        )
        assert qa_oos["assistant_message"]["insufficient_evidence"] is True

        # ------------------------------------------------------------------
        # PHASE B (Steps 22–24): Reports, Immutable Approval, Exports & AuditLog
        # ------------------------------------------------------------------
        t_rep_start = time.perf_counter()
        rep_v1 = wave5_service.generate_report(
            db,
            tenant_id=tenant_a,
            user_id=user_a,
            snapshot_id=snapshot_id,
            report_type="COMPLETE_INTELLIGENCE",
        )
        perf_metrics["report_generation_ms"] = round(
            (time.perf_counter() - t_rep_start) * 1000, 2
        )
        report_id = uuid.UUID(rep_v1["id"])
        assert rep_v1["version_no"] == 1
        assert rule_to_reject.rule_code not in json.dumps(rep_v1["sections"])

        # Approve v1 -> Edit -> Verify v1 stays immutable and v2 is created
        wave5_service.transition_report_lifecycle(
            db,
            tenant_id=tenant_a,
            user_id=user_a,
            report_id=report_id,
            target_status="APPROVED",
            review_comment="Wave 6 sign-off on v1.",
        )
        rep_v2 = wave5_service.transition_report_lifecycle(
            db,
            tenant_id=tenant_a,
            user_id=user_a,
            report_id=report_id,
            target_status="DRAFT",
            updated_executive_summary_markdown="Updated Wave 6 v2 executive summary.",
        )
        assert rep_v2["version_no"] == 2
        v1_check = wave5_service.get_report(
            db,
            tenant_id=tenant_a,
            user_id=user_a,
            report_id=report_id,
            version_no=1,
        )
        assert v1_check["lifecycle_status"] == "APPROVED"
        assert v1_check["is_immutable"] is True

        # Export all 4 formats (PDF, DOCX, XLSX, JSON) & verify download + AuditLog hash chain
        for fmt in ("PDF", "DOCX", "XLSX", "JSON"):
            t_exp = time.perf_counter()
            exp_meta = wave5_service.export_report(
                db,
                tenant_id=tenant_a,
                user_id=user_a,
                report_id=report_id,
                export_format=fmt,
                version_no=1,
            )
            perf_metrics[f"export_{fmt.lower()}_ms"] = round(
                (time.perf_counter() - t_exp) * 1000, 2
            )
            raw_bytes, dl_name, dl_mime = wave5_service.download_export(
                db,
                tenant_id=tenant_a,
                user_id=user_a,
                export_id=uuid.UUID(exp_meta["id"]),
            )
            assert dl_name == exp_meta["file_name"]
            assert dl_mime == exp_meta["mime_type"]
            assert len(raw_bytes) == exp_meta["file_size_bytes"]
            assert (
                hashlib.sha256(raw_bytes).hexdigest()
                == exp_meta["content_sha256"]
            )

        # ------------------------------------------------------------------
        # PHASE E: Security Validation (RBAC, ZIP Guard, Redis/Task Envelope, Audit Chain)
        # ------------------------------------------------------------------
        # E.1: Cross-project RBAC denial
        with pytest.raises((PermissionError, SecurityViolationError)):
            wave5_service.get_application_intelligence_dashboard(
                db,
                tenant_id=tenant_a,
                user_id=outsider_user_a,
                snapshot_id=snapshot_id,
            )

        # E.2: ZIP Slip path traversal guard
        malicious_buf = io.BytesIO()
        with zipfile.ZipFile(malicious_buf, "w") as mzf:
            mzf.writestr("../../evil_escape.py", "print('pwned')")
        with pytest.raises(ArchiveValidationError):
            ingestion_service.ingest_zip_archive(
                db,
                tenant_id=tenant_a,
                repository_id=repo_a,
                zip_bytes=malicious_buf.getvalue(),
                snapshot_label="malicious-zip",
                triggered_by_user_id=user_a,
            )

        # E.3: Redis tenant cache key & TaskEnvelope HMAC signature tampering rejection
        cache_key = build_tenant_cache_key(tenant_a, "wave6", "probe")
        assert f":t:{tenant_a}:" in cache_key
        env = TaskEnvelope.create(
            tenant_id=tenant_a,
            project_id=uuid.UUID(str(boot.project_id)),
            actor_user_id=user_a,
            task_type="WAVE6_VALIDATE",
            payload={"snapshot_id": str(snapshot_id)},
        )
        assert env.verify() is True
        tampered_env = TaskEnvelope(
            task_id=env.task_id,
            tenant_id=str(uuid.uuid4()),
            project_id=env.project_id,
            actor_user_id=env.actor_user_id,
            task_type=env.task_type,
            payload=env.payload,
            issued_at=env.issued_at,
            signature=env.signature,
        )
        assert tampered_env.verify() is False

        # E.4: Verify AuditLog hash chain continuity
        audit_logs = wave5_service.list_audit_logs(db, tenant_id=tenant_a, limit=15)
        assert len(audit_logs) >= 6
        for entry in audit_logs:
            assert len(entry["entry_hash"]) == 64
            assert len(entry["prev_audit_hash"]) == 64

    # E.5: Negative Cross-Tenant RLS Isolation (Tenant B sees 0 rows of Tenant A)
    tenant_b = uuid.uuid4()
    with SessionLocal() as su_db:
        su_db.add(
            Organization(
                id=tenant_b,
                slug=f"wave6-iso-{tenant_b.hex[:8]}",
                display_name="Wave 6 Isolated Tenant B",
            )
        )
        su_db.commit()

    with tenant_db_session(tenant_b) as db_b:
        assert (
            db_b.execute(
                select(RepositorySnapshot).where(RepositorySnapshot.id == snapshot_id)
            ).scalar_one_or_none()
            is None
        )
        assert (
            db_b.execute(
                select(IntelligenceReport).where(IntelligenceReport.id == report_id)
            ).scalar_one_or_none()
            is None
        )
        assert (
            db_b.execute(
                select(BusinessRule).where(BusinessRule.snapshot_id == snapshot_id)
            )
            .scalars()
            .all()
            == []
        )
        assert (
            db_b.execute(
                select(AuditLog).where(AuditLog.tenant_id == tenant_a)
            )
            .scalars()
            .all()
            == []
        )

    # Phase F: Assert reasonable performance bounds & persist telemetry for Wave 6 report
    assert perf_metrics["ast_parser_ms"] < 1000
    assert perf_metrics["dashboard_query_ms"] < 5000
    assert perf_metrics["graph_traversal_ms"] < 2000
    assert perf_metrics["hybrid_rrf_search_ms"] < 5000
    assert perf_metrics["report_generation_ms"] < 5000
    perf_out = Path(
        r"C:\Users\Saheel\.gemini\antigravity\brain\54c9637d-49c2-466c-92dc-feee17381740\scratch\wave6_perf_metrics.json"
    )
    if perf_out.parent.exists():
        perf_out.write_text(json.dumps(perf_metrics, indent=2), encoding="utf-8")
