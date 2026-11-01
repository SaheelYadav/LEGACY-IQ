# LegacyIQ — Tenant Ownership & Isolation Matrix (Design Phase D3)

**Document ID**: `D3-04`  
**Status**: Architecture Specification  

---

## 1. Multi-Tenant Ownership Principles

LegacyIQ operates on a shared PostgreSQL 17 cluster with **Defense-in-Depth Tenant Isolation** enforced at three simultaneous layers:

1. **DDL Composite Foreign Key Layer (Structural Prevention of Cross-Tenant Joins)**:
   - All **64 strictly tenant-owned (`TENANT_DIRECT`) tables** define `PRIMARY KEY (tenant_id, id)`.
   - Every foreign key between two tenant-owned tables includes `tenant_id` as the leading column:
     ```sql
     FOREIGN KEY (tenant_id, <parent>_id) REFERENCES <parent_table>(tenant_id, id)
     ```
   - For the 2 `HYBRID_CATALOG` tables (`roles`, `prompt_templates`) where `tenant_id` is nullable (`NULL` for system defaults), foreign keys (`role_id`, `prompt_template_id`) are guarded by a mandatory `BEFORE INSERT OR UPDATE` trigger verifying `parent.tenant_id IS NULL OR parent.tenant_id = NEW.tenant_id`.
   - This makes it **mathematically impossible** for a row owned by Tenant A (`tenant_id = 'aaaa...'`) to reference a `snapshot_id`, `code_symbol_id`, `finding_id`, `role_id`, or `evidence_anchor_id` owned by Tenant B (`tenant_id = 'bbbb...'`), even if application code has a bug or RLS is temporarily bypassed during a migration.

