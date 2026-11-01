# LegacyIQ — Wave 6 Security Validation Report

**Phase:** Wave 6 — System Integration & End-to-End Validation (Phase E)  
**Date:** 2026-11-01  
**Database Engine:** PostgreSQL 17.11 (`pgvector 0.8.7`)  
**Status:** Verified & Enforced

---

## 1. Executive Summary

Wave 6 Phase E validated all multi-tenant security controls, Row-Level Security (RLS) policies, project-level Role-Based Access Control (RBAC), archive ingestion security guards, tenant-isolated object storage, Redis cache/task-envelope cryptography, and tamper-evident SHA-256 hash-chained audit logging across the integrated M0 + Waves 1–5 platform.

All negative security tests passed without destructive operations against existing data.

---

## 2. PostgreSQL Row-Level Security (RLS) & Tenant Ownership Verification

### 2.1 Canonical Table & RLS Coverage
- **Total Canonical Base Tables**: `76` (excluding `alembic_version`)
- **Global / Pre-Tenant Reference Tables (`4`)**:
  - `organizations` (Tenant root entity)
  - `users` (Global identity table; tenant linkage enforced via `organization_memberships`)
  - `permissions` (Global permission catalog)
  - `embedding_model_versions` (System-wide local embedding model registry)
- **Tenant-Scoped Tables with `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` (`72`)**:
  - Verified via `pg_class` query (`relrowsecurity = true AND relforcerowsecurity = true`): **`72` of `72` tables enforced**.
  - Session GUC binding: Every tenant transaction activates `SET LOCAL app.current_tenant_id = '<tenant-uuid>'` via [`activate_tenant_rls`](file:///C:/LegacyIQ/backend/app/db/session.py) and [`tenant_db_session`](file:///C:/LegacyIQ/backend/app/db/session.py).
  - Fail-closed policy expression: `NULLIF(current_setting('app.current_tenant_id', true), '')::uuid = tenant_id`.

### 2.2 Negative Cross-Tenant Isolation Proofs
Executed across Waves 1–6 integration suites ([`test_wave1_integration_db.py`](file:///C:/LegacyIQ/backend/tests/test_wave1_integration_db.py), [`test_wave2_integration_db.py`](file:///C:/LegacyIQ/backend/tests/test_wave2_integration_db.py), [`test_wave3_integration_db.py`](file:///C:/LegacyIQ/backend/tests/test_wave3_integration_db.py), [`test_wave4_integration_db.py`](file:///C:/LegacyIQ/backend/tests/test_wave4_integration_db.py), [`test_wave5_integration_db.py`](file:///C:/LegacyIQ/backend/tests/test_wave5_integration_db.py), and [`test_wave6_system_integration.py`](file:///C:/LegacyIQ/backend/tests/test_wave6_system_integration.py)):
- When queried from an authenticated `Tenant B` session (`tenant_db_session(tenant_b)`), `Tenant A` records return **`0` rows** across:
  - `repositories`, `repository_snapshots`, `artifacts`, `artifact_versions`
  - `code_files`, `code_symbols`, `document_chunks`, `artifact_embeddings`
  - `db_schemas`, `db_tables`, `api_services`, `api_endpoints`, `infra_resources`, `doc_sections`
  - `evidence_anchors`, `knowledge_entities`, `knowledge_relationships`, `findings`
  - `business_domains`, `business_processes`, `business_rules`, `requirements`, `knowledge_conflicts`
  - `test_suites`, `test_cases`, `test_coverage_links`, `technical_debt_items`, `modernization_recommendations`
  - `qa_conversations`, `qa_messages`, `intelligence_reports`, `intelligence_report_versions`, `report_exports`, `audit_logs`

---

## 3. Project-Level RBAC & Authorization Validation

- **Mechanism**: [`verify_project_access`](file:///C:/LegacyIQ/backend/app/core/security.py) verifies both active `OrganizationMembership` (`status == 'ACTIVE'`) and `ProjectMembership` role permissions (`project:read`, `project:write`, `project:admin`) before serving project-scoped intelligence, Q&A conversations, reports, or export downloads.
- **Negative Verification**:
  - An active member of `Tenant A` who is **not** assigned to `Project A` (`outsider_user_a`) is deterministically denied (`PermissionError` / `SecurityViolationError` -> HTTP `403 Forbidden`) when attempting to:
    1. View the Unified Application Intelligence Dashboard (`get_application_intelligence_dashboard`)
    2. Ask a question or read a conversation in Semantic Q&A (`ask_question`)
    3. Generate, transition, or read an Intelligence Report (`generate_report`, `get_report`)
    4. Export or download a report artifact (`export_report`, `get_export_download_payload`)

---

## 4. ZIP Ingestion & File Storage Security

### 4.1 Archive Validation Guards ([`IngestionService`](file:///C:/LegacyIQ/backend/app/services/ingestion_service.py))
- **Zip-Slip Path Traversal Prevention**: Rejects any archive entry containing `..`, leading `/` or `\`, or Windows drive prefixes (`C:`) with `ArchiveValidationError`. Verified in `test_zip_slip_path_traversal_guard`, `test_zip_ingestion_security_guards`, and `test_wave6_phases_b_c_d_e_f_complete_system_integration`.
- **Compression Bomb & Size Quotas**: Enforces maximum archive size, maximum file count, maximum per-file uncompressed size, and compression ratio ceilings before extracting bytes.
- **Zero-Execution Guarantee**: Ingested source code is parsed strictly as inert UTF-8 text / AST trees and never executed.

### 4.2 Tenant-Scoped Object Storage ([`TenantObjectStorage`](file:///C:/LegacyIQ/backend/app/integrations/storage.py))
- Content-addressed blobs are stored under physically partitioned tenant directories (`<vault_root>/<tenant_id>/<sha256[:2]>/<sha256>`).
- Even when two tenants upload byte-for-byte identical files or export reports, `Tenant B` cannot probe or read `Tenant A`'s storage namespace (`test_tenant_object_storage_isolation`).

---

## 5. Redis Cache Isolation, Signed Task Envelopes & Secret Redaction

- **Redis Tenant Cache Keys**: [`build_tenant_cache_key`](file:///C:/LegacyIQ/backend/app/core/security.py) enforces `legacyiq:t:<tenant_id>:p:<project_id>:<namespace>:<key>`, preventing cross-tenant cache collisions.
- **HMAC-SHA256 Signed Task Envelopes**: [`TaskEnvelope`](file:///C:/LegacyIQ/backend/app/core/security.py) signs `(task_id, tenant_id, project_id, actor_user_id, task_type, payload, issued_at)` with HMAC-SHA256. Any tampering with `tenant_id` or `payload` fails `.verify() == False`.
- **Credential Masking**: `mask_connection_url` masks passwords in `DATABASE_URL` and `REDIS_URL` across all logs and health responses (`test_url_masking_never_exposes_password`).

---

## 6. Tamper-Evident Audit Logging (`audit_logs`)

- Every report generation (`REPORT_GENERATED`), lifecycle review transition (`REPORT_LIFECYCLE_TRANSITION`), export generation (`EXPORT_GENERATED`), and export download (`EXPORT_DOWNLOADED`) appends an immutable row to `audit_logs`.
- Each row computes `entry_hash = SHA256(canonical_json(tenant_id, prev_audit_hash, actor_user_id, action_code, target_resource_type, target_resource_id, metadata_diff, occurred_at))`, chaining directly to the preceding tenant entry's `entry_hash` (`prev_audit_hash`).

