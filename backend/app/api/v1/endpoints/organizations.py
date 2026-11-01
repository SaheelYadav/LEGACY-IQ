"""Organization, membership, and local-first bootstrap endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    DEFAULT_DEMO_APP_ID,
    DEFAULT_DEMO_PROJECT_ID,
    DEFAULT_DEMO_REPO_ID,
    DEFAULT_DEMO_TENANT_ID,
    DEFAULT_DEMO_USER_ID,
    DEFAULT_DEMO_WORKSPACE_ID,
    ROLE_CODE_TO_UUID,
    get_tenant_context,
)
from app.core.security import (
    ROLE_ORG_OWNER_ID,
    TenantContext,
)
from app.db.session import activate_tenant_rls, get_db
from app.models.identity import Organization, OrganizationMembership, Role, User
from app.models.ingestion import Repository, RepositorySnapshot
from app.models.projects import Application, Project, ProjectMembership, Workspace
from app.schemas.platform import (
    BootstrapContextResponse,
    MembershipCreateRequest,
    OrganizationCreateRequest,
    OrganizationMembershipResponse,
    OrganizationResponse,
)

router = APIRouter()


@router.post(
    "/bootstrap",
    response_model=BootstrapContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Idempotently provision default local-first enterprise tenant, workspace, project, application, and repository",
)
def bootstrap_default_context(db: Session = Depends(get_db)) -> BootstrapContextResponse:
    """
    Ensure a default organization (`acme-enterprise`), owner user (`architect@legacyiq.local`),
    workspace (`core-modernization`), project (`CORE`), application (`core-monolith`), and
    repository (`legacy-monolith`) exist for immediate local-first discovery and frontend integration.
    """
    user = db.execute(select(User).where(User.id == DEFAULT_DEMO_USER_ID)).scalar_one_or_none()
    if user is None:
        user = db.execute(
            select(User).where(User.email == "architect@legacyiq.local")
        ).scalar_one_or_none()
    if user is None:
        user = User(
            id=DEFAULT_DEMO_USER_ID,
            email="architect@legacyiq.local",
            full_name="Lead Platform Architect",
            password_hash="local-dev-only",
            auth_provider="LOCAL",
            is_system_admin=False,
        )
        db.add(user)
        db.flush()

    activate_tenant_rls(db, DEFAULT_DEMO_TENANT_ID)

    org = db.execute(
        select(Organization).where(Organization.id == DEFAULT_DEMO_TENANT_ID)
    ).scalar_one_or_none()
    if org is None:
        org = Organization(
            id=DEFAULT_DEMO_TENANT_ID,
            slug="acme-enterprise",
            display_name="Acme Enterprise Modernization",
            status="ACTIVE",
            tier="ENTERPRISE",
        )
        db.add(org)
        db.flush()

    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.tenant_id == org.id,
            OrganizationMembership.user_id == user.id,
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = OrganizationMembership(
            id=uuid.uuid4(),
            tenant_id=org.id,
            user_id=user.id,
            role_id=ROLE_ORG_OWNER_ID,
            status="ACTIVE",
        )
        db.add(membership)
        db.flush()

    workspace = db.execute(
        select(Workspace).where(
            Workspace.tenant_id == org.id,
            Workspace.id == DEFAULT_DEMO_WORKSPACE_ID,
        )
    ).scalar_one_or_none()
    if workspace is None:
        workspace = Workspace(
            id=DEFAULT_DEMO_WORKSPACE_ID,
            tenant_id=org.id,
            slug="core-modernization",
            name="Core Modernization Portfolio",
            is_default=True,
        )
        db.add(workspace)
        db.flush()

    project = db.execute(
        select(Project).where(
            Project.tenant_id == org.id,
            Project.id == DEFAULT_DEMO_PROJECT_ID,
        )
    ).scalar_one_or_none()
    if project is None:
        project = Project(
            id=DEFAULT_DEMO_PROJECT_ID,
            tenant_id=org.id,
            workspace_id=workspace.id,
            key="CORE",
            name="Core Banking & Order Platform",
            description="Multi-language legacy application discovery project.",
            lifecycle_status="ACTIVE",
            legal_hold_active=False,
        )
        db.add(project)
        db.flush()

    proj_mem = db.execute(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == org.id,
            ProjectMembership.project_id == project.id,
            ProjectMembership.org_membership_id == membership.id,
        )
    ).scalar_one_or_none()
    if proj_mem is None:
        proj_mem = ProjectMembership(
            id=uuid.uuid4(),
            tenant_id=org.id,
            project_id=project.id,
            org_membership_id=membership.id,
            role_id=ROLE_ORG_OWNER_ID,
        )
        db.add(proj_mem)
        db.flush()

    app_row = db.execute(
        select(Application).where(
            Application.tenant_id == org.id,
            Application.id == DEFAULT_DEMO_APP_ID,
        )
    ).scalar_one_or_none()
    if app_row is None:
        app_row = Application(
            id=DEFAULT_DEMO_APP_ID,
            tenant_id=org.id,
            project_id=project.id,
            code="core-monolith",
            name="Core Enterprise Monolith",
            architecture_style="MONOLITH",
            criticality_tier="TIER_1",
            primary_languages=["python", "java", "typescript", "javascript", "php"],
        )
        db.add(app_row)
        db.flush()

    repo = db.execute(
        select(Repository).where(
            Repository.tenant_id == org.id,
            Repository.id == DEFAULT_DEMO_REPO_ID,
        )
    ).scalar_one_or_none()
    if repo is None:
        repo = Repository(
            id=DEFAULT_DEMO_REPO_ID,
            tenant_id=org.id,
            application_id=app_row.id,
            connector_id=None,
            name="legacy-monolith",
            source_type="ZIP_ARCHIVE",
            default_branch="main",
            status="REGISTERED",
        )
        db.add(repo)
        db.flush()

    latest_snapshot = db.execute(
        select(RepositorySnapshot)
        .where(
            RepositorySnapshot.tenant_id == org.id,
            RepositorySnapshot.repository_id == repo.id,
        )
        .order_by(RepositorySnapshot.captured_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    db.commit()

    return BootstrapContextResponse(
        tenant_id=org.id,
        organization_name=org.display_name,
        organization_slug=org.slug,
        user_id=user.id,
        user_email=user.email,
        user_display_name=user.full_name,
        role_code="ORG_OWNER",
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        project_id=project.id,
        project_key=project.key,
        project_name=project.name,
        default_repository_id=repo.id,
        default_repository_name=repo.name,
        latest_snapshot_id=latest_snapshot.id if latest_snapshot else None,
    )


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization tenant and bind the owner membership",
)
def create_organization(
    payload: OrganizationCreateRequest,
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    user = db.execute(
        select(User).where(User.email == payload.owner_email.lower().strip())
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=payload.owner_email.lower().strip(),
            full_name=payload.owner_name,
            auth_provider="LOCAL",
            is_system_admin=False,
        )
        db.add(user)
        db.flush()

    new_org_id = uuid.uuid4()
    activate_tenant_rls(db, new_org_id)

    org = Organization(
        id=new_org_id,
        slug=payload.slug,
        display_name=payload.name,
        status="ACTIVE",
        tier=payload.plan_tier,
    )
    db.add(org)
    db.flush()

    membership = OrganizationMembership(
        id=uuid.uuid4(),
        tenant_id=org.id,
        user_id=user.id,
        role_id=ROLE_ORG_OWNER_ID,
        status="ACTIVE",
    )
    db.add(membership)
    db.commit()
    db.refresh(org)
    return OrganizationResponse(
        id=org.id,
        slug=org.slug,
        name=org.display_name,
        status=org.status,
        plan_tier=org.tier,
        created_at=org.created_at,
    )


@router.get(
    "/organizations/current",
    response_model=OrganizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the active organization for the authenticated tenant context",
)
def get_current_organization(
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> OrganizationResponse:
    db, ctx = deps
    org = db.execute(
        select(Organization).where(Organization.id == ctx.tenant_id)
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return OrganizationResponse(
        id=org.id,
        slug=org.slug,
        name=org.display_name,
        status=org.status,
        plan_tier=org.tier,
        created_at=org.created_at,
    )


@router.get(
    "/organizations/{tenant_id}/memberships",
    response_model=list[OrganizationMembershipResponse],
    status_code=status.HTTP_200_OK,
    summary="List organization memberships within the verified tenant",
)
def list_organization_memberships(
    tenant_id: uuid.UUID,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> list[OrganizationMembershipResponse]:
    db, ctx = deps
    if tenant_id != ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant membership access denied.",
        )

    rows = db.execute(
        select(OrganizationMembership, User, Role)
        .join(User, User.id == OrganizationMembership.user_id)
        .join(Role, Role.id == OrganizationMembership.role_id)
        .where(OrganizationMembership.tenant_id == ctx.tenant_id)
        .order_by(User.email.asc())
    ).all()

    return [
        OrganizationMembershipResponse(
            id=mem.id,
            tenant_id=mem.tenant_id,
            user_id=usr.id,
            user_email=usr.email,
            user_display_name=usr.full_name,
            role_id=role.id,
            role_code=role.code,
            status=mem.status,
        )
        for mem, usr, role in rows
    ]


@router.post(
    "/organizations/{tenant_id}/memberships",
    response_model=OrganizationMembershipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or update a member in the organization",
)
def add_organization_membership(
    tenant_id: uuid.UUID,
    payload: MembershipCreateRequest,
    deps: tuple[Session, TenantContext] = Depends(get_tenant_context),
) -> OrganizationMembershipResponse:
    db, ctx = deps
    if tenant_id != ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant membership creation denied.",
        )
    if not ctx.has_permission("org:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'org:manage' required to manage organization memberships.",
        )

    clean_email = payload.email.lower().strip()
    user = db.execute(select(User).where(User.email == clean_email)).scalar_one_or_none()
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=clean_email,
            full_name=payload.display_name,
            auth_provider="LOCAL",
            is_system_admin=False,
        )
        db.add(user)
        db.flush()

    role_id = ROLE_CODE_TO_UUID[payload.role_code]
    mem = OrganizationMembership(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        user_id=user.id,
        role_id=role_id,
        status="ACTIVE",
    )
    db.add(mem)
    db.commit()

    return OrganizationMembershipResponse(
        id=mem.id,
        tenant_id=mem.tenant_id,
        user_id=user.id,
        user_email=user.email,
        user_display_name=user.full_name,
        role_id=role_id,
        role_code=payload.role_code,
        status=mem.status,
    )
