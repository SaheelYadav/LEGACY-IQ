"""Workspace, Project, Project Membership, and Application endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ROLE_CODE_TO_UUID, get_tenant_context
from app.core.security import (
    SecurityViolationError,
    TenantContext,
    verify_project_access,
)
from app.models.identity import OrganizationMembership
from app.models.projects import Application, Project, ProjectMembership, Workspace
from app.schemas.platform import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ProjectCreateRequest,
    ProjectMembershipCreateRequest,
    ProjectResponse,
    WorkspaceCreateRequest,
    WorkspaceResponse,
)

router = APIRouter()


@router.get(
    "/workspaces",
    response_model=list[WorkspaceResponse],
    status_code=status.HTTP_200_OK,
    summary="List workspaces in the active tenant",
)
def list_workspaces(
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[WorkspaceResponse]:
    db, ctx = deps
    rows = db.execute(
        select(Workspace)
        .where(Workspace.tenant_id == ctx.tenant_id)
        .order_by(Workspace.created_at.asc())
    ).scalars().all()
    return [
        WorkspaceResponse(
            id=w.id,
            tenant_id=w.tenant_id,
            slug=w.slug,
            name=w.name,
            description=None,
            is_archived=False,
            created_at=w.created_at,
        )
        for w in rows
    ]


@router.post(
    "/workspaces",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace in the active tenant",
)
def create_workspace(
    payload: WorkspaceCreateRequest,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> WorkspaceResponse:
    db, ctx = deps
    if not ctx.has_permission("project:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'project:write' required to create workspaces.",
        )
    ws = Workspace(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        slug=payload.slug,
        name=payload.name,
        is_default=False,
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return WorkspaceResponse(
        id=ws.id,
        tenant_id=ws.tenant_id,
        slug=ws.slug,
        name=ws.name,
        description=payload.description,
        is_archived=False,
        created_at=ws.created_at,
    )


@router.get(
    "/projects",
    response_model=list[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List projects accessible to the authenticated user in the active tenant",
)
def list_projects(
    workspace_id: uuid.UUID | None = Query(default=None),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[ProjectResponse]:
    db, ctx = deps
    stmt = select(Project).where(Project.tenant_id == ctx.tenant_id)
    if workspace_id is not None:
        stmt = stmt.where(Project.workspace_id == workspace_id)
    if ctx.org_role_code != "ORG_OWNER":
        stmt = stmt.join(
            ProjectMembership,
            (ProjectMembership.tenant_id == Project.tenant_id)
            & (ProjectMembership.project_id == Project.id),
        ).where(ProjectMembership.org_membership_id == ctx.org_membership_id)
    rows = db.execute(stmt.order_by(Project.created_at.asc())).scalars().all()
    return [
        ProjectResponse(
            id=p.id,
            tenant_id=p.tenant_id,
            workspace_id=p.workspace_id,
            key=p.key,
            name=p.name,
            description=p.description,
            status=p.lifecycle_status,
            default_retention_days=365,
            created_at=p.created_at,
        )
        for p in rows
    ]


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project and assign the creator as project member",
)
def create_project(
    payload: ProjectCreateRequest,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> ProjectResponse:
    db, ctx = deps
    if not ctx.has_permission("project:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'project:write' required to create projects.",
        )
    project = Project(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        workspace_id=payload.workspace_id,
        key=payload.key,
        name=payload.name,
        description=payload.description,
        lifecycle_status="ACTIVE",
        legal_hold_active=False,
    )
    db.add(project)
    db.flush()

    pm = ProjectMembership(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project.id,
        org_membership_id=ctx.org_membership_id,
        role_id=ctx.org_role_id,
    )
    db.add(pm)
    db.commit()
    db.refresh(project)
    return ProjectResponse(
        id=project.id,
        tenant_id=project.tenant_id,
        workspace_id=project.workspace_id,
        key=project.key,
        name=project.name,
        description=project.description,
        status=project.lifecycle_status,
        default_retention_days=payload.default_retention_days,
        created_at=project.created_at,
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project details (enforces project-level RBAC)",
)
def get_project(
    project_id: uuid.UUID,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> ProjectResponse:
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

    project = db.execute(
        select(Project).where(
            Project.tenant_id == ctx.tenant_id,
            Project.id == project_id,
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectResponse(
        id=project.id,
        tenant_id=project.tenant_id,
        workspace_id=project.workspace_id,
        key=project.key,
        name=project.name,
        description=project.description,
        status=project.lifecycle_status,
        default_retention_days=365,
        created_at=project.created_at,
    )


@router.post(
    "/projects/{project_id}/memberships",
    status_code=status.HTTP_201_CREATED,
    summary="Grant a tenant member access to a specific project",
)
def add_project_membership(
    project_id: uuid.UUID,
    payload: ProjectMembershipCreateRequest,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> dict[str, str]:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=project_id,
            required_permission="project:write",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    target_org_mem = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.tenant_id == ctx.tenant_id,
            OrganizationMembership.user_id == payload.user_id,
        )
    ).scalar_one_or_none()
    if target_org_mem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user is not a member of this organization.",
        )

    role_id = ROLE_CODE_TO_UUID[payload.role_code]
    pm = ProjectMembership(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=project_id,
        org_membership_id=target_org_mem.id,
        role_id=role_id,
    )
    db.add(pm)
    db.commit()
    return {
        "id": str(pm.id),
        "tenant_id": str(pm.tenant_id),
        "project_id": str(pm.project_id),
        "user_id": str(payload.user_id),
        "role_code": payload.role_code,
    }


@router.get(
    "/applications",
    response_model=list[ApplicationResponse],
    status_code=status.HTTP_200_OK,
    summary="List applications in a project",
)
def list_applications(
    project_id: uuid.UUID = Query(...),
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[ApplicationResponse]:
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
        select(Application)
        .where(
            Application.tenant_id == ctx.tenant_id,
            Application.project_id == project_id,
        )
        .order_by(Application.created_at.asc())
    ).scalars().all()
    return [
        ApplicationResponse(
            id=a.id,
            tenant_id=a.tenant_id,
            project_id=a.project_id,
            slug=a.code,
            name=a.name,
            primary_language=a.primary_languages[0] if a.primary_languages else None,
            criticality_tier=a.criticality_tier,
            created_at=a.created_at,
        )
        for a in rows
    ]


@router.post(
    "/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an application within a project",
)
def create_application(
    payload: ApplicationCreateRequest,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> ApplicationResponse:
    db, ctx = deps
    try:
        verify_project_access(
            db,
            tenant_context=ctx,
            project_id=payload.project_id,
            required_permission="project:write",
        )
    except SecurityViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    app_row = Application(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        project_id=payload.project_id,
        code=payload.slug,
        name=payload.name,
        primary_languages=[payload.primary_language] if payload.primary_language else [],
        criticality_tier=payload.criticality_tier,
    )
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return ApplicationResponse(
        id=app_row.id,
        tenant_id=app_row.tenant_id,
        project_id=app_row.project_id,
        slug=app_row.code,
        name=app_row.name,
        primary_language=payload.primary_language,
        criticality_tier=app_row.criticality_tier,
        created_at=app_row.created_at,
    )
