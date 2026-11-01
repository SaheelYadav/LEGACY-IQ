"""Wave 5 API Endpoints: Unified Application Intelligence Dashboard, Semantic Q&A Assistant, 11-Type Report Generation Engine, Immutable Report Versioning & Multi-Format Export Governance."""

from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context
from app.core.security import SecurityViolationError, TenantContext
from app.db.session import activate_tenant_rls
from app.services.reporting_qa_export_service import ReportingQaExportService

router = APIRouter(tags=["reporting-governance"])


class CreateConversationRequest(BaseModel):
    snapshot_id: uuid.UUID
    title: str | None = None


class AskQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class GenerateReportRequest(BaseModel):
    report_type: str = Field(
        default="COMPLETE_INTELLIGENCE",
        description=(
            "APPLICATION_DISCOVERY | TECHNICAL_ARCHITECTURE | BUSINESS_RULES_PROCESSES | "
            "REQUIREMENTS_SPECIFICATION | API_DATABASE_INTELLIGENCE | SECURITY_RISK_ASSESSMENT | "
            "TESTING_COVERAGE_ASSESSMENT | TECHNICAL_DEBT_ASSESSMENT | MODERNIZATION_ASSESSMENT | "
            "EXECUTIVE_SUMMARY | COMPLETE_INTELLIGENCE"
        ),
    )
    initial_status: str = Field(
        default="GENERATED", description="DRAFT | GENERATED"
    )
    custom_title: str | None = None


class ReportLifecycleTransitionRequest(BaseModel):
    target_status: str = Field(
        ...,
        description="DRAFT | GENERATED | SUBMITTED_FOR_REVIEW | APPROVED | REJECTED | ARCHIVED",
    )
    review_comment: str | None = None
    updated_title: str | None = None
    updated_executive_summary_markdown: str | None = None


class ReportExportRequest(BaseModel):
    export_format: str = Field(
        default="PDF", description="PDF | DOCX | XLSX | JSON"
    )
    version_no: int | None = None
    custom_branding: dict[str, Any] | None = None


