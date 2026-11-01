"""Wave 4 API Endpoints: Test Intelligence, Coverage & Gaps, Risk Register, Technical Debt, Modernization Assessment, Phased Roadmap & Human Review."""

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
from app.models.ingestion import Repository
from app.services.testing_modernization_service import TestingModernizationService

router = APIRouter(tags=["testing-modernization"])


class ModernizationRecommendationReviewRequest(BaseModel):
    new_status: str = Field(
        ...,
        description="APPROVED | REJECTED | MODIFIED_BY_HUMAN | PENDING_REVIEW",
    )
    review_comment: str | None = None
    updated_title: str | None = None
    updated_target_state_architecture: str | None = None
    updated_effort_tshirt: str | None = Field(
        default=None, description="XS | S | M | L | XL"
    )


class TestCaseReviewRequest(BaseModel):
    __test__ = False
    new_status: str = Field(
        ...,
        description="APPROVED | REJECTED | MODIFIED_BY_HUMAN | PENDING_REVIEW",
    )
    review_comment: str | None = None
    updated_generated_code_blueprint: str | None = None


@router.post("/snapshots/{snapshot_id}/testing-modernization/analyze")
def trigger_wave4_testing_modernization_analysis(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Execute or re-execute the Wave 4 Testing, Risk, Technical Debt & Modernization Intelligence pipeline."""
    db, ctx = ctx_pair
    snap, _ = _verify_snapshot_project_access(
        db,
        ctx=ctx,
        snapshot_id=snapshot_id,
        required_permission="analysis:run",
    )

    repo = db.execute(
        select(Repository).where(
            Repository.tenant_id == ctx.tenant_id,
            Repository.id == snap.repository_id,
        )
    ).scalar_one()

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
            detail="No analysis run found for snapshot; run ingestion or Wave 2/3 analysis first.",
        )

    svc = TestingModernizationService()
    summary = svc.execute_wave4_pipeline(
        db,
        tenant_id=ctx.tenant_id,
        application_id=repo.application_id,
        snapshot=snap,
        analysis_run=latest_run,
    )
    db.commit()
    activate_tenant_rls(db, ctx.tenant_id)
    out = asdict(summary)
    out["snapshot_id"] = str(out["snapshot_id"])
    out["analysis_run_id"] = str(out["analysis_run_id"])
    return out


@router.get("/snapshots/{snapshot_id}/test-intelligence")
def get_snapshot_test_intelligence_endpoint(
    snapshot_id: uuid.UUID,
    suite_origin: str | None = Query(default=None),
    test_kind: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return discovered repository test suites/cases, generated test blueprints, and coverage mappings."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = TestingModernizationService()
    return svc.get_test_intelligence(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
        suite_origin=suite_origin,
        test_kind=test_kind,
    )


@router.get("/snapshots/{snapshot_id}/coverage-and-gaps")
def get_snapshot_coverage_and_gaps_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return discovered vs. inferred test coverage metrics, untested requirements, and untested critical components."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = TestingModernizationService()
    return svc.get_coverage_and_gaps(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
    )


@router.get("/snapshots/{snapshot_id}/risk-register")
def get_snapshot_risk_register_endpoint(
    snapshot_id: uuid.UUID,
    severity: str | None = Query(default=None),
    risk_category: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return security, dependency, architectural, SPOF, data integrity, performance, and operational risk findings."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = TestingModernizationService()
    return svc.get_risk_register(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
        severity=severity,
        risk_category=risk_category,
    )


@router.get("/snapshots/{snapshot_id}/technical-debt")
def get_snapshot_technical_debt_endpoint(
    snapshot_id: uuid.UUID,
    debt_category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return quantified technical debt items and measured vs. heuristic-estimated metrics."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = TestingModernizationService()
    return svc.get_technical_debt(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
        debt_category=debt_category,
        severity=severity,
    )


@router.get("/snapshots/{snapshot_id}/modernization-assessment")
def get_snapshot_modernization_assessment_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return multi-dimensional modernization posture assessment grounded in snapshot evidence."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = TestingModernizationService()
    return svc.get_modernization_assessment(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
    )


@router.get("/snapshots/{snapshot_id}/modernization-roadmap")
def get_snapshot_modernization_roadmap_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return prioritized modernization recommendations and the 4-phase modernization roadmap."""
    db, ctx = ctx_pair
    _verify_snapshot_project_access(db, ctx=ctx, snapshot_id=snapshot_id)
    svc = TestingModernizationService()
    return svc.get_recommendations_and_roadmap(
        db,
        tenant_id=ctx.tenant_id,
        snapshot_id=snapshot_id,
    )


@router.post("/modernization-recommendations/{recommendation_id}/review")
def review_modernization_recommendation_endpoint(
    recommendation_id: uuid.UUID,
    payload: ModernizationRecommendationReviewRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Human review action (`APPROVED`, `REJECTED`, `MODIFIED_BY_HUMAN`) for a ModernizationRecommendation."""
    db, ctx = ctx_pair
    if not (
        ctx.has_permission("finding:review")
        or ctx.has_permission("project:write")
        or ctx.org_role_code in ("ORG_OWNER", "ARCHITECT", "REVIEWER")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'finding:review' required to review modernization recommendations.",
        )
    svc = TestingModernizationService()
    try:
        res = svc.review_modernization_recommendation(
            db,
            tenant_id=ctx.tenant_id,
            recommendation_id=recommendation_id,
            reviewer_user_id=ctx.user_id,
            new_status=payload.new_status,
            review_comment=payload.review_comment,
            updated_title=payload.updated_title,
            updated_target_state_architecture=payload.updated_target_state_architecture,
            updated_effort_tshirt=payload.updated_effort_tshirt,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/test-cases/{test_case_id}/review")
def review_test_case_endpoint(
    test_case_id: uuid.UUID,
    payload: TestCaseReviewRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Human review action (`APPROVED`, `REJECTED`, `MODIFIED_BY_HUMAN`) for a discovered or generated TestCase."""
    db, ctx = ctx_pair
    if not (
        ctx.has_permission("finding:review")
        or ctx.has_permission("project:write")
        or ctx.org_role_code in ("ORG_OWNER", "ARCHITECT", "REVIEWER")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'finding:review' required to review test cases.",
        )
    svc = TestingModernizationService()
    try:
        res = svc.review_test_case(
            db,
            tenant_id=ctx.tenant_id,
            test_case_id=test_case_id,
            reviewer_user_id=ctx.user_id,
            new_status=payload.new_status,
            review_comment=payload.review_comment,
            updated_generated_code_blueprint=payload.updated_generated_code_blueprint,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

