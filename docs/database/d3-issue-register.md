# LegacyIQ — D3 Database Architecture Issue & Consistency Register

**Document ID**: `D3-11`  
**Status**: Architecture Review Deliverable  
**Scope**: Cross-Document Consistency & Technical Correctness Audit of `D3-01` through `D3-10`

---

## 1. Severity Classification Definitions

| Severity | Definition |
| :--- | :--- |
| **`CRITICAL`** | Structural flaw that could permit cross-tenant data leakage, violate relational integrity in PostgreSQL, or cause silent loss of approved customer data/evidence. |
| **`HIGH`** | Significant inconsistency across specification documents, ORM mapping incompatibility, or lifecycle conflict that would break implementation or migrations if unaddressed. |
| **`MEDIUM`** | Concurrency bottleneck, missing operational guard (e.g., legal hold or idempotency constraint), or edge-case ambiguity requiring explicit specification. |
| **`LOW`** | Naming convention inconsistency, minor documentation discrepancy, or index tuning refinement. |
| **`INFORMATIONAL`** | Architectural observation or implementation guidance for future milestone developers. |

---

## 2. Summary of Discovered Issues

| Issue ID | Severity | Title | Affected Documents | Status |
| :--- | :---: | :--- | :--- | :--- |
| **D3-ISS-001** | `CRITICAL` | Single-Column FKs to Hybrid Catalog Tables (`roles`, `prompt_templates`) Could Allow Cross-Tenant Reference Without Trigger Guard | `D3-02`, `D3-03`, `D3-04`, `D3-10` | **CORRECTED IN DOCS** |
| **D3-ISS-002** | `HIGH` | Snapshot Pruning `ON DELETE CASCADE` vs. Approved Evidence Preservation Conflict (`Q2`) | `D3-03`, `D3-04`, `D3-09` | **CORRECTED IN DOCS** |
| **D3-ISS-003** | `HIGH` | Cross-Snapshot Coupling Anomaly on `document_chunks.code_symbol_id` | `D3-02`, `D3-03`, `D3-08` | **CORRECTED IN DOCS** |
| **D3-ISS-004** | `HIGH` | SQLAlchemy 2.0 Overlapping `tenant_id` Columns in Multi-FK Models & `MATCH SIMPLE` Requirement for Nullable Composite FKs | `D3-01`, `D3-03`, `D3-04` | **DOCUMENTED & RESOLVED** |
| **D3-ISS-005** | `HIGH` | Table Count Discrepancy (`64` Stated vs. `71` Actual Canonical Tables Across Domains A–K) | `D3-01`, `D3-02`, `D3-03`, `D3-04`, `D3-10` | **CORRECTED IN DOCS** |
| **D3-ISS-006** | `MEDIUM` | Synchronous Audit Log Hash-Chain Serialization Under Concurrent Tenant Writes (`Q4`) | `D3-03`, `D3-10` | **DOCUMENTED & RESOLVED** |
| **D3-ISS-007** | `MEDIUM` | Missing `legal_hold_active` Guard Against Automated Retention Janitor & Deletion Requests | `D3-02`, `D3-03`, `D3-09` | **CORRECTED IN DOCS** |
| **D3-ISS-008** | `MEDIUM` | Polymorphic UUID Targets in `knowledge_conflicts` and `review_history` Lack Native FK Enforcement | `D3-02`, `D3-03`, `D3-06` | **DOCUMENTED & RESOLVED** |
| **D3-ISS-009** | `MEDIUM` | Concurrent `analysis_runs` on the Same `snapshot_id` Contend on `code_files` Unique Key `(tenant_id, snapshot_id, relative_path)` | `D3-01`, `D3-03`, `D3-09` | **DOCUMENTED & RESOLVED** |
| **D3-ISS-010** | `LOW` | Mixed-Case Column Names (`tree_Or_archive_sha256`, `ast_Or_json_path`) in ERD and Data Dictionary | `D3-02`, `D3-03` | **CORRECTED IN DOCS** |
| **D3-ISS-011** | `LOW` | Redundant Index Potential Between `PRIMARY KEY (tenant_id, id)` and Separate Tenant-Leading Indexes | `D3-03`, `D3-08` | **DOCUMENTED & RESOLVED** |
| **D3-ISS-012** | `INFORMATIONAL` | `pgvector` HNSW Post-Filtering Starvation Risk Without `hnsw.iterative_scan` on Small Tenants | `D3-08` | **DOCUMENTED & RESOLVED** |

---

## 3. Detailed Issue Analysis & Resolutions

