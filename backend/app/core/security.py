"""Enterprise multi-tenant security, RBAC resolution, signed task envelopes, and archive safety."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.identity import (
    Organization,
    OrganizationMembership,
    Permission,
    Role,
    RolePermission,
    User,
)
from app.models.projects import Project, ProjectMembership

# Canonical deterministic UUIDs seeded in migration 0003
ROLE_ORG_OWNER_ID = uuid.UUID("00000000-0000-7000-8000-000000000201")
ROLE_ARCHITECT_ID = uuid.UUID("00000000-0000-7000-8000-000000000202")
ROLE_REVIEWER_ID = uuid.UUID("00000000-0000-7000-8000-000000000203")
ROLE_VIEWER_ID = uuid.UUID("00000000-0000-7000-8000-000000000204")

DEFAULT_EMBEDDING_MODEL_VERSION_ID = uuid.UUID("00000000-0000-7000-8000-000000000301")


class SecurityViolationError(PermissionError):
    """Raised when tenant isolation, RBAC, or path boundary checks fail."""


@dataclass(frozen=True)
class TenantContext:
    """
    Verified multi-tenant security context bound to an authenticated user
    and an active organization membership.
    """

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    org_membership_id: uuid.UUID
    org_role_id: uuid.UUID
    org_role_code: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    is_enforced: bool = True

    def has_permission(self, permission_code: str) -> bool:
        """Check whether the user's organization-level role grants a permission."""
        return permission_code in self.permissions or self.org_role_code == "ORG_OWNER"


@dataclass(frozen=True)
class ProjectAccessContext:
    """Verified project-scoped RBAC context within a tenant."""

    tenant_context: TenantContext
    project_id: uuid.UUID
    effective_role_id: uuid.UUID
    effective_role_code: str
    effective_permissions: frozenset[str] = field(default_factory=frozenset)

    def has_permission(self, permission_code: str) -> bool:
        return (
            permission_code in self.effective_permissions
            or self.effective_role_code == "ORG_OWNER"
        )


def validate_safe_extract_path(base_dir: Path, target_path: Path) -> Path:
    """
    Prevent Zip-Slip and path traversal when inspecting untrusted archives or repos.
    Raises ValueError if target_path resolves outside base_dir.
    """
    resolved_base = base_dir.resolve()
    resolved_target = target_path.resolve()
    if not resolved_target.is_relative_to(resolved_base):
        raise ValueError("Security violation: path traversal detected outside workspace root.")
    return resolved_target


def build_tenant_cache_key(
    tenant_id: uuid.UUID | str,
    domain: str,
    entity_id: uuid.UUID | str,
    project_id: uuid.UUID | str | None = None,
) -> str:
    """
    Construct a deterministic tenant-prefixed Redis key per D3 section 10:
    lq:{env}:t:{tenant_id}:p:{project_id}:{domain}:{entity_id}
    """
    tid = str(uuid.UUID(str(tenant_id)))
    pid = str(uuid.UUID(str(project_id))) if project_id is not None else "global"
    clean_domain = domain.strip().lower().replace(":", "_")
    return f"lq:{settings.APP_ENV}:t:{tid}:p:{pid}:{clean_domain}:{entity_id}"


@dataclass(frozen=True)
class TaskEnvelope:
    """
    HMAC-signed background worker payload envelope carrying verified tenant context.
    Prevents cross-tenant payload tampering on Redis queues.
    """

    task_id: str
    tenant_id: str
    project_id: str
    actor_user_id: str
    task_type: str
    payload: dict[str, Any]
    issued_at: str
    signature: str

    @classmethod
    def create(
        cls,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        task_type: str,
        payload: dict[str, Any],
    ) -> TaskEnvelope:
        task_id = str(uuid.uuid4())
        issued_at = datetime.now(timezone.utc).isoformat()
        unsigned = {
            "task_id": task_id,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "actor_user_id": str(actor_user_id),
            "task_type": task_type,
            "payload": payload,
            "issued_at": issued_at,
        }
        sig = cls._sign_dict(unsigned)
        return cls(**unsigned, signature=sig)

    @staticmethod
    def _sign_dict(data: dict[str, Any]) -> str:
        secret = f"{settings.APP_NAME}:{settings.APP_ENV}:task-hmac-key".encode("utf-8")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(secret, canonical, hashlib.sha256).hexdigest()

    def verify(self) -> bool:
        unsigned = {
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "actor_user_id": self.actor_user_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "issued_at": self.issued_at,
        }
        expected = self._sign_dict(unsigned)
        return hmac.compare_digest(self.signature, expected)


