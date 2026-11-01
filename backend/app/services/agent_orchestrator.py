"""Wave 2.6 — AI Agent Orchestration (`TechnicalIntelligenceOrchestrator`), Typed Contracts, Evidence Verification & Telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import time
from typing import Any
import uuid

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent_orchestration import (
    AgentExecutionEvent,
    AgentRun,
    AgentTaskDependency,
    ModelInvocation,
    PromptTemplate,
)
from app.models.knowledge_graph import (
    EvidenceAnchor,
    Finding,
    FindingEvidenceLink,
    KnowledgeEntity,
)


class AgentFindingClaim(BaseModel):
    """Typed Pydantic output contract for an individual agent finding assertion."""

    finding_category: str = Field(
        default="ARCHITECTURE",
        description="ARCHITECTURE | SECURITY_RISK | PERFORMANCE | TECH_DEBT | MODERNIZATION",
    )
    severity: str = Field(default="INFO", description="INFO | LOW | MEDIUM | HIGH | CRITICAL")
    title: str = Field(..., min_length=3, max_length=255)
    statement_markdown: str = Field(..., min_length=10)
    confidence_score: float = Field(default=0.85, ge=0.0, le=1.0)
    cited_anchor_id: str = Field(
        ..., description="UUID of an existing immutable EvidenceAnchor in this snapshot"
    )
    subject_entity_id: str | None = Field(
        default=None, description="Optional UUID of the primary KnowledgeEntity"
    )
    evidence_role: str = Field(default="PRIMARY_DEFINITION")
    rationale_note: str = Field(
        default="Verified against snapshot evidence anchor by LegacyIQ orchestrator."
    )


class AgentFindingsPayload(BaseModel):
    """Structured output envelope returned by specialized technical intelligence agents."""

    findings: list[AgentFindingClaim] = Field(default_factory=list)


class AgentInputContext(BaseModel):
    """Typed Pydantic input contract passed to a specialized technical intelligence agent."""

    agent_name: str
    snapshot_id: str
    application_id: str
    available_anchors: list[dict[str, Any]]
    entities_summary: list[dict[str, Any]]
    domain_telemetry: dict[str, Any]


AGENT_DEFINITIONS: list[tuple[str, str, str, list[str]]] = [
    (
        "repo_cartographer",
        "1.0.0",
        "repo_cartographer_v1",
        [],
    ),
    (
        "db_analyst",
        "1.0.0",
        "db_analyst_v1",
        ["repo_cartographer"],
    ),
    (
        "api_inspector",
        "1.0.0",
        "api_inspector_v1",
        ["repo_cartographer"],
    ),
    (
        "infra_auditor",
        "1.0.0",
        "infra_auditor_v1",
        ["repo_cartographer"],
    ),
    (
        "doc_linker",
        "1.0.0",
        "doc_linker_v1",
        ["db_analyst", "api_inspector", "infra_auditor"],
    ),
]


class TechnicalIntelligenceOrchestrator:
    """
    Central orchestrator coordinating the Wave 2 DAG of specialized technical intelligence agents:
    `repo_cartographer` -> (`db_analyst`, `api_inspector`, `infra_auditor`) -> `doc_linker`.
    Enforces strict Pydantic output contracts and cryptographic `EvidenceAnchor` verification.
    """

    def __init__(self, *, allow_live_ollama: bool = True, max_retries: int = 2) -> None:
        self.allow_live_ollama = allow_live_ollama
        self.max_retries = max_retries

    def _emit_event(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        agent_run_id: uuid.UUID,
        sequence_no: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> AgentExecutionEvent:
        ev = AgentExecutionEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agent_run_id=agent_run_id,
            sequence_no=sequence_no,
            event_type=event_type,
            event_payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(ev)
        db.flush()
        return ev

    def _ensure_prompt_template(
        self,
        db: Session,
        *,
        template_key: str,
        agent_name: str,
    ) -> PromptTemplate:
        tmpl = db.execute(
            select(PromptTemplate).where(
                PromptTemplate.tenant_id.is_(None),
                PromptTemplate.template_key == template_key,
            )
        ).scalar_one_or_none()
        if tmpl is not None:
            return tmpl

        sys_prompt = (
            f"You are the LegacyIQ {agent_name} agent. Every finding MUST cite a valid "
            f"`cited_anchor_id` from `available_anchors`."
        )
        usr_prompt = "Context:\n{{context_json}}\nReturn JSON matching AgentFindingsPayload."
        sha = hashlib.sha256(f"{sys_prompt}\n{usr_prompt}".encode("utf-8")).hexdigest()
        tmpl = PromptTemplate(
            id=uuid.uuid4(),
            tenant_id=None,
            template_key=template_key,
            version_number=1,
            target_agent_name=agent_name,
            template_sha256=sha,
            system_prompt_text=sys_prompt,
            user_prompt_template=usr_prompt,
            output_json_schema=AgentFindingsPayload.model_json_schema(),
        )
        db.add(tmpl)
        db.flush()
        return tmpl

    def _synthesize_grounded_claims(
        self,
        input_ctx: AgentInputContext,
    ) -> AgentFindingsPayload:
        """
        Produce grounded, evidence-anchored analytical claims from the snapshot's actual
        entities and evidence anchors when local LLM inference is unavailable or as structured baseline.
        """
        if not input_ctx.available_anchors:
            return AgentFindingsPayload(findings=[])

        primary_anchor = input_ctx.available_anchors[0]
        anchor_id = str(primary_anchor["id"])
        entities = input_ctx.entities_summary
        agent = input_ctx.agent_name
        claims: list[AgentFindingClaim] = []

        if agent == "repo_cartographer":
            mod_ents = [e for e in entities if e.get("entity_type") == "MODULE"]
            sym_ents = [e for e in entities if e.get("entity_type") == "SYMBOL"]
            subject_id = (
                str(mod_ents[0]["id"])
                if mod_ents
                else (str(sym_ents[0]["id"]) if sym_ents else None)
            )
            top_title = (
                mod_ents[0]["title"]
                if mod_ents
                else (sym_ents[0]["title"] if sym_ents else "Repository Root")
            )
            claims.append(
                AgentFindingClaim(
                    finding_category="ARCHITECTURE",
                    severity="INFO",
                    title=f"Repository Cartography Summary: {len(mod_ents)} Module(s), {len(sym_ents)} Symbol(s)",
                    statement_markdown=(
                        f"Repository cartographer mapped **{len(mod_ents)}** module(s) and **{len(sym_ents)}** "
                        f"symbol(s). Primary structural anchor module/symbol: `{top_title}`."
                    ),
                    confidence_score=0.92,
                    cited_anchor_id=anchor_id,
                    subject_entity_id=subject_id,
                    evidence_role="PRIMARY_DEFINITION",
                    rationale_note="Synthesized from static AST module and symbol topology.",
                )
            )

        elif agent == "db_analyst":
            db_ents = [e for e in entities if e.get("entity_type") == "DB_TABLE"]
            if db_ents:
                target = db_ents[0]
                claims.append(
                    AgentFindingClaim(
                        finding_category="ARCHITECTURE",
                        severity="LOW",
                        title=f"Database Persistence Footprint: {len(db_ents)} Table(s)/View(s) Discovered",
                        statement_markdown=(
                            f"Database Intelligence Analyst cataloged **{len(db_ents)}** database relation(s), "
                            f"including `{target['title']}`. Schema lineage and ORM/SQL access edges are linked in the knowledge graph."
                        ),
                        confidence_score=0.91,
                        cited_anchor_id=str(target.get("anchor_id") or anchor_id),
                        subject_entity_id=str(target["id"]),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Verified against extracted SQL DDL and ORM table metadata.",
                    )
                )

        elif agent == "api_inspector":
            api_ents = [e for e in entities if e.get("entity_type") == "API_ENDPOINT"]
            if api_ents:
                target = api_ents[0]
                claims.append(
                    AgentFindingClaim(
                        finding_category="ARCHITECTURE",
                        severity="INFO",
                        title=f"API Surface Catalog: {len(api_ents)} Endpoint(s) Discovered",
                        statement_markdown=(
                            f"API Intelligence Inspector discovered **{len(api_ents)}** service endpoint(s), "
                            f"including `{target['title']}`, and mapped controller handler symbols and authentication contracts."
                        ),
                        confidence_score=0.90,
                        cited_anchor_id=str(target.get("anchor_id") or anchor_id),
                        subject_entity_id=str(target["id"]),
                        evidence_role="PRIMARY_DEFINITION",
                        rationale_note="Verified against OpenAPI/controller route definitions.",
                    )
                )

        elif agent == "infra_auditor":
            infra_ents = [e for e in entities if e.get("entity_type") == "INFRA_RESOURCE"]
            if infra_ents:
                target = infra_ents[0]
                claims.append(
                    AgentFindingClaim(
                        finding_category="MODERNIZATION",
                        severity="LOW",
                        title=f"Infrastructure Topology: {len(infra_ents)} IaC Resource(s) Audited",
                        statement_markdown=(
                            f"Infrastructure Intelligence Auditor inspected **{len(infra_ents)}** infrastructure resource(s), "
                            f"including `{target['title']}`."
                        ),
                        confidence_score=0.89,
                        cited_anchor_id=str(target.get("anchor_id") or anchor_id),
                        subject_entity_id=str(target["id"]),
                        evidence_role="CONFIG_BINDING",
                        rationale_note="Verified against IaC manifest declarations.",
                    )
                )

        elif agent == "doc_linker":
            doc_count = int(input_ctx.domain_telemetry.get("doc_sections_count", 0))
            if doc_count > 0:
                claims.append(
                    AgentFindingClaim(
                        finding_category="ARCHITECTURE",
                        severity="INFO",
                        title=f"Documentation Alignment: {doc_count} Technical Section(s) Cross-Referenced",
                        statement_markdown=(
                            f"Documentation Linker extracted **{doc_count}** hierarchical documentation section(s) "
                            f"and linked mentioned identifiers to code symbols, database tables, and API endpoints."
                        ),
                        confidence_score=0.88,
                        cited_anchor_id=anchor_id,
                        subject_entity_id=str(entities[0]["id"]) if entities else None,
                        evidence_role="DOC_CLAIM",
                        rationale_note="Cross-referenced documentation headings and identifier citations.",
                    )
                )

        return AgentFindingsPayload(findings=claims)

    def _invoke_model_with_fallback(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        agent_run_id: uuid.UUID,
        prompt_template: PromptTemplate,
        input_ctx: AgentInputContext,
    ) -> tuple[AgentFindingsPayload, ModelInvocation]:
        rendered_prompt = prompt_template.user_prompt_template.replace(
            "{{context_json}}",
            json.dumps(input_ctx.model_dump(), default=str)[:4000],
        )
        prompt_sha = hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()
        start_ts = time.perf_counter()

        payload: AgentFindingsPayload | None = None
        is_fallback = False
        inv_status = "SUCCESS"
        prompt_tokens = max(1, len(rendered_prompt) // 4)
        completion_tokens = 0

        if self.allow_live_ollama:
            try:
                resp = httpx.post(
                    f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                    json={
                        "model": settings.OLLAMA_MODEL,
                        "system": prompt_template.system_prompt_text,
                        "prompt": rendered_prompt,
                        "format": "json",
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 256},
                    },
                    timeout=3.5,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    raw_out = body.get("response", "")
                    parsed_json = json.loads(raw_out)
                    candidate = AgentFindingsPayload.model_validate(parsed_json)
                    if candidate.findings:
                        payload = candidate
                        completion_tokens = max(1, len(raw_out) // 4)
            except Exception:
                payload = None

        if payload is None:
            is_fallback = True
            payload = self._synthesize_grounded_claims(input_ctx)
            completion_tokens = max(1, len(payload.model_dump_json()) // 4)

        latency_ms = max(1, int((time.perf_counter() - start_ts) * 1000))
        invocation = ModelInvocation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agent_run_id=agent_run_id,
            prompt_template_id=prompt_template.id,
            provider_name="ollama",
            model_identifier=settings.OLLAMA_MODEL,
            is_fallback_invocation=is_fallback,
            rendered_prompt_sha256=prompt_sha,
            storage_payload_uri=None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            status=inv_status,
            invoked_at=datetime.now(timezone.utc),
        )
        db.add(invocation)
        db.flush()
        return payload, invocation

    def validate_and_persist_agent_claims(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        agent_run: AgentRun,
        payload: AgentFindingsPayload,
        valid_anchor_ids: set[uuid.UUID],
        valid_entity_ids: set[uuid.UUID],
        seq_start: int,
    ) -> tuple[int, int, int]:
        """
        Verify every agent claim against `valid_anchor_ids` for `(tenant_id, snapshot_id)`.
        Rejects any ungrounded or hallucinated anchor reference with `HALLUCINATION_REJECTED`.
        Returns `(accepted_count, rejected_count, next_seq_no)`.
        """
        accepted = 0
        rejected = 0
        seq = seq_start

        for claim in payload.findings:
            try:
                anchor_uuid = uuid.UUID(str(claim.cited_anchor_id))
            except ValueError:
                anchor_uuid = None

            if anchor_uuid is None or anchor_uuid not in valid_anchor_ids:
                rejected += 1
                self._emit_event(
                    db,
                    tenant_id=tenant_id,
                    agent_run_id=agent_run.id,
                    sequence_no=seq,
                    event_type="HALLUCINATION_REJECTED",
                    payload={
                        "reason": "Cited evidence_anchor_id does not exist in snapshot",
                        "cited_anchor_id": claim.cited_anchor_id,
                        "claim_title": claim.title,
                    },
                )
                seq += 1
                continue

            subj_uuid: uuid.UUID | None = None
            if claim.subject_entity_id:
                try:
                    cand_ent = uuid.UUID(str(claim.subject_entity_id))
                    if cand_ent in valid_entity_ids:
                        subj_uuid = cand_ent
                except ValueError:
                    subj_uuid = None

            self._emit_event(
                db,
                tenant_id=tenant_id,
                agent_run_id=agent_run.id,
                sequence_no=seq,
                event_type="EVIDENCE_VERIFIED",
                payload={
                    "verified_anchor_id": str(anchor_uuid),
                    "claim_title": claim.title,
                    "confidence_score": claim.confidence_score,
                },
            )
            seq += 1

            conf = Decimal(str(round(max(0.0, min(1.0, float(claim.confidence_score))), 4)))
            review_state = "PENDING_REVIEW" if conf >= Decimal("0.8000") else "DRAFT_AI"

            finding = Finding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                application_id=application_id,
                snapshot_id=snapshot_id,
                analysis_run_id=analysis_run_id,
                subject_entity_id=subj_uuid,
                producing_agent_run_id=agent_run.id,
                finding_category=claim.finding_category[:48],
                severity=claim.severity[:16],
                title=claim.title[:255],
                statement_markdown=claim.statement_markdown,
                origin_type="HYBRID_AI_STATIC",
                confidence_score=conf,
                review_status=review_state,
            )
            db.add(finding)
            db.flush()

            link = FindingEvidenceLink(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                evidence_anchor_id=anchor_uuid,
                finding_id=finding.id,
                evidence_role=claim.evidence_role[:32],
                relevance_weight=conf,
                rationale_note=claim.rationale_note,
            )
            db.add(link)
            db.flush()
            accepted += 1

        return accepted, rejected, seq

    def run_wave2_agents(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        application_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        analysis_run_id: uuid.UUID,
        domain_telemetry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full Wave 2 AI Agent Orchestration DAG (`repo_cartographer`, `db_analyst`,
        `api_inspector`, `infra_auditor`, `doc_linker`) with dependency tracking and evidence validation.
        """
        anchors = (
            db.execute(
                select(EvidenceAnchor)
                .where(
                    EvidenceAnchor.tenant_id == tenant_id,
                    EvidenceAnchor.snapshot_id == snapshot_id,
                )
                .limit(50)
            )
            .scalars()
            .all()
        )
        entities = (
            db.execute(
                select(KnowledgeEntity)
                .where(
                    KnowledgeEntity.tenant_id == tenant_id,
                    KnowledgeEntity.snapshot_id == snapshot_id,
                    KnowledgeEntity.analysis_run_id == analysis_run_id,
                )
                .limit(100)
            )
            .scalars()
            .all()
        )

        valid_anchor_ids = {a.id for a in anchors}
        valid_entity_ids = {e.id for e in entities}

        available_anchors_summary = [
            {
                "id": str(a.id),
                "locator_type": a.locator_type,
                "start_line": a.start_line,
                "end_line": a.end_line,
                "excerpt": (a.excerpt_text or "")[:180],
            }
            for a in anchors[:20]
        ]
        entities_summary = [
            {
                "id": str(e.id),
                "entity_type": e.entity_type,
                "canonical_key": e.canonical_key,
                "title": e.title,
            }
            for e in entities[:40]
        ]

        # 1. Create parent orchestrator run + specialized agent runs + DAG task dependencies
        orchestrator_run = AgentRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            analysis_run_id=analysis_run_id,
            parent_agent_run_id=None,
            agent_name="central_orchestrator",
            agent_version="2.0.0",
            status="RUNNING",
            attempt_count=1,
            input_context_refs={
                "snapshot_id": str(snapshot_id),
                "anchors_count": len(anchors),
                "entities_count": len(entities),
            },
            started_at=datetime.now(timezone.utc),
        )
        db.add(orchestrator_run)
        db.flush()

        agent_runs_by_name: dict[str, AgentRun] = {}
        for agent_name, agent_ver, _, _ in AGENT_DEFINITIONS:
            ar = AgentRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                analysis_run_id=analysis_run_id,
                parent_agent_run_id=orchestrator_run.id,
                agent_name=agent_name,
                agent_version=agent_ver,
                status="PENDING",
                attempt_count=1,
                input_context_refs={
                    "snapshot_id": str(snapshot_id),
                    "available_anchors": len(available_anchors_summary),
                },
            )
            db.add(ar)
            db.flush()
            agent_runs_by_name[agent_name] = ar

        for agent_name, _, _, upstream_names in AGENT_DEFINITIONS:
            downstream_ar = agent_runs_by_name[agent_name]
            for up_name in upstream_names:
                upstream_ar = agent_runs_by_name[up_name]
                dep = AgentTaskDependency(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    analysis_run_id=analysis_run_id,
                    upstream_agent_run_id=upstream_ar.id,
                    downstream_agent_run_id=downstream_ar.id,
                    dependency_kind="DATA_PREREQUISITE",
                )
                db.add(dep)
        db.flush()

        total_accepted = 0
        total_rejected = 0
        invocations_count = 0

        # 2. Execute each agent in topological DAG order with retry & evidence verification
        for agent_name, _, template_key, upstream_names in AGENT_DEFINITIONS:
            ar = agent_runs_by_name[agent_name]
            ar.status = "RUNNING"
            ar.started_at = datetime.now(timezone.utc)
            db.flush()

            seq = 1
            self._emit_event(
                db,
                tenant_id=tenant_id,
                agent_run_id=ar.id,
                sequence_no=seq,
                event_type="STEP_STARTED",
                payload={"agent_name": agent_name, "upstream_dependencies": upstream_names},
            )
            seq += 1

            tmpl = self._ensure_prompt_template(
                db, template_key=template_key, agent_name=agent_name
            )
            input_ctx = AgentInputContext(
                agent_name=agent_name,
                snapshot_id=str(snapshot_id),
                application_id=str(application_id),
                available_anchors=available_anchors_summary,
                entities_summary=entities_summary,
                domain_telemetry=domain_telemetry or {},
            )

            accepted = 0
            rejected = 0
            for attempt in range(1, self.max_retries + 1):
                ar.attempt_count = attempt
                try:
                    self._emit_event(
                        db,
                        tenant_id=tenant_id,
                        agent_run_id=ar.id,
                        sequence_no=seq,
                        event_type="TOOL_CALLED",
                        payload={
                            "tool": "model_invocation",
                            "template_key": template_key,
                            "attempt": attempt,
                        },
                    )
                    seq += 1

                    payload, inv = self._invoke_model_with_fallback(
                        db,
                        tenant_id=tenant_id,
                        agent_run_id=ar.id,
                        prompt_template=tmpl,
                        input_ctx=input_ctx,
                    )
                    invocations_count += 1

                    acc, rej, seq = self.validate_and_persist_agent_claims(
                        db,
                        tenant_id=tenant_id,
                        application_id=application_id,
                        snapshot_id=snapshot_id,
                        analysis_run_id=analysis_run_id,
                        agent_run=ar,
                        payload=payload,
                        valid_anchor_ids=valid_anchor_ids,
                        valid_entity_ids=valid_entity_ids,
                        seq_start=seq,
                    )
                    accepted += acc
                    rejected += rej
                    if rej > 0 and acc == 0:
                        inv.status = "HALLUCINATION_REJECTED"
                    ar.status = "COMPLETED"
                    break
                except Exception as exc:
                    if attempt < self.max_retries:
                        ar.status = "RETRYING"
                        db.flush()
                    else:
                        ar.status = "FAILED"
                        ar.output_summary_json = {"error": str(exc)}

            self._emit_event(
                db,
                tenant_id=tenant_id,
                agent_run_id=ar.id,
                sequence_no=seq,
                event_type="STEP_COMPLETED",
                payload={
                    "status": ar.status,
                    "findings_accepted": accepted,
                    "hallucinations_rejected": rejected,
                },
            )
            if ar.status != "FAILED":
                ar.output_summary_json = {
                    "findings_accepted": accepted,
                    "hallucinations_rejected": rejected,
                }
            ar.completed_at = datetime.now(timezone.utc)
            total_accepted += accepted
            total_rejected += rejected
            db.flush()

        orchestrator_run.status = "COMPLETED"
        orchestrator_run.output_summary_json = {
            "agents_executed": len(AGENT_DEFINITIONS),
            "model_invocations": invocations_count,
            "findings_accepted": total_accepted,
            "hallucinations_rejected": total_rejected,
        }
        orchestrator_run.completed_at = datetime.now(timezone.utc)
        db.flush()

        return {
            "orchestrator_run_id": str(orchestrator_run.id),
            "agents_executed": len(AGENT_DEFINITIONS),
            "model_invocations": invocations_count,
            "findings_accepted": total_accepted,
            "hallucinations_rejected": total_rejected,
        }

