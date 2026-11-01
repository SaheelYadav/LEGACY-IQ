"""Wave 2 API Endpoints: Database, API, Infrastructure, Documentation, Unified Knowledge Graph, Provenance & AI Agent Orchestration."""

from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context
from app.core.security import (
    SecurityViolationError,
    TenantContext,
    verify_project_access,
)
from app.db.session import activate_tenant_rls
from app.models.agent_orchestration import (
    AgentExecutionEvent,
    AgentRun,
    AgentTaskDependency,
    ModelInvocation,
)
from app.models.code_intelligence import AnalysisRun
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
from app.models.projects import Application
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
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.technical_intelligence_service import TechnicalIntelligenceService

router = APIRouter()


class FindingReviewRequest(BaseModel):
    new_status: str = Field(
        ...,
        description="APPROVED | REJECTED | MODIFIED_BY_HUMAN | PENDING_REVIEW",
    )
    review_comment: str | None = None
    updated_title: str | None = None
    updated_statement_markdown: str | None = None


def _verify_snapshot_project_access(
    db: Session,
    *,
    ctx: TenantContext,
    snapshot_id: uuid.UUID,
    required_permission: str = "project:read",
) -> tuple[RepositorySnapshot, uuid.UUID]:
    """Resolve snapshot -> repository -> application -> project and enforce project-level RBAC."""
    row = db.execute(
        select(RepositorySnapshot, Application.project_id)
        .join(
            Repository,
            (Repository.tenant_id == RepositorySnapshot.tenant_id)
            & (Repository.id == RepositorySnapshot.repository_id),
        )
        .join(
            Application,
            (Application.tenant_id == Repository.tenant_id)
            & (Application.id == Repository.application_id),
        )
        .where(
            RepositorySnapshot.tenant_id == ctx.tenant_id,
            RepositorySnapshot.id == snapshot_id,
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found.",
        )
    snap, proj_id = row
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=proj_id,
            required_permission=required_permission,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return snap, proj_id


@router.post("/snapshots/{snapshot_id}/analyze-wave2")
def analyze_snapshot_wave2(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Run or refresh the Wave 2 Technical Intelligence, Unified Knowledge Graph & Agent Orchestration pipeline."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(
        db,
        ctx=ctx,
        snapshot_id=snapshot_id,
        required_permission="analysis:run",
    )
    service = TechnicalIntelligenceService()
    try:
        summary = service.run_wave2_pipeline(
            db,
            tenant_id=ctx.tenant_id,
            snapshot_id=snapshot_id,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {
        "snapshot_id": str(summary.snapshot_id),
        "analysis_run_id": str(summary.analysis_run_id),
        "db_schemas_count": summary.db_schemas_count,
        "db_tables_count": summary.db_tables_count,
        "db_columns_count": summary.db_columns_count,
        "db_foreign_keys_count": summary.db_foreign_keys_count,
        "api_services_count": summary.api_services_count,
        "api_endpoints_count": summary.api_endpoints_count,
        "infra_resources_count": summary.infra_resources_count,
        "doc_sections_count": summary.doc_sections_count,
        "knowledge_entities_count": summary.knowledge_entities_count,
        "knowledge_relationships_count": summary.knowledge_relationships_count,
        "evidence_anchors_count": summary.evidence_anchors_count,
        "findings_count": summary.findings_count,
        "agent_runs_count": summary.agent_runs_count,
    }


@router.get("/snapshots/{snapshot_id}/database")
def get_snapshot_database_intelligence(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return discovered SQL/ORM schemas, tables, columns, and foreign-key relationships for a snapshot."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    schemas = (
        db.execute(
            select(DbSchema).where(
                DbSchema.tenant_id == ctx.tenant_id,
                DbSchema.snapshot_id == snapshot_id,
            )
        )
        .scalars()
        .all()
    )
    schema_ids = [s.id for s in schemas]
    tables = (
        db.execute(
            select(DbTable).where(
                DbTable.tenant_id == ctx.tenant_id,
                DbTable.db_schema_id.in_(schema_ids) if schema_ids else False,
            )
        )
        .scalars()
        .all()
        if schema_ids
        else []
    )
    table_ids = [t.id for t in tables]
    columns = (
        db.execute(
            select(DbColumn)
            .where(
                DbColumn.tenant_id == ctx.tenant_id,
                DbColumn.db_table_id.in_(table_ids) if table_ids else False,
            )
            .order_by(DbColumn.ordinal_position)
        )
        .scalars()
        .all()
        if table_ids
        else []
    )
    fks = (
        db.execute(
            select(DbForeignKey).where(
                DbForeignKey.tenant_id == ctx.tenant_id,
                DbForeignKey.source_table_id.in_(table_ids) if table_ids else False,
            )
        )
        .scalars()
        .all()
        if table_ids
        else []
    )

    cols_by_table: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for col in columns:
        cols_by_table.setdefault(col.db_table_id, []).append(
            {
                "id": str(col.id),
                "column_name": col.column_name,
                "ordinal_position": col.ordinal_position,
                "data_type": col.data_type,
                "is_nullable": col.is_nullable,
                "is_primary_key": col.is_primary_key,
                "is_pii_candidate": col.is_pii_candidate,
            }
        )

    schema_by_id = {s.id: s for s in schemas}
    table_by_id = {t.id: t for t in tables}

    return {
        "snapshot_id": str(snapshot_id),
        "schemas": [
            {
                "id": str(s.id),
                "schema_name": s.schema_name,
                "db_engine": s.db_engine,
                "discovery_source": s.discovery_source,
            }
            for s in schemas
        ],
        "tables": [
            {
                "id": str(t.id),
                "db_schema_id": str(t.db_schema_id),
                "schema_name": schema_by_id[t.db_schema_id].schema_name
                if t.db_schema_id in schema_by_id
                else "public",
                "table_name": t.table_name,
                "table_kind": t.table_kind,
                "mapped_orm_symbol_id": str(t.mapped_orm_symbol_id)
                if t.mapped_orm_symbol_id
                else None,
                "comment_text": t.comment_text,
                "columns": cols_by_table.get(t.id, []),
            }
            for t in tables
        ],
        "foreign_keys": [
            {
                "id": str(fk.id),
                "source_table_id": str(fk.source_table_id),
                "source_table_name": table_by_id[fk.source_table_id].table_name
                if fk.source_table_id in table_by_id
                else "",
                "target_table_id": str(fk.target_table_id),
                "target_table_name": table_by_id[fk.target_table_id].table_name
                if fk.target_table_id in table_by_id
                else "",
                "constraint_name": fk.constraint_name,
                "source_column_names": fk.source_column_names,
                "target_column_names": fk.target_column_names,
                "relation_origin": fk.relation_origin,
            }
            for fk in fks
        ],
    }


@router.get("/snapshots/{snapshot_id}/apis")
def get_snapshot_api_intelligence(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return discovered REST, OpenAPI/Swagger, and GraphQL services and endpoints for a snapshot."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    services = (
        db.execute(
            select(ApiService).where(
                ApiService.tenant_id == ctx.tenant_id,
                ApiService.snapshot_id == snapshot_id,
            )
        )
        .scalars()
        .all()
    )
    svc_ids = [s.id for s in services]
    endpoints = (
        db.execute(
            select(ApiEndpoint).where(
                ApiEndpoint.tenant_id == ctx.tenant_id,
                ApiEndpoint.api_service_id.in_(svc_ids) if svc_ids else False,
            )
        )
        .scalars()
        .all()
        if svc_ids
        else []
    )
    svc_by_id = {s.id: s for s in services}

    return {
        "snapshot_id": str(snapshot_id),
        "services": [
            {
                "id": str(s.id),
                "service_name": s.service_name,
                "protocol": s.protocol,
                "base_path": s.base_path,
            }
            for s in services
        ],
        "endpoints": [
            {
                "id": str(ep.id),
                "api_service_id": str(ep.api_service_id),
                "service_name": svc_by_id[ep.api_service_id].service_name
                if ep.api_service_id in svc_by_id
                else "",
                "protocol": svc_by_id[ep.api_service_id].protocol
                if ep.api_service_id in svc_by_id
                else "REST",
                "handler_symbol_id": str(ep.handler_symbol_id)
                if ep.handler_symbol_id
                else None,
                "http_method": ep.http_method,
                "route_pattern": ep.route_pattern,
                "auth_required_inferred": ep.auth_required_inferred,
                "request_schema_json": ep.request_schema_json,
                "response_schema_json": ep.response_schema_json,
            }
            for ep in endpoints
        ],
    }


@router.get("/snapshots/{snapshot_id}/infrastructure")
def get_snapshot_infrastructure_intelligence(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return discovered Dockerfile, Docker Compose, Kubernetes, Terraform, and CloudFormation resources."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    resources = (
        db.execute(
            select(InfraResource).where(
                InfraResource.tenant_id == ctx.tenant_id,
                InfraResource.snapshot_id == snapshot_id,
            )
        )
        .scalars()
        .all()
    )
    return {
        "snapshot_id": str(snapshot_id),
        "resources": [
            {
                "id": str(r.id),
                "iac_tool": r.iac_tool,
                "resource_type": r.resource_type,
                "resource_name": r.resource_name,
                "source_artifact_version_id": str(r.source_artifact_version_id),
                "configuration_attributes": r.configuration_attributes,
            }
            for r in resources
        ],
    }


@router.get("/snapshots/{snapshot_id}/documentation")
def get_snapshot_documentation_intelligence(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return hierarchical documentation sections extracted from Markdown, HTML, DOCX, XLSX, and PDF files."""
    db, ctx = ctx_pair
    snap, _ = _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)

    rows = db.execute(
        select(DocSection, Artifact.canonical_path)
        .join(
            ArtifactVersion,
            (ArtifactVersion.tenant_id == DocSection.tenant_id)
            & (ArtifactVersion.id == DocSection.artifact_version_id),
        )
        .join(
            Artifact,
            (Artifact.tenant_id == ArtifactVersion.tenant_id)
            & (Artifact.id == ArtifactVersion.artifact_id),
        )
        .where(
            DocSection.tenant_id == ctx.tenant_id,
            Artifact.repository_id == snap.repository_id,
        )
        .order_by(Artifact.canonical_path, DocSection.start_line)
    ).all()

    return {
        "snapshot_id": str(snapshot_id),
        "sections": [
            {
                "id": str(sec.id),
                "artifact_version_id": str(sec.artifact_version_id),
                "canonical_path": path,
                "parent_section_id": str(sec.parent_section_id)
                if sec.parent_section_id
                else None,
                "heading_path": sec.heading_path,
                "heading_level": sec.heading_level,
                "start_line": sec.start_line,
                "end_line": sec.end_line,
                "content_markdown": sec.content_markdown,
            }
            for sec, path in rows
        ],
    }


@router.get("/snapshots/{snapshot_id}/graph")
def get_snapshot_knowledge_graph(
    snapshot_id: uuid.UUID,
    entity_type: str | None = Query(default=None),
    relationship_type: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return Unified Knowledge Graph entities, relationships, and provenance counts for a snapshot."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    ent_stmt = select(KnowledgeEntity).where(
        KnowledgeEntity.tenant_id == ctx.tenant_id,
        KnowledgeEntity.snapshot_id == snapshot_id,
    )
    if entity_type:
        ent_stmt = ent_stmt.where(KnowledgeEntity.entity_type == entity_type.upper())
    entities = db.execute(ent_stmt.limit(500)).scalars().all()

    rel_stmt = select(KnowledgeRelationship).where(
        KnowledgeRelationship.tenant_id == ctx.tenant_id,
        KnowledgeRelationship.snapshot_id == snapshot_id,
    )
    if relationship_type:
        rel_stmt = rel_stmt.where(
            KnowledgeRelationship.relationship_type == relationship_type.upper()
        )
    relationships = db.execute(rel_stmt.limit(1000)).scalars().all()

    type_counts: dict[str, int] = {}
    for e in entities:
        type_counts[e.entity_type] = type_counts.get(e.entity_type, 0) + 1

    rel_counts: dict[str, int] = {}
    for r in relationships:
        rel_counts[r.relationship_type] = rel_counts.get(r.relationship_type, 0) + 1

    return {
        "snapshot_id": str(snapshot_id),
        "entity_counts_by_type": type_counts,
        "relationship_counts_by_type": rel_counts,
        "entities": [
            {
                "id": str(e.id),
                "entity_type": e.entity_type,
                "canonical_key": e.canonical_key,
                "title": e.title,
                "summary_description": e.summary_description,
                "origin_type": e.origin_type,
                "confidence_score": float(e.confidence_score),
                "review_status": e.review_status,
                "attributes_json": e.attributes_json,
            }
            for e in entities
        ],
        "relationships": [
            {
                "id": str(r.id),
                "source_entity_id": str(r.source_entity_id),
                "target_entity_id": str(r.target_entity_id),
                "relationship_type": r.relationship_type,
                "origin_type": r.origin_type,
                "confidence_score": float(r.confidence_score),
                "edge_weight": float(r.edge_weight),
                "review_status": r.review_status,
                "edge_metadata": r.edge_metadata,
            }
            for r in relationships
        ],
    }


@router.get("/snapshots/{snapshot_id}/graph/traverse")
def traverse_snapshot_knowledge_graph(
    snapshot_id: uuid.UUID,
    root_entity_id: uuid.UUID = Query(...),
    max_hops: int = Query(default=3, ge=1, le=6),
    direction: str = Query(default="OUTGOING"),
    relationship_type: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Execute cycle-safe recursive CTE traversal from `root_entity_id`."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    graph_service = KnowledgeGraphService()
    rel_types = [relationship_type] if relationship_type else None
    return graph_service.traverse_subgraph(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
        root_entity_id=root_entity_id,
        max_hops=max_hops,
        direction=direction,
        relationship_types=rel_types,
    )


@router.get("/snapshots/{snapshot_id}/findings")
def get_snapshot_findings(
    snapshot_id: uuid.UUID,
    category: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return findings with their linked cryptographic `evidence_anchors` and review history."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    stmt = select(Finding).where(
        Finding.tenant_id == ctx.tenant_id,
        Finding.snapshot_id == snapshot_id,
    )
    if category:
        stmt = stmt.where(Finding.finding_category == category.upper())
    if review_status:
        stmt = stmt.where(Finding.review_status == review_status.upper())

    findings = db.execute(stmt.order_by(Finding.created_at.desc())).scalars().all()
    finding_ids = [f.id for f in findings]

    evidence_by_finding: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if finding_ids:
        link_rows = db.execute(
            select(FindingEvidenceLink, EvidenceAnchor)
            .join(
                EvidenceAnchor,
                (EvidenceAnchor.tenant_id == FindingEvidenceLink.tenant_id)
                & (EvidenceAnchor.id == FindingEvidenceLink.evidence_anchor_id),
            )
            .where(
                FindingEvidenceLink.tenant_id == ctx.tenant_id,
                FindingEvidenceLink.finding_id.in_(finding_ids),
            )
        ).all()
        for link, anchor in link_rows:
            if link.finding_id is None:
                continue
            evidence_by_finding.setdefault(link.finding_id, []).append(
                {
                    "link_id": str(link.id),
                    "evidence_anchor_id": str(anchor.id),
                    "artifact_version_id": str(anchor.artifact_version_id),
                    "locator_type": anchor.locator_type,
                    "start_line": anchor.start_line,
                    "end_line": anchor.end_line,
                    "snippet_sha256": anchor.snippet_sha256,
                    "excerpt_text": anchor.excerpt_text,
                    "evidence_role": link.evidence_role,
                    "relevance_weight": float(link.relevance_weight),
                    "rationale_note": link.rationale_note,
                }
            )

    conflicts = (
        db.execute(
            select(KnowledgeConflict).where(
                KnowledgeConflict.tenant_id == ctx.tenant_id,
                KnowledgeConflict.snapshot_id == snapshot_id,
            )
        )
        .scalars()
        .all()
    )

    return {
        "snapshot_id": str(snapshot_id),
        "findings": [
            {
                "id": str(f.id),
                "finding_category": f.finding_category,
                "severity": f.severity,
                "title": f.title,
                "statement_markdown": f.statement_markdown,
                "origin_type": f.origin_type,
                "confidence_score": float(f.confidence_score),
                "review_status": f.review_status,
                "subject_entity_id": str(f.subject_entity_id) if f.subject_entity_id else None,
                "producing_agent_run_id": str(f.producing_agent_run_id)
                if f.producing_agent_run_id
                else None,
                "version_no": f.version_no,
                "evidence": evidence_by_finding.get(f.id, []),
            }
            for f in findings
        ],
        "conflicts": [
            {
                "id": str(c.id),
                "conflict_type": c.conflict_type,
                "status": c.status,
                "primary_entity_or_finding_id": str(c.primary_entity_or_finding_id),
                "conflicting_entity_or_finding_id": str(c.conflicting_entity_or_finding_id),
                "resolution_notes": c.resolution_notes,
            }
            for c in conflicts
        ],
    }


@router.post("/findings/{finding_id}/review")
def review_finding_endpoint(
    finding_id: uuid.UUID,
    payload: FindingReviewRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Transition a finding's review state and record an immutable `ReviewHistory` entry."""
    db, ctx = ctx_pair
    if not (
        ctx.has_permission("finding:review")
        or ctx.has_permission("project:write")
        or ctx.org_role_code in ("ORG_OWNER", "ARCHITECT", "REVIEWER")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'finding:review' required to review findings.",
        )
    graph_service = KnowledgeGraphService()
    try:
        updated = graph_service.review_finding(
            db,
            tenant_id=ctx.tenant_id,
            finding_id=finding_id,
            reviewer_user_id=ctx.user_id,
            new_status=payload.new_status,
            review_comment=payload.review_comment,
            updated_title=payload.updated_title,
            updated_statement_markdown=payload.updated_statement_markdown,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    history_rows = (
        db.execute(
            select(ReviewHistory)
            .where(
                ReviewHistory.tenant_id == ctx.tenant_id,
                ReviewHistory.target_object_type == "FINDING",
                ReviewHistory.target_object_id == finding_id,
            )
            .order_by(ReviewHistory.reviewed_at.desc())
        )
        .scalars()
        .all()
    )

    return {
        "id": str(updated.id),
        "title": updated.title,
        "statement_markdown": updated.statement_markdown,
        "review_status": updated.review_status,
        "version_no": updated.version_no,
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


@router.get("/snapshots/{snapshot_id}/agents")
def get_snapshot_agent_orchestration(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return AI Agent Orchestration runs, task dependencies, model invocations, and execution telemetry."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    runs = (
        db.execute(
            select(AnalysisRun).where(
                AnalysisRun.tenant_id == ctx.tenant_id,
                AnalysisRun.snapshot_id == snapshot_id,
            )
        )
        .scalars()
        .all()
    )
    run_ids = [r.id for r in runs]
    if not run_ids:
        return {
            "snapshot_id": str(snapshot_id),
            "agent_runs": [],
            "task_dependencies": [],
            "model_invocations": [],
            "execution_events": [],
        }

    agent_runs = (
        db.execute(
            select(AgentRun)
            .where(
                AgentRun.tenant_id == ctx.tenant_id,
                AgentRun.analysis_run_id.in_(run_ids),
            )
            .order_by(AgentRun.started_at.asc().nullsfirst())
        )
        .scalars()
        .all()
    )
    agent_run_ids = [ar.id for ar in agent_runs]

    deps = (
        db.execute(
            select(AgentTaskDependency).where(
                AgentTaskDependency.tenant_id == ctx.tenant_id,
                AgentTaskDependency.analysis_run_id.in_(run_ids),
            )
        )
        .scalars()
        .all()
    )

    invocations = (
        db.execute(
            select(ModelInvocation)
            .where(
                ModelInvocation.tenant_id == ctx.tenant_id,
                ModelInvocation.agent_run_id.in_(agent_run_ids) if agent_run_ids else False,
            )
            .order_by(ModelInvocation.invoked_at.asc())
        )
        .scalars()
        .all()
        if agent_run_ids
        else []
    )

    events = (
        db.execute(
            select(AgentExecutionEvent)
            .where(
                AgentExecutionEvent.tenant_id == ctx.tenant_id,
                AgentExecutionEvent.agent_run_id.in_(agent_run_ids) if agent_run_ids else False,
            )
            .order_by(AgentExecutionEvent.occurred_at.asc(), AgentExecutionEvent.sequence_no.asc())
        )
        .scalars()
        .all()
        if agent_run_ids
        else []
    )

    return {
        "snapshot_id": str(snapshot_id),
        "agent_runs": [
            {
                "id": str(ar.id),
                "analysis_run_id": str(ar.analysis_run_id),
                "parent_agent_run_id": str(ar.parent_agent_run_id)
                if ar.parent_agent_run_id
                else None,
                "agent_name": ar.agent_name,
                "agent_version": ar.agent_version,
                "status": ar.status,
                "attempt_count": ar.attempt_count,
                "input_context_refs": ar.input_context_refs,
                "output_summary_json": ar.output_summary_json,
                "started_at": ar.started_at.isoformat() if ar.started_at else None,
                "completed_at": ar.completed_at.isoformat() if ar.completed_at else None,
            }
            for ar in agent_runs
        ],
        "task_dependencies": [
            {
                "id": str(d.id),
                "upstream_agent_run_id": str(d.upstream_agent_run_id),
                "downstream_agent_run_id": str(d.downstream_agent_run_id),
                "dependency_kind": d.dependency_kind,
            }
            for d in deps
        ],
        "model_invocations": [
            {
                "id": str(inv.id),
                "agent_run_id": str(inv.agent_run_id),
                "provider_name": inv.provider_name,
                "model_identifier": inv.model_identifier,
                "is_fallback_invocation": inv.is_fallback_invocation,
                "prompt_tokens": inv.prompt_tokens,
                "completion_tokens": inv.completion_tokens,
                "total_tokens": inv.total_tokens,
                "latency_ms": inv.latency_ms,
                "status": inv.status,
            }
            for inv in invocations
        ],
        "execution_events": [
            {
                "id": str(ev.id),
                "agent_run_id": str(ev.agent_run_id),
                "sequence_no": ev.sequence_no,
                "event_type": ev.event_type,
                "event_payload": ev.event_payload,
            }
            for ev in events
        ],
    }

