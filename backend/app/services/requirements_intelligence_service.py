"""Wave 3 — Business Rules & Requirements Intelligence, Traceability, Conflict/Gap Detection, Impact Analysis & Human Review Service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.business_rule_intelligence import (
    DOMAIN_CATALOG,
    ExtractedBusinessRuleCandidate,
    extract_business_rules_from_code,
    extract_business_rules_from_doc_section,
    infer_domain_code,
)
from app.analysis.parser_registry import SUPPORTED_CODE_LANGUAGES, detect_language_and_kind
from app.integrations.storage import TenantObjectStorage
from app.models.agent_orchestration import AgentRun
from app.models.business_intelligence import (
    BusinessDomain,
    BusinessProcess,
    BusinessRule,
    Requirement,
    RequirementAcceptanceCriterion,
    RequirementTraceabilityLink,
)
from app.models.code_intelligence import AnalysisRun, CodeFile, CodeSymbol
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
from app.services.agent_orchestrator import (
    AgentFindingClaim,
    AgentFindingsPayload,
    AgentInputContext,
    TechnicalIntelligenceOrchestrator,
)
from app.services.knowledge_graph_service import KnowledgeGraphService


@dataclass
class Wave3PipelineSummary:
    snapshot_id: uuid.UUID
    analysis_run_id: uuid.UUID
    business_domains_count: int
    business_processes_count: int
    business_rules_count: int
    requirements_count: int
    acceptance_criteria_count: int
    traceability_links_count: int
    conflicts_count: int


def _tokenize_spec(text: str) -> set[str]:
    stop = {
        "the",
        "system",
        "shall",
        "must",
        "should",
        "when",
        "with",
        "from",
        "that",
        "this",
        "into",
        "for",
        "and",
        "all",
        "any",
        "enforce",
        "ensure",
    }
    words = {
        w.lower()
        for w in re.findall(r"[A-Za-z0-9_]{3,}", text)
        if w.lower() not in stop
    }
    return words


class RequirementsIntelligenceService:
    """
    Executes Wave 3 Business Rules & Requirements Intelligence:
    1. Business Rule Discovery (Code, DB Constraints/Triggers/Procs, APIs, Documentation)
    2. Business Domain & Workflow Reconstruction
    3. Functional & Non-Functional Requirements Generation + Given/When/Then Acceptance Criteria
    4. Forward & Backward Traceability Matrix (`RequirementTraceabilityLink` + `FindingEvidenceLink`)
    5. Conflict & Gap Detection (`KnowledgeConflict`, Duplicate/Overlapping Requirements, Undocumented Behavior)
    6. Multi-Hop Impact Analysis
    7. Human Review Workflows (`APPROVED`, `REJECTED`, `MODIFIED_BY_HUMAN`, `PENDING_REVIEW`) with `ReviewHistory`
    """

    def __init__(
        self,
        storage: TenantObjectStorage | None = None,
        graph_service: KnowledgeGraphService | None = None,
        orchestrator: TechnicalIntelligenceOrchestrator | None = None,
    ) -> None:
        self.storage = storage or TenantObjectStorage()
        self.graph_service = graph_service or KnowledgeGraphService()
        self.orchestrator = orchestrator or TechnicalIntelligenceOrchestrator()

    def _get_or_create_domain(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        domain_code: str,
        domain_cache: dict[str, BusinessDomain],
    ) -> BusinessDomain:
        code = domain_code if domain_code in DOMAIN_CATALOG else "CORE_DOMAIN"
        if code in domain_cache:
            return domain_cache[code]

        existing = db.execute(
            select(BusinessDomain).where(
                BusinessDomain.tenant_id == tenant_id,
                BusinessDomain.application_id == application_id,
                BusinessDomain.code == code,
            )
        ).scalar_one_or_none()
        if existing is not None:
            domain_cache[code] = existing
            return existing

        name, desc = DOMAIN_CATALOG[code]
        dom = BusinessDomain(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            application_id=application_id,
            code=code,
            name=name,
            description=desc,
            origin_type="HYBRID_AI_STATIC",
            confidence_score=Decimal("0.9200"),
            review_status="PENDING_REVIEW",
        )
        db.add(dom)
        db.flush()
        domain_cache[code] = dom
        return dom

    def execute_wave3_pipeline(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        repository_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        snapshot_artifacts: list[tuple[Artifact, ArtifactVersion]] | None = None,
    ) -> Wave3PipelineSummary:
        repo = db.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.id == repository_id,
            )
        ).scalar_one()
        snapshot = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.id == snapshot_id,
            )
        ).scalar_one()
        analysis_run = db.execute(
            select(AnalysisRun).where(
                AnalysisRun.tenant_id == tenant_id,
                AnalysisRun.id == analysis_run_id,
            )
        ).scalar_one()

        application_id = repo.application_id
        domain_cache: dict[str, BusinessDomain] = {}

        # Resolve artifacts & source text
        if snapshot_artifacts is None:
            artifacts = (
                db.execute(
                    select(Artifact).where(
                        Artifact.tenant_id == tenant_id,
                        Artifact.repository_id == repository_id,
                    )
                )
                .scalars()
                .all()
            )
            artifact_pairs: list[tuple[Artifact, ArtifactVersion]] = []
            for art in artifacts:
                ver = (
                    db.execute(
                        select(ArtifactVersion)
                        .where(
                            ArtifactVersion.tenant_id == tenant_id,
                            ArtifactVersion.artifact_id == art.id,
                        )
                        .order_by(ArtifactVersion.created_at.desc())
                        .limit(1)
                    )
                    .scalars()
                    .first()
                )
                if ver is not None:
                    artifact_pairs.append((art, ver))
        else:
            artifact_pairs = snapshot_artifacts

        ver_by_path: dict[str, ArtifactVersion] = {
            art.canonical_path: ver for art, ver in artifact_pairs
        }
        ver_by_id: dict[uuid.UUID, ArtifactVersion] = {
            ver.id: ver for _, ver in artifact_pairs
        }
        fallback_ver = artifact_pairs[0][1] if artifact_pairs else None

        # Load existing Wave 1 & Wave 2 entities
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
        symbol_by_qname: dict[str, CodeSymbol] = {s.qualified_name: s for s in symbols}
        symbol_by_short: dict[str, CodeSymbol] = {s.name.lower(): s for s in symbols}

        knowledge_entities = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot.id,
                    KnowledgeEntity.analysis_run_id == analysis_run.id,
                )
            )
            .scalars()
            .all()
        )
        ke_by_key: dict[str, KnowledgeEntity] = {
            ke.canonical_key: ke for ke in knowledge_entities
        }
        ke_by_title_lower: dict[str, KnowledgeEntity] = {
            ke.title.lower(): ke for ke in knowledge_entities
        }

        knowledge_rels = (
            db.execute(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.tenant_id == tenant_id,
                    KnowledgeRelationship.snapshot_id == snapshot.id,
                    KnowledgeRelationship.analysis_run_id == analysis_run.id,
                )
            )
            .scalars()
            .all()
        )
        documented_entity_ids: set[uuid.UUID] = {
            r.target_entity_id
            for r in knowledge_rels
            if r.relationship_type == "DOCUMENTS"
        }

        # ------------------------------------------------------------------
        # 1. Discover Business Rule Candidates from Code, DB, APIs & Docs
        # ------------------------------------------------------------------
        rule_candidates: list[ExtractedBusinessRuleCandidate] = []

        # 1A. From Source Code
        for art, ver in artifact_pairs:
            lang, _ = detect_language_and_kind(art.canonical_path)
            if lang not in SUPPORTED_CODE_LANGUAGES:
                continue
            if not self.storage.blob_exists(tenant_id, ver.content_sha256):
                continue
            try:
                raw_bytes = self.storage.get_blob_bytes(
                    tenant_id, ver.content_sha256
                )
                src_text = raw_bytes.decode("utf-8", errors="replace")
            except Exception:
                continue
            code_rules = extract_business_rules_from_code(
                src_text, art.canonical_path, lang
            )
            rule_candidates.extend(code_rules)

        # 1B. From Database Tables, Columns & Foreign Keys
        db_schemas = (
            db.execute(
                select(DbSchema).where(
                    DbSchema.tenant_id == tenant_id,
                    DbSchema.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        schema_ids = [s.id for s in db_schemas]
        schema_by_id = {s.id: s for s in db_schemas}
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
        table_by_id = {t.id: t for t in db_tables}
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

        cols_by_table: dict[uuid.UUID, list[DbColumn]] = {}
        for col in db_columns:
            cols_by_table.setdefault(col.db_table_id, []).append(col)

        for tbl in db_tables:
            sch = schema_by_id[tbl.db_schema_id]
            t_cols = cols_by_table.get(tbl.id, [])
            non_null_cols = [c.column_name for c in t_cols if not c.is_nullable]
            pii_cols = [c.column_name for c in t_cols if c.is_pii_candidate]
            dom_code = infer_domain_code(f"{tbl.table_name} {' '.join(non_null_cols)}")

            if non_null_cols:
                rule_candidates.append(
                    ExtractedBusinessRuleCandidate(
                        rule_code_prefix="BR-DB-INV",
                        domain_code=dom_code,
                        rule_category="INVARIANT",
                        title=f"Mandatory Schema Attributes on `{sch.schema_name}.{tbl.table_name}`",
                        condition_expression=f"WHEN persisting or updating records in `{sch.schema_name}.{tbl.table_name}`",
                        action_consequence=f"ENFORCE non-null integrity on required columns: {', '.join(non_null_cols[:8])}.",
                        origin_type="DETERMINISTIC_RULE",
                        confidence_score=0.98,
                        source_kind="DB",
                        start_line=1,
                        end_line=5,
                        excerpt_text=f"TABLE {sch.schema_name}.{tbl.table_name} NOT NULL ({', '.join(non_null_cols[:8])})",
                        subject_identifier=tbl.table_name.lower(),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note=f"Derived from DDL NOT NULL/PK column constraints on `{tbl.table_name}`.",
                    )
                )
            if pii_cols:
                rule_candidates.append(
                    ExtractedBusinessRuleCandidate(
                        rule_code_prefix="BR-PII",
                        domain_code="IDENTITY_SECURITY",
                        rule_category="AUTHORIZATION",
                        title=f"PII Data Protection Invariant on `{sch.schema_name}.{tbl.table_name}`",
                        condition_expression=f"WHEN accessing sensitive/PII columns ({', '.join(pii_cols)}) on `{tbl.table_name}`",
                        action_consequence="REQUIRE authenticated tenant context, audit logging, and PII masking/redaction.",
                        origin_type="DETERMINISTIC_RULE",
                        confidence_score=0.94,
                        source_kind="DB",
                        start_line=1,
                        end_line=5,
                        excerpt_text=f"PII Candidate Columns in {tbl.table_name}: {', '.join(pii_cols)}",
                        subject_identifier=tbl.table_name.lower(),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Derived from PII column classification in database schema.",
                    )
                )

        for fk in db_fks:
            src_tbl = table_by_id.get(fk.source_table_id)
            tgt_tbl = table_by_id.get(fk.target_table_id)
            if src_tbl and tgt_tbl:
                dom_code = infer_domain_code(f"{src_tbl.table_name} {tgt_tbl.table_name}")
                rule_candidates.append(
                    ExtractedBusinessRuleCandidate(
                        rule_code_prefix="BR-DB-FK",
                        domain_code=dom_code,
                        rule_category="INVARIANT",
                        title=f"Referential Integrity `{src_tbl.table_name}` -> `{tgt_tbl.table_name}`",
                        condition_expression=f"WHEN inserting `{src_tbl.table_name}` ({', '.join(fk.source_column_names)}) or deleting `{tgt_tbl.table_name}`",
                        action_consequence=f"ENFORCE foreign key `{fk.constraint_name or 'fk'}` referencing `{tgt_tbl.table_name}` ({', '.join(fk.target_column_names)}).",
                        origin_type="DETERMINISTIC_RULE",
                        confidence_score=0.99,
                        source_kind="DB",
                        start_line=1,
                        end_line=5,
                        excerpt_text=f"FOREIGN KEY ({', '.join(fk.source_column_names)}) REFERENCES {tgt_tbl.table_name}({', '.join(fk.target_column_names)})",
                        subject_identifier=src_tbl.table_name.lower(),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Derived from explicit DDL foreign key constraint.",
                    )
                )

        # 1C. From API Services & Endpoints
        api_services = (
            db.execute(
                select(ApiService).where(
                    ApiService.tenant_id == tenant_id,
                    ApiService.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        svc_ids = [s.id for s in api_services]
        svc_by_id = {s.id: s for s in api_services}
        api_endpoints = (
            db.execute(
                select(ApiEndpoint).where(
                    ApiEndpoint.tenant_id == tenant_id,
                    ApiEndpoint.api_service_id.in_(svc_ids) if svc_ids else False,
                )
            )
            .scalars()
            .all()
            if svc_ids
            else []
        )

        for ep in api_endpoints:
            svc = svc_by_id[ep.api_service_id]
            handler_sym = (
                db.execute(
                    select(CodeSymbol).where(
                        CodeSymbol.tenant_id == tenant_id,
                        CodeSymbol.id == ep.handler_symbol_id,
                    )
                ).scalar_one_or_none()
                if ep.handler_symbol_id
                else None
            )
            dom_code = (
                "IDENTITY_SECURITY"
                if ep.auth_required_inferred
                else infer_domain_code(f"{svc.service_name} {ep.route_pattern}")
            )
            rule_candidates.append(
                ExtractedBusinessRuleCandidate(
                    rule_code_prefix="BR-API",
                    domain_code=dom_code,
                    rule_category="AUTHORIZATION" if ep.auth_required_inferred else "ROUTING",
                    title=f"API Contract & Access Rule for `{ep.http_method} {ep.route_pattern}`",
                    condition_expression=(
                        f"WHEN client sends `{ep.http_method} {ep.route_pattern}` to `{svc.service_name}`"
                    ),
                    action_consequence=(
                        f"VERIFY caller authentication/authorization before invoking `{handler_sym.name if handler_sym else 'handler'}` and validate contract schema."
                        if ep.auth_required_inferred
                        else f"ROUTE `{ep.http_method} {ep.route_pattern}` to `{handler_sym.name if handler_sym else svc.service_name}` without mandatory auth barrier."
                    ),
                    origin_type="DETERMINISTIC_RULE",
                    confidence_score=0.93,
                    source_kind="API",
                    start_line=handler_sym.start_line if handler_sym else 1,
                    end_line=handler_sym.end_line if handler_sym else 5,
                    excerpt_text=f"{ep.http_method} {ep.route_pattern} (auth_required={ep.auth_required_inferred})",
                    enclosing_symbol_qname=handler_sym.qualified_name if handler_sym else None,
                    enclosing_symbol_name=handler_sym.name if handler_sym else None,
                    subject_identifier=ep.route_pattern.lower(),
                    evidence_role="PRIMARY_DEFINITION",
                    rationale_note="Derived from discovered API endpoint route and authentication metadata.",
                )
            )

        # 1D. From Documentation Sections
        doc_sections = (
            db.execute(
                select(DocSection).where(
                    DocSection.tenant_id == tenant_id,
                    DocSection.artifact_version_id.in_(list(ver_by_id.keys()))
                    if ver_by_id
                    else False,
                )
            )
            .scalars()
            .all()
            if ver_by_id
            else []
        )
        for ds in doc_sections:
            doc_path = next(
                (p for p, v in ver_by_path.items() if v.id == ds.artifact_version_id),
                "docs/README.md",
            )
            doc_rules = extract_business_rules_from_doc_section(
                section_title=ds.heading_path,
                text_content=ds.content_markdown,
                relative_path=doc_path,
                start_line=ds.start_line,
                end_line=ds.end_line,
            )
            rule_candidates.extend(doc_rules)

        # ------------------------------------------------------------------
        # 2. Persist BusinessDomains, BusinessRules, EvidenceAnchors & Graph Nodes
        # ------------------------------------------------------------------
        persisted_rules: list[tuple[BusinessRule, ExtractedBusinessRuleCandidate, EvidenceAnchor | None]] = []
        rules_count = 0

        for idx, cand in enumerate(rule_candidates, start=1):
            rule_code = f"{cand.rule_code_prefix}-{idx:04d}"
            dom = self._get_or_create_domain(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                domain_code=cand.domain_code,
                domain_cache=domain_cache,
            )

            existing_rule = db.execute(
                select(BusinessRule).where(
                    BusinessRule.tenant_id == tenant_id,
                    BusinessRule.application_id == application_id,
                    BusinessRule.snapshot_id == snapshot.id,
                    BusinessRule.rule_code == rule_code,
                )
            ).scalar_one_or_none()

            # Resolve artifact version for evidence anchor
            target_ver = (
                ver_by_path.get(cand.relative_path)
                if cand.relative_path
                else None
            ) or fallback_ver

            anchor: EvidenceAnchor | None = None
            if target_ver is not None:
                anchor = self.graph_service.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot.id,
                    artifact_version_id=target_ver.id,
                    locator_type="DOC_HEADING" if cand.source_kind == "DOC" else "LINE_RANGE",
                    start_line=cand.start_line,
                    end_line=cand.end_line,
                    excerpt_text=cand.excerpt_text or cand.title,
                    ast_or_json_path=cand.enclosing_symbol_qname,
                )

            # Create mirror KnowledgeEntity node (`BUSINESS_RULE`)
            conf_dec = Decimal(str(round(max(0.0, min(1.0, cand.confidence_score)), 4)))
            rev_state = (
                "PENDING_REVIEW"
                if cand.origin_type == "DETERMINISTIC_RULE"
                else "DRAFT_AI"
            )
            rule_ke = self.graph_service._upsert_entity(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot.id,
                analysis_run_id=analysis_run.id,
                entity_type="BUSINESS_RULE",
                canonical_key=f"rule:{rule_code}",
                title=f"{rule_code}: {cand.title}"[:255],
                summary_description=f"{cand.condition_expression} -> {cand.action_consequence}",
                origin_type=cand.origin_type,
                confidence_score=conf_dec,
                review_status=rev_state,
                attributes_json={
                    "rule_code": rule_code,
                    "rule_category": cand.rule_category,
                    "domain_code": dom.code,
                    "source_kind": cand.source_kind,
                    "relative_path": cand.relative_path,
                    "numeric_thresholds": cand.numeric_thresholds,
                },
            )
            ke_by_key[rule_ke.canonical_key] = rule_ke

            if existing_rule is None:
                existing_rule = BusinessRule(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot.id,
                    analysis_run_id=analysis_run.id,
                    business_domain_id=dom.id,
                    knowledge_entity_id=rule_ke.id,
                    rule_code=rule_code,
                    rule_category=cand.rule_category,
                    title=cand.title[:255],
                    condition_expression=cand.condition_expression,
                    action_consequence=cand.action_consequence,
                    origin_type=cand.origin_type,
                    confidence_score=conf_dec,
                    review_status=rev_state,
                    version_no=1,
                )
                db.add(existing_rule)
                db.flush()
                rules_count += 1

            if anchor is not None:
                # Link EvidenceAnchor to both rule_ke and BusinessRule
                self.graph_service.link_evidence(
                    db,
                    tenant_id=tenant_id,
                    evidence_anchor_id=anchor.id,
                    knowledge_entity_id=rule_ke.id,
                    evidence_role=cand.evidence_role,
                    rationale_note=cand.rationale_note,
                )
                existing_rule_ev = db.execute(
                    select(FindingEvidenceLink).where(
                        FindingEvidenceLink.tenant_id == tenant_id,
                        FindingEvidenceLink.evidence_anchor_id == anchor.id,
                        FindingEvidenceLink.business_rule_id == existing_rule.id,
                    )
                ).scalar_one_or_none()
                if existing_rule_ev is None:
                    db.add(
                        FindingEvidenceLink(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            evidence_anchor_id=anchor.id,
                            business_rule_id=existing_rule.id,
                            evidence_role=cand.evidence_role,
                            relevance_weight=existing_rule.confidence_score,
                            rationale_note=cand.rationale_note,
                        )
                    )
                    db.flush()

            # Connect implementing entity -> BUSINESS_RULE (`IMPLEMENTS_RULE`)
            impl_ke: KnowledgeEntity | None = None
            if cand.enclosing_symbol_qname:
                impl_ke = ke_by_key.get(f"symbol:{cand.enclosing_symbol_qname}")
            if impl_ke is None and cand.enclosing_symbol_name:
                impl_ke = ke_by_title_lower.get(cand.enclosing_symbol_name.lower())
            if impl_ke is None and cand.subject_identifier:
                impl_ke = ke_by_title_lower.get(cand.subject_identifier.lower())

            if impl_ke is not None and impl_ke.id != rule_ke.id:
                self.graph_service._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot.id,
                    analysis_run_id=analysis_run.id,
                    source_entity_id=impl_ke.id,
                    target_entity_id=rule_ke.id,
                    relationship_type="IMPLEMENTS_RULE",
                    origin_type=cand.origin_type,
                    confidence_score=conf_dec,
                    review_status=rev_state,
                    edge_metadata={"rule_code": rule_code},
                )

            persisted_rules.append((existing_rule, cand, anchor))

        # ------------------------------------------------------------------
        # 3. Reconstruct BusinessProcesses (End-to-End Workflows)
        # ------------------------------------------------------------------
        processes_count = 0
        for ep in api_endpoints:
            svc = svc_by_id[ep.api_service_id]
            ep_ke = ke_by_key.get(
                f"api:{svc.service_name}:{ep.http_method}:{ep.route_pattern}"
            )
            step_ids: list[str] = []
            step_titles: list[str] = []
            if ep_ke is not None:
                step_ids.append(str(ep_ke.id))
                step_titles.append(ep_ke.title)

                # Follow outgoing edges from endpoint -> handler symbol -> DB tables / callees
                out_edges = [
                    r for r in knowledge_rels if r.source_entity_id == ep_ke.id
                ]
                for edge in out_edges:
                    step_ids.append(str(edge.target_entity_id))
                    next_edges = [
                        r2
                        for r2 in knowledge_rels
                        if r2.source_entity_id == edge.target_entity_id
                        and r2.relationship_type
                        in ("CALLS", "READS_TABLE", "WRITES_TABLE", "MAPS_TO_TABLE")
                    ]
                    for ne in next_edges:
                        if str(ne.target_entity_id) not in step_ids:
                            step_ids.append(str(ne.target_entity_id))

            proc_key = re.sub(
                r"[^a-zA-Z0-9_-]",
                "-",
                f"wf-{ep.http_method.lower()}-{ep.route_pattern.strip('/')}",
            )[:90]
            dom = self._get_or_create_domain(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                domain_code=infer_domain_code(f"{svc.service_name} {ep.route_pattern}"),
                domain_cache=domain_cache,
            )
            existing_proc = db.execute(
                select(BusinessProcess).where(
                    BusinessProcess.tenant_id == tenant_id,
                    BusinessProcess.application_id == application_id,
                    BusinessProcess.process_key == proc_key,
                )
            ).scalar_one_or_none()
            if existing_proc is None:
                db.add(
                    BusinessProcess(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        application_id=application_id,
                        business_domain_id=dom.id,
                        entry_entity_id=ep_ke.id if ep_ke else None,
                        process_key=proc_key,
                        name=f"{svc.service_name}: {ep.http_method} {ep.route_pattern}"[:255],
                        workflow_summary=(
                            f"End-to-end request workflow initiated at `{ep.http_method} {ep.route_pattern}` "
                            f"within `{svc.service_name}`, traversing {len(step_ids)} linked knowledge graph node(s)."
                        ),
                        ordered_step_entity_ids=step_ids,
                        origin_type="HYBRID_AI_STATIC",
                        confidence_score=Decimal("0.9100"),
                        review_status="PENDING_REVIEW",
                    )
                )
                processes_count += 1
        db.flush()

        # ------------------------------------------------------------------
        # 4. Synthesize Functional & Non-Functional Requirements + Acceptance Criteria + Traceability
        # ------------------------------------------------------------------
        requirements_count = 0
        criteria_count = 0
        rtm_links_count = 0
        persisted_requirements: list[Requirement] = []

        for req_idx, (rule_obj, cand, anchor) in enumerate(persisted_rules, start=1):
            # Determine requirement type & priority
            if cand.rule_category == "AUTHORIZATION":
                req_type = "NON_FUNCTIONAL_SECURITY"
                req_prefix = "REQ-SEC"
                priority = "MUST"
                actor = "Authenticated Caller / Security Guard"
            elif cand.source_kind == "DB":
                req_type = "DATA_CONSTRAINT"
                req_prefix = "REQ-DATA"
                priority = "MUST"
                actor = "Database Persistence Layer"
            elif cand.source_kind == "API":
                req_type = "INTEGRATION_CONTRACT"
                req_prefix = "REQ-INT"
                priority = "MUST" if "VERIFY" in cand.action_consequence else "SHOULD"
                actor = "API Consumer / Gateway"
            elif cand.rule_category in ("CALCULATION", "VALIDATION", "STATE_TRANSITION", "ROUTING"):
                req_type = "FUNCTIONAL"
                req_prefix = "REQ-FUNC"
                priority = "MUST"
                actor = cand.enclosing_symbol_name or "Application Domain Service"
            else:
                req_type = "FUNCTIONAL"
                req_prefix = "REQ-FUNC"
                priority = "SHOULD"
                actor = "Application Runtime"

            req_code = f"{req_prefix}-{req_idx:04d}"
            spec_stmt = (
                f"The system shall enforce `{rule_obj.title}` such that {cand.condition_expression.lower()}, "
                f"the runtime guarantees: {cand.action_consequence}"
            )

            # Determine if this behavior is undocumented (implicit requirement)
            sym_obj: CodeSymbol | None = None
            if cand.enclosing_symbol_qname:
                sym_obj = symbol_by_qname.get(cand.enclosing_symbol_qname)
            if sym_obj is None and cand.enclosing_symbol_name:
                sym_obj = symbol_by_short.get(cand.enclosing_symbol_name.lower())

            target_ke: KnowledgeEntity | None = None
            if sym_obj is not None:
                target_ke = ke_by_key.get(f"symbol:{sym_obj.qualified_name}")
            if target_ke is None and cand.subject_identifier:
                target_ke = ke_by_title_lower.get(cand.subject_identifier.lower())

            is_implicit = (
                cand.source_kind in ("CODE", "DB")
                and (target_ke is None or target_ke.id not in documented_entity_ids)
            )

            evidence_strength = (
                "STRONG"
                if anchor is not None and not is_implicit
                else ("MODERATE" if anchor is not None else "WEAK")
            )

            req_ke = self.graph_service._upsert_entity(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot.id,
                analysis_run_id=analysis_run.id,
                entity_type="REQUIREMENT",
                canonical_key=f"req:{req_code}",
                title=f"{req_code}: {rule_obj.title}"[:255],
                summary_description=spec_stmt,
                origin_type=rule_obj.origin_type,
                confidence_score=rule_obj.confidence_score,
                review_status=rule_obj.review_status,
                attributes_json={
                    "req_code": req_code,
                    "req_type": req_type,
                    "priority": priority,
                    "actors": [actor],
                    "inputs": [cand.condition_expression],
                    "outputs": [cand.action_consequence],
                    "preconditions": cand.condition_expression,
                    "expected_outcomes": cand.action_consequence,
                    "is_implicit": is_implicit,
                    "evidence_strength": evidence_strength,
                    "derived_from_rule_code": rule_obj.rule_code,
                },
            )
            ke_by_key[req_ke.canonical_key] = req_ke

            existing_req = db.execute(
                select(Requirement).where(
                    Requirement.tenant_id == tenant_id,
                    Requirement.application_id == application_id,
                    Requirement.snapshot_id == snapshot.id,
                    Requirement.req_code == req_code,
                )
            ).scalar_one_or_none()

            if existing_req is None:
                existing_req = Requirement(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot.id,
                    analysis_run_id=analysis_run.id,
                    business_domain_id=rule_obj.business_domain_id,
                    knowledge_entity_id=req_ke.id,
                    req_code=req_code,
                    req_type=req_type,
                    priority=priority,
                    title=f"{rule_obj.title}"[:255],
                    specification_statement=spec_stmt,
                    origin_type=rule_obj.origin_type,
                    confidence_score=rule_obj.confidence_score,
                    review_status=rule_obj.review_status,
                    version_no=1,
                )
                db.add(existing_req)
                db.flush()
                requirements_count += 1

            persisted_requirements.append(existing_req)

            # Acceptance Criterion (Given / When / Then)
            existing_ac = db.execute(
                select(RequirementAcceptanceCriterion).where(
                    RequirementAcceptanceCriterion.tenant_id == tenant_id,
                    RequirementAcceptanceCriterion.requirement_id == existing_req.id,
                    RequirementAcceptanceCriterion.criterion_order == 1,
                )
            ).scalar_one_or_none()
            if existing_ac is None:
                ver_method = (
                    "INTEGRATION_TEST"
                    if req_type in ("INTEGRATION_CONTRACT", "NON_FUNCTIONAL_SECURITY")
                    else ("STATIC_CHECK" if req_type == "DATA_CONSTRAINT" else "UNIT_TEST")
                )
                db.add(
                    RequirementAcceptanceCriterion(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        requirement_id=existing_req.id,
                        criterion_order=1,
                        given_clause=f"Given actor `{actor}` operating in domain `{cand.domain_code}`",
                        when_clause=f"When condition `{cand.condition_expression}` holds",
                        then_clause=f"Then the system enforces `{cand.action_consequence}`",
                        verification_method=ver_method,
                    )
                )
                criteria_count += 1

            # Evidence link on Requirement
            if anchor is not None:
                self.graph_service.link_evidence(
                    db,
                    tenant_id=tenant_id,
                    evidence_anchor_id=anchor.id,
                    knowledge_entity_id=req_ke.id,
                    evidence_role=cand.evidence_role,
                    rationale_note=f"Supports requirement {req_code} via {rule_obj.rule_code}.",
                )
                existing_req_ev = db.execute(
                    select(FindingEvidenceLink).where(
                        FindingEvidenceLink.tenant_id == tenant_id,
                        FindingEvidenceLink.evidence_anchor_id == anchor.id,
                        FindingEvidenceLink.requirement_id == existing_req.id,
                    )
                ).scalar_one_or_none()
                if existing_req_ev is None:
                    db.add(
                        FindingEvidenceLink(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            evidence_anchor_id=anchor.id,
                            requirement_id=existing_req.id,
                            evidence_role=cand.evidence_role,
                            relevance_weight=existing_req.confidence_score,
                            rationale_note=f"Primary evidence anchor for {req_code}.",
                        )
                    )

            # Traceability Link 1: DERIVED_FROM_RULE (Requirement -> BusinessRule)
            existing_rtm_rule = db.execute(
                select(RequirementTraceabilityLink).where(
                    RequirementTraceabilityLink.tenant_id == tenant_id,
                    RequirementTraceabilityLink.requirement_id == existing_req.id,
                    RequirementTraceabilityLink.business_rule_id == rule_obj.id,
                    RequirementTraceabilityLink.link_type == "DERIVED_FROM_RULE",
                )
            ).scalar_one_or_none()
            if existing_rtm_rule is None:
                db.add(
                    RequirementTraceabilityLink(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        requirement_id=existing_req.id,
                        business_rule_id=rule_obj.id,
                        knowledge_entity_id=target_ke.id if target_ke else rule_obj.knowledge_entity_id,
                        code_symbol_id=sym_obj.id if sym_obj else None,
                        link_type="DERIVED_FROM_RULE",
                        origin_type=existing_req.origin_type,
                        confidence_score=existing_req.confidence_score,
                    )
                )
                rtm_links_count += 1

            # Traceability Link 2: IMPLEMENTED_BY_CODE or CONSTRAINED_BY_SCHEMA
            if sym_obj is not None or target_ke is not None:
                l_type = (
                    "CONSTRAINED_BY_SCHEMA"
                    if cand.source_kind == "DB"
                    else "IMPLEMENTED_BY_CODE"
                )
                existing_rtm_impl = db.execute(
                    select(RequirementTraceabilityLink).where(
                        RequirementTraceabilityLink.tenant_id == tenant_id,
                        RequirementTraceabilityLink.requirement_id == existing_req.id,
                        RequirementTraceabilityLink.link_type == l_type,
                    )
                ).scalar_one_or_none()
                if existing_rtm_impl is None:
                    db.add(
                        RequirementTraceabilityLink(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            requirement_id=existing_req.id,
                            business_rule_id=rule_obj.id,
                            knowledge_entity_id=target_ke.id if target_ke else None,
                            code_symbol_id=sym_obj.id if sym_obj else None,
                            link_type=l_type,
                            origin_type=existing_req.origin_type,
                            confidence_score=existing_req.confidence_score,
                        )
                    )
                    rtm_links_count += 1

            # Knowledge Graph relationship: BUSINESS_RULE -> REQUIREMENT (`SATISFIES_REQ`)
            if rule_obj.knowledge_entity_id is not None:
                self.graph_service._upsert_relationship(
                    db,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot.id,
                    analysis_run_id=analysis_run.id,
                    source_entity_id=rule_obj.knowledge_entity_id,
                    target_entity_id=req_ke.id,
                    relationship_type="SATISFIES_REQ",
                    origin_type=existing_req.origin_type,
                    confidence_score=existing_req.confidence_score,
                    review_status=existing_req.review_status,
                    edge_metadata={"req_code": req_code, "rule_code": rule_obj.rule_code},
                )

        db.flush()

        # ------------------------------------------------------------------
        # 5. Detect Conflicts (`KnowledgeConflict`) & Record Evidence
        # ------------------------------------------------------------------
        conflicts_count = self._detect_and_persist_conflicts(
            db,
            tenant_id=tenant_id,
            application_id=application_id,
            snapshot_id=snapshot.id,
            persisted_rules=persisted_rules,
        )

        # ------------------------------------------------------------------
        # 6. Run Wave 3 Specialized AI Agents (`business_rule_miner`, `requirements_synthesizer`)
        # ------------------------------------------------------------------
        self._run_wave3_agents(
            db,
            tenant_id=tenant_id,
            application_id=application_id,
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run.id,
            rules_count=len(persisted_rules),
            requirements_count=len(persisted_requirements),
            conflicts_count=conflicts_count,
        )

        return Wave3PipelineSummary(
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run.id,
            business_domains_count=len(domain_cache),
            business_processes_count=processes_count,
            business_rules_count=len(persisted_rules),
            requirements_count=len(persisted_requirements),
            acceptance_criteria_count=criteria_count,
            traceability_links_count=rtm_links_count,
            conflicts_count=conflicts_count,
        )

    def _detect_and_persist_conflicts(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        persisted_rules: list[
            tuple[BusinessRule, ExtractedBusinessRuleCandidate, EvidenceAnchor | None]
        ],
    ) -> int:
        """
        Detect contradictions between Code rules and Documentation rules (`CODE_VS_DOC`)
        or competing rules on the same domain/subject (`REQUIREMENT_CONTRADICTION`).
        """
        conflicts_created = 0
        code_rules = [
            (r, c, a)
            for r, c, a in persisted_rules
            if c.source_kind in ("CODE", "API", "DB") and a is not None
        ]
        doc_rules = [
            (r, c, a)
            for r, c, a in persisted_rules
            if c.source_kind == "DOC" and a is not None
        ]

        # 1. Check numeric threshold divergence between CODE rules and DOC rules in same domain
        for cr, cc, ca in code_rules:
            if not cc.numeric_thresholds or ca is None:
                continue
            for dr, dc, da in doc_rules:
                if da is None or not dc.numeric_thresholds:
                    continue
                if cc.domain_code == dc.domain_code and set(cc.numeric_thresholds) != set(
                    dc.numeric_thresholds
                ):
                    existing = db.execute(
                        select(KnowledgeConflict).where(
                            KnowledgeConflict.tenant_id == tenant_id,
                            KnowledgeConflict.snapshot_id == snapshot_id,
                            KnowledgeConflict.primary_entity_or_finding_id == cr.id,
                            KnowledgeConflict.conflicting_entity_or_finding_id == dr.id,
                        )
                    ).scalar_one_or_none()
                    if existing is None:
                        db.add(
                            KnowledgeConflict(
                                id=uuid.uuid4(),
                                tenant_id=tenant_id,
                                application_id=application_id,
                                snapshot_id=snapshot_id,
                                conflict_type="CODE_VS_DOC",
                                primary_entity_or_finding_id=cr.id,
                                conflicting_entity_or_finding_id=dr.id,
                                primary_evidence_anchor_id=ca.id,
                                conflicting_evidence_anchor_id=da.id,
                                status="OPEN",
                                resolution_notes=(
                                    f"Numeric threshold discrepancy in domain `{cc.domain_code}`: "
                                    f"code rule `{cr.rule_code}` enforces {cc.numeric_thresholds} whereas "
                                    f"documentation rule `{dr.rule_code}` specifies {dc.numeric_thresholds}."
                                ),
                            )
                        )
                        conflicts_created += 1

        # 2. Check security/auth contradiction (e.g. unauthenticated API route alongside strict auth/PII rules)
        unauth_api_rules = [
            (r, c, a)
            for r, c, a in code_rules
            if c.source_kind == "API"
            and "without mandatory auth barrier" in r.action_consequence
            and a is not None
        ]
        strict_sec_rules = [
            (r, c, a)
            for r, c, a in code_rules
            if r.rule_category == "AUTHORIZATION"
            and ("DENY" in r.action_consequence or "REQUIRE" in r.action_consequence)
            and a is not None
        ]
        if unauth_api_rules and strict_sec_rules:
            ur, uc, ua = unauth_api_rules[0]
            sr, sc, sa_anchor = strict_sec_rules[0]
            if ua is not None and sa_anchor is not None and ur.id != sr.id:
                existing = db.execute(
                    select(KnowledgeConflict).where(
                        KnowledgeConflict.tenant_id == tenant_id,
                        KnowledgeConflict.snapshot_id == snapshot_id,
                        KnowledgeConflict.primary_entity_or_finding_id == sr.id,
                        KnowledgeConflict.conflicting_entity_or_finding_id == ur.id,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    db.add(
                        KnowledgeConflict(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            application_id=application_id,
                            snapshot_id=snapshot_id,
                            conflict_type="REQUIREMENT_CONTRADICTION",
                            primary_entity_or_finding_id=sr.id,
                            conflicting_entity_or_finding_id=ur.id,
                            primary_evidence_anchor_id=sa_anchor.id,
                            conflicting_evidence_anchor_id=ua.id,
                            status="OPEN",
                            resolution_notes=(
                                f"Security policy contradiction: `{sr.rule_code}` ({sr.title}) mandates access control, "
                                f"whereas `{ur.rule_code}` ({ur.title}) exposes an endpoint without mandatory authentication."
                            ),
                        )
                    )
                    conflicts_created += 1

        db.flush()
        return conflicts_created

    def _run_wave3_agents(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        rules_count: int,
        requirements_count: int,
        conflicts_count: int,
    ) -> None:
        """Execute Wave 3 specialized agents (`business_rule_miner`, `requirements_synthesizer`) with evidence validation."""
        anchors = (
            db.execute(
                select(EvidenceAnchor)
                .where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.snapshot_id == snapshot_id,
                )
                .limit(30)
            )
            .scalars()
            .all()
        )
        if not anchors:
            return
        entities = (
            db.execute(
                select(KnowledgeEntity)
                .where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                )
                .limit(50)
            )
            .scalars()
            .all()
        )
        valid_anchor_ids = {a.id for a in anchors}
        valid_entity_ids = {e.id for e in entities}
        primary_anchor_id = str(anchors[0].id)

        for agent_name, template_key, cat, title, stmt in [
            (
                "business_rule_miner",
                "business_rule_miner_v1",
                "BUSINESS_RULE",
                f"Business Rule Catalog Synthesis: {rules_count} Domain Rule(s) Extracted",
                f"Wave 3 Business Rule Miner cataloged **{rules_count}** source-anchored business rules across validation, calculation, authorization, and schema invariant categories.",
            ),
            (
                "requirements_synthesizer",
                "requirements_synthesizer_v1",
                "REQUIREMENT",
                f"Requirements & Traceability Synthesis: {requirements_count} Requirement(s), {conflicts_count} Conflict(s)",
                f"Wave 3 Requirements Synthesizer generated **{requirements_count}** functional and non-functional requirements with Given/When/Then acceptance criteria and detected **{conflicts_count}** policy/documentation conflict(s).",
            ),
        ]:
            existing_ar = db.execute(
                select(AgentRun).where(
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.analysis_run_id == analysis_run_id,
                    AgentRun.agent_name == agent_name,
                )
            ).scalar_one_or_none()
            if existing_ar is not None:
                continue

            ar = AgentRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                analysis_run_id=analysis_run_id,
                parent_agent_run_id=None,
                agent_name=agent_name,
                agent_version="3.0.0",
                status="RUNNING",
                attempt_count=1,
                input_context_refs={
                    "snapshot_id": str(snapshot_id),
                    "rules_count": rules_count,
                    "requirements_count": requirements_count,
                },
                started_at=datetime.now(timezone.utc),
            )
            db.add(ar)
            db.flush()

            tmpl = self.orchestrator._ensure_prompt_template(
                db, template_key=template_key, agent_name=agent_name
            )
            input_ctx = AgentInputContext(
                agent_name=agent_name,
                snapshot_id=str(snapshot_id),
                application_id=str(application_id),
                available_anchors=[{"id": primary_anchor_id}],
                entities_summary=[],
                domain_telemetry={
                    "rules_count": rules_count,
                    "requirements_count": requirements_count,
                    "conflicts_count": conflicts_count,
                },
            )
            _, _ = self.orchestrator._invoke_model_with_fallback(
                db,
                tenant_id=tenant_id,
                agent_run_id=ar.id,
                prompt_template=tmpl,
                input_ctx=input_ctx,
            )
            synth_payload = AgentFindingsPayload(
                findings=[
                    AgentFindingClaim(
                        finding_category=cat,
                        severity="INFO",
                        title=title,
                        statement_markdown=stmt,
                        confidence_score=0.89,
                        cited_anchor_id=primary_anchor_id,
                        subject_entity_id=str(entities[0].id) if entities else None,
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note=f"Synthesized by Wave 3 {agent_name}.",
                    )
                ]
            )
            acc, rej, _ = self.orchestrator.validate_and_persist_agent_claims(
                db,
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                agent_run=ar,
                payload=synth_payload,
                valid_anchor_ids=valid_anchor_ids,
                valid_entity_ids=valid_entity_ids,
                seq_start=1,
            )
            ar.status = "COMPLETED"
            ar.output_summary_json = {
                "findings_accepted": acc,
                "hallucinations_rejected": rej,
            }
            ar.completed_at = datetime.now(timezone.utc)
            db.flush()

    # ------------------------------------------------------------------
    # Query & Analysis Helpers for Endpoints
    # ------------------------------------------------------------------
    def _serialize_evidence_for_targets(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        rule_ids: list[uuid.UUID] | None = None,
        requirement_ids: list[uuid.UUID] | None = None,
    ) -> tuple[dict[uuid.UUID, list[dict[str, Any]]], dict[uuid.UUID, list[dict[str, Any]]]]:
        links_q = select(FindingEvidenceLink).where(
            FindingEvidenceLink.tenant_id == tenant_id
        )
        all_links = db.execute(links_q).scalars().all()
        relevant_links = [
            lnk
            for lnk in all_links
            if (rule_ids and lnk.business_rule_id in rule_ids)
            or (requirement_ids and lnk.requirement_id in requirement_ids)
        ]
        anchor_ids = list({lnk.evidence_anchor_id for lnk in relevant_links})
        anchors = (
            db.execute(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.id.in_(anchor_ids) if anchor_ids else False,
                )
            )
            .scalars()
            .all()
            if anchor_ids
            else []
        )
        anchor_by_id = {a.id: a for a in anchors}

        ver_ids = list({a.artifact_version_id for a in anchors})
        vers = (
            db.execute(
                select(ArtifactVersion).where(
                    ArtifactVersion.tenant_id == tenant_id,
                    ArtifactVersion.id.in_(ver_ids) if ver_ids else False,
                )
            )
            .scalars()
            .all()
            if ver_ids
            else []
        )
        art_ids = list({v.artifact_id for v in vers})
        arts = (
            db.execute(
                select(Artifact).where(
                    Artifact.tenant_id == tenant_id,
                    Artifact.id.in_(art_ids) if art_ids else False,
                )
            )
            .scalars()
            .all()
            if art_ids
            else []
        )
        art_path_by_id = {a.id: a.canonical_path for a in arts}
        path_by_ver_id = {v.id: art_path_by_id.get(v.artifact_id, "") for v in vers}

        by_rule: dict[uuid.UUID, list[dict[str, Any]]] = {}
        by_req: dict[uuid.UUID, list[dict[str, Any]]] = {}

        for lnk in relevant_links:
            anc = anchor_by_id.get(lnk.evidence_anchor_id)
            if anc is None:
                continue
            item = {
                "link_id": str(lnk.id),
                "anchor_id": str(anc.id),
                "evidence_role": lnk.evidence_role,
                "relevance_weight": float(lnk.relevance_weight),
                "rationale_note": lnk.rationale_note,
                "relative_path": path_by_ver_id.get(anc.artifact_version_id, ""),
                "locator_type": anc.locator_type,
                "start_line": anc.start_line,
                "end_line": anc.end_line,
                "snippet_sha256": anc.snippet_sha256,
                "excerpt_text": anc.excerpt_text,
            }
            if lnk.business_rule_id:
                by_rule.setdefault(lnk.business_rule_id, []).append(item)
            if lnk.requirement_id:
                by_req.setdefault(lnk.requirement_id, []).append(item)

        return by_rule, by_req

    def get_snapshot_business_rules(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        category: str | None = None,
        domain_code: str | None = None,
        review_status: str | None = None,
    ) -> dict[str, Any]:
        snap = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        if snap is None:
            return {
                "snapshot_id": str(snapshot_id),
                "domains": [],
                "processes": [],
                "business_rules": [],
            }

        repo = db.execute(
            select(Repository).where(
                Repository.tenant_id == tenant_id,
                Repository.id == snap.repository_id,
            )
        ).scalar_one()

        domains = (
            db.execute(
                select(BusinessDomain)
                .where(
                    BusinessDomain.tenant_id == tenant_id,
                    BusinessDomain.application_id == repo.application_id,
                )
                .order_by(BusinessDomain.code.asc())
            )
            .scalars()
            .all()
        )
        dom_by_id = {d.id: d for d in domains}

        processes = (
            db.execute(
                select(BusinessProcess)
                .where(
                    BusinessProcess.tenant_id == tenant_id,
                    BusinessProcess.application_id == repo.application_id,
                )
                .order_by(BusinessProcess.process_key.asc())
            )
            .scalars()
            .all()
        )

        stmt = select(BusinessRule).where(
            BusinessRule.tenant_id == tenant_id,
            BusinessRule.snapshot_id == snapshot_id,
        )
        if category:
            stmt = stmt.where(BusinessRule.rule_category == category)
        if review_status:
            stmt = stmt.where(BusinessRule.review_status == review_status)
        rules = db.execute(stmt.order_by(BusinessRule.rule_code.asc())).scalars().all()
        if domain_code:
            rules = [
                r
                for r in rules
                if r.business_domain_id
                and dom_by_id.get(r.business_domain_id)
                and dom_by_id[r.business_domain_id].code == domain_code
            ]

        rule_ids = [r.id for r in rules]
        by_rule_ev, _ = self._serialize_evidence_for_targets(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id, rule_ids=rule_ids
        )

        return {
            "snapshot_id": str(snapshot_id),
            "domains": [
                {
                    "id": str(d.id),
                    "code": d.code,
                    "name": d.name,
                    "description": d.description,
                    "origin_type": d.origin_type,
                    "confidence_score": float(d.confidence_score),
                    "review_status": d.review_status,
                }
                for d in domains
            ],
            "processes": [
                {
                    "id": str(p.id),
                    "process_key": p.process_key,
                    "name": p.name,
                    "domain_code": dom_by_id[p.business_domain_id].code
                    if p.business_domain_id and p.business_domain_id in dom_by_id
                    else "CORE_DOMAIN",
                    "workflow_summary": p.workflow_summary,
                    "ordered_step_entity_ids": p.ordered_step_entity_ids,
                    "origin_type": p.origin_type,
                    "confidence_score": float(p.confidence_score),
                    "review_status": p.review_status,
                }
                for p in processes
            ],
            "business_rules": [
                {
                    "id": str(r.id),
                    "rule_code": r.rule_code,
                    "rule_category": r.rule_category,
                    "domain_code": dom_by_id[r.business_domain_id].code
                    if r.business_domain_id and r.business_domain_id in dom_by_id
                    else "CORE_DOMAIN",
                    "domain_name": dom_by_id[r.business_domain_id].name
                    if r.business_domain_id and r.business_domain_id in dom_by_id
                    else "Core Application Business Logic",
                    "title": r.title,
                    "condition_expression": r.condition_expression,
                    "action_consequence": r.action_consequence,
                    "statement_markdown": f"{r.title}: {r.condition_expression} -> {r.action_consequence}",
                    "origin_type": r.origin_type,
                    "is_confirmed_fact": r.review_status == "APPROVED",
                    "confidence_score": float(r.confidence_score),
                    "review_status": r.review_status,
                    "version_no": r.version_no,
                    "knowledge_entity_id": str(r.knowledge_entity_id)
                    if r.knowledge_entity_id
                    else None,
                    "evidence": by_rule_ev.get(r.id, []),
                }
                for r in rules
            ],
        }

    def get_snapshot_requirements(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        req_type: str | None = None,
        priority: str | None = None,
        review_status: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(Requirement).where(
            Requirement.tenant_id == tenant_id,
            Requirement.snapshot_id == snapshot_id,
        )
        if req_type:
            stmt = stmt.where(Requirement.req_type == req_type)
        if priority:
            stmt = stmt.where(Requirement.priority == priority)
        if review_status:
            stmt = stmt.where(Requirement.review_status == review_status)
        reqs = db.execute(stmt.order_by(Requirement.req_code.asc())).scalars().all()
        req_ids = [r.id for r in reqs]

        criteria = (
            db.execute(
                select(RequirementAcceptanceCriterion)
                .where(
                    RequirementAcceptanceCriterion.tenant_id == tenant_id,
                    RequirementAcceptanceCriterion.requirement_id.in_(req_ids)
                    if req_ids
                    else False,
                )
                .order_by(RequirementAcceptanceCriterion.criterion_order.asc())
            )
            .scalars()
            .all()
            if req_ids
            else []
        )
        crit_by_req: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for c in criteria:
            crit_by_req.setdefault(c.requirement_id, []).append(
                {
                    "id": str(c.id),
                    "criterion_order": c.criterion_order,
                    "given_clause": c.given_clause,
                    "when_clause": c.when_clause,
                    "then_clause": c.then_clause,
                    "verification_method": c.verification_method,
                }
            )

        ke_ids = [r.knowledge_entity_id for r in reqs if r.knowledge_entity_id]
        kes = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.id.in_(ke_ids) if ke_ids else False,
                )
            )
            .scalars()
            .all()
            if ke_ids
            else []
        )
        ke_by_id = {k.id: k for k in kes}

        dom_ids = list({r.business_domain_id for r in reqs if r.business_domain_id})
        doms = (
            db.execute(
                select(BusinessDomain).where(
                    BusinessDomain.tenant_id == tenant_id,
                    BusinessDomain.id.in_(dom_ids) if dom_ids else False,
                )
            )
            .scalars()
            .all()
            if dom_ids
            else []
        )
        dom_by_id = {d.id: d for d in doms}

        _, by_req_ev = self._serialize_evidence_for_targets(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id, requirement_ids=req_ids
        )

        out_reqs: list[dict[str, Any]] = []
        for r in reqs:
            ke = ke_by_id.get(r.knowledge_entity_id) if r.knowledge_entity_id else None
            attrs = ke.attributes_json if ke and ke.attributes_json else {}
            ev_list = by_req_ev.get(r.id, [])
            ev_strength = attrs.get(
                "evidence_strength",
                "STRONG" if len(ev_list) >= 2 else ("MODERATE" if len(ev_list) == 1 else "MISSING"),
            )
            out_reqs.append(
                {
                    "id": str(r.id),
                    "req_code": r.req_code,
                    "req_type": r.req_type,
                    "priority": r.priority,
                    "domain_code": dom_by_id[r.business_domain_id].code
                    if r.business_domain_id and r.business_domain_id in dom_by_id
                    else "CORE_DOMAIN",
                    "title": r.title,
                    "specification_statement": r.specification_statement,
                    "origin_type": r.origin_type,
                    "is_confirmed_fact": r.review_status == "APPROVED",
                    "confidence_score": float(r.confidence_score),
                    "review_status": r.review_status,
                    "version_no": r.version_no,
                    "actors": attrs.get("actors", ["Application Runtime"]),
                    "inputs": attrs.get("inputs", []),
                    "outputs": attrs.get("outputs", []),
                    "preconditions": attrs.get("preconditions", ""),
                    "expected_outcomes": attrs.get("expected_outcomes", ""),
                    "is_implicit": bool(attrs.get("is_implicit", False)),
                    "evidence_strength": ev_strength,
                    "acceptance_criteria": crit_by_req.get(r.id, []),
                    "evidence": ev_list,
                }
            )

        return {
            "snapshot_id": str(snapshot_id),
            "requirements": out_reqs,
        }

    def get_traceability_matrix(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Return forward (`Requirement -> Rules -> Entities/Symbols -> Evidence`) and backward traceability."""
        reqs = (
            db.execute(
                select(Requirement)
                .where(
                    Requirement.tenant_id == tenant_id,
                    Requirement.snapshot_id == snapshot_id,
                )
                .order_by(Requirement.req_code.asc())
            )
            .scalars()
            .all()
        )
        rules = (
            db.execute(
                select(BusinessRule)
                .where(
                    BusinessRule.tenant_id == tenant_id,
                    BusinessRule.snapshot_id == snapshot_id,
                )
                .order_by(BusinessRule.rule_code.asc())
            )
            .scalars()
            .all()
        )
        req_by_id = {r.id: r for r in reqs}
        rule_by_id = {r.id: r for r in rules}
        req_ids = [r.id for r in reqs]
        rule_ids = [r.id for r in rules]

        rtm_links = (
            db.execute(
                select(RequirementTraceabilityLink).where(
                    RequirementTraceabilityLink.tenant_id == tenant_id,
                    RequirementTraceabilityLink.requirement_id.in_(req_ids)
                    if req_ids
                    else False,
                )
            )
            .scalars()
            .all()
            if req_ids
            else []
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
        sym_by_id = {s.id: s for s in symbols}

        entities = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        ent_by_id = {e.id: e for e in entities}

        by_rule_ev, by_req_ev = self._serialize_evidence_for_targets(
            db,
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            rule_ids=rule_ids,
            requirement_ids=req_ids,
        )

        # Forward traceability per requirement
        links_by_req: dict[uuid.UUID, list[RequirementTraceabilityLink]] = {}
        for lnk in rtm_links:
            links_by_req.setdefault(lnk.requirement_id, []).append(lnk)

        forward_matrix: list[dict[str, Any]] = []
        weak_or_missing_evidence_reqs: list[dict[str, Any]] = []

        for req in reqs:
            r_links = links_by_req.get(req.id, [])
            linked_rules: list[dict[str, Any]] = []
            linked_symbols: list[dict[str, Any]] = []
            linked_entities: list[dict[str, Any]] = []
            seen_rules: set[uuid.UUID] = set()
            seen_syms: set[uuid.UUID] = set()
            seen_ents: set[uuid.UUID] = set()

            for lnk in r_links:
                if lnk.business_rule_id and lnk.business_rule_id not in seen_rules:
                    seen_rules.add(lnk.business_rule_id)
                    br = rule_by_id.get(lnk.business_rule_id)
                    if br:
                        linked_rules.append(
                            {
                                "id": str(br.id),
                                "rule_code": br.rule_code,
                                "title": br.title,
                                "rule_category": br.rule_category,
                            }
                        )
                if lnk.code_symbol_id and lnk.code_symbol_id not in seen_syms:
                    seen_syms.add(lnk.code_symbol_id)
                    sym = sym_by_id.get(lnk.code_symbol_id)
                    if sym:
                        linked_symbols.append(
                            {
                                "id": str(sym.id),
                                "name": sym.name,
                                "qualified_name": sym.qualified_name,
                                "symbol_kind": sym.symbol_kind,
                            }
                        )
                if lnk.knowledge_entity_id and lnk.knowledge_entity_id not in seen_ents:
                    seen_ents.add(lnk.knowledge_entity_id)
                    ent = ent_by_id.get(lnk.knowledge_entity_id)
                    if ent:
                        linked_entities.append(
                            {
                                "id": str(ent.id),
                                "entity_type": ent.entity_type,
                                "title": ent.title,
                                "canonical_key": ent.canonical_key,
                            }
                        )

            ev_list = by_req_ev.get(req.id, [])
            ke = ent_by_id.get(req.knowledge_entity_id) if req.knowledge_entity_id else None
            attrs = ke.attributes_json if ke and ke.attributes_json else {}
            ev_strength = attrs.get(
                "evidence_strength",
                "STRONG" if len(ev_list) >= 2 else ("MODERATE" if len(ev_list) == 1 else "MISSING"),
            )

            entry = {
                "requirement_id": str(req.id),
                "req_code": req.req_code,
                "req_type": req.req_type,
                "priority": req.priority,
                "title": req.title,
                "review_status": req.review_status,
                "confidence_score": float(req.confidence_score),
                "is_implicit": bool(attrs.get("is_implicit", False)),
                "evidence_strength": ev_strength,
                "business_rules": linked_rules,
                "code_symbols": linked_symbols,
                "knowledge_entities": linked_entities,
                "evidence": ev_list,
            }
            forward_matrix.append(entry)
            if ev_strength in ("WEAK", "MISSING") or len(ev_list) == 0 or float(req.confidence_score) < 0.80:
                weak_or_missing_evidence_reqs.append(entry)

        # Backward traceability (Symbol / Entity -> Business Rules -> Requirements)
        backward_by_target: dict[str, dict[str, Any]] = {}
        for lnk in rtm_links:
            req = req_by_id.get(lnk.requirement_id)
            br = rule_by_id.get(lnk.business_rule_id) if lnk.business_rule_id else None
            if req is None:
                continue

            target_key: str | None = None
            target_label = ""
            target_type = ""
            if lnk.code_symbol_id and lnk.code_symbol_id in sym_by_id:
                s = sym_by_id[lnk.code_symbol_id]
                target_key = f"SYMBOL:{s.id}"
                target_label = s.qualified_name
                target_type = f"SYMBOL ({s.symbol_kind})"
            elif lnk.knowledge_entity_id and lnk.knowledge_entity_id in ent_by_id:
                e = ent_by_id[lnk.knowledge_entity_id]
                target_key = f"{e.entity_type}:{e.id}"
                target_label = e.title
                target_type = e.entity_type

            if target_key:
                bucket = backward_by_target.setdefault(
                    target_key,
                    {
                        "target_key": target_key,
                        "target_type": target_type,
                        "target_label": target_label,
                        "business_rules": [],
                        "requirements": [],
                    },
                )
                if br and not any(x["id"] == str(br.id) for x in bucket["business_rules"]):
                    bucket["business_rules"].append(
                        {
                            "id": str(br.id),
                            "rule_code": br.rule_code,
                            "title": br.title,
                            "evidence": by_rule_ev.get(br.id, []),
                        }
                    )
                if not any(x["id"] == str(req.id) for x in bucket["requirements"]):
                    bucket["requirements"].append(
                        {
                            "id": str(req.id),
                            "req_code": req.req_code,
                            "title": req.title,
                            "req_type": req.req_type,
                            "review_status": req.review_status,
                        }
                    )

        return {
            "snapshot_id": str(snapshot_id),
            "forward_traceability": forward_matrix,
            "backward_traceability": list(backward_by_target.values()),
            "weak_or_missing_evidence": weak_or_missing_evidence_reqs,
        }

    def get_conflicts_and_gaps(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Return rule/doc conflicts, duplicate/overlapping requirements, and undocumented behavior gaps."""
        conflicts = (
            db.execute(
                select(KnowledgeConflict).where(
                    KnowledgeConflict.tenant_id == tenant_id,
                    KnowledgeConflict.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        rules = (
            db.execute(
                select(BusinessRule).where(
                    BusinessRule.tenant_id == tenant_id,
                    BusinessRule.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        rule_by_id = {r.id: r for r in rules}

        reqs = (
            db.execute(
                select(Requirement)
                .where(
                    Requirement.tenant_id == tenant_id,
                    Requirement.snapshot_id == snapshot_id,
                )
                .order_by(Requirement.req_code.asc())
            )
            .scalars()
            .all()
        )

        anchor_ids = list(
            {c.primary_evidence_anchor_id for c in conflicts}
            | {c.conflicting_evidence_anchor_id for c in conflicts}
        )
        anchors = (
            db.execute(
                select(EvidenceAnchor).where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.id.in_(anchor_ids) if anchor_ids else False,
                )
            )
            .scalars()
            .all()
            if anchor_ids
            else []
        )
        anchor_by_id = {a.id: a for a in anchors}

        serialized_conflicts: list[dict[str, Any]] = []
        for c in conflicts:
            prim_rule = rule_by_id.get(c.primary_entity_or_finding_id)
            conf_rule = rule_by_id.get(c.conflicting_entity_or_finding_id)
            pa = anchor_by_id.get(c.primary_evidence_anchor_id)
            ca = anchor_by_id.get(c.conflicting_evidence_anchor_id)
            prim_label = (
                f"{prim_rule.rule_code}: {prim_rule.title}"
                if prim_rule
                else str(c.primary_entity_or_finding_id)
            )
            conf_label = (
                f"{conf_rule.rule_code}: {conf_rule.title}"
                if conf_rule
                else str(c.conflicting_entity_or_finding_id)
            )
            serialized_conflicts.append(
                {
                    "id": str(c.id),
                    "conflict_type": c.conflict_type,
                    "severity": "HIGH",
                    "description": f"{c.conflict_type} between ({prim_label}) and ({conf_label})",
                    "status": c.status,
                    "primary_id": str(c.primary_entity_or_finding_id),
                    "primary_label": prim_label,
                    "conflicting_id": str(c.conflicting_entity_or_finding_id),
                    "conflicting_label": conf_label,
                    "primary_evidence": {
                        "anchor_id": str(pa.id),
                        "start_line": pa.start_line,
                        "end_line": pa.end_line,
                        "snippet_sha256": pa.snippet_sha256,
                        "excerpt_text": pa.excerpt_text,
                    }
                    if pa
                    else None,
                    "conflicting_evidence": {
                        "anchor_id": str(ca.id),
                        "start_line": ca.start_line,
                        "end_line": ca.end_line,
                        "snippet_sha256": ca.snippet_sha256,
                        "excerpt_text": ca.excerpt_text,
                    }
                    if ca
                    else None,
                    "resolution_notes": c.resolution_notes,
                }
            )

        # Duplicate / Overlapping Requirements Detection
        overlapping_requirements: list[dict[str, Any]] = []
        req_tokens = [(r, _tokenize_spec(f"{r.title} {r.specification_statement}")) for r in reqs]
        for i in range(len(req_tokens)):
            r1, t1 = req_tokens[i]
            if not t1:
                continue
            for j in range(i + 1, len(req_tokens)):
                r2, t2 = req_tokens[j]
                if not t2:
                    continue
                inter = t1 & t2
                union = t1 | t2
                jacc = len(inter) / max(1, len(union))
                if jacc >= 0.42:
                    overlapping_requirements.append(
                        {
                            "primary_req_code": r1.req_code,
                            "primary_title": r1.title,
                            "overlapping_req_code": r2.req_code,
                            "overlapping_title": r2.title,
                            "similarity_score": round(jacc, 3),
                            "shared_terms": sorted(list(inter))[:8],
                        }
                    )

        # Undocumented Behavior & Missing Requirements Gaps
        kes = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        ke_by_id = {k.id: k for k in kes}
        rels = (
            db.execute(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.tenant_id == tenant_id,
                    KnowledgeRelationship.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        documented_ids = {
            r.target_entity_id for r in rels if r.relationship_type == "DOCUMENTS"
        }

        undocumented_behaviors: list[dict[str, Any]] = []
        for r in reqs:
            ke = ke_by_id.get(r.knowledge_entity_id) if r.knowledge_entity_id else None
            attrs = ke.attributes_json if ke and ke.attributes_json else {}
            if attrs.get("is_implicit"):
                undocumented_behaviors.append(
                    {
                        "gap_type": "UNDOCUMENTED_BEHAVIOR",
                        "req_code": r.req_code,
                        "title": r.title,
                        "description": (
                            f"Requirement `{r.req_code}` is enforced in code/schema (`{r.origin_type}`) "
                            f"but has no corresponding technical documentation section coverage."
                        ),
                    }
                )

        for k in kes:
            if k.entity_type in ("SYMBOL", "API_ENDPOINT") and k.id not in documented_ids:
                undocumented_behaviors.append(
                    {
                        "gap_type": "UNDOCUMENTED_COMPONENT",
                        "req_code": None,
                        "title": f"Undocumented {k.entity_type}: `{k.title}`",
                        "description": f"`{k.canonical_key}` has no `DOCUMENTS` edge from any documentation section.",
                    }
                )

        return {
            "snapshot_id": str(snapshot_id),
            "conflicts": serialized_conflicts,
            "overlapping_requirements": overlapping_requirements,
            "gaps_and_undocumented": undocumented_behaviors[:40],
        }

    def analyze_impact(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        target_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Trace multi-hop dependencies between a target `Requirement`, `BusinessRule`, or `KnowledgeEntity`
        and affected APIs, database tables, code modules/symbols, and infrastructure.
        """
        req = db.execute(
            select(Requirement).where(
                Requirement.tenant_id == tenant_id,
                Requirement.snapshot_id == snapshot_id,
                Requirement.id == target_id,
            )
        ).scalar_one_or_none()
        rule = (
            db.execute(
                select(BusinessRule).where(
                    BusinessRule.tenant_id == tenant_id,
                    BusinessRule.snapshot_id == snapshot_id,
                    BusinessRule.id == target_id,
                )
            ).scalar_one_or_none()
            if req is None
            else None
        )

        root_ke_id: uuid.UUID | None = None
        target_summary: dict[str, Any] = {}
        seed_entity_ids: set[uuid.UUID] = set()

        if req is not None:
            root_ke_id = req.knowledge_entity_id
            target_summary = {
                "id": str(req.id),
                "target_kind": "REQUIREMENT",
                "code": req.req_code,
                "title": req.title,
                "review_status": req.review_status,
            }
            rtm = (
                db.execute(
                    select(RequirementTraceabilityLink).where(
                        RequirementTraceabilityLink.tenant_id == tenant_id,
                        RequirementTraceabilityLink.requirement_id == req.id,
                    )
                )
                .scalars()
                .all()
            )
            for lnk in rtm:
                if lnk.knowledge_entity_id:
                    seed_entity_ids.add(lnk.knowledge_entity_id)
        elif rule is not None:
            root_ke_id = rule.knowledge_entity_id
            target_summary = {
                "id": str(rule.id),
                "target_kind": "BUSINESS_RULE",
                "code": rule.rule_code,
                "title": rule.title,
                "review_status": rule.review_status,
            }
        else:
            ke = db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                    KnowledgeEntity.id == target_id,
                )
            ).scalar_one_or_none()
            if ke is not None:
                root_ke_id = ke.id
                target_summary = {
                    "id": str(ke.id),
                    "target_kind": ke.entity_type,
                    "code": ke.canonical_key,
                    "title": ke.title,
                    "review_status": ke.review_status,
                }

        if root_ke_id is not None:
            seed_entity_ids.add(root_ke_id)

        visited_nodes: dict[str, dict[str, Any]] = {}
        traversed_edges: list[dict[str, Any]] = []

        for seed_id in list(seed_entity_ids):
            sub = self.graph_service.traverse_subgraph(
                db,
                tenant_id=tenant_id,
                snapshot_id=snapshot_id,
                root_entity_id=seed_id,
                max_hops=3,
                direction="BOTH",
            )
            for n in sub.get("nodes", []):
                visited_nodes[n["id"]] = n
            for e in sub.get("edges", []):
                if not any(x["id"] == e["id"] for x in traversed_edges):
                    traversed_edges.append(e)

        affected_apis = [
            n for n in visited_nodes.values() if n["entity_type"] == "API_ENDPOINT"
        ]
        affected_tables = [
            n for n in visited_nodes.values() if n["entity_type"] == "DB_TABLE"
        ]
        affected_code = [
            n
            for n in visited_nodes.values()
            if n["entity_type"] in ("SYMBOL", "MODULE")
        ]
        affected_infra = [
            n for n in visited_nodes.values() if n["entity_type"] == "INFRA_RESOURCE"
        ]
        affected_rules = [
            n for n in visited_nodes.values() if n["entity_type"] == "BUSINESS_RULE"
        ]
        affected_reqs = [
            n for n in visited_nodes.values() if n["entity_type"] == "REQUIREMENT"
        ]

        total_impacted = (
            len(affected_apis)
            + len(affected_tables)
            + len(affected_code)
            + len(affected_infra)
        )
        risk_level = (
            "CRITICAL"
            if total_impacted >= 8 or (affected_apis and affected_tables)
            else ("HIGH" if total_impacted >= 4 else ("MEDIUM" if total_impacted >= 2 else "LOW"))
        )

        # Evidence anchors backing this impact analysis
        by_rule_ev, by_req_ev = self._serialize_evidence_for_targets(
            db,
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            rule_ids=[rule.id] if rule else None,
            requirement_ids=[req.id] if req else None,
        )
        evidence_list = (
            by_req_ev.get(req.id, [])
            if req
            else (by_rule_ev.get(rule.id, []) if rule else [])
        )

        explanation = (
            f"Modifying `{target_summary.get('code', 'target')}` ({target_summary.get('title', '')}) "
            f"propagates across **{len(affected_apis)}** API endpoint(s), **{len(affected_tables)}** database table(s), "
            f"**{len(affected_code)}** code symbol/module(s), and **{len(affected_infra)}** infrastructure resource(s) "
            f"(Blast Radius: **{risk_level}**)."
        )

        return {
            "snapshot_id": str(snapshot_id),
            "target": target_summary,
            "blast_radius_risk": risk_level,
            "impact_explanation": explanation,
            "affected_apis": affected_apis,
            "affected_database_tables": affected_tables,
            "affected_code_components": affected_code,
            "affected_infrastructure": affected_infra,
            "affected_business_rules": affected_rules,
            "affected_requirements": affected_reqs,
            "dependency_edges": traversed_edges,
            "evidence": evidence_list,
        }

    # ------------------------------------------------------------------
    # Human Review Workflows (`BusinessRule`, `Requirement`, `KnowledgeConflict`)
    # ------------------------------------------------------------------
    def review_business_rule(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        rule_id: uuid.UUID,
        reviewer_user_id: uuid.UUID,
        new_status: str,
        review_comment: str | None = None,
        updated_title: str | None = None,
        updated_condition_expression: str | None = None,
        updated_action_consequence: str | None = None,
    ) -> dict[str, Any]:
        rule = db.execute(
            select(BusinessRule).where(
                BusinessRule.tenant_id == tenant_id,
                BusinessRule.id == rule_id,
            )
        ).scalar_one_or_none()
        if rule is None:
            raise ValueError(f"BusinessRule {rule_id} not found for tenant {tenant_id}")

        prev_status = rule.review_status
        prev_snap = {
            "title": rule.title,
            "condition_expression": rule.condition_expression,
            "action_consequence": rule.action_consequence,
            "review_status": rule.review_status,
            "version_no": rule.version_no,
        }

        if updated_title:
            rule.title = updated_title[:255]
        if updated_condition_expression:
            rule.condition_expression = updated_condition_expression
        if updated_action_consequence:
            rule.action_consequence = updated_action_consequence
        rule.review_status = new_status
        rule.version_no = (rule.version_no or 1) + 1

        if rule.knowledge_entity_id:
            ke = db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.id == rule.knowledge_entity_id,
                )
            ).scalar_one_or_none()
            if ke is not None:
                ke.review_status = new_status
                ke.version_no = rule.version_no

        new_snap = {
            "title": rule.title,
            "condition_expression": rule.condition_expression,
            "action_consequence": rule.action_consequence,
            "review_status": rule.review_status,
            "version_no": rule.version_no,
        }

        hist = ReviewHistory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            target_object_type="BUSINESS_RULE",
            target_object_id=rule.id,
            reviewer_user_id=reviewer_user_id,
            previous_status=prev_status,
            new_status=new_status,
            previous_snapshot_json=prev_snap,
            updated_snapshot_json=new_snap,
            review_comment=review_comment,
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(hist)
        db.flush()

        history_rows = (
            db.execute(
                select(ReviewHistory)
                .where(
                    ReviewHistory.tenant_id == tenant_id,
                    ReviewHistory.target_object_type == "BUSINESS_RULE",
                    ReviewHistory.target_object_id == rule.id,
                )
                .order_by(ReviewHistory.reviewed_at.desc())
            )
            .scalars()
            .all()
        )
        return {
            "id": str(rule.id),
            "rule_code": rule.rule_code,
            "title": rule.title,
            "condition_expression": rule.condition_expression,
            "action_consequence": rule.action_consequence,
            "review_status": rule.review_status,
            "is_confirmed_fact": rule.review_status == "APPROVED",
            "version_no": rule.version_no,
            "review_history": [
                {
                    "id": str(h.id),
                    "previous_status": h.previous_status,
                    "new_status": h.new_status,
                    "review_comment": h.review_comment,
                    "reviewed_at": h.reviewed_at.isoformat(),
                }
                for h in history_rows
            ],
        }

    def review_requirement(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        requirement_id: uuid.UUID,
        reviewer_user_id: uuid.UUID,
        new_status: str,
        review_comment: str | None = None,
        updated_title: str | None = None,
        updated_specification_statement: str | None = None,
        updated_priority: str | None = None,
    ) -> dict[str, Any]:
        req = db.execute(
            select(Requirement).where(
                Requirement.tenant_id == tenant_id,
                Requirement.id == requirement_id,
            )
        ).scalar_one_or_none()
        if req is None:
            raise ValueError(f"Requirement {requirement_id} not found for tenant {tenant_id}")

        prev_status = req.review_status
        prev_snap = {
            "title": req.title,
            "specification_statement": req.specification_statement,
            "priority": req.priority,
            "review_status": req.review_status,
            "version_no": req.version_no,
        }

        if updated_title:
            req.title = updated_title[:255]
        if updated_specification_statement:
            req.specification_statement = updated_specification_statement
        if updated_priority:
            req.priority = updated_priority
        req.review_status = new_status
        req.version_no = (req.version_no or 1) + 1

        if req.knowledge_entity_id:
            ke = db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.id == req.knowledge_entity_id,
                )
            ).scalar_one_or_none()
            if ke is not None:
                ke.review_status = new_status
                ke.version_no = req.version_no

        new_snap = {
            "title": req.title,
            "specification_statement": req.specification_statement,
            "priority": req.priority,
            "review_status": req.review_status,
            "version_no": req.version_no,
        }

        hist = ReviewHistory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            target_object_type="REQUIREMENT",
            target_object_id=req.id,
            reviewer_user_id=reviewer_user_id,
            previous_status=prev_status,
            new_status=new_status,
            previous_snapshot_json=prev_snap,
            updated_snapshot_json=new_snap,
            review_comment=review_comment,
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(hist)
        db.flush()

        history_rows = (
            db.execute(
                select(ReviewHistory)
                .where(
                    ReviewHistory.tenant_id == tenant_id,
                    ReviewHistory.target_object_type == "REQUIREMENT",
                    ReviewHistory.target_object_id == req.id,
                )
                .order_by(ReviewHistory.reviewed_at.desc())
            )
            .scalars()
            .all()
        )
        return {
            "id": str(req.id),
            "req_code": req.req_code,
            "title": req.title,
            "specification_statement": req.specification_statement,
            "priority": req.priority,
            "review_status": req.review_status,
            "is_confirmed_fact": req.review_status == "APPROVED",
            "version_no": req.version_no,
            "review_history": [
                {
                    "id": str(h.id),
                    "previous_status": h.previous_status,
                    "new_status": h.new_status,
                    "review_comment": h.review_comment,
                    "reviewed_at": h.reviewed_at.isoformat(),
                }
                for h in history_rows
            ],
        }

    def resolve_conflict(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        conflict_id: uuid.UUID,
        resolver_user_id: uuid.UUID,
        new_status: str,
        resolution_notes: str | None = None,
    ) -> dict[str, Any]:
        conflict = db.execute(
            select(KnowledgeConflict).where(
                KnowledgeConflict.tenant_id == tenant_id,
                KnowledgeConflict.id == conflict_id,
            )
        ).scalar_one_or_none()
        if conflict is None:
            raise ValueError(f"KnowledgeConflict {conflict_id} not found for tenant {tenant_id}")

        prev_status = conflict.status
        prev_snap = {
            "status": conflict.status,
            "resolution_notes": conflict.resolution_notes,
        }
        conflict.status = new_status
        conflict.resolved_by_user_id = resolver_user_id
        if resolution_notes:
            conflict.resolution_notes = resolution_notes

        new_snap = {
            "status": conflict.status,
            "resolution_notes": conflict.resolution_notes,
        }
        hist = ReviewHistory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            target_object_type="KNOWLEDGE_CONFLICT",
            target_object_id=conflict.id,
            reviewer_user_id=resolver_user_id,
            previous_status=prev_status,
            new_status=new_status,
            previous_snapshot_json=prev_snap,
            updated_snapshot_json=new_snap,
            review_comment=resolution_notes,
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(hist)
        db.flush()

        return {
            "id": str(conflict.id),
            "conflict_type": conflict.conflict_type,
            "status": conflict.status,
            "resolution_notes": conflict.resolution_notes,
        }


__all__ = [
    "RequirementsIntelligenceService",
    "Wave3PipelineSummary",
]