def _load_role_permissions(
    db: Session, role_id: uuid.UUID, tenant_id: uuid.UUID
) -> tuple[str, frozenset[str]]:
    """Resolve role code and permission codes for a system or tenant role."""
    role_row = db.execute(
        select(Role).where(
            Role.id == role_id,
            (Role.tenant_id.is_(None)) | (Role.tenant_id == tenant_id),
        )
    ).scalar_one_or_none()
    if role_row is None:
        raise SecurityViolationError(
            f"Role {role_id} not found or inaccessible for tenant {tenant_id}."
        )

    perm_codes = db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    ).scalars().all()
    return role_row.code, frozenset(perm_codes)


def verify_and_activate_tenant_context(
    db: Session,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    required_permission: str | None = None,
) -> TenantContext:
    """
    1. Activate PostgreSQL RLS context for `tenant_id` (`SET LOCAL ROLE legacyiq_app`
       and `set_config('app.current_tenant_id', ...)`).
    2. Verify that `user_id` exists in `users` and holds an `ACTIVE` membership
       in `organization_memberships` for `tenant_id` (and the organization is `ACTIVE`).
    3. Load the user's organization-level role and permissions.
    4. Optionally enforce `required_permission`.
    """
    from app.db.session import activate_tenant_rls

    activate_tenant_rls(db, tenant_id)

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise SecurityViolationError("Authenticated user does not exist.")

    org = db.execute(
        select(Organization).where(
            Organization.id == tenant_id,
            Organization.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if org is None:
        raise SecurityViolationError("Target organization does not exist or is not active.")

    membership = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.tenant_id == tenant_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if membership is None:
        raise SecurityViolationError(
            f"Access denied: user {user_id} is not an active member of organization {tenant_id}."
        )

    role_code, perms = _load_role_permissions(db, membership.role_id, tenant_id)
    ctx = TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        org_membership_id=membership.id,
        org_role_id=membership.role_id,
        org_role_code=role_code,
        permissions=perms,
        is_enforced=True,
    )
    if required_permission and not ctx.has_permission(required_permission):
        raise SecurityViolationError(
            f"Permission '{required_permission}' required in organization {tenant_id}."
        )
    return ctx


def verify_project_access(
    db: Session,
    *,
    tenant_context: TenantContext,
    project_id: uuid.UUID,
    required_permission: str | None = None,
) -> ProjectAccessContext:
    """
    Enforce project-level RBAC within the active tenant:
    - Confirm the project exists in `tenant_context.tenant_id`.
    - `ORG_OWNER` has implicit access to all projects in their organization.
    - Non-owner members must have a row in `project_memberships` for
      `(tenant_id, project_id, org_membership_id)`.
    """
    project = db.execute(
        select(Project).where(
            Project.tenant_id == tenant_context.tenant_id,
            Project.id == project_id,
        )
    ).scalar_one_or_none()
    if project is None:
        raise SecurityViolationError(
            f"Project {project_id} not found in tenant {tenant_context.tenant_id}."
        )

    proj_membership = db.execute(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant_context.tenant_id,
            ProjectMembership.project_id == project_id,
            ProjectMembership.org_membership_id == tenant_context.org_membership_id,
        )
    ).scalar_one_or_none()

    if proj_membership is not None:
        role_code, perms = _load_role_permissions(
            db, proj_membership.role_id, tenant_context.tenant_id
        )
        effective_role_id = proj_membership.role_id
        effective_role_code = role_code
        effective_perms = perms | tenant_context.permissions
    elif tenant_context.org_role_code == "ORG_OWNER":
        effective_role_id = tenant_context.org_role_id
        effective_role_code = tenant_context.org_role_code
        effective_perms = tenant_context.permissions
    else:
        raise SecurityViolationError(
            f"Access denied: user {tenant_context.user_id} does not have membership in project {project_id}."
        )

    proj_ctx = ProjectAccessContext(
        tenant_context=tenant_context,
        project_id=project_id,
        effective_role_id=effective_role_id,
        effective_role_code=effective_role_code,
        effective_permissions=effective_perms,
    )
    if required_permission and not proj_ctx.has_permission(required_permission):
        raise SecurityViolationError(
            f"Permission '{required_permission}' required for project {project_id}."
        )
    return proj_ctx
