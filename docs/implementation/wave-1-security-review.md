# LegacyIQ — Wave 1 Security Review

**Date**: 2026-11-01  
**Scope**: Multi-Tenant Isolation, PostgreSQL RLS, Project RBAC, Untrusted Archive Ingestion, Storage Vault, and Secret Hygiene

---

## 1. Non-Bypassable PostgreSQL Row-Level Security (RLS)

### Architectural Challenge & Solution
The local infrastructure container `legacyiq-postgres` connects with user `legacyiq_admin`, which holds `SUPERUSER` and `BYPASSRLS` privileges. In PostgreSQL, superusers bypass RLS policies even when `FORCE ROW LEVEL SECURITY` is enabled on tables.

To guarantee true database-enforced tenant isolation without altering the external Docker container configuration:
1. Migration `0001_wave1_identity_and_projects.py` creates a dedicated application role:
   ```sql
   CREATE ROLE legacyiq_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
   GRANT legacyiq_app TO legacyiq_admin;
   ```
2. Migration `0003_wave1_retrieval_and_rls_security.py` enables and forces RLS (`ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`) on all **29** tenant/hybrid-scoped tables and binds strict `FOR ALL TO legacyiq_app USING (...) WITH CHECK (...)` policies.
3. Every tenant-scoped database transaction in `backend/app/db/session.py` (`activate_tenant_rls` and `tenant_db_session`) executes:
   ```sql
   SET LOCAL ROLE legacyiq_app;
   SELECT set_config('app.current_tenant_id', :tid, true);
   ```
   Because both commands are transaction-local (`SET LOCAL` and `is_local = true`), they automatically reset on `COMMIT` or `ROLLBACK`, preventing connection-pool tenant bleed.

---

## 2. Composite Tenant Keys & Cross-Tenant Role Guards

- All 27 `TENANT_DIRECT` tables use composite primary keys `(tenant_id, id)` and composite foreign keys `(tenant_id, parent_id)` so cross-tenant relationships are structurally impossible at the relational constraint layer.
- Because `roles` is a `HYBRID_CATALOG` table (`tenant_id IS NULL` for system roles, `tenant_id = <UUID>` for custom tenant roles), PostgreSQL trigger `enforce_role_tenant_match()` is attached to both `organization_memberships` and `project_memberships` to block binding a custom role from Tenant A to a membership in Tenant B.

---

## 3. Application & Project-Level RBAC

- `verify_and_activate_tenant_context` (`backend/app/core/security.py`) never trusts a client-supplied `X-Tenant-Id` header unless `X-User-Id` holds an `ACTIVE` row in `organization_memberships` for that `tenant_id` and the `Organization` status is `ACTIVE`.
- `verify_project_access` enforces project-level authorization via `project_memberships` (with implicit org-wide access reserved strictly for `ORG_OWNER`).

---

## 4. Untrusted ZIP Archive & Static Analysis Safety

- **Zero Code Execution**: Uploaded source archives are never imported, evaluated, or executed. Python files are parsed with `ast.parse`, and Java/JS/TS/PHP files are parsed with deterministic lexical/structural scanners.
- **Zip-Slip Traversal Defense**: Both `PurePosixPath` inspection (rejecting `..`, leading `/`, and drive letters `:`) and `validate_safe_extract_path` (`Path.resolve().is_relative_to(...)`) are enforced before reading any archive entry.
- **Symlink Rejection**: Archive entries with UNIX symlink mode bits (`0o120000`) are rejected before extraction.
- **Resource Exhaustion Guards**: Enforces maximum compressed archive size (`50 MB`), maximum total uncompressed size (`150 MB`), maximum single-file size (`10 MB`), maximum file count (`2,500`), and compression-ratio bomb detection (`> 100x`).
- **Tenant-Isolated Blob Vault**: `TenantObjectStorage` partitions content-addressed blobs under `backend/storage_vault/<tenant_id>/blobs/<sha256[:2]>/<sha256>`, preventing cross-tenant deduplication side channels (D3-04).