@router.get("/snapshots/{snapshot_id}/intelligence-dashboard")
def get_application_intelligence_dashboard_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return the unified Waves 1–4 Application Intelligence Dashboard with measured vs. heuristic-estimated vs. inferred attribution."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        return svc.get_application_intelligence_dashboard(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            snapshot_id=snapshot_id,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/snapshots/{snapshot_id}/executive-insights")
def get_executive_insights_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return management-level Executive Reporting insights (health score, risk distribution, testing maturity, tech debt, modernization readiness, effort)."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        return svc.get_executive_insights(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            snapshot_id=snapshot_id,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/qa/conversations")
def create_qa_conversation_endpoint(
    payload: CreateConversationRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Create a new tenant- and project-isolated Semantic Q&A conversation session."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        res = svc.create_conversation(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            snapshot_id=payload.snapshot_id,
            title=payload.title,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/qa/conversations")
def list_qa_conversations_endpoint(
    project_id: uuid.UUID | None = Query(default=None),
    snapshot_id: uuid.UUID | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """List Semantic Q&A conversations accessible to the caller within the tenant/project."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        convs = svc.list_conversations(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            project_id=project_id,
            snapshot_id=snapshot_id,
        )
        return {"conversations": convs}
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/qa/conversations/{conversation_id}")
def get_qa_conversation_endpoint(
    conversation_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Retrieve a Semantic Q&A conversation and its full message history."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        return svc.get_conversation(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            conversation_id=conversation_id,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/qa/conversations/{conversation_id}/ask")
def ask_qa_conversation_question_endpoint(
    conversation_id: uuid.UUID,
    payload: AskQuestionRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Ask a natural-language question in an existing Semantic Q&A conversation."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        res = svc.ask_question(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            question=payload.question,
            conversation_id=conversation_id,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/snapshots/{snapshot_id}/qa/ask")
def ask_snapshot_qa_question_endpoint(
    snapshot_id: uuid.UUID,
    payload: AskQuestionRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Ask a natural-language question directly against a snapshot (creates a conversation automatically)."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        res = svc.ask_question(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            question=payload.question,
            snapshot_id=snapshot_id,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/snapshots/{snapshot_id}/reports/generate")
def generate_intelligence_report_endpoint(
    snapshot_id: uuid.UUID,
    payload: GenerateReportRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Generate or regenerate one of the 11 structured intelligence reports (preserving immutable approved versions)."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        res = svc.generate_report(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            snapshot_id=snapshot_id,
            report_type=payload.report_type,
            initial_status=payload.initial_status,
            custom_title=payload.custom_title,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/snapshots/{snapshot_id}/reports")
def list_snapshot_reports_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """List all intelligence reports generated for a snapshot along with the 11 available report types."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        return svc.list_reports(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            snapshot_id=snapshot_id,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/reports/{report_id}")
def get_intelligence_report_endpoint(
    report_id: uuid.UUID,
    version_no: int | None = Query(default=None),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Retrieve a structured intelligence report (current or historical version) and its full version list."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        return svc.get_report(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            report_id=report_id,
            version_no=version_no,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/reports/{report_id}/versions")
def list_report_versions_endpoint(
    report_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """List all historical and current versions of an intelligence report."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        rep = svc.get_report(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            report_id=report_id,
        )
        return {
            "report_id": rep["id"],
            "report_type": rep["report_type"],
            "current_version_no": rep["current_version_no"],
            "versions": rep["versions"],
        }
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/reports/{report_id}/lifecycle")
def transition_report_lifecycle_endpoint(
    report_id: uuid.UUID,
    payload: ReportLifecycleTransitionRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Transition report lifecycle (`DRAFT`, `GENERATED`, `SUBMITTED_FOR_REVIEW`, `APPROVED`, `REJECTED`, `ARCHIVED`). Approved versions are strictly immutable."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        res = svc.transition_report_lifecycle(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            report_id=report_id,
            target_status=payload.target_status,
            review_comment=payload.review_comment,
            updated_title=payload.updated_title,
            updated_executive_summary_markdown=payload.updated_executive_summary_markdown,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post("/reports/{report_id}/exports")
def export_intelligence_report_endpoint(
    report_id: uuid.UUID,
    payload: ReportExportRequest,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Generate a controlled export (`PDF`, `DOCX`, `XLSX`, `JSON`) with tenant storage isolation and tamper-evident `AuditLog` tracking."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        res = svc.export_report(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            report_id=report_id,
            export_format=payload.export_format,
            version_no=payload.version_no,
            custom_branding=payload.custom_branding,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return res
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/snapshots/{snapshot_id}/exports")
def list_snapshot_exports_endpoint(
    snapshot_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """List controlled report exports and tamper-evident `AuditLog` entries for a snapshot."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        return svc.list_exports(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            snapshot_id=snapshot_id,
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/exports/{export_id}/download")
def download_report_export_endpoint(
    export_id: uuid.UUID,
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> Response:
    """Safely download a generated report export binary (`PDF`, `DOCX`, `XLSX`, `JSON`) and record an `EXPORT_DOWNLOADED` audit event."""
    db, ctx = ctx_pair
    svc = ReportingQaExportService()
    try:
        raw_bytes, file_name, mime_type = svc.download_export(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            export_id=export_id,
        )
        db.commit()
        activate_tenant_rls(db, ctx.tenant_id)
        return Response(
            content=raw_bytes,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "Cache-Control": "no-store",
            },
        )
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/organizations/{tenant_id}/audit-logs")
def list_organization_audit_logs_endpoint(
    tenant_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    ctx_pair: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, Any]:
    """List hash-chained tamper-evident `AuditLog` entries for a tenant."""
    db, ctx = ctx_pair
    if tenant_id != ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant audit log access is denied.",
        )
    svc = ReportingQaExportService()
    return {
        "tenant_id": str(tenant_id),
        "audit_logs": svc.list_audit_logs(
            db, tenant_id=ctx.tenant_id, limit=limit
        ),
    }

