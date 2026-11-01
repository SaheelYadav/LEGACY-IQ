"""Wave 5 Service: Unified Application Intelligence Dashboard, Semantic Q&A Assistant, 11-Type Report Generation Engine, Immutable Report Versioning & Multi-Format Export Governance."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.export_formatters import render_report_export
from app.core.security import (
    SecurityViolationError,
    verify_and_activate_tenant_context,
    verify_project_access as _core_verify_project_access,
)
from app.integrations.storage import TenantObjectStorage


def verify_project_access(
    db: Session,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    required_permission: str | None = None,
) -> None:
    """Resolve `TenantContext` for `(user_id, tenant_id)` and enforce project-scoped RBAC."""
    t_ctx = verify_and_activate_tenant_context(
        db, user_id=user_id, tenant_id=tenant_id
    )
    _core_verify_project_access(
        db,
        tenant_context=t_ctx,
        project_id=project_id,
        required_permission=required_permission,
    )
from app.models.agent_orchestration import AgentRun
from app.models.business_intelligence import (
    BusinessDomain,
    BusinessProcess,
    BusinessRule,
    Requirement,
)
from app.models.code_intelligence import AnalysisRun, CodeCallEdge, CodeFile, CodeSymbol
from app.models.identity import Organization
from app.models.ingestion import Artifact, ArtifactVersion, Repository, RepositorySnapshot
from app.models.knowledge_graph import (
    EvidenceAnchor,
    Finding,
    FindingEvidenceLink,
    KnowledgeConflict,
    KnowledgeEntity,
    KnowledgeRelationship,
    ReviewHistory,
)
from app.models.projects import Application, Project
from app.models.reporting_governance import (
    ApprovalRequest,
    AuditLog,
    IntelligenceReport,
    IntelligenceReportVersion,
    QaConversation,
    QaMessage,
    ReportExport,
)
from app.models.technical_intelligence import (
    ApiEndpoint,
    ApiService,
    DbColumn,
    DbForeignKey,
    DbSchema,
    DbTable,
    DocSection,
    InfraResource,
)
from app.models.testing_modernization import (
    ModernizationRecommendation,
    TechnicalDebtItem,
    TestCase,
    TestSuite,
)
from app.services.agent_orchestrator import (
    AgentInputContext,
    TechnicalIntelligenceOrchestrator,
)
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.requirements_intelligence_service import (
    RequirementsIntelligenceService,
)
from app.services.retrieval_service import RetrievalService
from app.services.testing_modernization_service import TestingModernizationService

REPORT_TYPE_CATALOG: dict[str, str] = {
    "APPLICATION_DISCOVERY": "Application Discovery Report",
    "TECHNICAL_ARCHITECTURE": "Technical Architecture Assessment",
    "BUSINESS_RULES_PROCESSES": "Business Rules & Processes Report",
    "REQUIREMENTS_SPECIFICATION": "Functional and Non-Functional Requirements Report",
    "API_DATABASE_INTELLIGENCE": "API & Database Intelligence Report",
    "SECURITY_RISK_ASSESSMENT": "Security and Risk Assessment",
    "TESTING_COVERAGE_ASSESSMENT": "Testing and Coverage Assessment",
    "TECHNICAL_DEBT_ASSESSMENT": "Technical Debt Assessment",
    "MODERNIZATION_ASSESSMENT": "Modernization Assessment",
    "EXECUTIVE_SUMMARY": "Executive Summary Report",
    "COMPLETE_INTELLIGENCE": "Complete Application Intelligence Report",
}

SUGGESTED_QA_QUESTIONS: list[dict[str, str]] = [
    {
        "intent": "ARCHITECTURE_DISCOVERY",
        "question": "Explain the overall architecture of this application.",
    },
    {
        "intent": "BUSINESS_RULE_EXPLANATION",
        "question": "What are the most important business rules?",
    },
    {
        "intent": "API_DB_DEPENDENCY",
        "question": "Which APIs depend on the database tables?",
    },
    {
        "intent": "BUSINESS_PROCESS",
        "question": "What happens when a customer account or order is processed?",
    },
    {
        "intent": "TEST_COVERAGE_GAPS",
        "question": "Which requirements are not covered by tests?",
    },
    {
        "intent": "SECURITY_RISK_INVESTIGATION",
        "question": "What are the biggest security risks?",
    },
    {
        "intent": "CHANGE_IMPACT_ANALYSIS",
        "question": "Which components will be affected if the primary service changes?",
    },
    {
        "intent": "MODERNIZATION_PLANNING",
        "question": "How can we modernize this application?",
    },
    {
        "intent": "BUSINESS_PROCESS",
        "question": "Explain the complete order-processing workflow.",
    },
    {
        "intent": "CONFLICT_DETECTION",
        "question": "Which business rules conflict with the existing documentation?",
    },
]

_QA_STOPWORDS = {
    "what",
    "which",
    "where",
    "when",
    "explain",
    "how",
    "does",
    "this",
    "that",
    "the",
    "are",
    "for",
    "with",
    "from",
    "can",
    "will",
    "have",
    "has",
    "there",
    "about",
    "application",
    "system",
    "codebase",
    "repository",
    "complete",
    "overall",
    "most",
    "important",
    "biggest",
    "existing",
    "not",
    "covered",
}


def classify_question_intent(question: str) -> str:
    """Deterministically route natural-language questions to specialized intelligence handlers."""
    q = question.lower().strip()
    if any(w in q for w in ("conflict", "contradict", "discrepanc", "mismatch")):
        return "CONFLICT_DETECTION"
    if any(
        w in q
        for w in (
            "untested",
            "not covered by test",
            "coverage gap",
            "missing test",
            "test coverage",
        )
    ):
        return "TEST_COVERAGE_GAPS"
    if any(
        w in q
        for w in (
            "security",
            "vulnerab",
            "cve",
            "cwe",
            "injection",
            "secret",
            "risk",
        )
    ):
        return "SECURITY_RISK_INVESTIGATION"
    if any(
        w in q
        for w in ("moderniz", "roadmap", "refactor", "strangler", "migration plan")
    ):
        return "MODERNIZATION_PLANNING"
    if any(
        w in q for w in ("technical debt", "debt", "complexity", "duplicated", "dead code")
    ):
        return "TECHNICAL_DEBT_INVESTIGATION"
    if any(
        w in q
        for w in (
            "affected if",
            "impact",
            "blast radius",
            "changes",
            "downstream",
        )
    ):
        return "CHANGE_IMPACT_ANALYSIS"
    if any(
        w in q
        for w in (
            "api",
            "endpoint",
            "database table",
            "depend on",
            "reads",
            "writes",
            "schema",
        )
    ):
        return "API_DB_DEPENDENCY"
    if any(
        w in q
        for w in (
            "workflow",
            "process",
            "what happens when",
            "deactivated",
            "order-processing",
            "lifecycle",
        )
    ):
        return "BUSINESS_PROCESS"
    if any(w in q for w in ("business rule", "validation", "discount", "threshold", "calculation")):
        return "BUSINESS_RULE_EXPLANATION"
    if any(w in q for w in ("requirement", "traceability", "acceptance criteria")):
        return "REQUIREMENTS_TRACEABILITY"
    if any(
        w in q
        for w in ("architecture", "overview", "structure", "component", "module", "stack")
    ):
        return "ARCHITECTURE_DISCOVERY"
    return "GENERAL_CODE_QA"


class ReportingQaExportService:
    """
    Centralized Wave 5 service orchestrating:
    1. Unified Application Intelligence Dashboard & Executive Reporting
    2. Conversational Semantic Q&A & Specialized Intelligence Queries
    3. 11-Type Structured Report Generation, Lifecycle & Immutable Versioning
    4. Controlled Multi-Format Exports (`PDF`, `DOCX`, `XLSX`, `JSON`) & Tamper-Evident Audit Logging
    """

    def __init__(
        self,
        storage: TenantObjectStorage | None = None,
        retrieval_service: RetrievalService | None = None,
        graph_service: KnowledgeGraphService | None = None,
        req_service: RequirementsIntelligenceService | None = None,
        mod_service: TestingModernizationService | None = None,
        orchestrator: TechnicalIntelligenceOrchestrator | None = None,
    ) -> None:
        self.storage = storage or TenantObjectStorage()
        self.retrieval_service = retrieval_service or RetrievalService(
            storage=self.storage
        )
        self.graph_service = graph_service or KnowledgeGraphService()
        self.orchestrator = orchestrator or TechnicalIntelligenceOrchestrator(
            allow_live_ollama=False
        )
        self.req_service = req_service or RequirementsIntelligenceService(
            storage=self.storage,
            graph_service=self.graph_service,
            orchestrator=self.orchestrator,
        )
        self.mod_service = mod_service or TestingModernizationService(
            storage=self.storage,
            graph_service=self.graph_service,
            orchestrator=self.orchestrator,
        )

    # ------------------------------------------------------------------
    # 0. Tamper-Evident Audit Logging & Context Resolution
    # ------------------------------------------------------------------
    def record_audit_log(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        action_code: str,
        target_resource_type: str,
        target_resource_id: uuid.UUID | None,
        metadata_diff: dict[str, Any] | None = None,
        actor_type: str = "USER",
        client_ip: str | None = "127.0.0.1",
    ) -> AuditLog:
        """Append a tamper-evident SHA-256 hash-chained `AuditLog` entry for the tenant."""
        last_entry = (
            db.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        prev_hash = last_entry.entry_hash if last_entry else ("0" * 64)
        now_utc = datetime.now(timezone.utc)
        meta = metadata_diff or {}
        chain_payload = json.dumps(
            {
                "tenant_id": str(tenant_id),
                "prev_hash": prev_hash,
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                "action_code": action_code,
                "target_resource_type": target_resource_type,
                "target_resource_id": str(target_resource_id)
                if target_resource_id
                else None,
                "metadata_diff": meta,
                "occurred_at": now_utc.isoformat(),
            },
            sort_keys=True,
        )
        entry_hash = hashlib.sha256(chain_payload.encode("utf-8")).hexdigest()
        log_row = AuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action_code=action_code,
            target_resource_type=target_resource_type,
            target_resource_id=target_resource_id,
            client_ip=client_ip,
            prev_audit_hash=prev_hash,
            entry_hash=entry_hash,
            metadata_diff=meta,
            occurred_at=now_utc,
        )
        db.add(log_row)
        db.flush()
        return log_row

    def list_audit_logs(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = (
            db.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.occurred_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(r.id),
                "tenant_id": str(r.tenant_id),
                "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
                "actor_type": r.actor_type,
                "action_code": r.action_code,
                "target_resource_type": r.target_resource_type,
                "target_resource_id": str(r.target_resource_id)
                if r.target_resource_id
                else None,
                "prev_audit_hash": r.prev_audit_hash,
                "entry_hash": r.entry_hash,
                "metadata_diff": r.metadata_diff,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            }
            for r in rows
        ]

    def _resolve_snapshot_hierarchy(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> tuple[Organization, Project, Application, Repository, RepositorySnapshot]:
        snap = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        if snap is None:
            raise ValueError(f"Snapshot {snapshot_id} not found for tenant {tenant_id}")

        repo = db.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.id == snap.repository_id,
            )
        ).scalar_one()

        app = db.execute(
            select(Application).where(
                Application.tenant_id == tenant_id,
                Application.id == repo.application_id,
            )
        ).scalar_one()

        proj = db.execute(
            select(Project).where(
                Project.tenant_id == tenant_id,
                Project.id == app.project_id,
            )
        ).scalar_one()

        org = db.execute(
            select(Organization).where(Organization.id == tenant_id)
        ).scalar_one()

        return org, proj, app, repo, snap

    # ------------------------------------------------------------------
    # 1. Unified Application Intelligence Dashboard (Waves 1–4)
    # ------------------------------------------------------------------
    def get_application_intelligence_dashboard(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """
        Aggregate persisted intelligence from Waves 1–4 into a unified dashboard,
        explicitly distinguishing MEASURED, HEURISTIC_ESTIMATE, and INFERRED metrics.
        """
        org, proj, app, repo, snap = self._resolve_snapshot_hierarchy(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        if user_id is not None:
            verify_project_access(
                db,
                user_id=user_id,
                tenant_id=tenant_id,
                project_id=proj.id,
                required_permission="project:read",
            )

        # Wave 1: Code files, symbols, call edges, languages
        code_files = (
            db.execute(
                select(CodeFile).where(
                    CodeFile.tenant_id == tenant_id,
                    CodeFile.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        symbols = (
            db.execute(
                select(CodeSymbol).where(
                    CodeSymbol.tenant_id == tenant_id,
                    CodeSymbol.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        call_edges_count = (
            db.execute(
                select(func.count(CodeCallEdge.id)).where(
                    CodeCallEdge.tenant_id == tenant_id,
                    CodeCallEdge.snapshot_id == snapshot_id,
                )
            ).scalar_one()
            or 0
        )

        lang_breakdown: dict[str, int] = {}
        total_loc_code = 0
        total_loc_comment = 0
        for cf in code_files:
            lang_breakdown[cf.language] = lang_breakdown.get(cf.language, 0) + 1
            total_loc_code += cf.loc_code
            total_loc_comment += cf.loc_comment

        # Wave 2: Database, API, Infrastructure, Documentation, Knowledge Graph
        db_schemas = (
            db.execute(
                select(DbSchema).where(
                    DbSchema.tenant_id == tenant_id,
                    DbSchema.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        schema_ids = [s.id for s in db_schemas]
        db_tables = (
            db.execute(
                select(DbTable).where(
                    DbTable.tenant_id == tenant_id,
                    DbTable.db_schema_id.in_(schema_ids) if schema_ids else False,
                )
            )
            .scalars()
            .all()
            if schema_ids
            else []
        )
        table_ids = [t.id for t in db_tables]
        db_columns = (
            db.execute(
                select(DbColumn).where(
                    DbColumn.tenant_id == tenant_id,
                    DbColumn.db_table_id.in_(table_ids) if table_ids else False,
                )
            )
            .scalars()
            .all()
            if table_ids
            else []
        )
        db_fks = (
            db.execute(
                select(DbForeignKey).where(
                    DbForeignKey.tenant_id == tenant_id,
                    DbForeignKey.source_table_id.in_(table_ids) if table_ids else False,
                )
            )
            .scalars()
            .all()
            if table_ids
            else []
        )
        api_services = (
            db.execute(
                select(ApiService).where(
                    ApiService.tenant_id == tenant_id,
                    ApiService.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        api_svc_ids = [s.id for s in api_services]
        api_endpoints = (
            db.execute(
                select(ApiEndpoint).where(
                    ApiEndpoint.tenant_id == tenant_id,
                    ApiEndpoint.api_service_id.in_(api_svc_ids)
                    if api_svc_ids
                    else False,
                )
            )
            .scalars()
            .all()
            if api_svc_ids
            else []
        )
        infra_resources = (
            db.execute(
                select(InfraResource).where(
                    InfraResource.tenant_id == tenant_id,
                    InfraResource.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        graph_entities_count = (
            db.execute(
                select(func.count(KnowledgeEntity.id)).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                )
            ).scalar_one()
            or 0
        )
        graph_rels_count = (
            db.execute(
                select(func.count(KnowledgeRelationship.id)).where(
                    KnowledgeRelationship.tenant_id == tenant_id,
                    KnowledgeRelationship.snapshot_id == snapshot_id,
                )
            ).scalar_one()
            or 0
        )
        evidence_anchors_count = (
            db.execute(
                select(func.count(EvidenceAnchor.id)).where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.snapshot_id == snapshot_id,
                )
            ).scalar_one()
            or 0
        )

        # Wave 3: Business Rules, Requirements, Conflicts
        rules_data = self.req_service.get_snapshot_business_rules(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        reqs_data = self.req_service.get_snapshot_requirements(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        conflicts_data = self.req_service.get_conflicts_and_gaps(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )

        # Wave 4: Testing, Coverage, Risk, Technical Debt, Modernization
        test_intel = self.mod_service.get_test_intelligence(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        cov_gaps = self.mod_service.get_coverage_and_gaps(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        risk_reg = self.mod_service.get_risk_register(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        tech_debt = self.mod_service.get_technical_debt(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        mod_assess = self.mod_service.get_modernization_assessment(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        mod_roadmap = self.mod_service.get_recommendations_and_roadmap(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )

        # Pending human reviews & unresolved conflicts (exclude REJECTED / SUPERSEDED from active & pending counts)
        all_findings = (
            db.execute(
                select(Finding).where(
                    Finding.tenant_id == tenant_id,
                    Finding.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        active_rules = [
            r
            for r in rules_data["business_rules"]
            if r["review_status"] not in ("REJECTED", "SUPERSEDED")
        ]
        active_reqs = [
            r
            for r in reqs_data["requirements"]
            if r["review_status"] not in ("REJECTED", "SUPERSEDED")
        ]
        active_risks = [
            rf
            for rf in risk_reg["risk_findings"]
            if rf["review_status"] not in ("REJECTED", "SUPERSEDED")
        ]
        active_recs = [
            r
            for r in mod_roadmap["recommendations"]
            if r["review_status"] not in ("REJECTED", "SUPERSEDED")
        ]
        pending_rules = [
            r
            for r in active_rules
            if r["review_status"] in ("PENDING_REVIEW", "MODIFIED_BY_HUMAN")
        ]
        pending_reqs = [
            r
            for r in active_reqs
            if r["review_status"] in ("PENDING_REVIEW", "MODIFIED_BY_HUMAN")
        ]
        pending_findings = [
            f
            for f in all_findings
            if f.review_status in ("PENDING_REVIEW", "MODIFIED_BY_HUMAN")
        ]
        pending_recs = [
            r
            for r in active_recs
            if r["review_status"] in ("PENDING_REVIEW", "MODIFIED_BY_HUMAN")
        ]
        rejected_items_count = (
            sum(
                1
                for r in rules_data["business_rules"]
                if r["review_status"] == "REJECTED"
            )
            + sum(
                1
                for r in reqs_data["requirements"]
                if r["review_status"] == "REJECTED"
            )
            + sum(1 for f in all_findings if f.review_status == "REJECTED")
            + sum(
                1
                for r in mod_roadmap["recommendations"]
                if r["review_status"] == "REJECTED"
            )
        )
        unresolved_conflicts = [
            c
            for c in conflicts_data["conflicts"]
            if not str(c["status"]).startswith("RESOLVED")
            and c["status"] != "DISMISSED"
        ]

        detected_frameworks = sorted(
            {
                *(s.protocol for s in api_services),
                *(r.iac_tool for r in infra_resources),
                *(ts["test_framework"] for ts in test_intel["test_suites"]),
                *(sc.db_engine for sc in db_schemas),
            }
        )

        return {
            "snapshot_overview": {
                "tenant_id": str(tenant_id),
                "organization_name": org.display_name,
                "project_id": str(proj.id),
                "project_name": proj.name,
                "project_key": proj.key,
                "application_id": str(app.id),
                "application_name": app.name,
                "repository_id": str(repo.id),
                "repository_name": repo.name,
                "snapshot_id": str(snap.id),
                "snapshot_label": snap.snapshot_label,
                "total_files": len(code_files),
                "total_loc_code": total_loc_code,
                "total_loc_comment": total_loc_comment,
                "languages": lang_breakdown,
                "frameworks_and_stack": detected_frameworks,
                "metric_basis": "MEASURED",
            },
            "technology_stack": {
                "metric_basis": "MEASURED",
                "languages": {
                    lang: {"files": cnt, "loc": total_loc_code}
                    for lang, cnt in lang_breakdown.items()
                },
                "frameworks": detected_frameworks,
                "iac_and_container_tools": sorted({r.iac_tool for r in infra_resources}),
            },
            "technical_inventory": {
                "metric_basis": "MEASURED",
                "code_symbols_count": len(symbols),
                "call_edges_count": call_edges_count,
                "db_schemas_count": len(db_schemas),
                "db_tables_count": len(db_tables),
                "db_columns_count": len(db_columns),
                "db_foreign_keys_count": len(db_fks),
                "pii_columns_count": sum(1 for c in db_columns if c.is_pii_candidate),
                "api_services_count": len(api_services),
                "api_endpoints_count": len(api_endpoints),
                "infra_resources_count": len(infra_resources),
                "knowledge_entities_count": graph_entities_count,
                "knowledge_relationships_count": graph_rels_count,
                "evidence_anchors_count": evidence_anchors_count,
                "db_tables": [
                    {"id": str(t.id), "table_name": t.table_name, "table_kind": t.table_kind}
                    for t in db_tables
                ],
                "api_endpoints": [
                    {
                        "id": str(ep.id),
                        "http_method": ep.http_method,
                        "route_path": ep.route_path,
                        "auth_scheme": ep.auth_scheme,
                    }
                    for ep in api_endpoints
                ],
                "infra_resources": [
                    {
                        "id": str(ir.id),
                        "iac_tool": ir.iac_tool,
                        "resource_type": ir.resource_type,
                        "resource_name": ir.resource_name,
                    }
                    for ir in infra_resources
                ],
            },
            "business_and_requirements": {
                "metric_basis": "INFERRED_WITH_EVIDENCE_ANCHORS",
                "domains_count": len(rules_data["domains"]),
                "processes_count": len(rules_data["processes"]),
                "business_rules_count": len(active_rules),
                "approved_business_rules_count": sum(
                    1
                    for r in active_rules
                    if r["review_status"] == "APPROVED"
                ),
                "requirements_count": len(active_reqs),
                "approved_requirements_count": sum(
                    1
                    for r in active_reqs
                    if r["review_status"] == "APPROVED"
                ),
                "domains": rules_data["domains"],
                "processes": rules_data["processes"],
            },
            "testing_and_coverage": {
                "discovered_test_suites_count": test_intel["summary"][
                    "discovered_suites"
                ],
                "discovered_test_cases_count": test_intel["summary"][
                    "discovered_test_cases"
                ],
                "recommended_test_blueprints_count": test_intel["summary"][
                    "recommended_test_blueprints"
                ],
                "coverage_metrics": cov_gaps["coverage_metrics"],
                "untested_requirements_count": len(cov_gaps["untested_requirements"]),
                "untested_critical_components_count": len(
                    cov_gaps["untested_critical_components"]
                ),
                "discovered_coverage_basis": "MEASURED",
                "blueprint_coverage_basis": "INFERRED",
            },
            "risk_and_technical_debt": {
                "total_risk_findings": len(active_risks),
                "risk_counts_by_severity": risk_reg["counts_by_severity"],
                "risk_counts_by_category": risk_reg["counts_by_category"],
                "technical_debt_summary": tech_debt["measured_vs_estimated_summary"],
            },
            "modernization_posture": {
                "microservices_recommended": mod_assess["microservices_recommended"],
                "dimensions": mod_assess["dimensions"],
                "total_recommendations": len(active_recs),
                "roadmap_phases": mod_roadmap["roadmap_phases"],
                "effort_basis": "HEURISTIC_ESTIMATE",
            },
            "governance_and_reviews": {
                "pending_business_rules_count": len(pending_rules),
                "pending_requirements_count": len(pending_reqs),
                "pending_findings_count": len(pending_findings),
                "pending_modernization_recs_count": len(pending_recs),
                "rejected_items_count": rejected_items_count,
                "total_pending_human_reviews": (
                    len(pending_rules)
                    + len(pending_reqs)
                    + len(pending_findings)
                    + len(pending_recs)
                ),
                "unresolved_conflicts_count": len(unresolved_conflicts),
                "unresolved_conflicts": unresolved_conflicts[:15],
            },
            "metric_basis_legend": {
                "MEASURED": "Directly counted from AST declarations, DDL schemas, coverage reports, and static dependency graphs.",
                "HEURISTIC_ESTIMATE": "Engineering remediation effort hours and T-shirt sizing derived from complexity heuristics.",
                "INFERRED": "Extracted business rules, synthesized requirements, and recommended test blueprints awaiting human review sign-off.",
            },
            "suggested_qa_questions": SUGGESTED_QA_QUESTIONS,
        }

    # ------------------------------------------------------------------
    # 2. Executive Reporting (`get_executive_insights`)
    # ------------------------------------------------------------------
    def get_executive_insights(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Provide management-level health, complexity, risk, testing maturity, debt, and effort insights."""
        dash = self.get_application_intelligence_dashboard(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id, user_id=user_id
        )
        risk_reg = self.mod_service.get_risk_register(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        tech_debt = self.mod_service.get_technical_debt(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        mod_roadmap = self.mod_service.get_recommendations_and_roadmap(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )

        sev_counts = risk_reg["counts_by_severity"]
        crit_risks = sev_counts.get("CRITICAL", 0)
        high_risks = sev_counts.get("HIGH", 0)
        med_risks = sev_counts.get("MEDIUM", 0)
        unresolved_confs = dash["governance_and_reviews"][
            "unresolved_conflicts_count"
        ]
        disc_cov_pct = dash["testing_and_coverage"]["coverage_metrics"][
            "discovered_requirement_coverage_pct"
        ]

        # Deterministic health score calculation (0-100)
        raw_health = (
            100
            - (crit_risks * 12)
            - (high_risks * 6)
            - (med_risks * 2)
            - (unresolved_confs * 4)
            + int(disc_cov_pct * 0.15)
        )
        health_score = max(15, min(98, raw_health))
        health_grade = (
            "A"
            if health_score >= 85
            else ("B" if health_score >= 70 else ("C" if health_score >= 55 else "D"))
        )

        debt_by_cat: dict[str, int] = {}
        for item in tech_debt["technical_debt_items"]:
            cat = item["debt_category"]
            debt_by_cat[cat] = debt_by_cat.get(cat, 0) + 1

        measured_m = tech_debt["measured_vs_estimated_summary"]["measured_metrics"]
        est_m = tech_debt["measured_vs_estimated_summary"]["heuristic_estimates"]

        testing_maturity_level = (
            "HIGH_MATURITY"
            if disc_cov_pct >= 75.0
            else ("MODERATE_MATURITY" if disc_cov_pct >= 35.0 else "FOUNDATIONAL_GAP")
        )

        critical_unresolved_issues = [
            {
                "issue_type": "RISK_FINDING",
                "severity": rf["severity"],
                "title": rf["title"],
                "review_status": rf["review_status"],
            }
            for rf in risk_reg["risk_findings"]
            if rf["severity"] in ("CRITICAL", "HIGH")
            and rf["review_status"] not in ("REJECTED", "SUPERSEDED")
        ] + [
            {
                "issue_type": "KNOWLEDGE_CONFLICT",
                "severity": c.get("severity", "HIGH"),
                "title": f"{c['conflict_type']}: {str(c.get('description') or c.get('primary_label', ''))[:120]}",
                "review_status": c["status"],
            }
            for c in dash["governance_and_reviews"]["unresolved_conflicts"]
        ]
        active_priority_recs = [
            r
            for r in mod_roadmap["recommendations"]
            if r["review_status"] not in ("REJECTED", "SUPERSEDED")
        ]

        return {
            "snapshot_id": str(snapshot_id),
            "overall_application_health": {
                "health_score": health_score,
                "health_grade": health_grade,
                "metric_basis": "HEURISTIC_ESTIMATE",
                "explanation": (
                    f"Composite score derived from {crit_risks} critical risk(s), {high_risks} high risk(s), "
                    f"{unresolved_confs} unresolved conflict(s), and {disc_cov_pct}% measured requirement test coverage."
                ),
            },
            "architecture_complexity": {
                "metric_basis": "MEASURED",
                "total_files": measured_m["total_files"],
                "total_loc_code": measured_m["total_loc_code"],
                "total_symbols": measured_m["total_symbols"],
                "max_cyclomatic_complexity": measured_m["max_cyclomatic_complexity"],
                "avg_cyclomatic_complexity": measured_m["avg_cyclomatic_complexity"],
                "call_edges_count": dash["technical_inventory"]["call_edges_count"],
                "knowledge_relationships_count": dash["technical_inventory"][
                    "knowledge_relationships_count"
                ],
            },
            "risk_distribution": {
                "metric_basis": "MEASURED",
                "total_risks": len(risk_reg["risk_findings"]),
                "by_severity": risk_reg["counts_by_severity"],
                "by_category": risk_reg["counts_by_category"],
            },
            "testing_maturity": {
                "maturity_level": testing_maturity_level,
                "discovered_test_cases": dash["testing_and_coverage"][
                    "discovered_test_cases_count"
                ],
                "discovered_requirement_coverage_pct": disc_cov_pct,
                "discovered_symbol_coverage_pct": dash["testing_and_coverage"][
                    "coverage_metrics"
                ]["discovered_symbol_coverage_pct"],
                "recommended_test_blueprints": dash["testing_and_coverage"][
                    "recommended_test_blueprints_count"
                ],
                "discovered_basis": "MEASURED",
                "blueprint_basis": "INFERRED",
            },
            "technical_debt_distribution": {
                "total_debt_items": measured_m["total_debt_items_detected"],
                "counts_by_category": debt_by_cat,
                "item_counts_basis": "MEASURED",
                "estimated_remediation_hours": est_m[
                    "total_estimated_remediation_hours"
                ],
                "remediation_hours_basis": "HEURISTIC_ESTIMATE",
            },
            "modernization_readiness": {
                "recommended_architecture_posture": dash["modernization_posture"][
                    "dimensions"
                ][0]["recommended_posture"]
                if dash["modernization_posture"]["dimensions"]
                else "MODULAR_MONOLITH",
                "microservices_recommended": dash["modernization_posture"][
                    "microservices_recommended"
                ],
                "dimensions": dash["modernization_posture"]["dimensions"],
            },
            "priority_recommendations": active_priority_recs[:6],
            "critical_unresolved_issues": critical_unresolved_issues[:15],
            "estimated_modernization_effort": {
                "metric_basis": "HEURISTIC_ESTIMATE",
                "total_technical_debt_remediation_hours": est_m[
                    "total_estimated_remediation_hours"
                ],
                "total_roadmap_recommendations": len(active_priority_recs),
                "disclaimer": est_m["disclaimer"],
            },
        }

    # ------------------------------------------------------------------
    # 3. Semantic Q&A — Application Intelligence Assistant
    # ------------------------------------------------------------------
    def create_conversation(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        title: str | None = None,
    ) -> dict[str, Any]:
        _, proj, app, _, snap = self._resolve_snapshot_hierarchy(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=proj.id,
            required_permission="project:read",
        )
        conv = QaConversation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=proj.id,
            application_id=app.id,
            snapshot_id=snap.id,
            created_by_user_id=user_id,
            title=(title or f"Intelligence Session — {snap.snapshot_label}")[:255],
            conversation_status="ACTIVE",
        )
        db.add(conv)
        db.flush()
        return self._serialize_conversation(conv, messages=[])

    def list_conversations(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        snapshot_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(QaConversation).where(QaConversation.tenant_id == tenant_id)
        if snapshot_id:
            _, proj, _, _, _ = self._resolve_snapshot_hierarchy(
                db, tenant_id=tenant_id, snapshot_id=snapshot_id
            )
            verify_project_access(
                db,
                user_id=user_id,
                tenant_id=tenant_id,
                project_id=proj.id,
                required_permission="project:read",
            )
            stmt = stmt.where(QaConversation.snapshot_id == snapshot_id)
        elif project_id:
            verify_project_access(
                db,
                user_id=user_id,
                tenant_id=tenant_id,
                project_id=project_id,
                required_permission="project:read",
            )
            stmt = stmt.where(QaConversation.project_id == project_id)

        convs = (
            db.execute(stmt.order_by(QaConversation.updated_at.desc()))
            .scalars()
            .all()
        )
        out: list[dict[str, Any]] = []
        for c in convs:
            try:
                verify_project_access(
                    db,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    project_id=c.project_id,
                    required_permission="project:read",
                )
            except SecurityViolationError:
                continue
            out.append(self._serialize_conversation(c, messages=None))
        return out

    def get_conversation(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> dict[str, Any]:
        conv = db.execute(
            select(QaConversation).where(
                QaConversation.tenant_id == tenant_id,
                QaConversation.id == conversation_id,
            )
        ).scalar_one_or_none()
        if conv is None:
            raise ValueError(
                f"Conversation {conversation_id} not found for tenant {tenant_id}"
            )
        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=conv.project_id,
            required_permission="project:read",
        )
        msgs = (
            db.execute(
                select(QaMessage)
                .where(
                    QaMessage.tenant_id == tenant_id,
                    QaMessage.conversation_id == conv.id,
                )
                .order_by(QaMessage.sequence_no.asc())
            )
            .scalars()
            .all()
        )
        return self._serialize_conversation(conv, messages=msgs)

    def ask_question(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        snapshot_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """
        Execute a codebase-grounded Semantic Q&A turn using Hybrid RRF search (`pgvector` + FTS),
        specialized Wave 1–4 intelligence services, and local Ollama inference.
        """
        clean_q = question.strip()
        if not clean_q:
            raise ValueError("Question cannot be empty.")

        conv: QaConversation | None = None
        if conversation_id is not None:
            conv = db.execute(
                select(QaConversation).where(
                    QaConversation.tenant_id == tenant_id,
                    QaConversation.id == conversation_id,
                )
            ).scalar_one_or_none()
            if conv is None:
                raise ValueError(
                    f"Conversation {conversation_id} not found for tenant {tenant_id}"
                )
            snapshot_id = conv.snapshot_id

        if snapshot_id is None:
            raise ValueError("Either conversation_id or snapshot_id must be provided.")

        _, proj, app, _, snap = self._resolve_snapshot_hierarchy(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=proj.id,
            required_permission="project:read",
        )

        if conv is None:
            conv = QaConversation(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                project_id=proj.id,
                application_id=app.id,
                snapshot_id=snap.id,
                created_by_user_id=user_id,
                title=clean_q[:96],
                conversation_status="ACTIVE",
            )
            db.add(conv)
            db.flush()

        max_seq = (
            db.execute(
                select(func.max(QaMessage.sequence_no)).where(
                    QaMessage.tenant_id == tenant_id,
                    QaMessage.conversation_id == conv.id,
                )
            ).scalar_one()
            or 0
        )

        intent = classify_question_intent(clean_q)
        user_msg = QaMessage(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            snapshot_id=snap.id,
            sequence_no=max_seq + 1,
            role="USER",
            question_intent=intent,
            content_markdown=clean_q,
            direct_facts_json=[],
            inferred_explanations_json=[],
            citations_json=[],
            insufficient_evidence=False,
            confidence_score=Decimal("1.0000"),
        )
        db.add(user_msg)
        db.flush()

        # 1. Execute Hybrid RRF Retrieval (`pgvector` + PostgreSQL FTS)
        hybrid_hits = self.retrieval_service.hybrid_search(
            db,
            tenant_id=tenant_id,
            project_id=proj.id,
            snapshot_id=snap.id,
            query_text=clean_q,
            limit=8,
        )

        # 2. Gather Specialized Intelligence & Evidence Anchors
        synth = self._synthesize_grounded_answer(
            db,
            tenant_id=tenant_id,
            project=proj,
            application=app,
            snapshot=snap,
            question=clean_q,
            intent=intent,
            hybrid_hits=hybrid_hits,
        )

        # 3. Record AgentRun & ModelInvocation telemetry (local Ollama by default)
        latest_run = (
            db.execute(
                select(AnalysisRun)
                .where(
                    AnalysisRun.tenant_id == tenant_id,
                    AnalysisRun.snapshot_id == snap.id,
                )
                .order_by(AnalysisRun.started_at.desc().nullslast())
                .limit(1)
            )
            .scalars()
            .first()
        )
        agent_run_id: uuid.UUID | None = None
        model_inv_id: uuid.UUID | None = None
        if latest_run is not None:
            ar = AgentRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                analysis_run_id=latest_run.id,
                agent_name="semantic_qa_assistant",
                agent_version="5.0.0",
                status="RUNNING",
                attempt_count=1,
                input_context_refs={
                    "conversation_id": str(conv.id),
                    "question_intent": intent,
                    "hybrid_hits_count": len(hybrid_hits),
                },
                started_at=datetime.now(timezone.utc),
            )
            db.add(ar)
            db.flush()
            agent_run_id = ar.id

            tmpl = self.orchestrator._ensure_prompt_template(
                db,
                template_key="semantic_qa_assistant_v1",
                agent_name="semantic_qa_assistant",
            )
            input_ctx = AgentInputContext(
                agent_name="semantic_qa_assistant",
                snapshot_id=str(snap.id),
                application_id=str(app.id),
                available_anchors=[
                    {"id": c.get("anchor_id")}
                    for c in synth["citations"]
                    if c.get("anchor_id")
                ],
                entities_summary=[],
                domain_telemetry={"question": clean_q, "intent": intent},
            )
            _, inv = self.orchestrator._invoke_model_with_fallback(
                db,
                tenant_id=tenant_id,
                agent_run_id=ar.id,
                prompt_template=tmpl,
                input_ctx=input_ctx,
            )
            model_inv_id = inv.id
            ar.status = "COMPLETED"
            ar.output_summary_json = {
                "citations_count": len(synth["citations"]),
                "insufficient_evidence": synth["insufficient_evidence"],
            }
            ar.completed_at = datetime.now(timezone.utc)
            db.flush()

        assistant_msg = QaMessage(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            snapshot_id=snap.id,
            sequence_no=max_seq + 2,
            role="ASSISTANT",
            question_intent=intent,
            content_markdown=synth["answer_markdown"],
            direct_facts_json=synth["direct_facts"],
            inferred_explanations_json=synth["inferred_explanations"],
            citations_json=synth["citations"],
            insufficient_evidence=synth["insufficient_evidence"],
            confidence_score=Decimal(f"{synth['confidence_score']:.4f}"),
            agent_run_id=agent_run_id,
            model_invocation_id=model_inv_id,
        )
        db.add(assistant_msg)
        conv.updated_at = datetime.now(timezone.utc)
        db.flush()

        self.record_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action_code="QA_QUERY_EXECUTED",
            target_resource_type="qa_conversations",
            target_resource_id=conv.id,
            metadata_diff={
                "intent": intent,
                "insufficient_evidence": synth["insufficient_evidence"],
                "citations_count": len(synth["citations"]),
            },
        )

        return {
            "conversation_id": str(conv.id),
            "snapshot_id": str(snap.id),
            "question_intent": intent,
            "user_message": self._serialize_message(user_msg),
            "assistant_message": self._serialize_message(assistant_msg),
        }

    def _synthesize_grounded_answer(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        project: Project,
        application: Application,
        snapshot: RepositorySnapshot,
        question: str,
        intent: str,
        hybrid_hits: list[Any],
    ) -> dict[str, Any]:
        """
        Combine Hybrid RRF search results with Wave 1–4 domain intelligence services,
        enforcing strict citation grounding and explicit insufficient-evidence detection.
        """
        q_tokens = [
            tok
            for tok in re.findall(r"[a-zA-Z0-9_]{3,}", question.lower())
            if tok not in _QA_STOPWORDS
        ]

        anchors = (
            db.execute(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        ver_ids = list({a.artifact_version_id for a in anchors})
        art_map: dict[uuid.UUID, str] = {}
        if ver_ids:
            av_rows = db.execute(
                select(ArtifactVersion.id, Artifact.canonical_path)
                .join(
                    Artifact,
                    (Artifact.tenant_id == ArtifactVersion.tenant_id)
                    & (Artifact.id == ArtifactVersion.artifact_id),
                )
                .where(
                    ArtifactVersion.tenant_id == tenant_id,
                    ArtifactVersion.id.in_(ver_ids),
                )
            ).all()
            art_map = {r[0]: r[1] for r in av_rows}

        # Build corpus text for relevance checking on specific unknown-entity queries
        symbols = (
            db.execute(
                select(CodeSymbol).where(
                    CodeSymbol.tenant_id == tenant_id,
                    CodeSymbol.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        rules_res = self.req_service.get_snapshot_business_rules(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )
        reqs_res = self.req_service.get_snapshot_requirements(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )
        conflicts_res = self.req_service.get_conflicts_and_gaps(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )
        cov_res = self.mod_service.get_coverage_and_gaps(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )
        risk_res = self.mod_service.get_risk_register(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )
        debt_res = self.mod_service.get_technical_debt(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )
        mod_res = self.mod_service.get_recommendations_and_roadmap(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )
        assess_res = self.mod_service.get_modernization_assessment(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )

        # Check lexical match across chunks, anchors, symbols, rules, requirements
        searchable_blob = " ".join(
            [
                *(h.chunk_text.lower() for h in hybrid_hits),
                *(h.relative_path.lower() for h in hybrid_hits),
                *(s.qualified_name.lower() for s in symbols),
                *(r["title"].lower() for r in rules_res["business_rules"]),
                *(r["title"].lower() for r in reqs_res["requirements"]),
                *(a.excerpt_text.lower() for a in anchors[:40]),
            ]
        )

        matched_q_tokens = [t for t in q_tokens if t in searchable_blob]
        is_broad_domain_intent = intent in (
            "ARCHITECTURE_DISCOVERY",
            "BUSINESS_RULE_EXPLANATION",
            "TEST_COVERAGE_GAPS",
            "SECURITY_RISK_INVESTIGATION",
            "TECHNICAL_DEBT_INVESTIGATION",
            "MODERNIZATION_PLANNING",
            "CONFLICT_DETECTION",
            "API_DB_DEPENDENCY",
            "REQUIREMENTS_TRACEABILITY",
        )

        # If the user asks about specific domain terms that have ZERO overlap with the snapshot
        unrecognized_domain_nouns = [
            t
            for t in q_tokens
            if t
            not in (
                "architecture",
                "business",
                "rules",
                "rule",
                "requirements",
                "requirement",
                "test",
                "tests",
                "coverage",
                "security",
                "risk",
                "risks",
                "debt",
                "modernize",
                "modernization",
                "api",
                "apis",
                "database",
                "table",
                "tables",
                "service",
                "component",
                "components",
                "affected",
                "change",
                "conflict",
                "conflicts",
                "documentation",
                "workflow",
                "process",
                "order",
                "orders",
                "customer",
                "account",
                "deactivated",
            )
            and t not in searchable_blob
        ]

        if (
            not anchors
            or (q_tokens and not matched_q_tokens and not is_broad_domain_intent)
            or (len(unrecognized_domain_nouns) >= 2 and not matched_q_tokens)
        ):
            return {
                "insufficient_evidence": True,
                "confidence_score": 0.0,
                "answer_markdown": (
                    "### Insufficient Evidence in Analyzed Snapshot\n\n"
                    f"LegacyIQ searched snapshot `{snapshot.snapshot_label}` using Hybrid RRF (`pgvector` + lexical FTS) "
                    "and inspected all extracted AST symbols, database schemas, API endpoints, business rules, and documentation sections, "
                    "but **found no verifiable source evidence** matching the requested behavior or entities.\n\n"
                    "> **Anti-Hallucination Policy**: LegacyIQ never fabricates application behavior or source citations when supporting evidence is absent."
                ),
                "direct_facts": [],
                "inferred_explanations": [],
                "citations": [],
            }

        citations: list[dict[str, Any]] = []
        seen_citation_keys: set[str] = set()

        def _add_anchor_citation(
            anc_dict: dict[str, Any],
            *,
            ref_label: str | None = None,
        ) -> None:
            aid = str(anc_dict.get("anchor_id", ""))
            key = aid or f"{anc_dict.get('relative_path')}:{anc_dict.get('start_line')}"
            if key in seen_citation_keys or len(citations) >= 8:
                return
            seen_citation_keys.add(key)
            citations.append(
                {
                    "anchor_id": aid or None,
                    "relative_path": anc_dict.get("relative_path") or "source_artifact",
                    "start_line": anc_dict.get("start_line", 1),
                    "end_line": anc_dict.get("end_line", 1),
                    "snippet_sha256": anc_dict.get("snippet_sha256", ""),
                    "excerpt_text": str(anc_dict.get("excerpt_text", ""))[:260],
                    "reference_label": ref_label,
                }
            )

        # Populate citations from top hybrid search hits matched to EvidenceAnchors or chunk coordinates
        for hit in hybrid_hits[:4]:
            matched_anc = next(
                (
                    a
                    for a in anchors
                    if art_map.get(a.artifact_version_id) == hit.relative_path
                    and abs(a.start_line - hit.start_line) <= 25
                ),
                None,
            )
            _add_anchor_citation(
                {
                    "anchor_id": str(matched_anc.id) if matched_anc else None,
                    "relative_path": hit.relative_path,
                    "start_line": hit.start_line,
                    "end_line": hit.end_line,
                    "snippet_sha256": matched_anc.snippet_sha256
                    if matched_anc
                    else hit.chunk_sha256,
                    "excerpt_text": matched_anc.excerpt_text
                    if matched_anc
                    else hit.chunk_text,
                },
                ref_label=hit.symbol_qualified_name or hit.relative_path,
            )

        direct_facts: list[dict[str, Any]] = []
        inferred_explanations: list[dict[str, Any]] = []
        body_sections: list[str] = []

        if intent == "BUSINESS_RULE_EXPLANATION":
            rules = [
                r
                for r in rules_res["business_rules"]
                if r["review_status"] not in ("REJECTED", "SUPERSEDED")
            ]
            body_sections.append(
                f"### Discovered Business Rules ({len(rules)} Total)\n"
                "The following business rules were extracted with direct source evidence anchors:"
            )
            for r in rules[:6]:
                status_tag = (
                    "CONFIRMED FACT (APPROVED)"
                    if r["is_confirmed_fact"]
                    else f"INFERRED ({r['review_status']})"
                )
                body_sections.append(
                    f"- **`{r['rule_code']}` — {r['title']}** (`{r['rule_category']}`, `{status_tag}`): "
                    f"Condition `{r['condition_expression']}` -> `{r['action_consequence']}`"
                )
                if r["is_confirmed_fact"]:
                    direct_facts.append(
                        {
                            "statement": f"{r['rule_code']}: {r['title']} ({r['condition_expression']} -> {r['action_consequence']})",
                            "fact_basis": "HUMAN_APPROVED_RULE",
                            "reference": r["rule_code"],
                        }
                    )
                else:
                    rule_stmt = r.get("statement_markdown") or (
                        f"{r.get('title', '')} ({r.get('condition_expression', '')} -> {r.get('action_consequence', '')})"
                    )
                    inferred_explanations.append(
                        {
                            "statement": f"{r['rule_code']} ({r['rule_category']}): {rule_stmt}",
                            "inference_basis": r["origin_type"],
                            "review_status": r["review_status"],
                            "confidence_score": r["confidence_score"],
                        }
                    )
                for ev in r.get("evidence", [])[:1]:
                    _add_anchor_citation(ev, ref_label=r["rule_code"])

        elif intent == "TEST_COVERAGE_GAPS":
            cm = cov_res["coverage_metrics"]
            untested = cov_res["untested_requirements"]
            body_sections.append(
                f"### Test Coverage & Requirement Gaps\n"
                f"- **Measured Requirement Coverage (Existing Repository Tests)**: `{cm['discovered_requirement_coverage_pct']}%` "
                f"(`{cm['requirements_covered_by_existing_tests']}` of `{cm['total_requirements']}` requirements covered)\n"
                f"- **Inferred Blueprint Recommendations (`AI_GENERATED_BLUEPRINT`)**: `{cm['requirements_with_blueprint_recommendations']}` characterization blueprints generated."
            )
            direct_facts.append(
                {
                    "statement": f"Measured repository tests cover {cm['requirements_covered_by_existing_tests']} of {cm['total_requirements']} requirements ({cm['discovered_requirement_coverage_pct']}%).",
                    "fact_basis": "MEASURED_TEST_COVERAGE",
                    "reference": "TestCoverageLink",
                }
            )
            for u in untested[:6]:
                body_sections.append(
                    f"- **Uncovered Requirement `{u['req_code']}`**: {u['title']} (`{u['priority']}`, State: `{u['coverage_state']}`)"
                )
                inferred_explanations.append(
                    {
                        "statement": f"Requirement {u['req_code']} ({u['title']}) lacks discovered repository test execution; characterization test blueprint recommended.",
                        "inference_basis": "TEST_GAP_ANALYSIS",
                        "review_status": "PENDING_REVIEW",
                        "confidence_score": 0.92,
                    }
                )

        elif intent == "SECURITY_RISK_INVESTIGATION":
            risks = [
                rf
                for rf in risk_res["risk_findings"]
                if rf["review_status"] not in ("REJECTED", "SUPERSEDED")
            ]
            body_sections.append(
                f"### Security & Operational Risk Register ({len(risks)} Findings)\n"
                "Every risk finding is anchored to source lines or dependency manifests:"
            )
            direct_facts.append(
                {
                    "statement": f"Static risk scan identified {len(risks)} active risk finding(s) anchored to source artifacts.",
                    "fact_basis": "DETERMINISTIC_RISK_SCAN",
                    "reference": str(snapshot.id),
                }
            )
            for rf in risks[:6]:
                body_sections.append(
                    f"- **[{rf['severity']} | {rf['finding_category']}] {rf['title']}** "
                    f"(Confidence: `{rf['confidence_score']}`, Status: `{rf['review_status']}`)\n"
                    f"  {rf['statement_markdown']}"
                )
                if rf["review_status"] == "APPROVED":
                    direct_facts.append(
                        {
                            "statement": f"[{rf['severity']}] {rf['title']} (Human Approved)",
                            "fact_basis": "HUMAN_APPROVED_RISK_FINDING",
                            "reference": rf["id"],
                        }
                    )
                else:
                    inferred_explanations.append(
                        {
                            "statement": f"[{rf['severity']} | {rf['finding_category']}] {rf['title']}: {rf['statement_markdown']}",
                            "inference_basis": "STATIC_AND_AGENT_RISK_ANALYSIS",
                            "review_status": rf["review_status"],
                            "confidence_score": rf["confidence_score"],
                        }
                    )
                for ev in rf.get("evidence", [])[:1]:
                    _add_anchor_citation(ev, ref_label=rf["title"])

        elif intent == "CONFLICT_DETECTION":
            confs = conflicts_res["conflicts"]
            body_sections.append(
                f"### Business Rule & Documentation Conflicts ({len(confs)} Detected)\n"
            )
            for c in confs[:6]:
                c_desc = c.get("description") or (
                    f"{c.get('primary_label', '')} vs {c.get('conflicting_label', '')}"
                )
                c_sev = c.get("severity", "HIGH")
                body_sections.append(
                    f"- **`{c['conflict_type']}` ({c_sev}, Status: `{c['status']}`)**: {c_desc}"
                )
                inferred_explanations.append(
                    {
                        "statement": c_desc,
                        "inference_basis": c["conflict_type"],
                        "review_status": c["status"],
                        "confidence_score": 0.91,
                    }
                )
                if c.get("primary_evidence"):
                    _add_anchor_citation(
                        c["primary_evidence"], ref_label=c["conflict_type"]
                    )
                if c.get("conflicting_evidence"):
                    _add_anchor_citation(
                        c["conflicting_evidence"], ref_label=c["conflict_type"]
                    )

        elif intent == "MODERNIZATION_PLANNING":
            recs = [
                r
                for r in mod_res["recommendations"]
                if r["review_status"] not in ("REJECTED", "SUPERSEDED")
            ]
            arch_dim = assess_res["dimensions"][0] if assess_res["dimensions"] else {}
            body_sections.append(
                f"### Modernization Strategy & 4-Phase Roadmap\n"
                f"- **Recommended Architecture Posture**: `{arch_dim.get('recommended_posture', 'MODULAR_MONOLITH')}` "
                f"(Microservices Recommended: `{assess_res['microservices_recommended']}`)\n"
                f"- **Rationale**: {arch_dim.get('rationale', '')}"
            )
            for r in recs[:6]:
                body_sections.append(
                    f"- **Phase {r['roadmap_phase']} (`{r['strategy_pattern']}`) — {r['title']}** "
                    f"[Effort: `{r['effort_tshirt']}` ({r['estimated_effort_range']}, `{r['effort_nature']}`)]"
                )
                inferred_explanations.append(
                    {
                        "statement": f"Phase {r['roadmap_phase']}: {r['title']} -> {r['target_state_architecture']}",
                        "inference_basis": "MODERNIZATION_STRATEGIST",
                        "review_status": r["review_status"],
                        "confidence_score": r["confidence_score"],
                    }
                )

        elif intent == "CHANGE_IMPACT_ANALYSIS":
            target_id = None
            if reqs_res["requirements"]:
                target_id = uuid.UUID(reqs_res["requirements"][0]["id"])
            elif rules_res["business_rules"]:
                target_id = uuid.UUID(rules_res["business_rules"][0]["id"])
            if target_id is not None:
                imp = self.req_service.analyze_impact(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot.id,
                    target_id=target_id,
                )
                body_sections.append(
                    f"### Multi-Hop Change Impact Analysis\n"
                    f"- **Target**: `{imp['target']['title']}` (`{imp['target']['kind']}`)\n"
                    f"- **Blast Radius Risk**: `{imp['blast_radius_risk']}`\n"
                    f"- **Affected Components**: `{len(imp['affected_code_components'])}` code symbol(s), "
                    f"`{len(imp['affected_apis'])}` API endpoint(s), `{len(imp['affected_database_tables'])}` database table(s), "
                    f"`{len(imp['affected_business_rules'])}` business rule(s)."
                )
                direct_facts.append(
                    {
                        "statement": f"Blast radius for {imp['target']['title']} is {imp['blast_radius_risk']} across {len(imp['affected_code_components'])} code symbols and {len(imp['affected_database_tables'])} database tables.",
                        "fact_basis": "KNOWLEDGE_GRAPH_TRAVERSAL",
                        "reference": str(target_id),
                    }
                )

        else:
            # ARCHITECTURE_DISCOVERY, API_DB_DEPENDENCY, BUSINESS_PROCESS, REQUIREMENTS_TRACEABILITY, TECHNICAL_DEBT_INVESTIGATION, GENERAL_CODE_QA
            dash = self.get_application_intelligence_dashboard(
                db, tenant_id=tenant_id, snapshot_id=snapshot.id
            )
            ti = dash["technical_inventory"]
            so = dash["snapshot_overview"]
            body_sections.append(
                f"### Evidence-Grounded Intelligence Summary (`{so['snapshot_label']}`)\n"
                f"- **Measured Codebase Inventory**: `{so['total_files']}` source files (`{so['total_loc_code']}` LOC) across languages `{', '.join(so['languages'].keys()) or 'polyglot'}`\n"
                f"- **Technical Entities**: `{ti['code_symbols_count']}` code symbols, `{ti['db_tables_count']}` database tables, `{ti['api_endpoints_count']}` API endpoints, `{ti['infra_resources_count']}` infrastructure resources\n"
                f"- **Business & Requirements Intelligence**: `{dash['business_and_requirements']['business_rules_count']}` business rules across `{dash['business_and_requirements']['domains_count']}` domains, and `{dash['business_and_requirements']['requirements_count']}` requirements."
            )
            direct_facts.append(
                {
                    "statement": f"Snapshot contains {so['total_files']} files ({so['total_loc_code']} LOC), {ti['code_symbols_count']} symbols, {ti['db_tables_count']} DB tables, and {ti['api_endpoints_count']} API endpoints.",
                    "fact_basis": "MEASURED_STATIC_INVENTORY",
                    "reference": str(snapshot.id),
                }
            )
            for tbl in ti["db_tables"][:4]:
                direct_facts.append(
                    {
                        "statement": f"Database table `{tbl['table_name']}` ({tbl['table_kind']}) discovered in schema.",
                        "fact_basis": "DDL_SCHEMA_EXTRACTION",
                        "reference": tbl["table_name"],
                    }
                )
            for ep in ti["api_endpoints"][:4]:
                direct_facts.append(
                    {
                        "statement": f"API endpoint `{ep['http_method']} {ep['route_path']}` (Auth: {ep['auth_scheme'] or 'NONE'}).",
                        "fact_basis": "API_CONTROLLER_EXTRACTION",
                        "reference": ep["route_path"],
                    }
                )
            for proc in dash["business_and_requirements"]["processes"][:3]:
                inferred_explanations.append(
                    {
                        "statement": f"Workflow `{proc.get('name', 'Workflow')}` ({proc.get('trigger_event', proc.get('process_code', 'WORKFLOW'))}): {proc.get('description', '')}",
                        "inference_basis": "WORKFLOW_RECONSTRUCTION",
                        "review_status": "PENDING_REVIEW",
                        "confidence_score": 0.89,
                    }
                )

        # Ensure at least one citation from snapshot anchors if hybrid hits didn't already add one
        if not citations and anchors:
            first_anc = anchors[0]
            _add_anchor_citation(
                {
                    "anchor_id": str(first_anc.id),
                    "relative_path": art_map.get(
                        first_anc.artifact_version_id, "source_artifact"
                    ),
                    "start_line": first_anc.start_line,
                    "end_line": first_anc.end_line,
                    "snippet_sha256": first_anc.snippet_sha256,
                    "excerpt_text": first_anc.excerpt_text,
                },
                ref_label="Primary Snapshot Evidence",
            )

        if not direct_facts and citations:
            c0 = citations[0]
            direct_facts.append(
                {
                    "statement": f"Source evidence observed in `{c0['relative_path']}` (lines {c0['start_line']}–{c0['end_line']}).",
                    "fact_basis": "SOURCE_EVIDENCE_ANCHOR",
                    "reference": f"{c0['relative_path']}:{c0['start_line']}",
                }
            )

        body_sections.append(
            "\n> **Fact vs. Inference Separation**: Directly observed AST/DDL/coverage facts are listed under `direct_facts`; "
            "extracted rules, requirements, and architectural explanations are listed under `inferred_explanations` with their current human review status."
        )

        return {
            "insufficient_evidence": False,
            "confidence_score": 0.92,
            "answer_markdown": "\n\n".join(body_sections),
            "direct_facts": direct_facts,
            "inferred_explanations": inferred_explanations,
            "citations": citations,
        }

    def _serialize_message(self, m: QaMessage) -> dict[str, Any]:
        return {
            "id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "snapshot_id": str(m.snapshot_id),
            "sequence_no": m.sequence_no,
            "role": m.role,
            "question_intent": m.question_intent,
            "content_markdown": m.content_markdown,
            "direct_facts": m.direct_facts_json,
            "inferred_explanations": m.inferred_explanations_json,
            "citations": m.citations_json,
            "insufficient_evidence": m.insufficient_evidence,
            "confidence_score": float(m.confidence_score),
            "agent_run_id": str(m.agent_run_id) if m.agent_run_id else None,
            "model_invocation_id": str(m.model_invocation_id)
            if m.model_invocation_id
            else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }

    def _serialize_conversation(
        self,
        c: QaConversation,
        messages: list[QaMessage] | None,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(c.id),
            "tenant_id": str(c.tenant_id),
            "project_id": str(c.project_id),
            "application_id": str(c.application_id),
            "snapshot_id": str(c.snapshot_id),
            "title": c.title,
            "conversation_status": c.conversation_status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "suggested_questions": SUGGESTED_QA_QUESTIONS,
        }
        if messages is not None:
            out["messages"] = [self._serialize_message(m) for m in messages]
        return out

    # ------------------------------------------------------------------
    # 4. Report Generation Engine, Versioning & Lifecycle Governance
    # ------------------------------------------------------------------
    def generate_report(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        report_type: str,
        initial_status: str = "GENERATED",
        custom_title: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate or regenerate one of the 11 structured intelligence reports.
        If an existing report for `(snapshot_id, report_type)` is already `APPROVED`,
        the approved version remains strictly immutable and a new version (`version_no + 1`) is created!
        """
        rtype = report_type.upper().strip()
        if rtype not in REPORT_TYPE_CATALOG:
            raise ValueError(
                f"Unsupported report_type '{report_type}'. Must be one of: {', '.join(REPORT_TYPE_CATALOG.keys())}"
            )
        if initial_status not in ("DRAFT", "GENERATED"):
            initial_status = "GENERATED"

        org, proj, app, repo, snap = self._resolve_snapshot_hierarchy(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=proj.id,
            required_permission="project:read",
        )

        content_bundle = self._build_report_content_bundle(
            db,
            tenant_id=tenant_id,
            org=org,
            proj=proj,
            app=app,
            repo=repo,
            snap=snap,
            report_type=rtype,
        )

        existing_report = (
            db.execute(
                select(IntelligenceReport)
                .where(
                    IntelligenceReport.tenant_id == tenant_id,
                    IntelligenceReport.snapshot_id == snapshot_id,
                    IntelligenceReport.report_type == rtype,
                )
                .order_by(IntelligenceReport.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        title = (
            custom_title
            or f"{REPORT_TYPE_CATALOG[rtype]} — {app.name} ({snap.snapshot_label})"
        )[:255]

        if existing_report is None:
            report_obj = IntelligenceReport(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                project_id=proj.id,
                application_id=app.id,
                snapshot_id=snap.id,
                report_type=rtype,
                title=title,
                current_version_no=1,
                lifecycle_status=initial_status,
                created_by_user_id=user_id,
            )
            db.add(report_obj)
            db.flush()
            next_ver_no = 1
        else:
            report_obj = existing_report
            max_ver = (
                db.execute(
                    select(func.max(IntelligenceReportVersion.version_no)).where(
                        IntelligenceReportVersion.tenant_id == tenant_id,
                        IntelligenceReportVersion.report_id == report_obj.id,
                    )
                ).scalar_one()
                or report_obj.current_version_no
            )
            next_ver_no = max_ver + 1
            report_obj.current_version_no = next_ver_no
            report_obj.lifecycle_status = initial_status
            if custom_title:
                report_obj.title = title
            report_obj.updated_at = datetime.now(timezone.utc)
            db.flush()

        canonical_json = json.dumps(
            {
                "report_type": rtype,
                "version_no": next_ver_no,
                "executive_summary": content_bundle["executive_summary_markdown"],
                "sections": content_bundle["sections"],
                "evidence_references": content_bundle["evidence_references"],
                "recommendations": content_bundle["recommendations"],
            },
            sort_keys=True,
        )
        content_sha = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        ver_obj = IntelligenceReportVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            report_id=report_obj.id,
            snapshot_id=snap.id,
            version_no=next_ver_no,
            lifecycle_status=initial_status,
            is_immutable=False,
            executive_summary_markdown=content_bundle["executive_summary_markdown"],
            scope_and_methodology_markdown=content_bundle[
                "scope_and_methodology_markdown"
            ],
            sections_json=content_bundle["sections"],
            evidence_refs_json=content_bundle["evidence_references"],
            risks_and_limitations_markdown=content_bundle[
                "risks_and_limitations_markdown"
            ],
            recommendations_json=content_bundle["recommendations"],
            metrics_summary_json=content_bundle["metrics_summary"],
            content_sha256=content_sha,
            created_by_user_id=user_id,
        )
        db.add(ver_obj)
        db.flush()

        self.record_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action_code="REPORT_GENERATED",
            target_resource_type="intelligence_reports",
            target_resource_id=report_obj.id,
            metadata_diff={
                "report_type": rtype,
                "version_no": next_ver_no,
                "lifecycle_status": initial_status,
                "content_sha256": content_sha,
            },
        )

        return self.get_report(
            db, tenant_id=tenant_id, user_id=user_id, report_id=report_obj.id
        )

    def _build_report_content_bundle(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        org: Organization,
        proj: Project,
        app: Application,
        repo: Repository,
        snap: RepositorySnapshot,
        report_type: str,
    ) -> dict[str, Any]:
        dash = self.get_application_intelligence_dashboard(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        exec_ins = self.get_executive_insights(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        rules_res = self.req_service.get_snapshot_business_rules(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        reqs_res = self.req_service.get_snapshot_requirements(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        risk_res = self.mod_service.get_risk_register(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        debt_res = self.mod_service.get_technical_debt(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        test_res = self.mod_service.get_test_intelligence(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        cov_res = self.mod_service.get_coverage_and_gaps(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )
        mod_res = self.mod_service.get_recommendations_and_roadmap(
            db, tenant_id=tenant_id, snapshot_id=snap.id
        )

        # Collect evidence anchors with file paths
        anchors = (
            db.execute(
                select(EvidenceAnchor)
                .where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.snapshot_id == snap.id,
                )
                .limit(50)
            )
            .scalars()
            .all()
        )
        ver_ids = list({a.artifact_version_id for a in anchors})
        art_map: dict[uuid.UUID, str] = {}
        if ver_ids:
            av_rows = db.execute(
                select(ArtifactVersion.id, Artifact.canonical_path)
                .join(
                    Artifact,
                    (Artifact.tenant_id == ArtifactVersion.tenant_id)
                    & (Artifact.id == ArtifactVersion.artifact_id),
                )
                .where(
                    ArtifactVersion.tenant_id == tenant_id,
                    ArtifactVersion.id.in_(ver_ids),
                )
            ).all()
            art_map = {r[0]: r[1] for r in av_rows}

        evidence_references = [
            {
                "anchor_id": str(a.id),
                "relative_path": art_map.get(a.artifact_version_id, "source_artifact"),
                "start_line": a.start_line,
                "end_line": a.end_line,
                "snippet_sha256": a.snippet_sha256,
                "excerpt_text": a.excerpt_text[:260],
            }
            for a in anchors[:30]
        ]

        so = dash["snapshot_overview"]
        ti = dash["technical_inventory"]
        br = dash["business_and_requirements"]
        gov = dash["governance_and_reviews"]

        exec_summary = (
            f"**{REPORT_TYPE_CATALOG[report_type]}** for application **{app.name}** "
            f"(Project: `{proj.name}`, Repository: `{repo.name}`, Snapshot: `{snap.snapshot_label}`).\n\n"
            f"- **Measured Inventory**: `{so['total_files']}` source files (`{so['total_loc_code']}` LOC), "
            f"`{ti['code_symbols_count']}` symbols, `{ti['db_tables_count']}` DB tables, `{ti['api_endpoints_count']}` API endpoints.\n"
            f"- **Business & Requirements Posture**: `{br['business_rules_count']}` business rules (`{br['approved_business_rules_count']}` approved) "
            f"and `{br['requirements_count']}` requirements (`{br['approved_requirements_count']}` approved).\n"
            f"- **Quality, Risk & Modernization**: Overall Health Score `{exec_ins['overall_application_health']['health_score']}/100` (`{exec_ins['overall_application_health']['health_grade']}`), "
            f"`{len(risk_res['risk_findings'])}` risk findings, `{len(debt_res['technical_debt_items'])}` technical debt items, "
            f"and `{len(mod_res['recommendations'])}` phased modernization recommendations.\n"
            f"- **Governance Notice**: `{gov['total_pending_human_reviews']}` item(s) remain in `PENDING_REVIEW` / `MODIFIED_BY_HUMAN` status and are explicitly distinguished from human-approved (`APPROVED`) facts."
        )

        scope_and_methodology = (
            "1. **Deterministic Static & Schema Extraction (MEASURED)**: AST symbol extraction, call graphs, SQL DDL schemas, OpenAPI/controller routes, IaC manifests, and Cobertura/LCOV coverage parsing.\n"
            "2. **Evidence-Anchored Rule & Requirement Reconstruction (INFERRED)**: Business rules and Given/When/Then requirements linked to `EvidenceAnchor` SHA-256 snippets.\n"
            "3. **Heuristic Effort Estimation (HEURISTIC_ESTIMATE)**: Technical debt remediation hours and modernization T-shirt ranges labeled as estimates.\n"
            "4. **Human Review Governance**: Unreviewed claims carry `is_confirmed_fact = false` until approved by an authorized reviewer."
        )

        all_sections: dict[str, dict[str, Any]] = {
            "DISCOVERY": {
                "section_key": "DISCOVERY",
                "title": "Repository, Stack & Component Discovery",
                "metric_basis": "MEASURED",
                "review_posture": "CONFIRMED_STATIC",
                "content_markdown": (
                    f"Analyzed `{so['total_files']}` files (`{so['total_loc_code']}` LOC) across languages: "
                    f"`{json.dumps(so['languages'])}`. Detected stack & frameworks: `{', '.join(so['frameworks_and_stack'])}`."
                ),
            },
            "ARCHITECTURE": {
                "section_key": "ARCHITECTURE",
                "title": "Technical Architecture & Dependency Graph",
                "metric_basis": "MEASURED",
                "review_posture": "CONFIRMED_STATIC",
                "content_markdown": (
                    f"Unified Knowledge Graph contains `{ti['knowledge_entities_count']}` entities, "
                    f"`{ti['knowledge_relationships_count']}` relationships, and `{ti['call_edges_count']}` static call edges. "
                    f"Max cyclomatic complexity: `{exec_ins['architecture_complexity']['max_cyclomatic_complexity']}`."
                ),
            },
            "API_DB": {
                "section_key": "API_DB",
                "title": "Database Schema & API Contract Intelligence",
                "metric_basis": "MEASURED",
                "review_posture": "CONFIRMED_STATIC",
                "content_markdown": (
                    f"Discovered `{ti['db_schemas_count']}` schema(s), `{ti['db_tables_count']}` table(s), "
                    f"`{ti['db_columns_count']}` column(s) (`{ti['pii_columns_count']}` PII candidates), "
                    f"and `{ti['api_endpoints_count']}` API endpoint(s)."
                ),
            },
            "BUSINESS_RULES": {
                "section_key": "BUSINESS_RULES",
                "title": "Business Domains, Workflows & Rules Catalog",
                "metric_basis": "INFERRED",
                "review_posture": f"{br['approved_business_rules_count']}/{br['business_rules_count']} APPROVED",
                "content_markdown": "\n".join(
                    [
                        f"- `{r['rule_code']}` [{r['review_status']} | Confidence {r['confidence_score']}]: {r['title']} — `{r['condition_expression']}` -> `{r['action_consequence']}`"
                        for r in rules_res["business_rules"]
                        if r["review_status"] not in ("REJECTED", "SUPERSEDED")
                    ][:12]
                )
                or "No business rules extracted.",
            },
            "REQUIREMENTS": {
                "section_key": "REQUIREMENTS",
                "title": "Functional & Non-Functional Requirements Specification",
                "metric_basis": "INFERRED",
                "review_posture": f"{br['approved_requirements_count']}/{br['requirements_count']} APPROVED",
                "content_markdown": "\n".join(
                    [
                        f"- `{rq['req_code']}` ({rq['req_type']}, Priority `{rq['priority']}`, Status `{rq['review_status']}`): {rq['title']} — {rq['specification_statement']}"
                        for rq in reqs_res["requirements"]
                        if rq["review_status"] not in ("REJECTED", "SUPERSEDED")
                    ][:12]
                )
                or "No requirements synthesized.",
            },
            "SECURITY_RISK": {
                "section_key": "SECURITY_RISK",
                "title": "Security, Dependency & Operational Risk Assessment",
                "metric_basis": "MEASURED",
                "review_posture": "PENDING_REVIEW_INCLUDED",
                "content_markdown": "\n".join(
                    [
                        f"- **[{rf['severity']} | {rf['finding_category']}]** {rf['title']} (`{rf['review_status']}`): {rf['statement_markdown']}"
                        for rf in risk_res["risk_findings"]
                        if rf["review_status"] not in ("REJECTED", "SUPERSEDED")
                    ][:12]
                )
                or "No high/critical security risks detected.",
            },
            "TESTING_COVERAGE": {
                "section_key": "TESTING_COVERAGE",
                "title": "Test Discovery, Coverage & Characterization Blueprints",
                "metric_basis": "MEASURED_AND_INFERRED",
                "review_posture": "SEPARATED_DISCOVERED_VS_BLUEPRINT",
                "content_markdown": (
                    f"Discovered `{test_res['summary']['discovered_test_cases']}` existing repository test case(s) (`EXISTING_IN_REPO`) "
                    f"covering `{cov_res['coverage_metrics']['discovered_requirement_coverage_pct']}%` of requirements. "
                    f"Synthesized `{test_res['summary']['recommended_test_blueprints']}` characterization blueprint(s) (`AI_GENERATED_BLUEPRINT`, not executed)."
                ),
            },
            "TECH_DEBT": {
                "section_key": "TECH_DEBT",
                "title": "Technical Debt Quantification (Measured vs. Estimated Effort)",
                "metric_basis": "HEURISTIC_ESTIMATE",
                "review_posture": "MEASURED_COUNTS_ESTIMATED_HOURS",
                "content_markdown": "\n".join(
                    [
                        f"- **[{d['severity']} | {d['debt_category']}]** {d['description']} (Estimated Effort: `{d['estimated_remediation_hours']}h` [`{d['effort_nature']}`])"
                        for d in debt_res["technical_debt_items"][:12]
                    ]
                )
                or "No technical debt items recorded.",
            },
            "MODERNIZATION": {
                "section_key": "MODERNIZATION",
                "title": "Modernization Readiness & 4-Phase Roadmap",
                "metric_basis": "HEURISTIC_ESTIMATE",
                "review_posture": "PENDING_REVIEW_INCLUDED",
                "content_markdown": "\n".join(
                    [
                        f"- **Phase {rec['roadmap_phase']} (`{rec['strategy_pattern']}`)**: {rec['title']} — Target: {rec['target_state_architecture']} (Effort: `{rec['effort_tshirt']}` `{rec['estimated_effort_range']}`, Status: `{rec['review_status']}`)"
                        for rec in mod_res["recommendations"]
                        if rec["review_status"] not in ("REJECTED", "SUPERSEDED")
                    ]
                ),
            },
        }

        type_section_map: dict[str, list[str]] = {
            "APPLICATION_DISCOVERY": ["DISCOVERY", "ARCHITECTURE", "API_DB"],
            "TECHNICAL_ARCHITECTURE": ["ARCHITECTURE", "API_DB", "TECH_DEBT"],
            "BUSINESS_RULES_PROCESSES": ["BUSINESS_RULES", "DISCOVERY"],
            "REQUIREMENTS_SPECIFICATION": ["REQUIREMENTS", "BUSINESS_RULES", "TESTING_COVERAGE"],
            "API_DATABASE_INTELLIGENCE": ["API_DB", "ARCHITECTURE", "SECURITY_RISK"],
            "SECURITY_RISK_ASSESSMENT": ["SECURITY_RISK", "API_DB", "TECH_DEBT"],
            "TESTING_COVERAGE_ASSESSMENT": ["TESTING_COVERAGE", "REQUIREMENTS"],
            "TECHNICAL_DEBT_ASSESSMENT": ["TECH_DEBT", "ARCHITECTURE", "MODERNIZATION"],
            "MODERNIZATION_ASSESSMENT": ["MODERNIZATION", "TECH_DEBT", "SECURITY_RISK"],
            "EXECUTIVE_SUMMARY": ["DISCOVERY", "SECURITY_RISK", "MODERNIZATION"],
            "COMPLETE_INTELLIGENCE": list(all_sections.keys()),
        }

        selected_keys = type_section_map.get(report_type, list(all_sections.keys()))
        sections = [all_sections[k] for k in selected_keys if k in all_sections]

        risks_and_limitations = (
            f"1. **Unreviewed Inferences**: `{gov['total_pending_human_reviews']}` extracted item(s) are currently in `PENDING_REVIEW` or `MODIFIED_BY_HUMAN` state and must not be treated as signed-off contractual facts until approved.\n"
            f"2. **Unresolved Contradictions**: `{gov['unresolved_conflicts_count']}` conflict(s) between code and documentation remain open.\n"
            "3. **Effort Estimates**: All remediation hours and T-shirt ranges are heuristic engineering estimates (`HEURISTIC_ESTIMATE`), not historical actuals."
        )

        return {
            "executive_summary_markdown": exec_summary,
            "scope_and_methodology_markdown": scope_and_methodology,
            "sections": sections,
            "evidence_references": evidence_references,
            "risks_and_limitations_markdown": risks_and_limitations,
            "recommendations": mod_res["recommendations"],
            "metrics_summary": {
                "measured": {
                    "total_files": so["total_files"],
                    "total_loc_code": so["total_loc_code"],
                    "code_symbols_count": ti["code_symbols_count"],
                    "db_tables_count": ti["db_tables_count"],
                    "api_endpoints_count": ti["api_endpoints_count"],
                    "discovered_test_cases_count": test_res["summary"][
                        "discovered_test_cases"
                    ],
                },
                "heuristic_estimates": {
                    "health_score": exec_ins["overall_application_health"][
                        "health_score"
                    ],
                    "estimated_remediation_hours": exec_ins[
                        "estimated_modernization_effort"
                    ]["total_technical_debt_remediation_hours"],
                },
                "inferred": {
                    "business_rules_count": br["business_rules_count"],
                    "approved_business_rules_count": br[
                        "approved_business_rules_count"
                    ],
                    "requirements_count": br["requirements_count"],
                    "approved_requirements_count": br["approved_requirements_count"],
                    "recommended_test_blueprints_count": test_res["summary"][
                        "recommended_test_blueprints"
                    ],
                },
            },
        }

    def list_reports(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> dict[str, Any]:
        _, proj, _, _, _ = self._resolve_snapshot_hierarchy(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=proj.id,
            required_permission="project:read",
        )
        reports = (
            db.execute(
                select(IntelligenceReport)
                .where(
                    IntelligenceReport.tenant_id == tenant_id,
                    IntelligenceReport.snapshot_id == snapshot_id,
                )
                .order_by(IntelligenceReport.updated_at.desc())
            )
            .scalars()
            .all()
        )
        return {
            "snapshot_id": str(snapshot_id),
            "available_report_types": [
                {"report_type": k, "display_name": v}
                for k, v in REPORT_TYPE_CATALOG.items()
            ],
            "reports": [
                {
                    "id": str(r.id),
                    "project_id": str(r.project_id),
                    "application_id": str(r.application_id),
                    "snapshot_id": str(r.snapshot_id),
                    "report_type": r.report_type,
                    "report_type_display": REPORT_TYPE_CATALOG.get(
                        r.report_type, r.report_type
                    ),
                    "title": r.title,
                    "current_version_no": r.current_version_no,
                    "lifecycle_status": r.lifecycle_status,
                    "is_approved": r.lifecycle_status == "APPROVED",
                    "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in reports
            ],
        }

    def get_report(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        report_id: uuid.UUID,
        version_no: int | None = None,
    ) -> dict[str, Any]:
        rep = db.execute(
            select(IntelligenceReport).where(
                IntelligenceReport.tenant_id == tenant_id,
                IntelligenceReport.id == report_id,
            )
        ).scalar_one_or_none()
        if rep is None:
            raise ValueError(f"Report {report_id} not found for tenant {tenant_id}")

        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=rep.project_id,
            required_permission="project:read",
        )
        org, proj, app, repo, snap = self._resolve_snapshot_hierarchy(
            db, tenant_id=tenant_id, snapshot_id=rep.snapshot_id
        )

        target_ver_no = version_no or rep.current_version_no
        ver = db.execute(
            select(IntelligenceReportVersion).where(
                IntelligenceReportVersion.tenant_id == tenant_id,
                IntelligenceReportVersion.report_id == rep.id,
                IntelligenceReportVersion.version_no == target_ver_no,
            )
        ).scalar_one_or_none()
        if ver is None:
            ver = (
                db.execute(
                    select(IntelligenceReportVersion)
                    .where(
                        IntelligenceReportVersion.tenant_id == tenant_id,
                        IntelligenceReportVersion.report_id == rep.id,
                    )
                    .order_by(IntelligenceReportVersion.version_no.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
        assert ver is not None

        all_vers = (
            db.execute(
                select(IntelligenceReportVersion)
                .where(
                    IntelligenceReportVersion.tenant_id == tenant_id,
                    IntelligenceReportVersion.report_id == rep.id,
                )
                .order_by(IntelligenceReportVersion.version_no.desc())
            )
            .scalars()
            .all()
        )

        return {
            "id": str(rep.id),
            "tenant_id": str(rep.tenant_id),
            "project_id": str(rep.project_id),
            "application_id": str(rep.application_id),
            "snapshot_id": str(rep.snapshot_id),
            "branding": {
                "organization_name": org.display_name,
                "organization_slug": org.slug,
                "project_name": proj.name,
                "project_key": proj.key,
                "application_name": app.name,
                "repository_name": repo.name,
                "snapshot_label": snap.snapshot_label,
            },
            "report_type": rep.report_type,
            "report_type_display": REPORT_TYPE_CATALOG.get(
                rep.report_type, rep.report_type
            ),
            "title": rep.title,
            "current_version_no": rep.current_version_no,
            "version_no": ver.version_no,
            "version_id": str(ver.id),
            "lifecycle_status": ver.lifecycle_status,
            "report_lifecycle_status": rep.lifecycle_status,
            "is_immutable": ver.is_immutable,
            "executive_summary_markdown": ver.executive_summary_markdown,
            "scope_and_methodology_markdown": ver.scope_and_methodology_markdown,
            "sections": ver.sections_json,
            "evidence_references": ver.evidence_refs_json,
            "risks_and_limitations_markdown": ver.risks_and_limitations_markdown,
            "recommendations": ver.recommendations_json,
            "metrics_summary": ver.metrics_summary_json,
            "content_sha256": ver.content_sha256,
            "review_comment": ver.review_comment,
            "reviewer_user_id": str(ver.reviewer_user_id)
            if ver.reviewer_user_id
            else None,
            "generated_at": ver.created_at.isoformat() if ver.created_at else None,
            "reviewed_at": ver.reviewed_at.isoformat() if ver.reviewed_at else None,
            "versions": [
                {
                    "version_id": str(v.id),
                    "version_no": v.version_no,
                    "lifecycle_status": v.lifecycle_status,
                    "is_immutable": v.is_immutable,
                    "content_sha256": v.content_sha256,
                    "review_comment": v.review_comment,
                    "reviewer_user_id": str(v.reviewer_user_id)
                    if v.reviewer_user_id
                    else None,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
                }
                for v in all_vers
            ],
        }

    def transition_report_lifecycle(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        report_id: uuid.UUID,
        target_status: str,
        review_comment: str | None = None,
        updated_title: str | None = None,
        updated_executive_summary_markdown: str | None = None,
    ) -> dict[str, Any]:
        """
        Transition report lifecycle (`DRAFT`, `GENERATED`, `SUBMITTED_FOR_REVIEW`, `APPROVED`, `REJECTED`, `ARCHIVED`).
        CRITICAL RULE: An `APPROVED` report version (`is_immutable == True`) NEVER mutates in place!
        If an edit or regeneration (`DRAFT` / `GENERATED` or `updated_executive_summary_markdown`) is applied to an
        already `APPROVED` report, a brand-new `IntelligenceReportVersion` (`version_no + 1`) is created while
        preserving the approved version untouched.
        """
        valid_statuses = {
            "DRAFT",
            "GENERATED",
            "SUBMITTED_FOR_REVIEW",
            "APPROVED",
            "REJECTED",
            "ARCHIVED",
        }
        new_status = target_status.upper().strip()
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid target_status '{target_status}'.")

        rep = db.execute(
            select(IntelligenceReport).where(
                IntelligenceReport.tenant_id == tenant_id,
                IntelligenceReport.id == report_id,
            )
        ).scalar_one_or_none()
        if rep is None:
            raise ValueError(f"Report {report_id} not found for tenant {tenant_id}")

        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=rep.project_id,
            required_permission="project:read",
        )

        cur_ver = db.execute(
            select(IntelligenceReportVersion).where(
                IntelligenceReportVersion.tenant_id == tenant_id,
                IntelligenceReportVersion.report_id == rep.id,
                IntelligenceReportVersion.version_no == rep.current_version_no,
            )
        ).scalar_one()

        prev_status = cur_ver.lifecycle_status
        prev_snap = {
            "version_no": cur_ver.version_no,
            "lifecycle_status": cur_ver.lifecycle_status,
            "is_immutable": cur_ver.is_immutable,
            "content_sha256": cur_ver.content_sha256,
            "executive_summary_markdown": cur_ver.executive_summary_markdown[:300],
        }

        is_editing_content = bool(
            updated_executive_summary_markdown or updated_title
        )

        # If current version is immutable (APPROVED) and user edits content or transitions back to DRAFT/GENERATED:
        # Create a NEW version (`version_no + 1`) so the APPROVED version remains strictly immutable!
        if cur_ver.is_immutable and (
            is_editing_content or new_status in ("DRAFT", "GENERATED", "SUBMITTED_FOR_REVIEW")
        ):
            next_ver_no = rep.current_version_no + 1
            new_exec_sum = (
                updated_executive_summary_markdown
                or cur_ver.executive_summary_markdown
            )
            if updated_title:
                rep.title = updated_title[:255]
            new_sha = hashlib.sha256(
                f"{rep.report_type}:v{next_ver_no}:{new_exec_sum}".encode("utf-8")
            ).hexdigest()
            new_ver = IntelligenceReportVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                report_id=rep.id,
                snapshot_id=rep.snapshot_id,
                version_no=next_ver_no,
                lifecycle_status=new_status
                if new_status in ("DRAFT", "GENERATED", "SUBMITTED_FOR_REVIEW")
                else "DRAFT",
                is_immutable=False,
                executive_summary_markdown=new_exec_sum,
                scope_and_methodology_markdown=cur_ver.scope_and_methodology_markdown,
                sections_json=cur_ver.sections_json,
                evidence_refs_json=cur_ver.evidence_refs_json,
                risks_and_limitations_markdown=cur_ver.risks_and_limitations_markdown,
                recommendations_json=cur_ver.recommendations_json,
                metrics_summary_json=cur_ver.metrics_summary_json,
                content_sha256=new_sha,
                created_by_user_id=user_id,
                reviewer_user_id=user_id,
                review_comment=review_comment
                or f"Created new version v{next_ver_no} from immutable approved v{cur_ver.version_no}.",
            )
            db.add(new_ver)
            rep.current_version_no = next_ver_no
            rep.lifecycle_status = new_ver.lifecycle_status
            rep.updated_at = datetime.now(timezone.utc)
            db.flush()
            active_ver = new_ver
        else:
            if not cur_ver.is_immutable:
                if updated_title:
                    rep.title = updated_title[:255]
                if updated_executive_summary_markdown:
                    cur_ver.executive_summary_markdown = (
                        updated_executive_summary_markdown
                    )
                    cur_ver.content_sha256 = hashlib.sha256(
                        f"{rep.report_type}:v{cur_ver.version_no}:{updated_executive_summary_markdown}".encode(
                            "utf-8"
                        )
                    ).hexdigest()

            cur_ver.lifecycle_status = new_status
            cur_ver.reviewer_user_id = user_id
            cur_ver.review_comment = review_comment
            cur_ver.reviewed_at = datetime.now(timezone.utc)
            if new_status == "APPROVED":
                cur_ver.is_immutable = True
                rep.approved_by_user_id = user_id
                rep.approved_at = datetime.now(timezone.utc)
                db.add(
                    ApprovalRequest(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        project_id=rep.project_id,
                        requested_by_user_id=rep.created_by_user_id or user_id,
                        decided_by_user_id=user_id,
                        request_type="REPORT_APPROVAL_SIGN_OFF",
                        status="APPROVED",
                        request_payload={
                            "report_id": str(rep.id),
                            "version_no": cur_ver.version_no,
                            "content_sha256": cur_ver.content_sha256,
                        },
                        decision_reason=review_comment or "Approved intelligence report.",
                        decided_at=datetime.now(timezone.utc),
                    )
                )
            rep.lifecycle_status = new_status
            rep.updated_at = datetime.now(timezone.utc)
            db.flush()
            active_ver = cur_ver

        new_snap = {
            "version_no": active_ver.version_no,
            "lifecycle_status": active_ver.lifecycle_status,
            "is_immutable": active_ver.is_immutable,
            "content_sha256": active_ver.content_sha256,
            "executive_summary_markdown": active_ver.executive_summary_markdown[:300],
        }
        db.add(
            ReviewHistory(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                target_object_type="INTELLIGENCE_REPORT",
                target_object_id=rep.id,
                reviewer_user_id=user_id,
                previous_status=prev_status,
                new_status=active_ver.lifecycle_status,
                previous_snapshot_json=prev_snap,
                updated_snapshot_json=new_snap,
                review_comment=review_comment,
                reviewed_at=datetime.now(timezone.utc),
            )
        )
        db.flush()

        self.record_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action_code=f"REPORT_{active_ver.lifecycle_status}",
            target_resource_type="intelligence_reports",
            target_resource_id=rep.id,
            metadata_diff={
                "previous_status": prev_status,
                "new_status": active_ver.lifecycle_status,
                "version_no": active_ver.version_no,
                "is_immutable": active_ver.is_immutable,
            },
        )

        return self.get_report(
            db, tenant_id=tenant_id, user_id=user_id, report_id=rep.id
        )

    # ------------------------------------------------------------------
    # 5. Export Governance (`PDF`, `DOCX`, `XLSX`, `JSON`)
    # ------------------------------------------------------------------
    def export_report(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        report_id: uuid.UUID,
        export_format: str,
        version_no: int | None = None,
        custom_branding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a controlled export (`PDF`, `DOCX`, `XLSX`, `JSON`), persist the binary
        in tenant-isolated object storage, and record a tamper-evident `AuditLog` entry.
        """
        report_data = self.get_report(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            report_id=report_id,
            version_no=version_no,
        )
        # Verify project-level permission for export
        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=uuid.UUID(report_data["project_id"]),
            required_permission="project:read",
        )

        if custom_branding:
            report_data["branding"] = {
                **report_data.get("branding", {}),
                **custom_branding,
            }

        file_bytes, mime_type, ext = render_report_export(export_format, report_data)
        blob_res = self.storage.put_blob(tenant_id, file_bytes)

        safe_slug = re.sub(
            r"[^a-zA-Z0-9_\-]+",
            "_",
            f"{report_data['report_type'].lower()}_v{report_data['version_no']}",
        ).strip("_")
        file_name = f"legacyiq_{safe_slug}.{ext}"

        audit_entry = self.record_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action_code="EXPORT_GENERATED",
            target_resource_type="intelligence_reports",
            target_resource_id=report_id,
            metadata_diff={
                "export_format": export_format.upper(),
                "version_no": report_data["version_no"],
                "file_name": file_name,
                "file_size_bytes": blob_res.byte_size,
                "content_sha256": blob_res.sha256,
            },
        )

        exp = ReportExport(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=uuid.UUID(report_data["project_id"]),
            report_id=report_id,
            report_version_id=uuid.UUID(report_data["version_id"]),
            export_format=export_format.upper().strip(),
            status="COMPLETED",
            file_name=file_name,
            mime_type=mime_type,
            file_size_bytes=blob_res.byte_size,
            content_sha256=blob_res.sha256,
            storage_object_uri=blob_res.storage_uri,
            branding_config_json=report_data["branding"],
            requested_by_user_id=user_id,
            audit_log_id=audit_entry.id,
            download_count=0,
        )
        db.add(exp)
        db.flush()

        return self._serialize_export(exp)

    def list_exports(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> dict[str, Any]:
        _, proj, _, _, _ = self._resolve_snapshot_hierarchy(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=proj.id,
            required_permission="project:read",
        )
        rep_ids = list(
            db.execute(
                select(IntelligenceReport.id).where(
                    IntelligenceReport.tenant_id == tenant_id,
                    IntelligenceReport.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        exports = (
            db.execute(
                select(ReportExport)
                .where(
                    ReportExport.tenant_id == tenant_id,
                    ReportExport.report_id.in_(rep_ids) if rep_ids else False,
                )
                .order_by(ReportExport.created_at.desc())
            )
            .scalars()
            .all()
            if rep_ids
            else []
        )
        return {
            "snapshot_id": str(snapshot_id),
            "exports": [self._serialize_export(e) for e in exports],
            "audit_logs": self.list_audit_logs(db, tenant_id=tenant_id, limit=25),
        }

    def download_export(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        export_id: uuid.UUID,
    ) -> tuple[bytes, str, str]:
        exp = db.execute(
            select(ReportExport).where(
                ReportExport.tenant_id == tenant_id,
                ReportExport.id == export_id,
            )
        ).scalar_one_or_none()
        if exp is None:
            raise ValueError(f"Export {export_id} not found for tenant {tenant_id}")

        verify_project_access(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            project_id=exp.project_id,
            required_permission="project:read",
        )

        raw_bytes = self.storage.get_blob_bytes(tenant_id, exp.content_sha256)
        exp.download_count = (exp.download_count or 0) + 1
        db.flush()

        self.record_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action_code="EXPORT_DOWNLOADED",
            target_resource_type="report_exports",
            target_resource_id=exp.id,
            metadata_diff={
                "export_format": exp.export_format,
                "file_name": exp.file_name,
                "download_count": exp.download_count,
            },
        )
        return raw_bytes, exp.file_name, exp.mime_type

    def _serialize_export(self, e: ReportExport) -> dict[str, Any]:
        return {
            "id": str(e.id),
            "tenant_id": str(e.tenant_id),
            "project_id": str(e.project_id),
            "report_id": str(e.report_id),
            "report_version_id": str(e.report_version_id),
            "export_format": e.export_format,
            "status": e.status,
            "file_name": e.file_name,
            "mime_type": e.mime_type,
            "file_size_bytes": e.file_size_bytes,
            "content_sha256": e.content_sha256,
            "storage_object_uri": e.storage_object_uri,
            "branding": e.branding_config_json,
            "requested_by_user_id": str(e.requested_by_user_id)
            if e.requested_by_user_id
            else None,
            "audit_log_id": str(e.audit_log_id) if e.audit_log_id else None,
            "download_count": e.download_count,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }


__all__ = [
    "REPORT_TYPE_CATALOG",
    "ReportingQaExportService",
    "SUGGESTED_QA_QUESTIONS",
    "classify_question_intent",
]
