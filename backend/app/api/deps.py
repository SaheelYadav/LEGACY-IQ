"""FastAPI dependencies for authenticated tenant RLS sessions and RBAC."""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    ROLE_ARCHITECT_ID,
    ROLE_ORG_OWNER_ID,
    ROLE_REVIEWER_ID,
    ROLE_VIEWER_ID,
    SecurityViolationError,
    TenantContext,
    verify_access_token,
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
    x_tenant_id: uuid.UUID | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> tuple[Session, TenantContext]:
    """
    FastAPI dependency that:
    1. Resolves identity from `Authorization: Bearer <jwt>` (if provided or required via
       `AUTH_ENFORCE_BEARER_TOKEN`) or from `X-Tenant-Id` + `X-User-Id` headers.
    2. Prevents cross-identity spoofing if both a Bearer token and `X-Tenant-Id` / `X-User-Id`
       headers are supplied.
    3. Activates PostgreSQL RLS (`SET LOCAL ROLE legacyiq_app` + `app.current_tenant_id`).
    4. Verifies `user_id` is an active member of `tenant_id` in `organization_memberships`.
    5. Returns `(db, tenant_context)`.
    """
    resolved_tenant_id = x_tenant_id
    resolved_user_id = x_user_id

    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
            )
        try:
            claims = verify_access_token(parts[1].strip())
            token_tid = uuid.UUID(str(claims["tid"]))
            token_uid = uuid.UUID(str(claims["sub"]))
        except (SecurityViolationError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

        if x_tenant_id is not None and x_tenant_id != token_tid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security violation: X-Tenant-Id header does not match Bearer token tenant claim.",
            )
        if x_user_id is not None and x_user_id != token_uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security violation: X-User-Id header does not match Bearer token subject claim.",
            )
        resolved_tenant_id = token_tid
        resolved_user_id = token_uid
    elif settings.AUTH_ENFORCE_BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication token is required when AUTH_ENFORCE_BEARER_TOKEN=true.",
        )

    if resolved_tenant_id is None or resolved_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication headers (provide Authorization: Bearer <token> or X-Tenant-Id and X-User-Id).",
        )

    try:
        ctx = verify_and_activate_tenant_context(
            db, user_id=resolved_user_id, tenant_id=resolved_tenant_id
        )
        return db, ctx
    except SecurityViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
