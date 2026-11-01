"""FastAPI dependencies for authenticated tenant RLS sessions and RBAC."""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    ROLE_ARCHITECT_ID,
    ROLE_ORG_OWNER_ID,
    ROLE_REVIEWER_ID,
    ROLE_VIEWER_ID,
    SecurityViolationError,
    TenantContext,
    verify_and_activate_tenant_context,
)
from app.db.session import get_db

ROLE_CODE_TO_UUID: dict[str, uuid.UUID] = {
    "ORG_OWNER": ROLE_ORG_OWNER_ID,
    "ARCHITECT": ROLE_ARCHITECT_ID,
    "REVIEWER": ROLE_REVIEWER_ID,
    "VIEWER": ROLE_VIEWER_ID,
}

DEFAULT_DEMO_TENANT_ID = uuid.UUID("00000000-0000-7000-8000-000000000901")
DEFAULT_DEMO_USER_ID = uuid.UUID("00000000-0000-7000-8000-000000000902")
DEFAULT_DEMO_WORKSPACE_ID = uuid.UUID("00000000-0000-7000-8000-000000000903")
DEFAULT_DEMO_PROJECT_ID = uuid.UUID("00000000-0000-7000-8000-000000000904")
DEFAULT_DEMO_APP_ID = uuid.UUID("00000000-0000-7000-8000-000000000905")
DEFAULT_DEMO_REPO_ID = uuid.UUID("00000000-0000-7000-8000-000000000906")


def get_tenant_context(
    x_tenant_id: uuid.UUID = Header(..., alias="X-Tenant-Id"),
    x_user_id: uuid.UUID = Header(..., alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> tuple[Session, TenantContext]:
    """
    FastAPI dependency that:
    1. Activates PostgreSQL RLS (`SET LOCAL ROLE legacyiq_app` + `app.current_tenant_id`).
    2. Verifies `x_user_id` is an active member of `x_tenant_id` in `organization_memberships`.
    3. Returns `(db, tenant_context)`.
    """
    try:
        ctx = verify_and_activate_tenant_context(
            db, user_id=x_user_id, tenant_id=x_tenant_id
        )
        return db, ctx
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
