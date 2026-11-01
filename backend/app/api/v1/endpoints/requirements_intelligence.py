"""Wave 3 API Endpoints: Business Rules, Requirements Intelligence, Traceability, Conflict/Gap Detection, Impact Analysis & Human Review."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context
from app.api.v1.endpoints.technical_intelligence import _verify_snapshot_project_access
from app.core.security import TenantContext
from app.db.session import activate_tenant_rls
from app.models.code_intelligence import AnalysisRun
from app.services.requirements_intelligence_service import RequirementsIntelligenceService

router = APIRouter(tags=["requirements-intelligence"])


class BusinessRuleReviewRequest(BaseModel):
    new_status: str = Field(
        ...,
        description="APPROVED | REJECTED | MODIFIED_BY_HUMAN | PENDING_REVIEW",
    )
    review_comment: str | None = None
    updated_title: str | None = None
    updated_condition_expression: str | None = None
    updated_action_consequence: str | None = None


class RequirementReviewRequest(BaseModel):
    new_status: str = Field(
        ...,
        description="APPROVED | REJECTED | MODIFIED_BY_HUMAN | PENDING_REVIEW",
    )
    review_comment: str | None = None
    updated_title: str | None = None
    updated_specification_statement: str | None = None
    updated_priority: str | None = Field(default=None, description="MUST | SHOULD | COULD")


class ConflictResolveRequest(BaseModel):
    new_status: str = Field(
        ...,
        description="RESOLVED_KEEP_PRIMARY | RESOLVED_KEEP_CONFLICTING | RESOLVED_MERGED | DISMISSED | OPEN",
    )
    resolution_notes: str | None = None


@router.post("/snapshots/{snapshot_id}/requirements-intelligence/analyze")
def trigger_requirements_intelligence_analysis(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Execute or re-execute the Wave 3 Business Rules & Requirements Intelligence pipeline for a snapshot."""
    db, ctx = ctx_pair
    snap, _ = _verify_snapshot_project_access(
        db,
        ctx=ctx,
        snapshot_id=snapshot_id,
        required_permission="analysis:run",
    )

    latest_run = (
        db.execute(
            select(AnalysisRun)
            .where(
                AnalysisRun.tenant_id == ctx.tenant_id,
                AnalysisRun.snapshot_id == snapshot_id,
            )
            .order_by(AnalysisRun.started_at.desc().nullslast())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if latest_run is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No analysis run found for snapshot; run ingestion or Wave 2 analysis first.",
        )

    svc = RequirementsIntelligenceService()
    summary = svc.execute_wave3_pipeline(
        db,
        tenant_id=ctx.tenant_id,
        repository_id=snap.repository_id,
        snapshot_id=snap.id,
        analysis_run_id=latest_run.id,
    )
    db.commit()
    activate_tenant_rls(db, ctx.tenant_id)
    out = asdict(summary)
    out["snapshot_id"] = str(out["snapshot_id"])
    out["analysis_run_id"] = str(out["analysis_run_id"])
    return out


@router.get("/snapshots/{snapshot_id}/business-rules")
def get_snapshot_business_rules_endpoint(
    snapshot_id: uuid.UUID,
    category: str | None = Query(default=None),
    domain_code: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return discovered business domains, processes, and source-anchored business rules for a snapshot."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = RequirementsIntelligenceService()
    return svc.get_snapshot_business_rules(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
        category=category,
        domain_code=domain_code,
        review_status=review_status,
    )


@router.post("/business-rules/{rule_id}/review")
def review_business_rule_endpoint(
    rule_id: uuid.UUID,
    payload: BusinessRuleReviewRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Approve, reject, edit, or request review on a BusinessRule and record an immutable `ReviewHistory` entry."""
    db, ctx = ctx_pair
    if not (
        ctx.has_permission("finding:review")
        or ctx.has_permission("project:write")
        or ctx.org_role_code in ("ORG_OWNER", "ARCHITECT", "REVIEWER")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'finding:review' required to review business rules.",
        )
    svc = RequirementsIntelligenceService()
    try:
        res = svc.review_business_rule(
            db,
            tenant_id=ctx.tenant_id,
            rule_id=rule_id,
            reviewer_user_id=ctx.user_id,
            new_status=payload.new_status,
            review_comment=payload.review_comment,
            updated_title=payload.updated_title,
            updated_condition_expression=payload.updated_condition_expression,
            updated_action_consequence=payload.updated_action_consequence,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/snapshots/{snapshot_id}/requirements")
def get_snapshot_requirements_endpoint(
    snapshot_id: uuid.UUID,
    req_type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return functional and non-functional requirements with Given/When/Then acceptance criteria and evidence."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = RequirementsIntelligenceService()
    return svc.get_snapshot_requirements(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
        req_type=req_type,
        priority=priority,
        review_status=review_status,
    )


@router.post("/requirements/{requirement_id}/review")
def review_requirement_endpoint(
    requirement_id: uuid.UUID,
    payload: RequirementReviewRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Approve, reject, edit, or request review on a Requirement and record an immutable `ReviewHistory` entry."""
    db, ctx = ctx_pair
    if not (
        ctx.has_permission("finding:review")
        or ctx.has_permission("project:write")
        or ctx.org_role_code in ("ORG_OWNER", "ARCHITECT", "REVIEWER")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'finding:review' required to review requirements.",
        )
    svc = RequirementsIntelligenceService()
    try:
        res = svc.review_requirement(
            db,
            tenant_id=ctx.tenant_id,
            requirement_id=requirement_id,
            reviewer_user_id=ctx.user_id,
            new_status=payload.new_status,
            review_comment=payload.review_comment,
            updated_title=payload.updated_title,
            updated_specification_statement=payload.updated_specification_statement,
            updated_priority=payload.updated_priority,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/snapshots/{snapshot_id}/traceability")
def get_snapshot_traceability_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return bidirectional (forward and backward) Requirements Traceability Matrix and weak/missing evidence diagnostics."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = RequirementsIntelligenceService()
    return svc.get_traceability_matrix(
        db, tenant_id=ctx.tenant_id, snapshot_id=snapshot_id
    )


@router.get("/snapshots/{snapshot_id}/conflicts-and-gaps")
def get_snapshot_conflicts_and_gaps_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return conflicting business rules, duplicate/overlapping requirements, and undocumented behavior gaps."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = RequirementsIntelligenceService()
    return svc.get_conflicts_and_gaps(
        db, tenant_id=ctx.tenant_id, snapshot_id=snapshot_id
    )


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict_endpoint(
    conflict_id: uuid.UUID,
    payload: ConflictResolveRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Resolve or dismiss a `KnowledgeConflict` and record an immutable `ReviewHistory` audit entry."""
    db, ctx = ctx_pair
    if not (
        ctx.has_permission("finding:review")
        or ctx.has_permission("project:write")
        or ctx.org_role_code in ("ORG_OWNER", "ARCHITECT", "REVIEWER")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'finding:review' required to resolve conflicts.",
        )
    svc = RequirementsIntelligenceService()
    try:
        res = svc.resolve_conflict(
            db,
            tenant_id=ctx.tenant_id,
            conflict_id=conflict_id,
            resolver_user_id=ctx.user_id,
            new_status=payload.new_status,
            resolution_notes=payload.resolution_notes,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/snapshots/{snapshot_id}/impact-analysis")
def get_snapshot_impact_analysis_endpoint(
    snapshot_id: uuid.UUID,
    target_id: uuid.UUID = Query(..., description="UUID of Requirement, BusinessRule, or KnowledgeEntity"),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Trace multi-hop dependencies and return affected APIs, database tables, code modules, and infrastructure."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = RequirementsIntelligenceService()
    return svc.analyze_impact(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
        target_id=target_id,
    )

