"""Wave 7: Production Hardening, Security Controls, Backup/Restore & Observability Tests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import subprocess
import time
import uuid

from fastapi import HTTPException
import pytest
from sqlalchemy import select, text

from app.api.deps import get_tenant_context
from app.api.v1.endpoints.requirements_intelligence import (
    BusinessRuleReviewRequest,
    get_snapshot_business_rules_endpoint,
    review_business_rule_endpoint,
)
from app.api.v1.endpoints.technical_intelligence import (
    FindingReviewRequest,
    get_snapshot_database_intelligence,
    review_finding_endpoint,
)
from app.api.v1.endpoints.testing_modernization import (
    ModernizationRecommendationReviewRequest,
    get_snapshot_risk_register_endpoint,
    review_modernization_recommendation_endpoint,
)
from app.core.config import DEV_DEFAULT_SECRET_KEY, PLACEHOLDER_TOKEN, Settings
from app.core.logging import RedactingFormatter, correlation_id_ctx, redact_sensitive_text
from app.core.security import (
    ROLE_ORG_OWNER_ID,
    ROLE_VIEWER_ID,
    SecurityViolationError,
    SlidingWindowRateLimiter,
    TaskEnvelope,
    create_access_token,
    verify_access_token,
    verify_and_activate_tenant_context,
)
from app.db.session import SessionLocal, tenant_db_session
from app.integrations.storage import TenantObjectStorage
from app.models.identity import Organization, OrganizationMembership, User
from app.models.ingestion import Repository, RepositorySnapshot
from app.models.projects import Application, Project, ProjectMembership, Workspace
from app.services.health_service import HealthService


def test_wave7_production_config_fail_fast_validation() -> None:
    """
    Phase B: Verify `Settings.validate_production_readiness()` and `assert_production_ready()`
    fail fast when `APP_ENV == 'production'` and unsafe defaults (`APP_DEBUG=True`,
    placeholder `DATABASE_URL`/`REDIS_URL`, default `APP_SECRET_KEY`, or wildcard CORS/Hosts)
    are present.
    """
    unsafe_prod = Settings(
        APP_ENV="production",
        APP_DEBUG=True,
        DATABASE_URL=f"postgresql+psycopg://legacyiq_admin:{PLACEHOLDER_TOKEN}@localhost:5432/legacyiq",
        REDIS_URL=f"redis://:{PLACEHOLDER_TOKEN}@localhost:6380/0",
        APP_SECRET_KEY=DEV_DEFAULT_SECRET_KEY,
        BACKEND_CORS_ORIGINS=["*"],
        ALLOWED_HOSTS=["*"],
    )
    errors = unsafe_prod.validate_production_readiness()
    assert len(errors) == 6
    with pytest.raises(RuntimeError, match="Production configuration validation failed"):
        unsafe_prod.assert_production_ready()

    safe_prod = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        DATABASE_URL="postgresql+psycopg://legacyiq_admin:real_strong_db_pass_99@db.internal:5432/legacyiq",
        REDIS_URL="redis://:real_strong_redis_pass_99@redis.internal:6379/0",
        APP_SECRET_KEY="prod-hmac-jwt-signing-secret-key-at-least-32-chars-long!",
        BACKEND_CORS_ORIGINS=["https://app.legacyiq.enterprise.internal"],
        ALLOWED_HOSTS=["api.legacyiq.enterprise.internal"],
    )
    assert safe_prod.validate_production_readiness() == []
    safe_prod.assert_production_ready()


def test_wave7_jwt_token_signing_expiration_and_tampering() -> None:
    """
    Phase C: Verify JWT token creation, claim verification, expiration rejection,
    and signature tampering rejection.
    """
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    token = create_access_token(
        user_id=uid,
        tenant_id=tid,
        role_code="ARCHITECT",
        expires_delta_minutes=15,
    )
    claims = verify_access_token(token)
    assert claims["sub"] == str(uid)
    assert claims["tid"] == str(tid)
    assert claims["role"] == "ARCHITECT"

    # Tampered signature must raise SecurityViolationError
    tampered = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    with pytest.raises(SecurityViolationError, match="Invalid authentication token"):
        verify_access_token(tampered)

    # Expired token must raise SecurityViolationError
    expired_token = create_access_token(
        user_id=uid,
        tenant_id=tid,
        role_code="VIEWER",
        expires_delta_minutes=-5,
    )
    with pytest.raises(SecurityViolationError, match="expired"):
        verify_access_token(expired_token)


def test_wave7_rate_limiter_and_log_secret_redaction() -> None:
    """
    Phase C & E: Verify sliding-window rate limiter enforcement and structured JSON/text
    log redaction of PostgreSQL/Redis passwords and Bearer tokens.
    """
    limiter = SlidingWindowRateLimiter()
    key = f"tenant-{uuid.uuid4()}:expensive"
    for i in range(3):
        allowed, rem = limiter.check_rate_limit(key, limit=3, window_seconds=60)
        assert allowed is True
        assert rem == 2 - i

    allowed_4th, rem_4th = limiter.check_rate_limit(key, limit=3, window_seconds=60)
    assert allowed_4th is False
    assert rem_4th == 0

    # Log redaction verification (URI credentials + Bearer JWTs)
    raw_msg = (
        "Connecting to postgresql+psycopg://admin:SuperSecretDbPass123@db:5432/legacyiq "
        "and redis://:RedisPass999@redis:6379/0 with Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.sig"
    )
    redacted = redact_sensitive_text(raw_msg)
    assert "SuperSecretDbPass123" not in redacted
    assert "RedisPass999" not in redacted
    assert "eyJhbGciOiJIUzI1NiJ9.secret.sig" not in redacted
    assert "***REDACTED***" in redacted

    # JSON formatter correlation ID injection
    tok = correlation_id_ctx.set("corr-wave7-test-123")
    try:
        formatter = RedactingFormatter(json_output=True)
        record = logging.LogRecord(
            name="legacyiq.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg=raw_msg,
            args=(),
            exc_info=None,
        )
        formatted_json = formatter.format(record)
        assert "corr-wave7-test-123" in formatted_json
        assert "SuperSecretDbPass123" not in formatted_json
    finally:
        correlation_id_ctx.reset(tok)


def test_wave7_storage_metrics_and_composite_readiness_probe() -> None:
    """
    Phase E: Verify storage vault health metrics and composite production readiness probe.
    """
    storage = TenantObjectStorage()
    metrics = storage.get_storage_metrics()
    assert metrics["status"] == "healthy"
    assert metrics["details"]["disk_total_gb"] > 0

    readiness = HealthService.get_readiness_summary()
    assert readiness["status"] == "ready"
    assert readiness["checks"]["database"]["status"] == "healthy"
    assert readiness["checks"]["redis"]["status"] == "healthy"
    assert readiness["checks"]["storage"]["status"] == "healthy"
    assert readiness["checks"]["ollama"]["deterministic_fallback_enabled"] is True


def test_wave7_cross_project_rbac_and_viewer_mutation_denial_integration() -> None:
    """
    Phase C (DEF-W7-001, DEF-W7-002, DEF-W7-003):
    Verify against live PostgreSQL that:
    1. Bearer JWT authentication works in `get_tenant_context` and rejects mismatched
       `X-Tenant-Id` / `X-User-Id` header spoofing (`403 Forbidden`).
    2. An authenticated `ARCHITECT` in Tenant A who is NOT a member of Project A is
       denied (`403 Forbidden`) on Wave 2 (`/database`), Wave 3 (`/business-rules`),
       and Wave 4 (`/risk-register`) snapshot endpoints (`DEF-W7-001`).
    3. A `VIEWER` member of Project A can read snapshot intelligence (`200 OK`) but is
       denied (`403 Forbidden`) when attempting to approve/reject findings, business rules,
       or modernization recommendations (`DEF-W7-002`).
    """
    tenant_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    outsider_architect_id = uuid.uuid4()
    viewer_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    app_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    snap_id = uuid.uuid4()

    with SessionLocal() as su_db:
        su_db.add_all(
            [
                User(
                    id=owner_id,
                    email=f"owner-{owner_id.hex[:8]}@wave7.local",
                    full_name="Wave 7 Owner",
                    auth_provider="LOCAL",
                ),
                User(
                    id=outsider_architect_id,
                    email=f"outsider-{outsider_architect_id.hex[:8]}@wave7.local",
                    full_name="Wave 7 Outsider Architect",
                    auth_provider="LOCAL",
                ),
                User(
                    id=viewer_id,
                    email=f"viewer-{viewer_id.hex[:8]}@wave7.local",
                    full_name="Wave 7 Read-Only Viewer",
                    auth_provider="LOCAL",
                ),
                Organization(
                    id=tenant_id,
                    slug=f"wave7-sec-{tenant_id.hex[:8]}",
                    display_name="Wave 7 Security Tenant",
                    status="ACTIVE",
                ),
            ]
        )
        su_db.commit()

    with tenant_db_session(tenant_id) as db:
        owner_mem_id = uuid.uuid4()
        outsider_mem_id = uuid.uuid4()
        viewer_mem_id = uuid.uuid4()
        db.add_all(
            [
                OrganizationMembership(
                    id=owner_mem_id,
                    tenant_id=tenant_id,
                    user_id=owner_id,
                    role_id=ROLE_ORG_OWNER_ID,
                    status="ACTIVE",
                ),
                OrganizationMembership(
                    id=outsider_mem_id,
                    tenant_id=tenant_id,
                    user_id=outsider_architect_id,
                    role_id=uuid.UUID("00000000-0000-7000-8000-000000000202"),  # ARCHITECT
                    status="ACTIVE",
                ),
                OrganizationMembership(
                    id=viewer_mem_id,
                    tenant_id=tenant_id,
                    user_id=viewer_id,
                    role_id=ROLE_VIEWER_ID,
                    status="ACTIVE",
                ),
                Workspace(
                    id=ws_id,
                    tenant_id=tenant_id,
                    slug="wave7-ws",
                    name="Wave 7 Workspace",
                    is_default=True,
                ),
            ]
        )
        db.flush()

        db.add(
            Project(
                id=proj_id,
                tenant_id=tenant_id,
                workspace_id=ws_id,
                key="W7SEC",
                name="Wave 7 Restricted Project",
                lifecycle_status="ACTIVE",
            )
        )
        db.flush()

        # Grant project membership ONLY to owner and viewer (NOT outsider_architect_id)
        db.add_all(
            [
                ProjectMembership(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    project_id=proj_id,
                    org_membership_id=owner_mem_id,
                    role_id=ROLE_ORG_OWNER_ID,
                ),
                ProjectMembership(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    project_id=proj_id,
                    org_membership_id=viewer_mem_id,
                    role_id=ROLE_VIEWER_ID,
                ),
                Application(
                    id=app_id,
                    tenant_id=tenant_id,
                    project_id=proj_id,
                    code="w7-app",
                    name="Wave 7 Application",
                    criticality_tier="TIER_1",
                ),
            ]
        )
        db.flush()

        db.add(
            Repository(
                id=repo_id,
                tenant_id=tenant_id,
                application_id=app_id,
                name="w7-repo",
                source_type="ZIP_ARCHIVE",
                status="REGISTERED",
            )
        )
        db.flush()

        db.add(
            RepositorySnapshot(
                id=snap_id,
                tenant_id=tenant_id,
                repository_id=repo_id,
                snapshot_number=1,
                tree_or_archive_sha256="a" * 64,
                total_files_count=1,
                total_bytes_size=100,
                status="ANALYZED",
            )
        )
        db.flush()

        # 1. Verify Bearer JWT auth + header mismatch spoofing rejection
        owner_jwt = create_access_token(
            user_id=owner_id, tenant_id=tenant_id, role_code="ORG_OWNER"
        )
        _, verified_owner_ctx = get_tenant_context(
            x_tenant_id=tenant_id,
            x_user_id=owner_id,
            authorization=f"Bearer {owner_jwt}",
            db=db,
        )
        assert verified_owner_ctx.user_id == owner_id

        with pytest.raises(HTTPException) as spoof_exc:
            get_tenant_context(
                x_tenant_id=uuid.uuid4(),
                x_user_id=owner_id,
                authorization=f"Bearer {owner_jwt}",
                db=db,
            )
        assert spoof_exc.value.status_code == 403

        # 2. Verify Outsider Architect (no ProjectMembership) is denied on Wave 2, 3, 4 snapshot endpoints
        outsider_ctx = verify_and_activate_tenant_context(
            db, user_id=outsider_architect_id, tenant_id=tenant_id
        )
        with pytest.raises(HTTPException) as w2_exc:
            get_snapshot_database_intelligence(snap_id, (db, outsider_ctx))
        assert w2_exc.value.status_code == 403

        with pytest.raises(HTTPException) as w3_exc:
            get_snapshot_business_rules_endpoint(
                snap_id, None, None, None, (db, outsider_ctx)
            )
        assert w3_exc.value.status_code == 403

        with pytest.raises(HTTPException) as w4_exc:
            get_snapshot_risk_register_endpoint(snap_id, None, None, (db, outsider_ctx))
        assert w4_exc.value.status_code == 403

        # 3. Verify Viewer (has ProjectMembership with VIEWER role) CAN read but CANNOT review/mutate
        viewer_ctx = verify_and_activate_tenant_context(
            db, user_id=viewer_id, tenant_id=tenant_id
        )
        db_intel = get_snapshot_database_intelligence(snap_id, (db, viewer_ctx))
        assert db_intel["snapshot_id"] == str(snap_id)

        with pytest.raises(HTTPException) as rev_f_exc:
            review_finding_endpoint(
                uuid.uuid4(),
                FindingReviewRequest(new_status="APPROVED"),
                (db, viewer_ctx),
            )
        assert rev_f_exc.value.status_code == 403

        with pytest.raises(HTTPException) as rev_br_exc:
            review_business_rule_endpoint(
                uuid.uuid4(),
                BusinessRuleReviewRequest(new_status="APPROVED"),
                (db, viewer_ctx),
            )
        assert rev_br_exc.value.status_code == 403

        with pytest.raises(HTTPException) as rev_mod_exc:
            review_modernization_recommendation_endpoint(
                uuid.uuid4(),
                ModernizationRecommendationReviewRequest(new_status="APPROVED"),
                (db, viewer_ctx),
            )
        assert rev_mod_exc.value.status_code == 403


def test_wave7_phase_d_postgresql_backup_and_isolated_restore_verification() -> None:
    """
    Phase D: Execute a real PostgreSQL logical backup (`pg_dump`) of the active `legacyiq`
    database inside the `legacyiq-postgres` container (or via SQL schema/data verification)
    and restore it into a separate ephemeral test database `legacyiq_wave7_restore_test`,
    confirming `pgvector` extension, `76` canonical tables, `72` FORCE RLS policies, and
    Alembic head `0007_wave5_qa_reports_export`, then cleanly drop `legacyiq_wave7_restore_test`
    while leaving the active `legacyiq` database untouched.
    """
    restore_db_name = "legacyiq_wave7_restore_test"
    backup_sql_path = Path(
        r"C:\Users\Saheel\.gemini\antigravity\brain\54c9637d-49c2-466c-92dc-feee17381740\scratch\legacyiq_wave7_backup.sql"
    )
    telemetry_path = Path(
        r"C:\Users\Saheel\.gemini\antigravity\brain\54c9637d-49c2-466c-92dc-feee17381740\scratch\wave7_backup_restore_telemetry.json"
    )
    backup_sql_path.parent.mkdir(parents=True, exist_ok=True)

    t_start = time.perf_counter()

    # 1. Run pg_dump inside legacyiq-postgres container (schema + data for alembic_version + roles + permissions)
    dump_cmd = [
        "docker",
        "exec",
        "legacyiq-postgres",
        "pg_dump",
        "-U",
        "legacyiq_admin",
        "-d",
        "legacyiq",
        "--no-owner",
        "--no-privileges",
    ]
    dump_proc = subprocess.run(
        dump_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    sql_dump_content = dump_proc.stdout
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql_dump_content or "vector" in sql_dump_content
    assert "CREATE TABLE public.organizations" in sql_dump_content
    assert "ROW LEVEL SECURITY" in sql_dump_content
    backup_sql_path.write_text(sql_dump_content, encoding="utf-8")
    backup_size_bytes = backup_sql_path.stat().st_size
    t_dump_ms = round((time.perf_counter() - t_start) * 1000, 2)

    # 2. Create isolated test database `legacyiq_wave7_restore_test` (never touch active `legacyiq`)
    t_restore_start = time.perf_counter()
    subprocess.run(
        [
            "docker",
            "exec",
            "legacyiq-postgres",
            "psql",
            "-U",
            "legacyiq_admin",
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE IF EXISTS {restore_db_name};",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    subprocess.run(
        [
            "docker",
            "exec",
            "legacyiq-postgres",
            "psql",
            "-U",
            "legacyiq_admin",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {restore_db_name};",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    try:
        # 3. Restore dump into `legacyiq_wave7_restore_test`
        restore_proc = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "legacyiq-postgres",
                "psql",
                "-U",
                "legacyiq_admin",
                "-d",
                restore_db_name,
            ],
            input=sql_dump_content,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=True,
        )
        assert restore_proc.returncode == 0
        t_restore_ms = round((time.perf_counter() - t_restore_start) * 1000, 2)

        # 4. Verify restored database integrity (pgvector, 76 tables, 72 FORCE RLS tables, alembic version)
        verify_sql = (
            "SELECT "
            "(SELECT extversion FROM pg_extension WHERE extname='vector') AS vector_ver, "
            "(SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name != 'alembic_version') AS table_cnt, "
            "(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity=true AND c.relforcerowsecurity=true) AS rls_cnt, "
            "(SELECT version_num FROM alembic_version LIMIT 1) AS alembic_ver;"
        )
        verify_proc = subprocess.run(
            [
                "docker",
                "exec",
                "legacyiq-postgres",
                "psql",
                "-U",
                "legacyiq_admin",
                "-d",
                restore_db_name,
                "-t",
                "-A",
                "-F",
                "|",
                "-c",
                verify_sql,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        parts = verify_proc.stdout.strip().split("|")
        assert len(parts) == 4
        vec_ver, tbl_cnt, rls_cnt, alembic_ver = (
            parts[0],
            int(parts[1]),
            int(parts[2]),
            parts[3],
        )
        assert vec_ver == "0.8.7"
        assert tbl_cnt == 76
        assert rls_cnt == 72
        assert alembic_ver == "0007_wave5_qa_reports_export"

        telemetry_path.write_text(
            json.dumps(
                {
                    "status": "VERIFIED",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_database": "legacyiq",
                    "target_restore_database": restore_db_name,
                    "backup_file_size_bytes": backup_size_bytes,
                    "pg_dump_duration_ms": t_dump_ms,
                    "psql_restore_duration_ms": t_restore_ms,
                    "restored_pgvector_version": vec_ver,
                    "restored_canonical_tables": tbl_cnt,
                    "restored_force_rls_tables": rls_cnt,
                    "restored_alembic_version": alembic_ver,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        # 5. Cleanly drop the temporary restore database so infrastructure stays clean
        subprocess.run(
            [
                "docker",
                "exec",
                "legacyiq-postgres",
                "psql",
                "-U",
                "legacyiq_admin",
                "-d",
                "postgres",
                "-c",
                f"DROP DATABASE IF EXISTS {restore_db_name};",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if backup_sql_path.exists():
            backup_sql_path.unlink()

