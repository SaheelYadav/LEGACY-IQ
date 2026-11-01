# LegacyIQ — Wave 7 Security Hardening Report

**Phase:** Wave 7 — Production Hardening & Deployment Readiness (Phase C)  
**Date:** 2026-11-01  
**Status:** Verified (`0` Open Critical/High Security Gaps)

---

## 1. Security Review Scope

Per Wave 7 Phase C requirements, the security review evaluated 15 security domains across the FastAPI backend (`C:\LegacyIQ\backend`) and Next.js frontend (`C:\LegacyIQ\frontend`):

1. Authentication token generation and validation (`JWT` HS256 signing, `exp`, `iat`, `jti`, `iss`).
2. Password handling and credential redaction.
3. Session and token expiration (`AUTH_TOKEN_EXPIRE_MINUTES`).
4. Refresh-token and identity provider boundary disclosures.
5. Password reset and account recovery boundaries.
6. Project-level RBAC enforcement across Waves 1–5.
7. Tenant-level access isolation (`FORCE ROW LEVEL SECURITY` on `72/72` tenant-owned tables).
8. API authorization on every sensitive read and mutation endpoint.
9. CORS, Trusted Hosts (`TrustedHostMiddleware`), and HTTP security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`).
10. File upload validation (`50 MB` compressed, `150 MB` uncompressed, `2,500` files, `100:1` bomb ratio).
11. ZIP extraction safeguards (`validate_safe_extract_path`).
12. Export download authorization (`verify_project_access` + `AuditLog` tracking).
13. Sensitive information redaction in logs (`RedactingFormatter` for DB/Redis URIs + `Bearer` tokens).
14. Sliding-window rate limiting (`SlidingWindowRateLimiter` on expensive and default endpoints).
15. Tamper-evident `AuditLog` SHA-256 hash-chain integrity.

---

## 2. Security Vulnerabilities Discovered & Remediated in Wave 7

| Finding ID | Severity | Component | Vulnerability Description | Remediation Implemented | Verification Test | Status |
| :--- | :---: | :--- | :--- | :--- | :--- | :---: |
| **SEC-W7-001** | **HIGH (`P1`)** | Wave 2 / Wave 3 / Wave 4 Snapshot Endpoints ([`technical_intelligence.py`](file:///C:/LegacyIQ/backend/app/api/v1/endpoints/technical_intelligence.py), [`requirements_intelligence.py`](file:///C:/LegacyIQ/backend/app/api/v1/endpoints/requirements_intelligence.py), [`testing_modernization.py`](file:///C:/LegacyIQ/backend/app/api/v1/endpoints/testing_modernization.py)) | While Wave 1 (`/repositories`, `/code/*`, `/search/hybrid`) and Wave 5 (`/intelligence-dashboard`, `/qa/*`, `/reports/*`, `/exports/*`) enforced `verify_project_access`, the Wave 2, Wave 3, and Wave 4 `/snapshots/{snapshot_id}/*` endpoints only checked `get_tenant_context`. An authenticated user in Tenant A who was **not** a member of Project A could query or trigger re-analysis on Project A's snapshots if they knew `snapshot_id`. | Added `_verify_snapshot_project_access` in [`technical_intelligence.py`](file:///C:/LegacyIQ/backend/app/api/v1/endpoints/technical_intelligence.py) and wired it into all 19 Wave 2, Wave 3, and Wave 4 `/snapshots/{snapshot_id}/*` endpoints (`project:read` for GETs, `analysis:run` for POST analysis triggers). | `test_wave7_cross_project_rbac_and_viewer_mutation_denial_integration` ([`test_wave7_production_hardening.py`](file:///C:/LegacyIQ/backend/tests/test_wave7_production_hardening.py)) | **FIXED & VERIFIED** |
| **SEC-W7-002** | **MEDIUM (`P1`)** | Human Review & Conflict Resolution Endpoints (`POST /findings/{id}/review`, `POST /business-rules/{id}/review`, `POST /requirements/{id}/review`, `POST /conflicts/{id}/resolve`, `POST /modernization-recommendations/{id}/review`, `POST /test-cases/{id}/review`) | Human review mutation endpoints verified tenant membership (`get_tenant_context`) but did not verify that the caller held `finding:review` / `project:write` permission (or `ORG_OWNER` / `ARCHITECT` / `REVIEWER` role), allowing a read-only `VIEWER` user to approve or reject findings and business rules. | Added explicit RBAC permission checks (`ctx.has_permission("finding:review") or ctx.has_permission("project:write")`) on all 6 human review and conflict resolution endpoints, returning `403 Forbidden` for `VIEWER` users. | `test_wave7_cross_project_rbac_and_viewer_mutation_denial_integration` ([`test_wave7_production_hardening.py`](file:///C:/LegacyIQ/backend/tests/test_wave7_production_hardening.py)) | **FIXED & VERIFIED** |
| **SEC-W7-003** | **MEDIUM (`P2`)** | Authentication & Task Signing ([`security.py`](file:///C:/LegacyIQ/backend/app/core/security.py), [`deps.py`](file:///C:/LegacyIQ/backend/app/api/deps.py), [`organizations.py`](file:///C:/LegacyIQ/backend/app/api/v1/endpoints/organizations.py)) | API authentication relied solely on unsigned `X-Tenant-Id` and `X-User-Id` headers, and `TaskEnvelope` HMAC signing used a static string derived from `APP_NAME:APP_ENV` rather than a dedicated secret key. | Added `APP_SECRET_KEY` (enforced `>= 32` chars in production), keyed `TaskEnvelope` HMAC-SHA256 with `APP_SECRET_KEY`, implemented HS256 JWT token issuance (`create_access_token`, `POST /api/v1/auth/token`, and `access_token` on `/api/v1/bootstrap`) and validation (`verify_access_token` checking `exp`, `iat`, `sub`, `tid`, `iss`), and updated `get_tenant_context` to validate `Authorization: Bearer <token>` and reject header/token mismatches (`403 Forbidden`). | `test_wave7_jwt_token_signing_expiration_and_tampering` & `test_wave7_cross_project_rbac_and_viewer_mutation_denial_integration` | **FIXED & VERIFIED** |
| **SEC-W7-004** | **MEDIUM (`P2`)** | Production Startup & Error Handling ([`config.py`](file:///C:/LegacyIQ/backend/app/core/config.py), [`main.py`](file:///C:/LegacyIQ/backend/app/main.py)) | Backend lacked a startup fail-fast guard if started with `APP_ENV=production` and unsafe defaults (`APP_DEBUG=true`, placeholder `DATABASE_URL`/`REDIS_URL`, default `APP_SECRET_KEY`, or wildcard CORS/Hosts), and lacked a global exception handler and `TrustedHostMiddleware`. | Implemented `Settings.validate_production_readiness()` and `assert_production_ready()` in [`config.py`](file:///C:/LegacyIQ/backend/app/core/config.py), added `TrustedHostMiddleware`, HTTP security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`), and `sanitized_unhandled_exception_handler` in [`main.py`](file:///C:/LegacyIQ/backend/app/main.py). | `test_wave7_production_config_fail_fast_validation` ([`test_wave7_production_hardening.py`](file:///C:/LegacyIQ/backend/tests/test_wave7_production_hardening.py)) | **FIXED & VERIFIED** |
| **SEC-W7-005** | **LOW (`P2`)** | Rate Limiting & Log Redaction ([`security.py`](file:///C:/LegacyIQ/backend/app/core/security.py), [`logging.py`](file:///C:/LegacyIQ/backend/app/core/logging.py)) | Expensive endpoints (`/upload-zip`, `/analyze*`, `/qa/*`, `/reports/generate`, `/exports`) lacked rate limiting, and `RedactingFormatter` redacted DB/Redis passwords but not `Bearer <jwt>` tokens in log messages. | Implemented `SlidingWindowRateLimiter` middleware (`429 Too Many Requests` with `Retry-After: 60` and `X-RateLimit-Remaining`) and extended `redact_sensitive_text` in [`logging.py`](file:///C:/LegacyIQ/backend/app/core/logging.py) to redact `Bearer` tokens. | `test_wave7_rate_limiter_and_log_secret_redaction` ([`test_wave7_production_hardening.py`](file:///C:/LegacyIQ/backend/tests/test_wave7_production_hardening.py)) | **FIXED & VERIFIED** |

---

## 3. Control-by-Control Verification Matrix

| Security Control | Implementation Reference | Status | Evidence |
| :--- | :--- | :---: | :--- |
| **JWT Token Signing & Expiration (`HS256`)** | [`create_access_token`](file:///C:/LegacyIQ/backend/app/core/security.py), [`verify_access_token`](file:///C:/LegacyIQ/backend/app/core/security.py) | `VERIFIED` | `test_wave7_jwt_token_signing_expiration_and_tampering` |
| **Bearer Token vs. Header Anti-Spoofing Guard** | [`get_tenant_context`](file:///C:/LegacyIQ/backend/app/api/deps.py) | `VERIFIED` | `test_wave7_cross_project_rbac_and_viewer_mutation_denial_integration` |
| **PostgreSQL `FORCE ROW LEVEL SECURITY` (`72/72` Tables)** | [`activate_tenant_rls`](file:///C:/LegacyIQ/backend/app/db/session.py) | `VERIFIED` | `test_postgres_76_tables_and_72_rls_policies_active` |
| **Project-Level RBAC Across All Waves (`1–5`)** | [`verify_project_access`](file:///C:/LegacyIQ/backend/app/core/security.py), [`_verify_snapshot_project_access`](file:///C:/LegacyIQ/backend/app/api/v1/endpoints/technical_intelligence.py) | `VERIFIED` | `test_wave7_cross_project_rbac_and_viewer_mutation_denial_integration` |
| **Role-Based Review Mutation Guard (`VIEWER` Denied)** | Wave 2/3/4 `/review` & `/resolve` endpoints | `VERIFIED` | `test_wave7_cross_project_rbac_and_viewer_mutation_denial_integration` |
| **ZIP Slip & Archive Bomb Protection** | [`IngestionService.validate_and_inspect_zip`](file:///C:/LegacyIQ/backend/app/services/ingestion_service.py) | `VERIFIED` | `test_zip_ingestion_security_guards` |
| **Tenant-Isolated Content-Addressed Storage Vault** | [`TenantObjectStorage`](file:///C:/LegacyIQ/backend/app/integrations/storage.py) | `VERIFIED` | `test_tenant_object_storage_isolation` |
| **Sliding-Window API Rate Limiting (`429`)** | [`SlidingWindowRateLimiter`](file:///C:/LegacyIQ/backend/app/core/security.py), [`main.py`](file:///C:/LegacyIQ/backend/app/main.py) | `VERIFIED` | `test_wave7_rate_limiter_and_log_secret_redaction` |
| **Log Redaction (DB/Redis Passwords + Bearer JWTs)** | [`redact_sensitive_text`](file:///C:/LegacyIQ/backend/app/core/logging.py) | `VERIFIED` | `test_wave7_rate_limiter_and_log_secret_redaction` |
| **Tamper-Evident `AuditLog` SHA-256 Hash Chain** | [`ReportingQaExportService.record_audit_log`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) | `VERIFIED` | `test_wave5_end_to_end_dashboard_qa_reports_versioning_exports_audit_and_rls` |
| **External OIDC/SAML SSO, Refresh Token Rotation & Password Reset** | [`User.auth_provider`](file:///C:/LegacyIQ/backend/app/models/identity.py) schema columns ready | `NOT_IMPLEMENTED` | Disclosed in [`wave7-known-limitations.md`](file:///C:/LegacyIQ/docs/implementation/wave7-known-limitations.md) |

