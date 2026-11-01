"""Wave 4 Service: Test Intelligence, Coverage & Gaps, Risk Register, Technical Debt, Modernization Assessment & Phased Roadmap."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.parser_registry import SUPPORTED_CODE_LANGUAGES, detect_language_and_kind
from app.analysis.testing_risk_modernization_intelligence import (
    ExtractedCoverageRecord,
    ExtractedDependencyRecord,
    ExtractedRiskCandidate,
    ExtractedTestCaseCandidate,
    extract_code_security_and_performance_risks,
    extract_tests_from_code,
    generate_missing_test_blueprint,
    is_test_file_path,
    parse_coverage_report,
    parse_dependency_manifests,
)
from app.integrations.storage import TenantObjectStorage
from app.models.agent_orchestration import AgentRun, AgentTaskDependency
from app.models.business_intelligence import (
    BusinessDomain,
    BusinessRule,
    Requirement,
    RequirementAcceptanceCriterion,
    RequirementTraceabilityLink,
)
from app.models.code_intelligence import (
    AnalysisRun,
    CodeCallEdge,
    CodeFile,
    CodeSymbol,
    CodeSymbolReference,
)
from app.models.ingestion import Artifact, ArtifactVersion, Repository, RepositorySnapshot
from app.models.knowledge_graph import (
    EvidenceAnchor,
    Finding,
    FindingEvidenceLink,
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
    InfraResource,
)
from app.models.testing_modernization import (
    ModernizationRecommendation,
    TechnicalDebtItem,
    TestCase,
    TestCoverageLink,
    TestSuite,
)
from app.services.agent_orchestrator import (
    AgentFindingClaim,
    AgentFindingsPayload,
    AgentInputContext,
    TechnicalIntelligenceOrchestrator,
)
from app.services.knowledge_graph_service import KnowledgeGraphService


RISK_FINDING_CATEGORIES = (
    "RISK_SECURITY",
    "RISK_DEPENDENCY",
    "RISK_ARCHITECTURE",
    "RISK_SPOF",
    "RISK_DATA_INTEGRITY",
    "RISK_PERFORMANCE",
    "RISK_OPERATIONAL",
)


@dataclass
class Wave4PipelineSummary:
    snapshot_id: uuid.UUID
    analysis_run_id: uuid.UUID
    discovered_test_suites_count: int
    discovered_test_cases_count: int
    generated_test_blueprints_count: int
    coverage_links_count: int
    risk_findings_count: int
    technical_debt_items_count: int
    modernization_recommendations_count: int


class TestingModernizationService:
    """
    Executes Wave 4 (Testing, Risk, Technical Debt & Modernization Intelligence)
    idempotently against a `RepositorySnapshot` and provides query & human-review operations.
    """

    __test__ = False

    def __init__(
        self,
        storage: TenantObjectStorage | None = None,
        graph_service: KnowledgeGraphService | None = None,
        orchestrator: TechnicalIntelligenceOrchestrator | None = None,
    ) -> None:
        self.storage = storage or TenantObjectStorage()
        self.graph_service = graph_service or KnowledgeGraphService()
        self.orchestrator = orchestrator or TechnicalIntelligenceOrchestrator(
            allow_live_ollama=False
        )

    def execute_wave4_pipeline(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot: RepositorySnapshot,
        analysis_run: AnalysisRun,
        snapshot_artifacts: list[tuple[Artifact, ArtifactVersion]] | None = None,
    ) -> Wave4PipelineSummary:
        # Resolve artifacts for snapshot
        artifact_pairs: list[tuple[Artifact, ArtifactVersion]] = []
        if snapshot_artifacts is None:
            arts = (
                db.execute(
                    select(Artifact).where(
                        Artifact.tenant_id == tenant_id,
                        Artifact.repository_id == snapshot.repository_id,
                    )
                )
                .scalars()
                .all()
            )
            for art in arts:
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
        fallback_ver = artifact_pairs[0][1] if artifact_pairs else None

        # Load Wave 1, Wave 2 & Wave 3 state
        code_files = (
            db.execute(
                select(CodeFile).where(
                    CodeFile.tenant_id == tenant_id,
                    CodeFile.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        file_by_id = {cf.id: cf for cf in code_files}

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
        symbol_by_id = {s.id: s for s in symbols}
        symbol_by_qname = {s.qualified_name: s for s in symbols}
        symbol_by_short: dict[str, CodeSymbol] = {s.name.lower(): s for s in symbols}

        call_edges = (
            db.execute(
                select(CodeCallEdge).where(
                    CodeCallEdge.tenant_id == tenant_id,
                    CodeCallEdge.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        sym_refs = (
            db.execute(
                select(CodeSymbolReference).where(
                    CodeSymbolReference.tenant_id == tenant_id,
                    CodeSymbolReference.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )

        knowledge_entities = (
            db.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        ke_by_symbol_id = {
            ke.source_symbol_id: ke
            for ke in knowledge_entities
            if ke.source_symbol_id is not None
        }
        ke_by_title_lower = {ke.title.lower(): ke for ke in knowledge_entities}

        knowledge_rels = (
            db.execute(
                select(KnowledgeRelationship).where(
                    KnowledgeRelationship.tenant_id == tenant_id,
                    KnowledgeRelationship.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )

        rules = (
            db.execute(
                select(BusinessRule).where(
                    BusinessRule.tenant_id == tenant_id,
                    BusinessRule.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        requirements = (
            db.execute(
                select(Requirement).where(
                    Requirement.tenant_id == tenant_id,
                    Requirement.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        rtm_links = (
            db.execute(
                select(RequirementTraceabilityLink).where(
                    RequirementTraceabilityLink.tenant_id == tenant_id,
                    RequirementTraceabilityLink.requirement_id.in_(
                        [r.id for r in requirements]
                    )
                    if requirements
                    else False,
                )
            )
            .scalars()
            .all()
            if requirements
            else []
        )

        # ------------------------------------------------------------------
        # 1. Scan Artifacts for Discovered Tests, Coverage Reports, Dependencies & Code Risks
        # ------------------------------------------------------------------
        discovered_test_candidates: list[ExtractedTestCaseCandidate] = []
        coverage_records: list[ExtractedCoverageRecord] = []
        dependency_records: list[ExtractedDependencyRecord] = []
        risk_candidates: list[ExtractedRiskCandidate] = []

        for art, ver in artifact_pairs:
            if not self.storage.blob_exists(tenant_id, ver.content_sha256):
                continue
            try:
                raw_bytes = self.storage.get_blob_bytes(tenant_id, ver.content_sha256)
                text_content = raw_bytes.decode("utf-8", errors="replace")
            except Exception:
                continue

            c_path = art.canonical_path
            lower_path = c_path.lower()
            lang, _ = detect_language_and_kind(c_path)

            # Coverage reports
            if lower_path.endswith(("coverage.xml", "cobertura.xml", "lcov.info", ".lcov")):
                coverage_records.extend(parse_coverage_report(text_content, c_path))

            # Dependency manifests
            if lower_path.endswith(("requirements.txt", "package.json")):
                dependency_records.extend(parse_dependency_manifests(text_content, c_path))

            # Source code & tests
            if lang in SUPPORTED_CODE_LANGUAGES:
                tests_found = extract_tests_from_code(text_content, c_path, lang)
                if tests_found:
                    discovered_test_candidates.extend(tests_found)
                code_risks = extract_code_security_and_performance_risks(
                    text_content, c_path, lang
                )
                if code_risks:
                    risk_candidates.extend(code_risks)

        # ------------------------------------------------------------------
        # 2. Persist Discovered TestSuites, TestCases & TestCoverageLinks
        # ------------------------------------------------------------------
        suite_cache: dict[str, TestSuite] = {}
        discovered_suites_count = 0
        discovered_cases_count = 0
        coverage_links_count = 0

        # Map symbol -> requirements and symbol -> business_rules from RTM
        reqs_by_symbol_id: dict[uuid.UUID, list[uuid.UUID]] = {}
        rules_by_symbol_id: dict[uuid.UUID, list[uuid.UUID]] = {}
        for lnk in rtm_links:
            if lnk.code_symbol_id:
                reqs_by_symbol_id.setdefault(lnk.code_symbol_id, []).append(
                    lnk.requirement_id
                )
                if lnk.business_rule_id:
                    rules_by_symbol_id.setdefault(lnk.code_symbol_id, []).append(
                        lnk.business_rule_id
                    )

        # Measured coverage lookup by path
        cov_by_path: dict[str, ExtractedCoverageRecord] = {
            cr.relative_path: cr for cr in coverage_records
        }

        covered_req_ids_discovered: set[uuid.UUID] = set()
        covered_rule_ids_discovered: set[uuid.UUID] = set()
        covered_symbol_ids_discovered: set[uuid.UUID] = set()

        for t_cand in discovered_test_candidates:
            suite_obj = suite_cache.get(t_cand.suite_name)
            if suite_obj is None:
                suite_obj = db.execute(
                    select(TestSuite).where(
                        TestSuite.tenant_id == tenant_id,
                        TestSuite.application_id == application_id,
                        TestSuite.snapshot_id == snapshot.id,
                        TestSuite.suite_name == t_cand.suite_name,
                    )
                ).scalar_one_or_none()
                if suite_obj is None:
                    suite_obj = TestSuite(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        application_id=application_id,
                        snapshot_id=snapshot.id,
                        suite_name=t_cand.suite_name[:255],
                        test_framework=t_cand.test_framework,
                        suite_origin="EXISTING_IN_REPO",
                    )
                    db.add(suite_obj)
                    db.flush()
                    discovered_suites_count += 1
                suite_cache[t_cand.suite_name] = suite_obj

            test_sym = (
                symbol_by_short.get(t_cand.enclosing_symbol_qname.lower())
                if t_cand.enclosing_symbol_qname
                else None
            )
            existing_tc = db.execute(
                select(TestCase).where(
                    TestCase.tenant_id == tenant_id,
                    TestCase.test_suite_id == suite_obj.id,
                    TestCase.test_key == t_cand.test_key[:255],
                )
            ).scalar_one_or_none()
            if existing_tc is None:
                existing_tc = TestCase(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    test_suite_id=suite_obj.id,
                    test_symbol_id=test_sym.id if test_sym else None,
                    analysis_run_id=analysis_run.id,
                    test_key=t_cand.test_key[:255],
                    title=t_cand.title[:255],
                    test_kind=t_cand.test_kind,
                    scenario_description=t_cand.scenario_description,
                    generated_code_blueprint=None,
                    last_observed_status="PASSED"
                    if t_cand.assertion_count > 0
                    else "UNKNOWN",
                    confidence_score=Decimal("0.9600"),
                    review_status="PENDING_REVIEW",
                )
                db.add(existing_tc)
                db.flush()
                discovered_cases_count += 1

            # Create EvidenceAnchor for discovered test
            t_ver = ver_by_path.get(t_cand.relative_path) or fallback_ver
            if t_ver is not None:
                self.graph_service.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot.id,
                    artifact_version_id=t_ver.id,
                    locator_type="LINE_RANGE",
                    start_line=t_cand.start_line,
                    end_line=t_cand.end_line,
                    excerpt_text=t_cand.excerpt_text,
                    ast_or_json_path=t_cand.test_key,
                )

            # Map test case to production symbols, business rules, and requirements
            matched_syms: list[CodeSymbol] = []
            for cid in t_cand.called_identifiers:
                sym = symbol_by_short.get(cid.lower())
                if sym and sym.id != (test_sym.id if test_sym else None):
                    matched_syms.append(sym)

            # Also check substring match in test title/calls against production symbols
            for sym in symbols:
                if is_test_file_path(file_by_id[sym.code_file_id].relative_path if sym.code_file_id in file_by_id else ""):
                    continue
                if sym.name.lower() in t_cand.test_key.lower() or any(
                    sym.name.lower() in c.lower() for c in t_cand.called_identifiers
                ):
                    if sym not in matched_syms:
                        matched_syms.append(sym)

            for m_sym in matched_syms[:8]:
                covered_symbol_ids_discovered.add(m_sym.id)
                m_file = file_by_id.get(m_sym.code_file_id)
                has_measured_cov = bool(
                    m_file and m_file.relative_path in cov_by_path
                )
                cov_src = (
                    "COVERAGE_REPORT" if has_measured_cov else "STATIC_CALL_GRAPH"
                )
                conf_val = Decimal("0.9900") if has_measured_cov else Decimal("0.9100")

                linked_rules = rules_by_symbol_id.get(m_sym.id, [])
                linked_reqs = reqs_by_symbol_id.get(m_sym.id, [])

                if not linked_reqs and not linked_rules:
                    existing_cov = db.execute(
                        select(TestCoverageLink).where(
                            TestCoverageLink.tenant_id == tenant_id,
                            TestCoverageLink.test_case_id == existing_tc.id,
                            TestCoverageLink.target_symbol_id == m_sym.id,
                        )
                    ).scalar_one_or_none()
                    if existing_cov is None:
                        db.add(
                            TestCoverageLink(
                                id=uuid.uuid4(),
                                tenant_id=tenant_id,
                                test_case_id=existing_tc.id,
                                target_symbol_id=m_sym.id,
                                target_business_rule_id=None,
                                target_requirement_id=None,
                                coverage_source=cov_src,
                                confidence_score=conf_val,
                            )
                        )
                        coverage_links_count += 1
                else:
                    for idx_r, req_id in enumerate(linked_reqs):
                        covered_req_ids_discovered.add(req_id)
                        b_rule_id = (
                            linked_rules[idx_r] if idx_r < len(linked_rules) else None
                        )
                        if b_rule_id:
                            covered_rule_ids_discovered.add(b_rule_id)
                        existing_cov = db.execute(
                            select(TestCoverageLink).where(
                                TestCoverageLink.tenant_id == tenant_id,
                                TestCoverageLink.test_case_id == existing_tc.id,
                                TestCoverageLink.target_symbol_id == m_sym.id,
                                TestCoverageLink.target_requirement_id == req_id,
                            )
                        ).scalar_one_or_none()
                        if existing_cov is None:
                            db.add(
                                TestCoverageLink(
                                    id=uuid.uuid4(),
                                    tenant_id=tenant_id,
                                    test_case_id=existing_tc.id,
                                    target_symbol_id=m_sym.id,
                                    target_business_rule_id=b_rule_id,
                                    target_requirement_id=req_id,
                                    coverage_source=cov_src,
                                    confidence_score=conf_val,
                                )
                            )
                            coverage_links_count += 1

                        # Also add VERIFIED_BY_TEST in requirement_traceability_links
                        existing_rtm_test = db.execute(
                            select(RequirementTraceabilityLink).where(
                                RequirementTraceabilityLink.tenant_id == tenant_id,
                                RequirementTraceabilityLink.requirement_id == req_id,
                                RequirementTraceabilityLink.test_case_id == existing_tc.id,
                                RequirementTraceabilityLink.link_type == "VERIFIED_BY_TEST",
                            )
                        ).scalar_one_or_none()
                        if existing_rtm_test is None:
                            db.add(
                                RequirementTraceabilityLink(
                                    id=uuid.uuid4(),
                                    tenant_id=tenant_id,
                                    requirement_id=req_id,
                                    business_rule_id=b_rule_id,
                                    knowledge_entity_id=ke_by_symbol_id[m_sym.id].id
                                    if m_sym.id in ke_by_symbol_id
                                    else None,
                                    code_symbol_id=m_sym.id,
                                    test_case_id=existing_tc.id,
                                    link_type="VERIFIED_BY_TEST",
                                    origin_type="DETERMINISTIC_PARSER",
                                    confidence_score=conf_val,
                                )
                            )

        db.flush()

        # ------------------------------------------------------------------
        # 3. Generate Missing Test Blueprints for Untested Requirements
        # ------------------------------------------------------------------
        generated_blueprints_count = 0
        untested_reqs = [
            r for r in requirements if r.id not in covered_req_ids_discovered
        ]
        if untested_reqs:
            blueprint_suite_name = "generated/characterization_test_blueprints.py"
            bp_suite = db.execute(
                select(TestSuite).where(
                    TestSuite.tenant_id == tenant_id,
                    TestSuite.application_id == application_id,
                    TestSuite.snapshot_id == snapshot.id,
                    TestSuite.suite_name == blueprint_suite_name,
                )
            ).scalar_one_or_none()
            if bp_suite is None:
                bp_suite = TestSuite(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot.id,
                    suite_name=blueprint_suite_name,
                    test_framework="GENERATED_BLUEPRINT",
                    suite_origin="AI_GENERATED_BLUEPRINT",
                )
                db.add(bp_suite)
                db.flush()

            for u_req in untested_reqs[:15]:
                ac = (
                    db.execute(
                        select(RequirementAcceptanceCriterion)
                        .where(
                            RequirementAcceptanceCriterion.tenant_id == tenant_id,
                            RequirementAcceptanceCriterion.requirement_id == u_req.id,
                        )
                        .order_by(RequirementAcceptanceCriterion.criterion_order.asc())
                        .limit(1)
                    )
                    .scalars()
                    .first()
                )
                given_c = ac.given_clause if ac else f"Given requirement {u_req.req_code}"
                when_c = ac.when_clause if ac else "When the governed operation is triggered"
                then_c = ac.then_clause if ac else f"Then {u_req.specification_statement}"

                req_rtm = [l for l in rtm_links if l.requirement_id == u_req.id]
                target_sym_id = next(
                    (l.code_symbol_id for l in req_rtm if l.code_symbol_id), None
                )
                target_rule_id = next(
                    (l.business_rule_id for l in req_rtm if l.business_rule_id), None
                )
                target_sym_obj = (
                    symbol_by_id.get(target_sym_id) if target_sym_id else None
                )

                t_key, t_kind, code_bp = generate_missing_test_blueprint(
                    req_code=u_req.req_code,
                    req_title=u_req.title,
                    req_type=u_req.req_type,
                    given_clause=given_c,
                    when_clause=when_c,
                    then_clause=then_c,
                    target_symbol_name=target_sym_obj.qualified_name
                    if target_sym_obj
                    else None,
                )

                existing_bp = db.execute(
                    select(TestCase).where(
                        TestCase.tenant_id == tenant_id,
                        TestCase.test_suite_id == bp_suite.id,
                        TestCase.test_key == t_key,
                    )
                ).scalar_one_or_none()
                if existing_bp is None:
                    existing_bp = TestCase(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        test_suite_id=bp_suite.id,
                        test_symbol_id=target_sym_id,
                        analysis_run_id=analysis_run.id,
                        test_key=t_key,
                        title=f"[Recommended Blueprint] Verify {u_req.req_code}: {u_req.title}"[:255],
                        test_kind=t_kind,
                        scenario_description=(
                            f"Recommended {t_kind.lower()} test for untested requirement `{u_req.req_code}`. "
                            f"{given_c}; {when_c}; {then_c}."
                        ),
                        generated_code_blueprint=code_bp,
                        last_observed_status="NOT_EXECUTED_BLUEPRINT",
                        confidence_score=Decimal("0.8400"),
                        review_status="DRAFT_AI",
                    )
                    db.add(existing_bp)
                    db.flush()
                    generated_blueprints_count += 1

                    db.add(
                        TestCoverageLink(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            test_case_id=existing_bp.id,
                            target_symbol_id=target_sym_id,
                            target_business_rule_id=target_rule_id,
                            target_requirement_id=u_req.id,
                            coverage_source="AI_TRACEABILITY",
                            confidence_score=Decimal("0.8400"),
                        )
                    )
                    coverage_links_count += 1

        db.flush()

        # ------------------------------------------------------------------
        # 4. Risk Intelligence Synthesis (Security, Dependency, Architecture, SPOF, Data, Performance, Infra)
        # ------------------------------------------------------------------
        # 4a. Dependency risks ONLY when backed by verified advisory match
        for dep in dependency_records:
            if dep.advisory_id and dep.advisory_severity:
                risk_candidates.append(
                    ExtractedRiskCandidate(
                        risk_category="DEPENDENCY",
                        severity=dep.advisory_severity,
                        likelihood="HIGH",
                        title=f"Vulnerable / EOL Dependency `{dep.package_name}` ({dep.version_spec}) [{dep.advisory_id}]",
                        statement_markdown=(
                            f"Manifest `{dep.manifest_path}` declares `{dep.package_name}{dep.version_spec}`, "
                            f"matching verified advisory **{dep.advisory_id}** ({dep.advisory_severity}): {dep.advisory_summary}"
                        ),
                        remediation_recommendation=(
                            f"Upgrade `{dep.package_name}` in `{dep.manifest_path}` to a patched, supported release and pin the cryptographic hash."
                        ),
                        affected_components=[dep.manifest_path, dep.package_name],
                        relative_path=dep.manifest_path,
                        start_line=dep.start_line,
                        end_line=dep.start_line,
                        excerpt_text=dep.excerpt_text,
                        confidence_score=0.98,
                        cwe_or_advisory_ref=dep.advisory_id,
                    )
                )

        # 4b. Unauthenticated State-Mutating API Endpoint Risk
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
            if ep.http_method in ("POST", "PUT", "DELETE", "PATCH") and not ep.auth_required_inferred:
                h_sym = symbol_by_id.get(ep.handler_symbol_id) if ep.handler_symbol_id else None
                h_file = file_by_id.get(h_sym.code_file_id) if h_sym else None
                risk_candidates.append(
                    ExtractedRiskCandidate(
                        risk_category="SECURITY",
                        severity="HIGH",
                        likelihood="HIGH",
                        title=f"Unauthenticated State-Mutating Endpoint `{ep.http_method} {ep.route_pattern}`",
                        statement_markdown=(
                            f"Endpoint `{ep.http_method} {ep.route_pattern}` performs state mutation without a detected authentication/authorization guard (`CWE-306`)."
                        ),
                        remediation_recommendation=(
                            "Enforce authentication middleware (`Depends(get_current_user)` / `@PreAuthorize`) and tenant RBAC verification on this route."
                        ),
                        affected_components=[ep.route_pattern, h_sym.qualified_name if h_sym else "API Gateway"],
                        relative_path=h_file.relative_path if h_file else "",
                        start_line=h_sym.start_line if h_sym else 1,
                        end_line=h_sym.end_line if h_sym else 5,
                        excerpt_text=f"{ep.http_method} {ep.route_pattern} (auth_required_inferred=False)",
                        confidence_score=0.91,
                        cwe_or_advisory_ref="CWE-306",
                    )
                )

        # 4c. Single Point of Failure (SPOF) & Tight Coupling Risk
        fan_in_by_sym: dict[uuid.UUID, int] = {}
        fan_out_by_sym: dict[uuid.UUID, int] = {}
        for ce in call_edges:
            fan_out_by_sym[ce.caller_symbol_id] = fan_out_by_sym.get(ce.caller_symbol_id, 0) + 1
            if ce.callee_symbol_id:
                fan_in_by_sym[ce.callee_symbol_id] = fan_in_by_sym.get(ce.callee_symbol_id, 0) + 1
        for sr in sym_refs:
            fan_in_by_sym[sr.referenced_symbol_id] = fan_in_by_sym.get(sr.referenced_symbol_id, 0) + 1

        prod_symbols = [
            s
            for s in symbols
            if s.code_file_id in file_by_id
            and not is_test_file_path(file_by_id[s.code_file_id].relative_path)
        ]
        for s in prod_symbols:
            f_in = fan_in_by_sym.get(s.id, 0)
            f_out = fan_out_by_sym.get(s.id, 0)
            s_file = file_by_id[s.code_file_id]
            if (f_in >= 2 or s.cyclomatic_complexity >= 6) and s.id not in covered_symbol_ids_discovered:
                risk_candidates.append(
                    ExtractedRiskCandidate(
                        risk_category="SPOF_COUPLING",
                        severity="HIGH" if s.cyclomatic_complexity >= 10 or f_in >= 4 else "MEDIUM",
                        likelihood="MEDIUM",
                        title=f"Untested Critical Component / SPOF Candidate `{s.qualified_name}`",
                        statement_markdown=(
                            f"Symbol `{s.qualified_name}` (`{s.symbol_kind}`) has measured cyclomatic complexity **{s.cyclomatic_complexity}**, "
                            f"fan-in **{f_in}**, fan-out **{f_out}**, and **0** discovered repository tests."
                        ),
                        remediation_recommendation=(
                            f"Add unit and characterization tests covering `{s.qualified_name}` before modifying downstream callers."
                        ),
                        affected_components=[s.qualified_name, s_file.relative_path],
                        relative_path=s_file.relative_path,
                        start_line=s.start_line,
                        end_line=s.end_line,
                        excerpt_text=s.signature_text or s.qualified_name,
                        confidence_score=0.93,
                    )
                )

        # 4d. Data Integrity & Database Migration Risk
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
        db_cols = (
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
        for tbl in db_tables:
            t_cols = [c for c in db_cols if c.db_table_id == tbl.id]
            pii_nullable = [c.column_name for c in t_cols if c.is_pii_candidate and c.is_nullable]
            has_pk = any(c.is_primary_key for c in t_cols)
            if not has_pk and tbl.table_kind == "TABLE":
                risk_candidates.append(
                    ExtractedRiskCandidate(
                        risk_category="DATA_INTEGRITY",
                        severity="HIGH",
                        likelihood="MEDIUM",
                        title=f"Database Table `{tbl.table_name}` Lacks Primary Key Constraint",
                        statement_markdown=(
                            f"Relational table `{tbl.table_name}` has no declared PRIMARY KEY column, risking duplicate rows and replication drift during migration."
                        ),
                        remediation_recommendation=(
                            f"Add a deterministic primary key constraint and uniqueness index to `{tbl.table_name}`."
                        ),
                        affected_components=[tbl.table_name],
                        relative_path="",
                        start_line=1,
                        end_line=5,
                        excerpt_text=f"TABLE {tbl.table_name} (is_primary_key=False)",
                        confidence_score=0.96,
                    )
                )
            if pii_nullable:
                risk_candidates.append(
                    ExtractedRiskCandidate(
                        risk_category="DATA_INTEGRITY",
                        severity="MEDIUM",
                        likelihood="MEDIUM",
                        title=f"Sensitive/PII Columns in `{tbl.table_name}` Require Encryption & Governance Audit",
                        statement_markdown=(
                            f"Table `{tbl.table_name}` contains PII-candidate columns (`{', '.join(pii_nullable)}`) that require column-level encryption, masking, and retention policies."
                        ),
                        remediation_recommendation=(
                            f"Apply envelope encryption or column masking for `{', '.join(pii_nullable)}` on `{tbl.table_name}`."
                        ),
                        affected_components=[tbl.table_name, *pii_nullable],
                        relative_path="",
                        start_line=1,
                        end_line=5,
                        excerpt_text=f"Table {tbl.table_name} PII columns: {', '.join(pii_nullable)}",
                        confidence_score=0.90,
                    )
                )

        # 4e. Operational & Infrastructure Risk
        infra_resources = (
            db.execute(
                select(InfraResource).where(
                    InfraResource.tenant_id == tenant_id,
                    InfraResource.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        for ir in infra_resources:
            attrs = ir.configuration_attributes or {}
            if ir.iac_tool == "DOCKERFILE" and (
                attrs.get("runs_as_root") is True or not attrs.get("has_healthcheck", True)
            ):
                risk_candidates.append(
                    ExtractedRiskCandidate(
                        risk_category="OPERATIONAL_INFRA",
                        severity="MEDIUM",
                        likelihood="MEDIUM",
                        title=f"Container Hardening Risk on `{ir.resource_name}` ({ir.iac_tool})",
                        statement_markdown=(
                            f"Container image `{ir.resource_name}` exhibits operational/security posture gaps (`attributes={attrs}`)."
                        ),
                        remediation_recommendation=(
                            "Specify a non-root `USER` directive and an explicit `HEALTHCHECK` instruction in the Dockerfile."
                        ),
                        affected_components=[ir.resource_name],
                        relative_path="",
                        start_line=1,
                        end_line=10,
                        excerpt_text=f"{ir.iac_tool} {ir.resource_name}: {attrs}",
                        confidence_score=0.92,
                    )
                )

        # Persist Risk Findings into `findings` + `finding_evidence_links`
        cat_map = {
            "SECURITY": "RISK_SECURITY",
            "DEPENDENCY": "RISK_DEPENDENCY",
            "ARCHITECTURAL": "RISK_ARCHITECTURE",
            "SPOF_COUPLING": "RISK_SPOF",
            "DATA_INTEGRITY": "RISK_DATA_INTEGRITY",
            "PERFORMANCE": "RISK_PERFORMANCE",
            "OPERATIONAL_INFRA": "RISK_OPERATIONAL",
        }
        risk_findings_count = 0
        persisted_risk_findings: list[tuple[Finding, ExtractedRiskCandidate]] = []

        for r_cand in risk_candidates:
            f_cat = cat_map.get(r_cand.risk_category, "RISK_ARCHITECTURE")
            existing_f = db.execute(
                select(Finding).where(
                    Finding.tenant_id == tenant_id,
                    Finding.application_id == application_id,
                    Finding.snapshot_id == snapshot.id,
                    Finding.finding_category == f_cat,
                    Finding.title == r_cand.title[:255],
                )
            ).scalar_one_or_none()

            subj_ke: KnowledgeEntity | None = None
            for comp in r_cand.affected_components:
                subj_ke = ke_by_title_lower.get(comp.lower())
                if subj_ke:
                    break

            r_ver = (
                ver_by_path.get(r_cand.relative_path)
                if r_cand.relative_path
                else None
            ) or fallback_ver
            r_anchor: EvidenceAnchor | None = None
            if r_ver is not None:
                r_anchor = self.graph_service.get_or_create_evidence_anchor(
                    db,
                    tenant_id=tenant_id,
                    snapshot_id=snapshot.id,
                    artifact_version_id=r_ver.id,
                    locator_type="LINE_RANGE",
                    start_line=max(1, r_cand.start_line),
                    end_line=max(1, r_cand.end_line),
                    excerpt_text=r_cand.excerpt_text or r_cand.title,
                    ast_or_json_path=r_cand.cwe_or_advisory_ref,
                )

            structured_md = (
                f"{r_cand.statement_markdown}\n\n"
                f"- **Risk Category**: `{r_cand.risk_category}`\n"
                f"- **Severity**: `{r_cand.severity}` | **Likelihood**: `{r_cand.likelihood}`\n"
                f"- **Affected Components**: {', '.join(f'`{c}`' for c in r_cand.affected_components)}\n"
                f"- **Reference**: `{r_cand.cwe_or_advisory_ref or 'STATIC_ANALYSIS'}`\n"
                f"- **Remediation Recommendation**: {r_cand.remediation_recommendation}"
            )

            if existing_f is None:
                existing_f = Finding(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    application_id=application_id,
                    snapshot_id=snapshot.id,
                    analysis_run_id=analysis_run.id,
                    subject_entity_id=subj_ke.id if subj_ke else None,
                    producing_agent_run_id=None,
                    finding_category=f_cat,
                    severity=r_cand.severity,
                    title=r_cand.title[:255],
                    statement_markdown=structured_md,
                    origin_type=r_cand.origin_type,
                    confidence_score=Decimal(str(round(r_cand.confidence_score, 4))),
                    review_status="PENDING_REVIEW",
                    version_no=1,
                )
                db.add(existing_f)
                db.flush()
                risk_findings_count += 1

            if r_anchor is not None:
                existing_lnk = db.execute(
                    select(FindingEvidenceLink).where(
                        FindingEvidenceLink.tenant_id == tenant_id,
                        FindingEvidenceLink.evidence_anchor_id == r_anchor.id,
                        FindingEvidenceLink.finding_id == existing_f.id,
                    )
                ).scalar_one_or_none()
                if existing_lnk is None:
                    db.add(
                        FindingEvidenceLink(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            evidence_anchor_id=r_anchor.id,
                            finding_id=existing_f.id,
                            evidence_role="PRIMARY_DEFINITION",
                            relevance_weight=existing_f.confidence_score,
                            rationale_note=r_cand.remediation_recommendation[:240],
                        )
                    )
            persisted_risk_findings.append((existing_f, r_cand))

        db.flush()

        # ------------------------------------------------------------------
        # 5. Technical Debt Intelligence (`technical_debt_items`)
        # ------------------------------------------------------------------
        debt_items_created: list[TechnicalDebtItem] = []

        def _upsert_debt_item(
            *,
            debt_cat: str,
            sev: str,
            est_hours: int,
            desc: str,
            entity_id: uuid.UUID | None = None,
            finding_id: uuid.UUID | None = None,
        ) -> TechnicalDebtItem:
            existing = db.execute(
                select(TechnicalDebtItem).where(
                    TechnicalDebtItem.tenant_id == tenant_id,
                    TechnicalDebtItem.snapshot_id == snapshot.id,
                    TechnicalDebtItem.debt_category == debt_cat,
                    TechnicalDebtItem.description == desc,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            item = TechnicalDebtItem(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot.id,
                analysis_run_id=analysis_run.id,
                affected_entity_id=entity_id,
                finding_id=finding_id,
                debt_category=debt_cat,
                severity=sev,
                estimated_remediation_hours=est_hours,
                description=desc,
            )
            db.add(item)
            db.flush()
            debt_items_created.append(item)
            return item

        # 5a. High Complexity Functions & Modules (Measured Cyclomatic/Cognitive Complexity)
        for s in prod_symbols:
            if s.cyclomatic_complexity >= 6 or s.cognitive_complexity >= 8:
                sev = "HIGH" if s.cyclomatic_complexity >= 12 else "MEDIUM"
                est_h = max(2, int(s.cyclomatic_complexity * 1.5))
                ke = ke_by_symbol_id.get(s.id)
                _upsert_debt_item(
                    debt_cat="HIGH_COMPLEXITY",
                    sev=sev,
                    est_hours=est_h,
                    entity_id=ke.id if ke else None,
                    desc=(
                        f"[MEASURED] Symbol `{s.qualified_name}` has cyclomatic complexity={s.cyclomatic_complexity}, "
                        f"cognitive complexity={s.cognitive_complexity}, lines={s.end_line - s.start_line + 1}. "
                        f"[ESTIMATE] Remediation effort ~{est_h}h to decompose branching logic."
                    ),
                )

        # 5b. Duplicated Code & Repeated Business Logic (Measured AST Body Hash & Rule Condition Collisions)
        hash_groups: dict[str, list[CodeSymbol]] = {}
        for s in prod_symbols:
            if s.body_ast_hash and (s.end_line - s.start_line) >= 3:
                hash_groups.setdefault(s.body_ast_hash, []).append(s)
        for ast_hash, dup_syms in hash_groups.items():
            if len(dup_syms) >= 2:
                names = ", ".join(f"`{x.qualified_name}`" for x in dup_syms[:4])
                ke = ke_by_symbol_id.get(dup_syms[0].id)
                _upsert_debt_item(
                    debt_cat="DUPLICATED_CODE",
                    sev="MEDIUM",
                    est_hours=4 * len(dup_syms),
                    entity_id=ke.id if ke else None,
                    desc=(
                        f"[MEASURED] {len(dup_syms)} symbols share identical structural AST hash `{ast_hash[:12]}...`: {names}. "
                        f"[ESTIMATE] ~{4 * len(dup_syms)}h to extract shared domain utility."
                    ),
                )

        # Also check repeated business rule condition expressions across symbols
        cond_groups: dict[str, list[BusinessRule]] = {}
        for br in rules:
            norm_c = br.condition_expression.strip().lower()
            if len(norm_c) > 12:
                cond_groups.setdefault(norm_c, []).append(br)
        for _, dup_rules in cond_groups.items():
            if len(dup_rules) >= 2:
                r_codes = ", ".join(f"`{r.rule_code}`" for r in dup_rules[:4])
                _upsert_debt_item(
                    debt_cat="DUPLICATED_CODE",
                    sev="MEDIUM",
                    est_hours=6,
                    entity_id=dup_rules[0].knowledge_entity_id,
                    desc=(
                        f"[MEASURED] Repeated business logic condition across {len(dup_rules)} rules ({r_codes}): "
                        f"`{dup_rules[0].condition_expression[:100]}`. [ESTIMATE] ~6h to consolidate policy evaluation."
                    ),
                )

        # 5c. Dead or Potentially Unused Code (Measured 0 incoming calls & 0 symbol references)
        entrypoint_sym_ids = {
            ep.handler_symbol_id for ep in api_endpoints if ep.handler_symbol_id
        }
        for s in prod_symbols:
            if (
                s.symbol_kind in ("FUNCTION", "METHOD")
                and not s.name.startswith("__")
                and s.id not in entrypoint_sym_ids
                and fan_in_by_sym.get(s.id, 0) == 0
                and s.id not in covered_symbol_ids_discovered
            ):
                ke = ke_by_symbol_id.get(s.id)
                _upsert_debt_item(
                    debt_cat="DEAD_CODE",
                    sev="LOW",
                    est_hours=2,
                    entity_id=ke.id if ke else None,
                    desc=(
                        f"[MEASURED] Symbol `{s.qualified_name}` has 0 incoming call edges, 0 symbol references, and is not bound to an API route. "
                        f"[ESTIMATE] ~2h to verify dynamic reflection usage or safely deprecate."
                    ),
                )

        # 5d. Circular Dependencies (Measured SCC / Cycle Edges in Knowledge Graph)
        cycle_rels = [
            r for r in knowledge_rels if r.relationship_type == "PART_OF_CYCLE"
        ]
        for cr in cycle_rels[:5]:
            _upsert_debt_item(
                debt_cat="CIRCULAR_DEPENDENCY",
                sev="HIGH",
                est_hours=12,
                entity_id=cr.source_entity_id,
                desc=(
                    f"[MEASURED] Strongly Connected Component (circular dependency cycle) detected involving entity `{cr.source_entity_id}` -> `{cr.target_entity_id}`. "
                    f"[ESTIMATE] ~12h to invert dependency via interface/domain event."
                ),
            )

        # 5e. Large / Tightly Coupled Modules & God Classes (Measured LOC & Method Count)
        methods_per_class: dict[uuid.UUID, int] = {}
        for s in prod_symbols:
            if s.parent_symbol_id:
                methods_per_class[s.parent_symbol_id] = (
                    methods_per_class.get(s.parent_symbol_id, 0) + 1
                )
        for s in prod_symbols:
            m_cnt = methods_per_class.get(s.id, 0)
            loc_span = max(1, s.end_line - s.start_line + 1)
            f_out = fan_out_by_sym.get(s.id, 0)
            if s.symbol_kind == "CLASS" and (loc_span >= 120 or m_cnt >= 6 or f_out >= 6):
                ke = ke_by_symbol_id.get(s.id)
                _upsert_debt_item(
                    debt_cat="GOD_CLASS",
                    sev="HIGH" if loc_span >= 250 or m_cnt >= 10 else "MEDIUM",
                    est_hours=16,
                    entity_id=ke.id if ke else None,
                    desc=(
                        f"[MEASURED] Class `{s.qualified_name}` spans {loc_span} lines with {m_cnt} methods and fan-out={f_out}. "
                        f"[ESTIMATE] ~16h to split responsibilities into focused domain services."
                    ),
                )

        # 5f. SQL Coupled to Controller / Service Without Repository Abstraction (`SQL_COUPLED_UI`)
        sql_rels = [
            r
            for r in knowledge_rels
            if r.relationship_type in ("READS_FROM", "WRITES_TO")
        ]
        if sql_rels:
            _upsert_debt_item(
                debt_cat="SQL_COUPLED_UI",
                sev="MEDIUM",
                est_hours=8,
                entity_id=sql_rels[0].source_entity_id,
                desc=(
                    f"[MEASURED] {len(sql_rels)} direct embedded SQL table access edge(s) (`READS_FROM`/`WRITES_TO`) detected inside application logic. "
                    f"[ESTIMATE] ~8h to encapsulate data access behind typed repository/DAO interfaces."
                ),
            )

        # 5g. Missing Tests on Requirements & Critical Business Logic (`MISSING_TESTS`)
        if untested_reqs:
            _upsert_debt_item(
                debt_cat="MISSING_TESTS",
                sev="HIGH" if len(untested_reqs) >= 3 else "MEDIUM",
                est_hours=max(4, len(untested_reqs) * 3),
                entity_id=untested_reqs[0].knowledge_entity_id,
                desc=(
                    f"[MEASURED] {len(untested_reqs)} of {len(requirements)} requirement(s) lack discovered repository tests (`EXISTING_IN_REPO`). "
                    f"[ESTIMATE] ~{max(4, len(untested_reqs) * 3)}h to implement and execute the generated characterization test blueprints."
                ),
            )

        # 5h. Outdated / Unpinned Dependencies (`DEPRECATED_DEPENDENCY`)
        for dep in dependency_records:
            if dep.is_outdated_or_eol or not dep.is_pinned:
                _upsert_debt_item(
                    debt_cat="DEPRECATED_DEPENDENCY",
                    sev="HIGH" if dep.advisory_id else "LOW",
                    est_hours=4 if dep.advisory_id else 2,
                    desc=(
                        f"[MEASURED] Dependency `{dep.package_name}` (`{dep.version_spec}`) in `{dep.manifest_path}` "
                        f"({'matched advisory ' + dep.advisory_id if dep.advisory_id else 'is unpinned'}). "
                        f"[ESTIMATE] ~{4 if dep.advisory_id else 2}h for version pinning and regression verification."
                    ),
                )

        db.flush()

        # ------------------------------------------------------------------
        # 6. Modernization Recommendations (`modernization_recommendations`)
        # ------------------------------------------------------------------
        recs_created = 0
        all_debt_items = (
            db.execute(
                select(TechnicalDebtItem).where(
                    TechnicalDebtItem.tenant_id == tenant_id,
                    TechnicalDebtItem.snapshot_id == snapshot.id,
                )
            )
            .scalars()
            .all()
        )
        debt_by_cat: dict[str, TechnicalDebtItem] = {
            d.debt_category: d for d in all_debt_items
        }

        domains = (
            db.execute(
                select(BusinessDomain).where(
                    BusinessDomain.tenant_id == tenant_id,
                    BusinessDomain.application_id == application_id,
                )
            )
            .scalars()
            .all()
        )

        rec_blueprints: list[dict[str, Any]] = []

        # Recommendation 1: Characterization Test Harness (Phase 1 Stabilization)
        if "MISSING_TESTS" in debt_by_cat or untested_reqs:
            d_item = debt_by_cat.get("MISSING_TESTS")
            rec_blueprints.append(
                {
                    "addressed_debt_id": d_item.id if d_item else None,
                    "strategy_pattern": "INTRODUCE_CHARACTERIZATION_TESTS",
                    "title": f"Establish Characterization Test Suite for {len(untested_reqs)} Untested Requirement(s)",
                    "current_state_summary": (
                        f"Measured repository coverage leaves {len(untested_reqs)} of {len(requirements)} discovered requirement(s) "
                        f"without automated regression tests, creating regression risk during refactoring."
                    ),
                    "target_state_architecture": (
                        "Automated CI test harness executing deterministic unit, API contract, and characterization tests "
                        "mapped to every `MUST`-priority business rule and requirement."
                    ),
                    "step_by_step_plan_markdown": (
                        "1. **Phase 1 (Stabilization)**: Review and adopt the generated characterization test blueprints (`generated/characterization_test_blueprints.py`).\n"
                        "2. Bind assertions to live service fixtures for each `MUST` requirement.\n"
                        "3. Export Cobertura `coverage.xml` in CI to promote coverage links from `STATIC_CALL_GRAPH` to `COVERAGE_REPORT`."
                    ),
                    "risk_level": "LOW",
                    "effort_tshirt": "S" if len(untested_reqs) <= 4 else "M",
                    "confidence_score": Decimal("0.9400"),
                }
            )

        # Recommendation 2: Raw SQL Decoupling & Data Access Layer (Phase 2 Architecture)
        if "SQL_COUPLED_UI" in debt_by_cat or sql_rels:
            d_item = debt_by_cat.get("SQL_COUPLED_UI")
            rec_blueprints.append(
                {
                    "addressed_debt_id": d_item.id if d_item else None,
                    "strategy_pattern": "REPLACE_RAW_SQL",
                    "title": "Decouple Embedded SQL Queries into Typed Repository / ORM Layer",
                    "current_state_summary": (
                        f"Detected {len(sql_rels)} direct SQL access edge(s) (`READS_FROM`/`WRITES_TO`) embedded inside business/API modules."
                    ),
                    "target_state_architecture": (
                        "Dedicated Repository pattern using parameterized SQLAlchemy ORM queries and explicit transaction boundaries."
                    ),
                    "step_by_step_plan_markdown": (
                        "1. **Phase 2 (Technical Debt & Architecture)**: Extract inline SQL strings into dedicated Repository methods.\n"
                        "2. Replace any string interpolation with bound parameters (`:param`).\n"
                        "3. Verify schema invariants against discovered `db_tables` and `db_foreign_keys`."
                    ),
                    "risk_level": "MEDIUM",
                    "effort_tshirt": "M",
                    "confidence_score": Decimal("0.9100"),
                }
            )

        # Recommendation 3: Dependency & Runtime Remediation (Phase 1 / Phase 3)
        if "DEPRECATED_DEPENDENCY" in debt_by_cat or any(r.risk_category == "SECURITY" for _, r in persisted_risk_findings):
            d_item = debt_by_cat.get("DEPRECATED_DEPENDENCY")
            rec_blueprints.append(
                {
                    "addressed_debt_id": d_item.id if d_item else None,
                    "strategy_pattern": "UPGRADE_RUNTIME",
                    "title": "Remediate Security Findings & Pin Dependency Manifests",
                    "current_state_summary": (
                        f"Identified {len(persisted_risk_findings)} security/operational risk finding(s) and {len(dependency_records)} dependency specification(s)."
                    ),
                    "target_state_architecture": (
                        "Zero hardcoded secrets, enforced authentication guards on all state-mutating API routes, and cryptographically pinned dependency lockfiles."
                    ),
                    "step_by_step_plan_markdown": (
                        "1. **Phase 1 (Critical Risks)**: Externalize secrets and enforce authentication dependencies on public mutation routes.\n"
                        "2. **Phase 3 (Platform Modernization)**: Upgrade any EOL/vulnerable packages and lock transitive dependencies."
                    ),
                    "risk_level": "LOW",
                    "effort_tshirt": "S",
                    "confidence_score": Decimal("0.9500"),
                }
            )

        # Recommendation 4: Evidence-Based Architecture Posture (Modular Monolith vs Service Extraction)
        # Note: Do NOT automatically recommend microservices unless multi-domain & scale evidence supports it
        distinct_non_core_domains = [d for d in domains if d.code != "CORE_DOMAIN"]
        if len(distinct_non_core_domains) >= 4 and len(prod_symbols) >= 25:
            rec_blueprints.append(
                {
                    "addressed_debt_id": debt_by_cat.get("GOD_CLASS", debt_by_cat.get("HIGH_COMPLEXITY")).id
                    if ("GOD_CLASS" in debt_by_cat or "HIGH_COMPLEXITY" in debt_by_cat)
                    else None,
                    "strategy_pattern": "EXTRACT_DOMAIN_SERVICE",
                    "title": f"Strangler-Fig Bounded Context Extraction Across {len(distinct_non_core_domains)} Discovered Domains",
                    "current_state_summary": (
                        f"Codebase spans {len(distinct_non_core_domains)} distinct business domains with {len(prod_symbols)} symbols and shared database tables."
                    ),
                    "target_state_architecture": (
                        "Well-defined bounded contexts with explicit API contracts and isolated database schemas before considering distributed services."
                    ),
                    "step_by_step_plan_markdown": (
                        "1. **Phase 2**: Enforce module boundary interfaces between discovered business domains.\n"
                        "2. **Phase 4 (Strategic Modernization)**: Where independent deployment scaling is justified by runtime telemetry, extract domain boundaries behind an API gateway."
                    ),
                    "risk_level": "HIGH",
                    "effort_tshirt": "L",
                    "confidence_score": Decimal("0.8300"),
                }
            )
        else:
            # Recommend Modular Monolith refinement instead of premature microservices
            d_item = debt_by_cat.get("HIGH_COMPLEXITY") or debt_by_cat.get("DUPLICATED_CODE")
            rec_blueprints.append(
                {
                    "addressed_debt_id": d_item.id if d_item else None,
                    "strategy_pattern": "MODULAR_MONOLITH_BOUNDARIES",
                    "title": "Consolidate Modular Monolith Boundaries (Avoid Premature Microservices)",
                    "current_state_summary": (
                        f"Snapshot contains {len(prod_symbols)} production symbol(s) across {len(domains)} domain(s) and {len(db_tables)} database table(s). "
                        f"Current scale and shared relational schema do NOT justify distributed microservice decomposition overhead."
                    ),
                    "target_state_architecture": (
                        "Clean Modular Monolith with isolated domain packages, decoupled repository interfaces, and shared ACID transactional guarantees."
                    ),
                    "step_by_step_plan_markdown": (
                        "1. **Phase 2 (Architecture Improvement)**: Refactor complex methods and duplicated business rules into domain-scoped service modules.\n"
                        "2. **Phase 4 (Strategic Optimization)**: Maintain single-deployable modular monolith posture while standardizing internal domain interfaces."
                    ),
                    "risk_level": "LOW",
                    "effort_tshirt": "M",
                    "confidence_score": Decimal("0.9200"),
                }
            )

        for rb in rec_blueprints:
            existing_rec = db.execute(
                select(ModernizationRecommendation).where(
                    ModernizationRecommendation.tenant_id == tenant_id,
                    ModernizationRecommendation.snapshot_id == snapshot.id,
                    ModernizationRecommendation.strategy_pattern == rb["strategy_pattern"],
                    ModernizationRecommendation.title == rb["title"][:255],
                )
            ).scalar_one_or_none()
            if existing_rec is None:
                db.add(
                    ModernizationRecommendation(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        application_id=application_id,
                        snapshot_id=snapshot.id,
                        analysis_run_id=analysis_run.id,
                        addressed_debt_id=rb["addressed_debt_id"],
                        strategy_pattern=rb["strategy_pattern"],
                        title=rb["title"][:255],
                        current_state_summary=rb["current_state_summary"],
                        target_state_architecture=rb["target_state_architecture"],
                        step_by_step_plan_markdown=rb["step_by_step_plan_markdown"],
                        risk_level=rb["risk_level"],
                        effort_tshirt=rb["effort_tshirt"],
                        confidence_score=rb["confidence_score"],
                        review_status="PENDING_REVIEW",
                    )
                )
                recs_created += 1

        db.flush()

        ti_summary = self.get_test_intelligence(
            db, tenant_id=tenant_id, snapshot_id=snapshot.id
        )["summary"]

        # ------------------------------------------------------------------
        # 7. Run Wave 4 Specialized AI Agents with DAG Dependencies
        # ------------------------------------------------------------------
        self._run_wave4_agents(
            db,
            tenant_id=tenant_id,
            application_id=application_id,
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run.id,
            discovered_tests=ti_summary["discovered_test_cases"],
            generated_blueprints=ti_summary["recommended_test_blueprints"],
            risk_count=len(persisted_risk_findings),
            debt_count=len(all_debt_items),
            recs_count=len(rec_blueprints),
        )

        return Wave4PipelineSummary(
            snapshot_id=snapshot.id,
            analysis_run_id=analysis_run.id,
            discovered_test_suites_count=ti_summary["discovered_suites"],
            discovered_test_cases_count=ti_summary["discovered_test_cases"],
            generated_test_blueprints_count=ti_summary["recommended_test_blueprints"],
            coverage_links_count=coverage_links_count,
            risk_findings_count=len(persisted_risk_findings),
            technical_debt_items_count=len(all_debt_items),
            modernization_recommendations_count=len(rec_blueprints),
        )

    def _run_wave4_agents(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        discovered_tests: int,
        generated_blueprints: int,
        risk_count: int,
        debt_count: int,
        recs_count: int,
    ) -> None:
        anchors = (
            db.execute(
                select(EvidenceAnchor)
                .where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.snapshot_id == snapshot_id,
                )
                .limit(20)
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
                .limit(30)
            )
            .scalars()
            .all()
        )
        valid_anchor_ids = {a.id for a in anchors}
        valid_entity_ids = {e.id for e in entities}
        primary_anchor_id = str(anchors[0].id)

        agent_specs = [
            (
                "test_intelligence_architect",
                "test_intelligence_architect_v1",
                "TEST_INTELLIGENCE",
                f"Test Intelligence Synthesis: {discovered_tests} Discovered Test(s), {generated_blueprints} Blueprint(s)",
                f"Wave 4 Test Intelligence Architect cataloged **{discovered_tests}** existing repository test(s) (`EXISTING_IN_REPO`) and synthesized **{generated_blueprints}** characterization test blueprint(s) (`AI_GENERATED_BLUEPRINT`).",
            ),
            (
                "risk_security_auditor",
                "risk_security_auditor_v1",
                "RISK_SYNTHESIS",
                f"Enterprise Risk Audit: {risk_count} Evidence-Backed Risk Finding(s)",
                f"Wave 4 Risk & Security Auditor identified **{risk_count}** security, dependency, SPOF, data integrity, and operational risk finding(s) with exact source evidence anchors.",
            ),
            (
                "technical_debt_analyzer",
                "technical_debt_analyzer_v1",
                "TECHNICAL_DEBT",
                f"Technical Debt Diagnostic: {debt_count} Quantified Debt Item(s)",
                f"Wave 4 Technical Debt Analyzer recorded **{debt_count}** debt item(s), separating measured AST/graph metrics from heuristic remediation effort estimates.",
            ),
            (
                "modernization_strategist",
                "modernization_strategist_v1",
                "MODERNIZATION",
                f"Modernization Strategy & 4-Phase Roadmap: {recs_count} Recommendation(s)",
                f"Wave 4 Modernization Strategist produced **{recs_count}** evidence-backed modernization recommendation(s) organized into a 4-phase stabilization and modernization roadmap.",
            ),
        ]

        created_runs: list[AgentRun] = []
        for agent_name, template_key, cat, title, stmt in agent_specs:
            existing_ar = db.execute(
                select(AgentRun).where(
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.analysis_run_id == analysis_run_id,
                    AgentRun.agent_name == agent_name,
                )
            ).scalar_one_or_none()
            if existing_ar is not None:
                created_runs.append(existing_ar)
                continue

            ar = AgentRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                analysis_run_id=analysis_run_id,
                parent_agent_run_id=created_runs[-1].id if created_runs else None,
                agent_name=agent_name,
                agent_version="4.0.0",
                status="RUNNING",
                attempt_count=1,
                input_context_refs={
                    "snapshot_id": str(snapshot_id),
                    "discovered_tests": discovered_tests,
                    "risk_count": risk_count,
                    "debt_count": debt_count,
                },
                started_at=datetime.now(timezone.utc),
            )
            db.add(ar)
            db.flush()

            if created_runs:
                prev_ar = created_runs[-1]
                db.add(
                    AgentTaskDependency(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        analysis_run_id=analysis_run_id,
                        upstream_agent_run_id=prev_ar.id,
                        downstream_agent_run_id=ar.id,
                        dependency_kind="DATA_PREREQUISITE",
                    )
                )
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
                    "discovered_tests": discovered_tests,
                    "generated_blueprints": generated_blueprints,
                    "risk_count": risk_count,
                    "debt_count": debt_count,
                    "recs_count": recs_count,
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
                        confidence_score=0.90,
                        cited_anchor_id=primary_anchor_id,
                        subject_entity_id=str(entities[0].id) if entities else None,
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note=f"Synthesized by Wave 4 {agent_name}.",
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
            created_runs.append(ar)

    # ------------------------------------------------------------------
    # Query Methods for FastAPI Endpoints
    # ------------------------------------------------------------------
    def get_test_intelligence(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        suite_origin: str | None = None,
        test_kind: str | None = None,
    ) -> dict[str, Any]:
        suites = (
            db.execute(
                select(TestSuite)
                .where(
                    TestSuite.tenant_id == tenant_id,
                    TestSuite.snapshot_id == snapshot_id,
                )
                .order_by(TestSuite.suite_name.asc())
            )
            .scalars()
            .all()
        )
        if suite_origin:
            suites = [s for s in suites if s.suite_origin == suite_origin]
        suite_by_id = {s.id: s for s in suites}
        suite_ids = list(suite_by_id.keys())

        cases = (
            db.execute(
                select(TestCase)
                .where(
                    TestCase.tenant_id == tenant_id,
                    TestCase.test_suite_id.in_(suite_ids) if suite_ids else False,
                )
                .order_by(TestCase.test_key.asc())
            )
            .scalars()
            .all()
            if suite_ids
            else []
        )
        if test_kind:
            cases = [c for c in cases if c.test_kind == test_kind]
        case_ids = [c.id for c in cases]

        cov_links = (
            db.execute(
                select(TestCoverageLink).where(
                    TestCoverageLink.tenant_id == tenant_id,
                    TestCoverageLink.test_case_id.in_(case_ids) if case_ids else False,
                )
            )
            .scalars()
            .all()
            if case_ids
            else []
        )
        links_by_case: dict[uuid.UUID, list[TestCoverageLink]] = {}
        for lnk in cov_links:
            links_by_case.setdefault(lnk.test_case_id, []).append(lnk)

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

        reqs = (
            db.execute(
                select(Requirement).where(
                    Requirement.tenant_id == tenant_id,
                    Requirement.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        req_by_id = {r.id: r for r in reqs}

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

        return {
            "snapshot_id": str(snapshot_id),
            "summary": {
                "total_suites": len(suites),
                "discovered_suites": sum(
                    1 for s in suites if s.suite_origin == "EXISTING_IN_REPO"
                ),
                "generated_blueprint_suites": sum(
                    1 for s in suites if s.suite_origin == "AI_GENERATED_BLUEPRINT"
                ),
                "total_test_cases": len(cases),
                "discovered_test_cases": sum(
                    1
                    for c in cases
                    if suite_by_id[c.test_suite_id].suite_origin == "EXISTING_IN_REPO"
                ),
                "recommended_test_blueprints": sum(
                    1
                    for c in cases
                    if suite_by_id[c.test_suite_id].suite_origin
                    == "AI_GENERATED_BLUEPRINT"
                ),
            },
            "test_suites": [
                {
                    "id": str(s.id),
                    "suite_name": s.suite_name,
                    "test_framework": s.test_framework,
                    "suite_origin": s.suite_origin,
                    "is_discovered_in_repo": s.suite_origin == "EXISTING_IN_REPO",
                }
                for s in suites
            ],
            "test_cases": [
                {
                    "id": str(c.id),
                    "test_suite_id": str(c.test_suite_id),
                    "suite_name": suite_by_id[c.test_suite_id].suite_name,
                    "test_framework": suite_by_id[c.test_suite_id].test_framework,
                    "suite_origin": suite_by_id[c.test_suite_id].suite_origin,
                    "is_discovered_in_repo": suite_by_id[c.test_suite_id].suite_origin
                    == "EXISTING_IN_REPO",
                    "test_key": c.test_key,
                    "title": c.title,
                    "test_kind": c.test_kind,
                    "scenario_description": c.scenario_description,
                    "generated_code_blueprint": c.generated_code_blueprint,
                    "last_observed_status": c.last_observed_status,
                    "confidence_score": float(c.confidence_score),
                    "review_status": c.review_status,
                    "is_confirmed_fact": c.review_status == "APPROVED",
                    "covered_targets": [
                        {
                            "coverage_link_id": str(l.id),
                            "coverage_source": l.coverage_source,
                            "is_measured_coverage": l.coverage_source
                            == "COVERAGE_REPORT",
                            "confidence_score": float(l.confidence_score),
                            "symbol_qualified_name": sym_by_id[
                                l.target_symbol_id
                            ].qualified_name
                            if l.target_symbol_id and l.target_symbol_id in sym_by_id
                            else None,
                            "rule_code": rule_by_id[
                                l.target_business_rule_id
                            ].rule_code
                            if l.target_business_rule_id
                            and l.target_business_rule_id in rule_by_id
                            else None,
                            "req_code": req_by_id[l.target_requirement_id].req_code
                            if l.target_requirement_id
                            and l.target_requirement_id in req_by_id
                            else None,
                        }
                        for l in links_by_case.get(c.id, [])
                    ],
                }
                for c in cases
            ],
        }

    def get_coverage_and_gaps(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Distinguish discovered test coverage (`COVERAGE_REPORT` / `STATIC_CALL_GRAPH` from `EXISTING_IN_REPO` suites)
        from estimated/inferred blueprint coverage (`AI_TRACEABILITY`) and surface untested requirements & critical components.
        """
        suites = (
            db.execute(
                select(TestSuite).where(
                    TestSuite.tenant_id == tenant_id,
                    TestSuite.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        suite_by_id = {s.id: s for s in suites}
        suite_ids = list(suite_by_id.keys())

        cases = (
            db.execute(
                select(TestCase).where(
                    TestCase.tenant_id == tenant_id,
                    TestCase.test_suite_id.in_(suite_ids) if suite_ids else False,
                )
            )
            .scalars()
            .all()
            if suite_ids
            else []
        )
        case_by_id = {c.id: c for c in cases}
        case_ids = list(case_by_id.keys())

        cov_links = (
            db.execute(
                select(TestCoverageLink).where(
                    TestCoverageLink.tenant_id == tenant_id,
                    TestCoverageLink.test_case_id.in_(case_ids) if case_ids else False,
                )
            )
            .scalars()
            .all()
            if case_ids
            else []
        )

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
        files = (
            db.execute(
                select(CodeFile).where(
                    CodeFile.tenant_id == tenant_id,
                    CodeFile.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        file_by_id = {f.id: f for f in files}
        prod_symbols = [
            s
            for s in symbols
            if s.code_file_id in file_by_id
            and not is_test_file_path(file_by_id[s.code_file_id].relative_path)
        ]

        discovered_req_ids: set[uuid.UUID] = set()
        inferred_blueprint_req_ids: set[uuid.UUID] = set()
        discovered_sym_ids: set[uuid.UUID] = set()
        measured_report_links = 0
        static_graph_links = 0
        ai_inferred_links = 0

        for l in cov_links:
            tc = case_by_id.get(l.test_case_id)
            st = suite_by_id.get(tc.test_suite_id) if tc else None
            is_existing = st is not None and st.suite_origin == "EXISTING_IN_REPO"
            if l.coverage_source == "COVERAGE_REPORT":
                measured_report_links += 1
            elif l.coverage_source in ("STATIC_CALL_GRAPH", "IMPORT_TRACE"):
                static_graph_links += 1
            else:
                ai_inferred_links += 1

            if is_existing:
                if l.target_requirement_id:
                    discovered_req_ids.add(l.target_requirement_id)
                if l.target_symbol_id:
                    discovered_sym_ids.add(l.target_symbol_id)
            else:
                if l.target_requirement_id:
                    inferred_blueprint_req_ids.add(l.target_requirement_id)

        untested_requirements = [
            {
                "id": str(r.id),
                "req_code": r.req_code,
                "req_type": r.req_type,
                "priority": r.priority,
                "title": r.title,
                "has_generated_blueprint": r.id in inferred_blueprint_req_ids,
                "coverage_state": "BLUEPRINT_RECOMMENDED_ONLY"
                if r.id in inferred_blueprint_req_ids
                else "UNCOVERED",
            }
            for r in reqs
            if r.id not in discovered_req_ids
        ]

        untested_critical_components = [
            {
                "symbol_id": str(s.id),
                "qualified_name": s.qualified_name,
                "symbol_kind": s.symbol_kind,
                "relative_path": file_by_id[s.code_file_id].relative_path,
                "cyclomatic_complexity": s.cyclomatic_complexity,
                "cognitive_complexity": s.cognitive_complexity,
            }
            for s in prod_symbols
            if s.id not in discovered_sym_ids
            and (s.cyclomatic_complexity >= 4 or s.symbol_kind == "CLASS")
        ]

        total_reqs = len(reqs)
        total_prod_syms = len(prod_symbols)
        discovered_req_pct = (
            round((len(discovered_req_ids) / total_reqs) * 100.0, 1)
            if total_reqs > 0
            else 0.0
        )
        discovered_sym_pct = (
            round((len(discovered_sym_ids) / total_prod_syms) * 100.0, 1)
            if total_prod_syms > 0
            else 0.0
        )

        return {
            "snapshot_id": str(snapshot_id),
            "coverage_metrics": {
                "total_requirements": total_reqs,
                "requirements_covered_by_existing_tests": len(discovered_req_ids),
                "requirements_with_blueprint_recommendations": len(
                    inferred_blueprint_req_ids
                ),
                "discovered_requirement_coverage_pct": discovered_req_pct,
                "total_production_symbols": total_prod_syms,
                "symbols_covered_by_existing_tests": len(discovered_sym_ids),
                "discovered_symbol_coverage_pct": discovered_sym_pct,
                "measured_coverage_report_links": measured_report_links,
                "static_call_graph_links": static_graph_links,
                "inferred_blueprint_links": ai_inferred_links,
            },
            "untested_requirements": untested_requirements,
            "untested_critical_components": untested_critical_components,
        }

    def get_risk_register(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        severity: str | None = None,
        risk_category: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(Finding).where(
            Finding.tenant_id == tenant_id,
            Finding.snapshot_id == snapshot_id,
            Finding.finding_category.in_(RISK_FINDING_CATEGORIES),
        )
        if severity:
            stmt = stmt.where(Finding.severity == severity)
        if risk_category:
            stmt = stmt.where(Finding.finding_category == risk_category)
        findings = db.execute(stmt.order_by(Finding.created_at.asc())).scalars().all()
        f_ids = [f.id for f in findings]

        ev_links = (
            db.execute(
                select(FindingEvidenceLink).where(
                    FindingEvidenceLink.tenant_id == tenant_id,
                    FindingEvidenceLink.finding_id.in_(f_ids) if f_ids else False,
                )
            )
            .scalars()
            .all()
            if f_ids
            else []
        )
        anchor_ids = list({l.evidence_anchor_id for l in ev_links})
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
        ev_by_finding: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for l in ev_links:
            if l.finding_id and l.evidence_anchor_id in anchor_by_id:
                anc = anchor_by_id[l.evidence_anchor_id]
                ev_by_finding.setdefault(l.finding_id, []).append(
                    {
                        "anchor_id": str(anc.id),
                        "start_line": anc.start_line,
                        "end_line": anc.end_line,
                        "snippet_sha256": anc.snippet_sha256,
                        "excerpt_text": anc.excerpt_text,
                        "rationale_note": l.rationale_note,
                    }
                )

        counts_by_sev: dict[str, int] = {}
        counts_by_cat: dict[str, int] = {}
        for f in findings:
            counts_by_sev[f.severity] = counts_by_sev.get(f.severity, 0) + 1
            counts_by_cat[f.finding_category] = (
                counts_by_cat.get(f.finding_category, 0) + 1
            )

        return {
            "snapshot_id": str(snapshot_id),
            "counts_by_severity": counts_by_sev,
            "counts_by_category": counts_by_cat,
            "risk_findings": [
                {
                    "id": str(f.id),
                    "finding_category": f.finding_category,
                    "severity": f.severity,
                    "likelihood": "HIGH"
                    if f.severity in ("CRITICAL", "HIGH")
                    else "MEDIUM",
                    "title": f.title,
                    "statement_markdown": f.statement_markdown,
                    "origin_type": f.origin_type,
                    "confidence_score": float(f.confidence_score),
                    "review_status": f.review_status,
                    "is_confirmed_fact": f.review_status == "APPROVED",
                    "version_no": f.version_no,
                    "evidence": ev_by_finding.get(f.id, []),
                }
                for f in findings
            ],
        }

    def get_technical_debt(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        debt_category: str | None = None,
        severity: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(TechnicalDebtItem).where(
            TechnicalDebtItem.tenant_id == tenant_id,
            TechnicalDebtItem.snapshot_id == snapshot_id,
        )
        if debt_category:
            stmt = stmt.where(TechnicalDebtItem.debt_category == debt_category)
        if severity:
            stmt = stmt.where(TechnicalDebtItem.severity == severity)
        items = db.execute(stmt.order_by(TechnicalDebtItem.severity.asc())).scalars().all()

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
        files = (
            db.execute(
                select(CodeFile).where(
                    CodeFile.tenant_id == tenant_id,
                    CodeFile.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )

        total_loc = sum(f.loc_code for f in files)
        max_cc = max((s.cyclomatic_complexity for s in symbols), default=0)
        avg_cc = (
            round(sum(s.cyclomatic_complexity for s in symbols) / len(symbols), 2)
            if symbols
            else 0.0
        )
        total_est_hours = sum(i.estimated_remediation_hours or 0 for i in items)

        return {
            "snapshot_id": str(snapshot_id),
            "measured_vs_estimated_summary": {
                "measured_metrics": {
                    "metric_nature": "MEASURED",
                    "total_files": len(files),
                    "total_loc_code": total_loc,
                    "total_symbols": len(symbols),
                    "max_cyclomatic_complexity": max_cc,
                    "avg_cyclomatic_complexity": avg_cc,
                    "total_debt_items_detected": len(items),
                },
                "heuristic_estimates": {
                    "metric_nature": "HEURISTIC_ESTIMATE",
                    "total_estimated_remediation_hours": total_est_hours,
                    "disclaimer": "Remediation hours are engineering effort estimates derived from item complexity and category, not measured historical actuals.",
                },
            },
            "technical_debt_items": [
                {
                    "id": str(i.id),
                    "debt_category": i.debt_category,
                    "severity": i.severity,
                    "estimated_remediation_hours": i.estimated_remediation_hours,
                    "is_effort_estimated": True,
                    "effort_nature": "HEURISTIC_ESTIMATE",
                    "description": i.description,
                    "affected_entity_id": str(i.affected_entity_id)
                    if i.affected_entity_id
                    else None,
                    "finding_id": str(i.finding_id) if i.finding_id else None,
                }
                for i in items
            ],
        }

    def get_modernization_assessment(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> dict[str, Any]:
        snap = db.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.tenant_id == tenant_id,
                RepositorySnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        repo = (
            db.execute(
                select(Repository).where(
                    Repository.tenant_id == tenant_id,
                    Repository.id == snap.repository_id,
                )
            ).scalar_one_or_none()
            if snap
            else None
        )
        domains = (
            db.execute(
                select(BusinessDomain).where(
                    BusinessDomain.tenant_id == tenant_id,
                    BusinessDomain.application_id == repo.application_id,
                )
            )
            .scalars()
            .all()
            if repo
            else []
        )
        files = (
            db.execute(
                select(CodeFile).where(
                    CodeFile.tenant_id == tenant_id,
                    CodeFile.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        infra = (
            db.execute(
                select(InfraResource).where(
                    InfraResource.tenant_id == tenant_id,
                    InfraResource.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        api_svcs = (
            db.execute(
                select(ApiService).where(
                    ApiService.tenant_id == tenant_id,
                    ApiService.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        risk_res = self.get_risk_register(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )
        debt_res = self.get_technical_debt(
            db, tenant_id=tenant_id, snapshot_id=snapshot_id
        )

        non_core_domains = [d.code for d in domains if d.code != "CORE_DOMAIN"]
        recommend_microservices = len(non_core_domains) >= 4 and len(files) >= 20
        iac_tools = sorted({r.iac_tool for r in infra})
        protocols = sorted({s.protocol for s in api_svcs})

        dimensions = [
            {
                "dimension": "ARCHITECTURE_POSTURE",
                "title": "Monolith vs. Modular Architecture & Service Decomposition",
                "recommended_posture": "SELECTIVE_DOMAIN_EXTRACTION"
                if recommend_microservices
                else "MODULAR_MONOLITH",
                "microservices_recommended": recommend_microservices,
                "rationale": (
                    f"Measured {len(files)} source file(s) across {len(domains)} business domain(s). "
                    + (
                        "Multi-domain scale supports selective Strangler-Fig boundary extraction."
                        if recommend_microservices
                        else "Evidence supports a well-structured Modular Monolith; premature microservice decomposition would add operational and distributed-transaction overhead without supporting scale evidence."
                    )
                ),
            },
            {
                "dimension": "DATABASE_MODERNIZATION",
                "title": "Database Schema & Data Access Modernization",
                "recommended_posture": "REPOSITORY_ABSTRACTION_AND_CONSTRAINTS",
                "rationale": (
                    "Enforce explicit foreign key and primary key constraints, encapsulate direct SQL queries behind repository interfaces, and protect PII columns."
                ),
            },
            {
                "dimension": "CLOUD_AND_INFRASTRUCTURE",
                "title": "Cloud Readiness & Container Infrastructure",
                "recommended_posture": "CONTAINER_HARDENING"
                if iac_tools
                else "STANDARDIZE_CONTAINER_PACKAGING",
                "rationale": (
                    f"Discovered IaC tooling: {', '.join(iac_tools) if iac_tools else 'None discovered in snapshot'}. "
                    "Focus on non-root container execution, healthchecks, and externalized secret configuration before cloud migration."
                ),
            },
            {
                "dimension": "API_AND_INTEGRATION",
                "title": "API Modernization & Contract Readiness",
                "recommended_posture": "CONTRACT_FIRST_AND_AUTH_GUARDED",
                "rationale": (
                    f"Discovered API protocols: {', '.join(protocols) if protocols else 'Internal modules'}. "
                    "Ensure all state-mutating endpoints enforce authentication and publish OpenAPI/GraphQL schemas."
                ),
            },
            {
                "dimension": "SECURITY_AND_OPERATIONS",
                "title": "Security & Operational Modernization",
                "recommended_posture": "ZERO_TRUST_AND_CHARACTERIZATION_TESTING",
                "rationale": (
                    f"Risk register contains {len(risk_res['risk_findings'])} finding(s) and {len(debt_res['technical_debt_items'])} technical debt item(s)."
                ),
            },
        ]

        return {
            "snapshot_id": str(snapshot_id),
            "microservices_recommended": recommend_microservices,
            "dimensions": dimensions,
        }

    def get_recommendations_and_roadmap(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> dict[str, Any]:
        recs = (
            db.execute(
                select(ModernizationRecommendation)
                .where(
                    ModernizationRecommendation.tenant_id == tenant_id,
                    ModernizationRecommendation.snapshot_id == snapshot_id,
                )
                .order_by(ModernizationRecommendation.confidence_score.desc())
            )
            .scalars()
            .all()
        )
        debt_items = (
            db.execute(
                select(TechnicalDebtItem).where(
                    TechnicalDebtItem.tenant_id == tenant_id,
                    TechnicalDebtItem.snapshot_id == snapshot_id,
                )
            )
            .scalars()
            .all()
        )
        debt_by_id = {d.id: d for d in debt_items}

        # Resolve supporting evidence anchors via linked findings / snapshot anchors
        finding_ids = [d.finding_id for d in debt_items if d.finding_id is not None]
        fe_links = (
            db.execute(
                select(FindingEvidenceLink).where(
                    FindingEvidenceLink.tenant_id == tenant_id,
                    FindingEvidenceLink.finding_id.in_(finding_ids)
                    if finding_ids
                    else False,
                )
            )
            .scalars()
            .all()
            if finding_ids
            else []
        )

        snap_anchors = (
            db.execute(
                select(EvidenceAnchor)
                .where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.snapshot_id == snapshot_id,
                )
                .order_by(EvidenceAnchor.created_at.asc())
                .limit(50)
            )
            .scalars()
            .all()
        )
        anchor_by_id = {a.id: a for a in snap_anchors}
        missing_anchor_ids = {
            l.evidence_anchor_id
            for l in fe_links
            if l.evidence_anchor_id not in anchor_by_id
        }
        if missing_anchor_ids:
            extra_anchors = (
                db.execute(
                    select(EvidenceAnchor).where(
                        EvidenceAnchor.tenant_id == tenant_id,
                        EvidenceAnchor.id.in_(list(missing_anchor_ids)),
                    )
                )
                .scalars()
                .all()
            )
            for ea in extra_anchors:
                anchor_by_id[ea.id] = ea

        fe_by_finding: dict[uuid.UUID, list[EvidenceAnchor]] = {}
        for l in fe_links:
            if l.finding_id and l.evidence_anchor_id in anchor_by_id:
                fe_by_finding.setdefault(l.finding_id, []).append(
                    anchor_by_id[l.evidence_anchor_id]
                )

        tshirt_hours = {
            "XS": "4–8 hours (Estimate)",
            "S": "8–24 hours (Estimate)",
            "M": "24–60 hours (Estimate)",
            "L": "60–120 hours (Estimate)",
            "XL": "120+ hours (Estimate)",
        }

        def _phase_for_strategy(strat: str) -> int:
            if strat in ("INTRODUCE_CHARACTERIZATION_TESTS", "UPGRADE_RUNTIME"):
                return 1
            if strat in ("REPLACE_RAW_SQL", "MODULAR_MONOLITH_BOUNDARIES"):
                return 2
            if strat in ("CONTAINER_SECURITY_HARDENING", "DATABASE_SCHEMA_DECOUPLING"):
                return 3
            return 4

        serialized_recs: list[dict[str, Any]] = []
        for r in recs:
            linked_debt = (
                debt_by_id.get(r.addressed_debt_id) if r.addressed_debt_id else None
            )
            rec_anchors: list[EvidenceAnchor] = []
            if linked_debt is not None:
                if linked_debt.finding_id and linked_debt.finding_id in fe_by_finding:
                    rec_anchors.extend(fe_by_finding[linked_debt.finding_id])
            if not rec_anchors and snap_anchors:
                rec_anchors.append(snap_anchors[0])

            dedup_evidence: list[dict[str, Any]] = []
            seen_anc_ids: set[uuid.UUID] = set()
            for anc in rec_anchors:
                if anc.id not in seen_anc_ids:
                    seen_anc_ids.add(anc.id)
                    dedup_evidence.append(
                        {
                            "anchor_id": str(anc.id),
                            "start_line": anc.start_line,
                            "end_line": anc.end_line,
                            "snippet_sha256": anc.snippet_sha256,
                            "excerpt_text": anc.excerpt_text[:260],
                        }
                    )

            phase_num = _phase_for_strategy(r.strategy_pattern)
            serialized_recs.append(
                {
                    "id": str(r.id),
                    "strategy_pattern": r.strategy_pattern,
                    "roadmap_phase": phase_num,
                    "title": r.title,
                    "current_state_summary": r.current_state_summary,
                    "target_state_architecture": r.target_state_architecture,
                    "step_by_step_plan_markdown": r.step_by_step_plan_markdown,
                    "risk_level": r.risk_level,
                    "effort_tshirt": r.effort_tshirt,
                    "estimated_effort_range": tshirt_hours.get(
                        r.effort_tshirt, "16–40 hours (Estimate)"
                    ),
                    "is_effort_estimated": True,
                    "effort_nature": "HEURISTIC_ESTIMATE",
                    "confidence_score": float(r.confidence_score),
                    "review_status": r.review_status,
                    "is_confirmed_fact": r.review_status == "APPROVED",
                    "addressed_debt_id": str(r.addressed_debt_id)
                    if r.addressed_debt_id
                    else None,
                    "addressed_debt_category": linked_debt.debt_category
                    if linked_debt
                    else None,
                    "evidence": dedup_evidence,
                }
            )

        roadmap_phases = [
            {
                "phase_number": 1,
                "phase_name": "Phase 1: Critical Risks & Stabilization",
                "objective": "Eliminate high/critical security exposures, pin vulnerable dependencies, and establish characterization tests before structural refactoring.",
                "prerequisites": ["Baseline snapshot ingestion & evidence anchor verification"],
                "expected_benefits": [
                    "Regression safety net for business rules",
                    "Remediation of CWE/CVE security findings",
                ],
                "effort_nature": "HEURISTIC_ESTIMATE",
                "recommendations": [
                    sr for sr in serialized_recs if sr["roadmap_phase"] == 1
                ],
            },
            {
                "phase_number": 2,
                "phase_name": "Phase 2: Technical Debt & Architecture Improvements",
                "objective": "Decouple inline SQL into repository interfaces, reduce high-complexity hotspots, and enforce clean modular boundaries.",
                "prerequisites": ["Phase 1 characterization test coverage"],
                "expected_benefits": [
                    "Lower cyclomatic complexity and reduced change amplification",
                    "Isolated data access layer",
                ],
                "effort_nature": "HEURISTIC_ESTIMATE",
                "recommendations": [
                    sr for sr in serialized_recs if sr["roadmap_phase"] == 2
                ],
            },
            {
                "phase_number": 3,
                "phase_name": "Phase 3: Platform & Infrastructure Modernization",
                "objective": "Harden container images, standardize CI coverage reporting, and enforce relational schema integrity constraints.",
                "prerequisites": ["Phase 2 repository abstraction"],
                "expected_benefits": [
                    "Production-grade container security posture",
                    "Deterministic database migration readiness",
                ],
                "effort_nature": "HEURISTIC_ESTIMATE",
                "recommendations": [
                    sr for sr in serialized_recs if sr["roadmap_phase"] == 3
                ],
            },
            {
                "phase_number": 4,
                "phase_name": "Phase 4: Strategic Modernization & Optimization",
                "objective": "Execute evidence-backed domain boundary consolidation or selective Strangler-Fig extraction where justified.",
                "prerequisites": [
                    "Phase 2 modular boundaries",
                    "Phase 3 infrastructure hardening",
                ],
                "expected_benefits": [
                    "Long-term domain maintainability and API contract alignment",
                ],
                "effort_nature": "HEURISTIC_ESTIMATE",
                "recommendations": [
                    sr for sr in serialized_recs if sr["roadmap_phase"] == 4
                ],
            },
        ]

        return {
            "snapshot_id": str(snapshot_id),
            "recommendations": serialized_recs,
            "roadmap_phases": roadmap_phases,
        }

    # ------------------------------------------------------------------
    # Human Review Workflows (`ModernizationRecommendation`, `TestCase`)
    # ------------------------------------------------------------------
    def review_modernization_recommendation(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        reviewer_user_id: uuid.UUID,
        new_status: str,
        review_comment: str | None = None,
        updated_title: str | None = None,
        updated_target_state_architecture: str | None = None,
        updated_effort_tshirt: str | None = None,
    ) -> dict[str, Any]:
        rec = db.execute(
            select(ModernizationRecommendation).where(
                ModernizationRecommendation.tenant_id == tenant_id,
                ModernizationRecommendation.id == recommendation_id,
            )
        ).scalar_one_or_none()
        if rec is None:
            raise ValueError(
                f"ModernizationRecommendation {recommendation_id} not found for tenant {tenant_id}"
            )

        prev_status = rec.review_status
        prev_snap = {
            "title": rec.title,
            "target_state_architecture": rec.target_state_architecture,
            "effort_tshirt": rec.effort_tshirt,
            "review_status": rec.review_status,
        }
        if updated_title:
            rec.title = updated_title[:255]
        if updated_target_state_architecture:
            rec.target_state_architecture = updated_target_state_architecture
        if updated_effort_tshirt:
            rec.effort_tshirt = updated_effort_tshirt
        rec.review_status = new_status

        new_snap = {
            "title": rec.title,
            "target_state_architecture": rec.target_state_architecture,
            "effort_tshirt": rec.effort_tshirt,
            "review_status": rec.review_status,
        }
        hist = ReviewHistory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            target_object_type="MODERNIZATION_RECOMMENDATION",
            target_object_id=rec.id,
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

        return {
            "id": str(rec.id),
            "title": rec.title,
            "strategy_pattern": rec.strategy_pattern,
            "target_state_architecture": rec.target_state_architecture,
            "effort_tshirt": rec.effort_tshirt,
            "review_status": rec.review_status,
            "is_confirmed_fact": rec.review_status == "APPROVED",
        }

    def review_test_case(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        test_case_id: uuid.UUID,
        reviewer_user_id: uuid.UUID,
        new_status: str,
        review_comment: str | None = None,
        updated_generated_code_blueprint: str | None = None,
    ) -> dict[str, Any]:
        tc = db.execute(
            select(TestCase).where(
                TestCase.tenant_id == tenant_id,
                TestCase.id == test_case_id,
            )
        ).scalar_one_or_none()
        if tc is None:
            raise ValueError(f"TestCase {test_case_id} not found for tenant {tenant_id}")

        prev_status = tc.review_status
        prev_snap = {
            "title": tc.title,
            "review_status": tc.review_status,
            "generated_code_blueprint": tc.generated_code_blueprint,
        }
        if updated_generated_code_blueprint is not None:
            tc.generated_code_blueprint = updated_generated_code_blueprint
        tc.review_status = new_status

        new_snap = {
            "title": tc.title,
            "review_status": tc.review_status,
            "generated_code_blueprint": tc.generated_code_blueprint,
        }
        hist = ReviewHistory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            target_object_type="TEST_CASE",
            target_object_id=tc.id,
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

        return {
            "id": str(tc.id),
            "test_key": tc.test_key,
            "title": tc.title,
            "review_status": tc.review_status,
            "is_confirmed_fact": tc.review_status == "APPROVED",
            "generated_code_blueprint": tc.generated_code_blueprint,
        }


__all__ = [
    "TestingModernizationService",
    "Wave4PipelineSummary",
]