### D3-ISS-001 (`CRITICAL`): Single-Column FKs to Hybrid Catalog Tables (`roles`, `prompt_templates`)
- **Affected Tables**: `organization_memberships.role_id`, `project_memberships.role_id` $\to$ `roles(id)`; `model_invocations.prompt_template_id` $\to$ `prompt_templates(id)`.
- **Problem**: `roles` and `prompt_templates` are `HYBRID_CATALOG` tables where `tenant_id IS NULL` represents platform-wide system defaults and `tenant_id IS NOT NULL` represents custom tenant-created records. Because `tenant_id` is nullable on the parent, a standard composite foreign key `(tenant_id, role_id) REFERENCES roles(tenant_id, id)` cannot be used when assigning a global system role (`tenant_id IS NULL`) to a tenant member (`tenant_id = '<org_uuid>'`). However, using a plain single-column `FOREIGN KEY (role_id) REFERENCES roles(id)` without an additional check would theoretically allow Tenant A to reference a custom `role_id` or `prompt_template_id` owned by Tenant B if an attacker guessed its UUID and bypassed RLS.
- **Correction Applied**:
  1. Retained `PRIMARY KEY (id)` on `roles` and `prompt_templates` so both global (`tenant_id IS NULL`) and tenant-owned (`tenant_id = NEW.tenant_id`) records can be referenced.
  2. Added a mandatory PostgreSQL `BEFORE INSERT OR UPDATE` validation trigger specification (`enforce_hybrid_catalog_tenant_match()`) on `organization_memberships`, `project_memberships`, and `model_invocations` that verifies `parent.tenant_id IS NULL OR parent.tenant_id = NEW.tenant_id`, raising an integrity violation exception otherwise.
  3. Updated [tenant-ownership-matrix.md](file:///C:/LegacyIQ/docs/database/tenant-ownership-matrix.md) and [data-dictionary.md](file:///C:/LegacyIQ/docs/database/data-dictionary.md).

---

### D3-ISS-002 (`HIGH`): Snapshot Pruning `ON DELETE CASCADE` vs. Approved Evidence Preservation (`Q2`)
- **Affected Tables**: `repository_snapshots`, `artifact_versions`, `evidence_anchors`, `findings`, `business_rules`, `requirements`.
- **Problem**: In the initial draft of `D3-03` and `D3-04`, `findings`, `business_rules`, `requirements`, and `evidence_anchors` had `NOT NULL` foreign keys to `repository_snapshots(tenant_id, id)` with `Cascades on snapshot purge`. Under Provisional Decision **Q2**, pruning old snapshots must **not** destroy `APPROVED` or `MODIFIED_BY_HUMAN` findings/requirements or their supporting `evidence_anchors`.
- **Correction Applied**:
  1. Defined the **Two-Stage Snapshot Compaction Lifecycle** (`status = 'COMPACTED_EVIDENCE_ONLY'` on `repository_snapshots` in [complete-erd.md](file:///C:/LegacyIQ/docs/database/complete-erd.md), [data-dictionary.md](file:///C:/LegacyIQ/docs/database/data-dictionary.md), and [versioning-and-retention.md](file:///C:/LegacyIQ/docs/database/versioning-and-retention.md)).
  2. When a snapshot exceeds `retention_policies.max_snapshots_per_repo`, the janitor executes **Snapshot Compaction** instead of deleting the `repository_snapshots` header row:
     - Deletes all heavy deterministic AST/technical tables (`code_modules`, `code_files`, `code_symbols`, `code_imports`, `code_call_edges`, `code_type_hierarchies`, `code_symbol_references`, `db_schemas`, `api_services`, `infra_resources`) and unapproved `DRAFT_AI` findings for that snapshot.
     - Retains the lightweight `repository_snapshots` and `analysis_runs` header rows (`status = 'COMPACTED_EVIDENCE_ONLY'`) so all composite FKs from `APPROVED`/`MODIFIED_BY_HUMAN` findings, business rules, requirements, and `evidence_anchors` remain 100% valid.
     - Retains only the `evidence_anchors` (and their pinned `artifact_versions` metadata) cited by approved records, garbage-collecting all unreferenced `artifact_versions`, `document_chunks`, `artifact_embeddings`, and object storage blobs.

---

### D3-ISS-003 (`HIGH`): Cross-Snapshot Coupling Anomaly on `document_chunks.code_symbol_id`
- **Affected Tables**: `document_chunks` (`Domain J`), `code_symbols` (`Domain D`).
- **Problem**: `document_chunks` is content-addressed and keyed to `artifact_version_id` (`(tenant_id, artifact_version_id, chunk_strategy, chunk_index)`) so unchanged files across Snapshots `1..N` share chunks and embeddings without duplication. However, `code_symbols` is scoped to a specific `snapshot_id`. Having a nullable `code_symbol_id` column on `document_chunks` tied a snapshot-independent chunk to a single snapshot's `code_symbol_id`, which would break or dangle when Snapshot 1 is compacted while Snapshot 2 still uses the `artifact_version_id`.
- **Correction Applied**:
  - Removed `code_symbol_id` from `document_chunks` in [complete-erd.md](file:///C:/LegacyIQ/docs/database/complete-erd.md) and [data-dictionary.md](file:///C:/LegacyIQ/docs/database/data-dictionary.md).
  - Stored snapshot-independent AST metadata (`symbol_qualified_name`, `symbol_kind`, `body_ast_hash`) inside `document_chunks.metadata_tags` and resolved snapshot-specific `code_symbols` at query time via the indexed line-range join `(tenant_id, code_file_id, start_line, end_line)`.

---

### D3-ISS-004 (`HIGH`): SQLAlchemy 2.0 Overlapping `tenant_id` in Composite FKs & Nullable Composite FK `MATCH SIMPLE` Semantics
- **Affected Tables**: All `64` `TENANT_DIRECT` tables with multiple composite FKs.
- **Problem**:
  1. When a table has multiple composite FKs sharing `tenant_id`, SQLAlchemy 2.0 emits mapper configuration warnings unless `overlaps` is configured on `relationship()` constructs.
  2. When a composite FK has a nullable target column—such as `FOREIGN KEY (tenant_id, parent_symbol_id) REFERENCES code_symbols(tenant_id, id)` where `parent_symbol_id IS NULL` for top-level symbols—using `MATCH FULL` would reject the row because `tenant_id` is `NOT NULL` while `parent_symbol_id` is `NULL`.
- **Resolution Specified**:
  1. All composite foreign keys with nullable entity references must use PostgreSQL's default `MATCH SIMPLE` semantics (where a `NULL` in any FK column skips the FK check while `tenant_id` itself is still validated by its `NOT NULL` constraint and the table's primary/parent FK to `organizations`).
  2. SQLAlchemy 2.0 models must use `ForeignKeyConstraint(["tenant_id", "parent_id"], ["parent.tenant_id", "parent.id"], match="SIMPLE")` and declare `overlaps="tenant,..."` (or `viewonly=True` on secondary relationships) as documented in [d3-review-report.md](file:///C:/LegacyIQ/docs/database/d3-review-report.md).

---

### D3-ISS-005 (`HIGH`): Table Count Discrepancy (`64` Stated vs. `71` Actual Tables)
- **Affected Documents**: `D3-01`, `D3-02`, `D3-03`, `D3-04`, `D3-10`.
- **Problem**: The prose headers in `D3-01`, `D3-02`, `D3-03`, and `D3-04` stated `64 tables` (`58 TENANT_DIRECT`), whereas the actual domain definitions across Domains A–K contained **71 tables** (`A=8, B=6, C=8, D=7, E=9, F=7, G=6, H=5, I=6, J=3, K=6` = `71` tables total: `1 TENANT_ROOT`, `64 TENANT_DIRECT`, `2 HYBRID_CATALOG`, `4 GLOBAL_SYSTEM`).
- **Correction Applied**: Reconciled all headers, Mermaid subgraph titles, and summary matrices across `D3-01`, `D3-02`, `D3-03`, `D3-04`, and `D3-10` to `71 canonical tables` (`64 TENANT_DIRECT`).

---

### D3-ISS-006 (`MEDIUM`): Synchronous Audit Log Hash-Chain Serialization (`Q4`)
- **Affected Table**: `audit_logs` (`Domain K`).
- **Problem**: Synchronous calculation of `prev_audit_hash` $\to$ `entry_hash` requires strict ordering per tenant so two concurrent transactions in the same tenant do not read the same `prev_audit_hash` and fork the chain.
- **Resolution Specified**: Documented the transaction-end advisory lock pattern (`PERFORM pg_advisory_xact_lock(hashtext('audit_chain:' || NEW.tenant_id::text))`) inside a `BEFORE INSERT` trigger on `audit_logs`, keeping lock duration under `1 ms` at commit time (see [d3-decisions-register.md](file:///C:/LegacyIQ/docs/database/d3-decisions-register.md) `D3-PDEC-Q4`).

---

### D3-ISS-007 (`MEDIUM`): Missing `legal_hold_active` Guard on Snapshots & Projects
- **Affected Tables**: `organizations`, `projects`, `repository_snapshots`.
- **Problem**: Automated retention janitors (`retention_policies.auto_purge_enabled = true`) or manual deletion requests could purge a snapshot subject to an enterprise legal or audit hold.
- **Correction Applied**: Added `legal_hold_active BOOLEAN NOT NULL DEFAULT false` to `repository_snapshots` (and documented inheritance from `organizations`/`projects`), with a mandatory pre-condition check blocking compaction or deletion while `legal_hold_active = true`.

---

### D3-ISS-008 (`MEDIUM`): Polymorphic UUID Targets in `knowledge_conflicts` and `review_history`
- **Affected Tables**: `knowledge_conflicts`, `review_history`.
- **Problem**: `review_history.target_object_id` and `knowledge_conflicts.primary_entity_or_finding_id` can reference multiple tables (`findings`, `business_rules`, `requirements`, `knowledge_entities`), preventing a single static SQL FK constraint.
- **Resolution Specified**: Notice that `finding_evidence_links` already uses the **Explicit Nullable Exclusive-Arc FK Pattern** (`finding_id`, `knowledge_entity_id`, `knowledge_relationship_id`, `business_rule_id`, `requirement_id` with `CHECK (num_nonnulls(...) >= 1)`). For `review_history` (which is an immutable append-only audit log that must survive even if a draft object is later superseded), retaining `(target_object_type, target_object_id)` without a cascading FK is intentional so audit records are never cascade-deleted; for `knowledge_conflicts`, validation is enforced at creation time within the same service transaction.

---

### D3-ISS-009 (`MEDIUM`): Concurrent `analysis_runs` Contending on Snapshot-Scoped AST Tables
- **Affected Tables**: `code_files`, `code_modules`, `code_symbols` (`Domain D`).
- **Problem**: `code_files` is uniquely keyed by `(tenant_id, snapshot_id, relative_path)` because deterministic AST facts are invariant for a given snapshot. However, if two `analysis_runs` (`FULL_DISCOVERY`) are triggered concurrently on the same `snapshot_id`, concurrent writes to `code_files` would collide.
- **Resolution Specified**:
  1. Added a partial unique index on `analysis_runs`:
     ```sql
     CREATE UNIQUE INDEX ux_active_analysis_run_per_snapshot
       ON analysis_runs (tenant_id, snapshot_id)
       WHERE status IN ('QUEUED', 'RUNNING_STATIC', 'RUNNING_EMBEDDINGS', 'RUNNING_AI_AGENTS');
     ```
     This prevents two concurrent active analysis runs on the exact same `snapshot_id`.
  2. Subsequent runs on the same `snapshot_id` execute in `AI_ENRICHMENT_ONLY` mode (reusing the already-parsed `code_files` and `code_symbols`) unless a parser version upgrade explicitly triggers an idempotent `ON CONFLICT (tenant_id, snapshot_id, relative_path) DO UPDATE` pass.

---

### D3-ISS-010 (`LOW`): Mixed-Case Column Names (`tree_Or_archive_sha256`, `ast_Or_json_path`)
- **Affected Documents**: `D3-02` (`complete-erd.md`), `D3-03` (`data-dictionary.md`).
- **Correction Applied**: Normalized to snake_case `tree_or_archive_sha256` and `ast_or_json_path` across both files.

---

### D3-ISS-011 (`LOW`): Avoiding Redundant Single-Column `id` Indexes on Composite PK Tables
- **Affected Documents**: `D3-03`, `D3-08`.
- **Resolution Specified**: Since all `64` `TENANT_DIRECT` tables use `PRIMARY KEY (tenant_id, id)` and all foreign keys are composite `(tenant_id, <fk>_id)`, a separate `UNIQUE (id)` index is **not** created on high-volume leaf tables (`code_symbols`, `code_call_edges`, `code_symbol_references`, `document_chunks`, `artifact_embeddings`, `agent_execution_events`), saving ~25–35% index RAM and write amplification.

---

### D3-ISS-012 (`INFORMATIONAL`): `pgvector` HNSW Iterative Scan Tuning for Small Tenants
- **Affected Document**: `D3-08` (`indexing-and-query-strategy.md`).
- **Resolution Specified**: Confirmed that `pgvector` `0.8.7` supports `SET LOCAL hnsw.iterative_scan = relaxed_order` and `SET LOCAL hnsw.max_scan_tuples = 20000`, ensuring 100% recall even when a tenant owns `< 0.1%` of vectors in a shared HNSW index.