2. **PostgreSQL Row-Level Security (RLS) Layer**:
   - Every tenant-owned table has `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
   - Default policy restricts `SELECT`, `INSERT`, `UPDATE`, and `DELETE` to rows matching `current_setting('app.current_tenant_id', true)::uuid`.

3. **Application Repository & TenantContext Layer**:
   - Every SQLAlchemy query and service method requires an explicit `TenantContext(tenant_id=...)` bound to the transaction via `SET LOCAL app.current_tenant_id = '<uuid>'`.

---

## 2. Classification Categories

| Ownership Class | Table Count | `tenant_id` Column | RLS Policy Type | Description |
| :--- | :---: | :---: | :--- | :--- |
| **`TENANT_ROOT`** | 1 | `id` *is* tenant root | `id = app_current_tenant_id()` | `organizations` table. |
| **`TENANT_DIRECT`** | 69 | `UUID NOT NULL` (Part of PK) | `tenant_id = app_current_tenant_id()` | Strictly owned by a single organization; all intra-tenant FKs are composite `(tenant_id, ...)`. |
| **`HYBRID_CATALOG`** | 2 | `UUID NULL` | `tenant_id IS NULL OR tenant_id = app_current_tenant_id()` | `roles` and `prompt_templates` (system defaults have `tenant_id IS NULL`; tenant custom entries have `tenant_id = <org_id>`). |
| **`GLOBAL_SYSTEM`** | 4 | None | Read-only or Membership-scoped | `users` (scoped via `organization_memberships`), `permissions`, `role_permissions`, `embedding_model_versions`. |

*(Total = **76 canonical tables** across Domains A–K, with **72 RLS-forced tables**.)*

---

## 3. Complete 71-Table Tenant Ownership & Lifecycle Matrix

| # | Domain | Table Name | Ownership Class | PK Structure | Cross-Tenant FK Prevention | RLS Enforced | Deletion / Offboarding Behaviour |
| :---: | :---: | :--- | :--- | :--- | :--- | :---: | :--- |
| 1 | **A** | `organizations` | `TENANT_ROOT` | `(id)` | Root authority | **YES** | Status -> `PENDING_DELETION` -> Crypto-shred + Cascade purge |
| 2 | **A** | `users` | `GLOBAL_SYSTEM` | `(id)` | Referenced via `organization_memberships` | **YES** (Self + shared org members) | PII pseudonymized on user GDPR erasure; preserved if member of other active orgs |
| 3 | **A** | `organization_memberships` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Hard cascade on tenant purge; soft `REVOKED` on member removal |
| 4 | **A** | `teams` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Hard cascade on tenant purge |
| 5 | **A** | `team_memberships` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `teams` & `organization_memberships` | **YES** | Hard cascade on team or membership removal |
| 6 | **A** | `roles` | `HYBRID_CATALOG` | `(id)` | `FK(tenant_id) -> organizations(id)` | **YES** (Read system + CRUD own tenant) | Custom roles cascade on tenant purge; system roles retained |
| 7 | **A** | `permissions` | `GLOBAL_SYSTEM` | `(id)` | Immutable catalog | Read-Only | Retained permanently |
| 8 | **A** | `role_permissions` | `GLOBAL_SYSTEM` | `(role_id, permission_id)` | Validated via `roles.tenant_id` trigger | **YES** (Via `roles` join) | Custom role mappings cascade on `roles` delete |
| 9 | **B** | `workspaces` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Hard cascade on tenant purge |
| 10 | **B** | `projects` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, workspace_id) -> workspaces` | **YES** | Soft archive or hard purge via `deletion_requests` |
| 11 | **B** | `project_memberships` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `projects` & `organization_memberships` | **YES** | Hard cascade on project purge |
| 12 | **B** | `applications` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, project_id) -> projects` | **YES** | Hard cascade on project purge |
| 13 | **B** | `application_environments` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, application_id) -> applications` | **YES** | Hard cascade on application purge |
| 14 | **B** | `analysis_scopes` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, application_id) -> applications` | **YES** | Hard cascade on application purge |
| 15 | **C** | `source_connectors` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Secret shredded immediately on revoke/purge |
| 16 | **C** | `repositories` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications` & `source_connectors` | **YES** | Purged on repository/project deletion request |
| 17 | **C** | `repository_branches` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, repository_id) -> repositories` | **YES** | Hard cascade on repository purge |
| 18 | **C** | `repository_commits` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, repository_id) -> repositories` | **YES** | Hard cascade on repository purge |
| 19 | **C** | `repository_snapshots` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `repositories`, `branches`, `commits` | **YES** | Immutable; purged only by retention policy or deletion request |
| 20 | **C** | `artifacts` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications` & `repositories` | **YES** | Purged when parent application/repository is deleted |
| 21 | **C** | `artifact_versions` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, artifact_id) -> artifacts` | **YES** | Immutable; object storage blob shredded when unreferenced |
| 22 | **C** | `ingestion_jobs` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `repositories` & `repository_snapshots` | **YES** | Purged per retention policy (default 90d) or repo delete |
| 23 | **D** | `code_modules` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, snapshot_id) -> repository_snapshots` | **YES** | Hard cascade on snapshot purge |
| 24 | **D** | `code_files` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots`, `artifact_versions`, `modules`, `analysis_runs` | **YES** | Hard cascade on snapshot purge |
| 25 | **D** | `code_symbols` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots`, `code_files`, `code_symbols` | **YES** | Hard cascade on snapshot purge |
| 26 | **D** | `code_imports` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots` & `code_files` | **YES** | Hard cascade on snapshot purge |
| 27 | **D** | `code_call_edges` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots` & `code_symbols` | **YES** | Hard cascade on snapshot purge |
| 28 | **D** | `code_type_hierarchies` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots` & `code_symbols` | **YES** | Hard cascade on snapshot purge |
| 29 | **D** | `code_symbol_references` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots`, `code_files`, `code_symbols` | **YES** | Hard cascade on snapshot purge |
| 30 | **E** | `db_schemas` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots` & `artifact_versions` | **YES** | Hard cascade on snapshot purge |
| 31 | **E** | `db_tables` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `db_schemas` & `code_symbols` | **YES** | Hard cascade on snapshot purge |
| 32 | **E** | `db_columns` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, db_table_id) -> db_tables` | **YES** | Hard cascade on snapshot purge |
| 33 | **E** | `db_foreign_keys` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `db_tables` (source & target) | **YES** | Hard cascade on snapshot purge |
| 34 | **E** | `api_services` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, snapshot_id) -> repository_snapshots` | **YES** | Hard cascade on snapshot purge |
| 35 | **E** | `api_endpoints` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `api_services` & `code_symbols` | **YES** | Hard cascade on snapshot purge |
| 36 | **E** | `infra_resources` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `snapshots` & `artifact_versions` | **YES** | Hard cascade on snapshot purge |
| 37 | **E** | `doc_sections` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `artifact_versions` & `doc_sections` | **YES** | Hard cascade on artifact version purge |
| 38 | **E** | `runtime_observations` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `environments`, `endpoints`, `symbols` | **YES** | Rolling TTL purge (default 90d) |
| 39 | **F** | `knowledge_entities` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_runs`, `symbols`, `db_tables`, `api_endpoints` | **YES** | Retained with snapshot/analysis run; cascades on snapshot purge |
| 40 | **F** | `knowledge_relationships` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_runs`, `knowledge_entities` | **YES** | Cascades on snapshot or analysis run purge |
| 41 | **F** | `findings` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_runs`, `knowledge_entities`, `agent_runs` | **YES** | Superseded across runs; cascades on application/snapshot purge |
| 42 | **F** | `evidence_anchors` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `artifact_versions` & `repository_snapshots` | **YES** | Immutable; retained while referenced by any finding/entity/rule/req |
| 43 | **F** | `finding_evidence_links` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `evidence_anchors`, `findings`, `entities`, `relationships`, `rules`, `requirements` | **YES** | Cascades when parent claim is deleted |
| 44 | **F** | `knowledge_conflicts` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `evidence_anchors` | **YES** | Retained with application audit history |
| 45 | **F** | `review_history` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Immutable audit log; purged only on full project/tenant erasure |
| 46 | **G** | `business_domains` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, application_id) -> applications` | **YES** | Cascades on application purge |
| 47 | **G** | `business_processes` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `business_domains`, `knowledge_entities` | **YES** | Cascades on application purge |
| 48 | **G** | `business_rules` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_runs`, `domains`, `entities` | **YES** | Versioned; cascades on application/snapshot purge |
| 49 | **G** | `requirements` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_runs`, `domains`, `entities` | **YES** | Versioned; cascades on application/snapshot purge |
| 50 | **G** | `requirement_acceptance_criteria` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, requirement_id) -> requirements` | **YES** | Cascades on requirement purge |
| 51 | **G** | `requirement_traceability_links` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `requirements`, `business_rules`, `entities`, `symbols`, `test_cases` | **YES** | Cascades on requirement purge |
| 52 | **H** | `test_suites` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications` & `repository_snapshots` | **YES** | Cascades on snapshot purge |
| 53 | **H** | `test_cases` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `test_suites`, `code_symbols`, `analysis_runs` | **YES** | Cascades on test suite purge |
| 54 | **H** | `test_coverage_links` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `test_cases`, `code_symbols`, `business_rules`, `requirements` | **YES** | Cascades on test case purge |
| 55 | **H** | `technical_debt_items` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_runs`, `entities`, `findings` | **YES** | Cascades on snapshot purge |
| 56 | **H** | `modernization_recommendations` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_runs`, `technical_debt_items` | **YES** | Cascades on application/snapshot purge |
| 57 | **I** | `analysis_runs` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `applications`, `snapshots`, `analysis_scopes` | **YES** | Cascades on snapshot purge |
| 58 | **I** | `agent_runs` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `analysis_runs` & `agent_runs` | **YES** | Cascades on analysis run purge |
| 59 | **I** | `agent_task_dependencies` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `analysis_runs` & `agent_runs` | **YES** | Cascades on analysis run purge |
| 60 | **I** | `prompt_templates` | `HYBRID_CATALOG` | `(id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Immutable while referenced by `model_invocations` |
| 61 | **I** | `model_invocations` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, agent_run_id) -> agent_runs` | **YES** | Purged per `retention_policies` (`AI_INVOCATION_LOGS`) |
| 62 | **I** | `agent_execution_events` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, agent_run_id) -> agent_runs` | **YES** | Rolling TTL purge (30–90 days) |
| 63 | **J** | `embedding_model_versions` | `GLOBAL_SYSTEM` | `(id)` | Global read-only catalog | Read-Only | Retained permanently |
| 64 | **J** | `document_chunks` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, artifact_version_id) -> artifact_versions` | **YES** | Cascades on `artifact_versions` purge |
| 65* | **J** | `artifact_embeddings` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id, document_chunk_id) -> document_chunks` | **YES** | Cascades on `document_chunks` purge |
| 66 | **K** | `qa_conversations` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `projects`, `applications`, `repository_snapshots` | **YES** | Cascades on project/snapshot purge |
| 67 | **K** | `qa_messages` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FK to `qa_conversations` | **YES** | Cascades on conversation purge |
| 68 | **K** | `intelligence_reports` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `projects`, `applications`, `repository_snapshots` | **YES** | Cascades on project/snapshot purge |
| 69 | **K** | `intelligence_report_versions` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `intelligence_reports` & `repository_snapshots` | **YES** (`APPROVED` Immutable) | Cascades on report purge |
| 70 | **K** | `report_exports` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `projects`, `intelligence_reports`, `intelligence_report_versions` | **YES** | Cascades on report purge |
| 71 | **K** | `audit_logs` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** (Append-Only) | Retained per compliance policy; exported/archived on tenant offboarding |
| 72 | **K** | `approval_requests` | `TENANT_DIRECT` | `(tenant_id, id)` | Composite FKs to `organizations` & `projects` | **YES** | Retained with audit history |
| 73 | **K** | `retention_policies` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Cascades on tenant purge |
| 74 | **K** | `deletion_requests` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Tombstone certificate retained after purge |
| 75 | **K** | `tenant_subscriptions` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Retained for commercial/billing archive |
| 76 | **K** | `tenant_usage_quotas` | `TENANT_DIRECT` | `(tenant_id, id)` | `FK(tenant_id) -> organizations(id)` | **YES** | Retained for commercial/billing archive |

*(Note: Rows 1–76 list all 76 physical tables across Domains A–K: Domain A=8, B=6, C=8, D=7, E=9, F=7, G=6, H=5, I=6, J=3, K=11, totaling **76 physical tables** and **72 RLS-forced tables**.)*

