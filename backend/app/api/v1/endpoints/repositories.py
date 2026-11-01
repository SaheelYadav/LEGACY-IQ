"""Repository, ZIP Upload, Snapshot, and Ingestion Job endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_context
from app.core.security import (
    SecurityViolationError,
    TenantContext,
    verify_project_access,
)
from app.models.ingestion import IngestionJob, Repository, RepositorySnapshot
from app.models.projects import Application
from app.schemas.platform import (
    IngestionJobResponse,
    RepositoryCreateRequest,
    RepositoryResponse,
    SnapshotResponse,
    ZipUploadResponse,
)
from app.services.ingestion_service import ArchiveValidationError, IngestionService

router = APIRouter()
ingestion_service = IngestionService()


def _ensure_project_application(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
) -> Application:
    if application_id is not None:
        app_row = db.execute(
            select(Application).where(
                Application.tenant_id == tenant_id,
                Application.id == application_id,
            )
        ).scalar_one_or_none()
        if app_row is not None:
            return app_row

    existing = db.execute(
        select(Application).where(
            Application.tenant_id == tenant_id,
            Application.project_id == project_id,
        )
    ).scalars().first()
    if existing is not None:
        return existing

    app_row = Application(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        code="default-app",
        name="Default Application",
        criticality_tier="TIER_1",
        primary_languages=["python", "java", "typescript", "javascript", "php"],
    )
    db.add(app_row)
    db.flush()
    return app_row


@router.get(
    "/repositories",
    response_model=list[RepositoryResponse],
    status_code=status.HTTP_200_OK,
    summary="List repositories in a project",
)
def list_repositories(
    project_id: uuid.UUID = Query(...),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[RepositoryResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    rows = db.execute(
        select(Repository, Application.project_id)
        .join(
            Application,
            (Application.tenant_id == Repository.tenant_id)
            & (Application.id == Repository.application_id),
        )
        .where(
            Repository.tenant_id == ctx.tenant_id,
            Application.project_id == project_id,
        )
        .order_by(Repository.created_at.desc())
    ).all()
    return [
        RepositoryResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            project_id=proj_id,
            application_id=r.application_id,
            name=r.name,
            default_branch=r.default_branch or "main",
            clone_url=r.remote_url,
            is_active=(r.status == "REGISTERED"),
            created_at=r.created_at,
        )
        for r, proj_id in rows
    ]


@router.post(
    "/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a repository in a project",
)
def create_repository(
    payload: RepositoryCreateRequest,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> RepositoryResponse:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=payload.project_id,
            required_permission="repo:ingest",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    app_row = _ensure_project_application(
        db,
        tenant_id=ctx.tenant_id,
        project_id=payload.project_id,
        application_id=payload.application_id,
    )

    repo = Repository(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        application_id=app_row.id,
        connector_id=None,
        name=payload.name,
        source_type="ZIP_ARCHIVE" if not payload.clone_url else "GIT_REMOTE",
        remote_url=payload.clone_url,
        default_branch=payload.default_branch,
        status="REGISTERED",
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return RepositoryResponse(
        id=repo.id,
        tenant_id=repo.tenant_id,
        project_id=app_row.project_id,
        application_id=repo.application_id,
        name=repo.name,
        default_branch=repo.default_branch or "main",
        clone_url=repo.remote_url,
        is_active=True,
        created_at=repo.created_at,
    )


@router.post(
    "/repositories/{repository_id}/upload-zip",
    response_model=ZipUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a ZIP source archive into an immutable repository snapshot",
)
def upload_repository_zip(
    repository_id: uuid.UUID,
    file: UploadFile = File(...),
    snapshot_label: str | None = Form(default=None),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> ZipUploadResponse:
    db, ctx = deps
    row = db.execute(
        select(Repository, Application.project_id)
        .join(
            Application,
            (Application.tenant_id == Repository.tenant_id)
            & (Application.id == Repository.application_id),
        )
        .where(
            Repository.tenant_id == ctx.tenant_id,
            Repository.id == repository_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    repo, proj_id = row

    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=proj_id,
            required_permission="repo:ingest",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    raw_bytes = file.file.read()
    try:
        outcome = ingestion_service.ingest_zip_archive(
            db,
            tenant_id=ctx.tenant_id,
            project_id=proj_id,
            repository_id=repo.id,
            zip_bytes=raw_bytes,
            snapshot_label=snapshot_label,
            triggered_by_user_id=ctx.user_id,
            run_analysis_and_indexing=True,
        )
        db.commit()
    except ArchiveValidationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ZipUploadResponse(
        repository_id=outcome.repository_id,
        snapshot_id=outcome.snapshot_id,
        ingestion_job_id=outcome.ingestion_job_id,
        analysis_run_id=outcome.analysis_run_id,
        tree_hash=outcome.tree_hash,
        is_duplicate_snapshot=outcome.is_duplicate_snapshot,
        files_processed=outcome.files_processed,
        total_bytes=outcome.total_bytes,
        chunks_indexed=outcome.chunks_indexed,
    )


def _to_snapshot_response(snap: RepositorySnapshot, proj_id: uuid.UUID) -> SnapshotResponse:
    return SnapshotResponse(
        id=snap.id,
        tenant_id=snap.tenant_id,
        project_id=proj_id,
        repository_id=snap.repository_id,
        snapshot_label=f"v{snap.snapshot_number} ({snap.tree_or_archive_sha256[:8]})",
        source_type="ZIP_UPLOAD",
        tree_hash=snap.tree_or_archive_sha256,
        file_count=int(snap.total_files_count),
        total_bytes=int(snap.total_bytes_size),
        status=snap.status,
        retention_class="STANDARD",
        legal_hold=snap.legal_hold_active,
        created_at=snap.captured_at,
    )


def _to_job_response(job: IngestionJob, proj_id: uuid.UUID) -> IngestionJobResponse:
    summary = job.stats_summary or {}
    return IngestionJobResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        project_id=proj_id,
        repository_id=job.repository_id,
        snapshot_id=job.snapshot_id,
        status=job.status,
        stage=str(summary.get("stage", job.status)),
        progress_pct=int(summary.get("progress_pct", 100 if job.status == "COMPLETED" else 0)),
        files_processed=int(summary.get("files_processed", 0)),
        bytes_processed=int(summary.get("bytes_processed", 0)),
        error_code=None,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.started_at or datetime.now(timezone.utc),
    )


@router.get(
    "/repositories/{repository_id}/snapshots",
    response_model=list[SnapshotResponse],
    status_code=status.HTTP_200_OK,
    summary="List immutable snapshots for a repository",
)
def list_repository_snapshots(
    repository_id: uuid.UUID,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[SnapshotResponse]:
    db, ctx = deps
    row = db.execute(
        select(Repository, Application.project_id)
        .join(
            Application,
            (Application.tenant_id == Repository.tenant_id)
            & (Application.id == Repository.application_id),
        )
        .where(
            Repository.tenant_id == ctx.tenant_id,
            Repository.id == repository_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    _, proj_id = row

    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=proj_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    rows = db.execute(
        select(RepositorySnapshot)
        .where(
            RepositorySnapshot.tenant_id == ctx.tenant_id,
            RepositorySnapshot.repository_id == repository_id,
        )
        .order_by(RepositorySnapshot.captured_at.desc())
    ).scalars().all()
    return [_to_snapshot_response(s, proj_id) for s in rows]


@router.get(
    "/snapshots",
    response_model=list[SnapshotResponse],
    status_code=status.HTTP_200_OK,
    summary="List snapshots in a project",
)
def list_project_snapshots(
    project_id: uuid.UUID = Query(...),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[SnapshotResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    rows = db.execute(
        select(RepositorySnapshot)
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
            Application.project_id == project_id,
        )
        .order_by(RepositorySnapshot.captured_at.desc())
    ).scalars().all()
    return [_to_snapshot_response(s, project_id) for s in rows]


@router.get(
    "/ingestion-jobs",
    response_model=list[IngestionJobResponse],
    status_code=status.HTTP_200_OK,
    summary="List ingestion jobs in a project",
)
def list_ingestion_jobs(
    project_id: uuid.UUID = Query(...),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[IngestionJobResponse]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    rows = db.execute(
        select(IngestionJob)
        .join(
            Repository,
            (Repository.tenant_id == IngestionJob.tenant_id)
            & (Repository.id == IngestionJob.repository_id),
        )
        .join(
            Application,
            (Application.tenant_id == Repository.tenant_id)
            & (Application.id == Repository.application_id),
        )
        .where(
            IngestionJob.tenant_id == ctx.tenant_id,
            Application.project_id == project_id,
        )
        .order_by(IngestionJob.started_at.desc())
    ).scalars().all()
    return [_to_job_response(j, project_id) for j in rows]


@router.get(
    "/ingestion-jobs/{job_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ingestion job status and progress",
)
def get_ingestion_job(
    job_id: uuid.UUID,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> IngestionJobResponse:
    db, ctx = deps
    row = db.execute(
        select(IngestionJob, Application.project_id)
        .join(
            Repository,
            (Repository.tenant_id == IngestionJob.tenant_id)
            & (Repository.id == IngestionJob.repository_id),
        )
        .join(
            Application,
            (Application.tenant_id == Repository.tenant_id)
            & (Application.id == Repository.application_id),
        )
        .where(
            IngestionJob.tenant_id == ctx.tenant_id,
            IngestionJob.id == job_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    job, proj_id = row

    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=proj_id,
            required_permission="project:read",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return _to_job_response(job, proj_id)
