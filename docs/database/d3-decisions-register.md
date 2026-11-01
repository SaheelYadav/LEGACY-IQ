# LegacyIQ — D3 Architectural & Provisional Decisions Register

**Document ID**: `D3-12`  
**Status**: Architecture Review Deliverable  

---

## 1. Finalized Baseline Architectural Decisions (`D3-DEC-001` to `D3-DEC-012`)

These 12 foundational decisions govern the LegacyIQ D3 architecture and are locked as baseline axioms:

| Decision ID | Title | Status | Architectural Enforcement |
| :--- | :--- | :---: | :--- |
| **D3-DEC-001** | Shared Multi-Tenant SaaS Infrastructure | **FINALIZED** | Shared PostgreSQL 17 tables with mandatory `tenant_id UUID NOT NULL` on all 64 `TENANT_DIRECT` tables. |
| **D3-DEC-002** | PostgreSQL 17 as System of Record | **FINALIZED** | All durable state in PostgreSQL 17; Redis 7 is strictly ephemeral cache/queue state. |
| **D3-DEC-003** | `pgvector` for Semantic Embeddings | **FINALIZED** | `pgvector` `0.8.7` (`artifact_embeddings.embedding vector(384)`) with HNSW cosine indexing. |
| **D3-DEC-004** | Relational Knowledge Graph Initially | **FINALIZED** | `knowledge_entities` and `knowledge_relationships` in PostgreSQL under ACID + RLS. |
| **D3-DEC-005** | NetworkX for Graph Projections | **FINALIZED** | Scoped in-memory `nx.MultiDiGraph` projections for Tarjan SCC, PageRank, community detection, and topological layering. |
| **D3-DEC-006** | Encrypted Tenant-Isolated Object Storage | **FINALIZED** | Content-addressed blobs under `s3://<bucket>/<tenant_id>/blobs/<sha256>` encrypted with per-tenant KMS DEK (`organizations.kms_key_id`). |
| **D3-DEC-007** | Immutable Repository Snapshots | **FINALIZED** | `repository_snapshots` (`tree_or_archive_sha256`) and `artifact_versions` (`content_sha256`) are append-only and never mutated in place. |
| **D3-DEC-008** | Versioned Analysis Runs | **FINALIZED** | Every parser and AI execution is bound to an immutable `analysis_runs` record with `pipeline_versions_manifest`. |
| **D3-DEC-009** | Hybrid Human Review | **FINALIZED** | Explicit `review_status` state machine and append-only `review_history` preserving original AI outputs alongside human edits. |
| **D3-DEC-010** | Centralized Agent Orchestration | **FINALIZED** | `agent_runs`, `agent_task_dependencies`, `prompt_templates`, `model_invocations`, and `agent_execution_events`. |
| **D3-DEC-011** | Explicit Tenant Ownership & PostgreSQL RLS | **FINALIZED** | Composite `(tenant_id, id)` PKs/FKs plus `ENABLE` & `FORCE ROW LEVEL SECURITY` bound to `app_current_tenant_id()`. |
| **D3-DEC-012** | Local-First AI Development | **FINALIZED** | Default inference via local Ollama (`qwen2.5-coder:3b`) and local embeddings (`BAAI/bge-small-en-v1.5`); cloud providers gated by `tenant_subscriptions.allow_cloud_llm_providers`. |

---

## 2. Provisional Product-Owner Decisions (`D3-PDEC-Q1` to `D3-PDEC-Q5`)

Per Product-Owner guidance, the following 5 decisions are incorporated into the D3 architecture specification and marked **`PROVISIONAL`** pending formal Architecture Review sign-off:

---

### `D3-PDEC-Q1` (`PROVISIONAL`): Fixed `vector(384)` Column with Model-Version Metadata & Future Migration Path
- **Decision Statement**:
  - `artifact_embeddings.embedding` uses the strongly-typed `vector(384)` column in PostgreSQL (`pgvector` v0.8.7), paired with `embedding_model_version_id` (`FK -> embedding_model_versions(id)`).
  - Default active model is `sentence_transformers` / `BAAI/bge-small-en-v1.5` (`vector_dimension = 384`, `distance_metric = 'COSINE'`).
- **Documented Future Migration Path (If 768- or 1536-Dim Models Are Introduced Later)**:
  1. Register the new model in `embedding_model_versions` (e.g., `vector_dimension = 768`, `is_active_default = false`).
  2. Add either a dimension-specific sibling table/partition `artifact_embeddings_768` or a nullable shadow column `embedding_768 vector(768)` with its own HNSW index (`CREATE INDEX CONCURRENTLY ... USING hnsw (embedding_768 vector_cosine_ops)`).
  3. Backfill embeddings asynchronously in background worker batches keyed by `document_chunk_id` without downtime or locking `vector(384)` queries.
  4. Flip `embedding_model_versions.is_active_default = true` once backfill completes.

---

### `D3-PDEC-Q2` (`PROVISIONAL`): Preserve Approved Evidence During Snapshot Pruning (Minimum-Necessary Compaction)
- **Decision Statement**:
  - When an older `repository_snapshot` is pruned under `retention_policies.max_snapshots_per_repo`, all evidence required by `APPROVED` and `MODIFIED_BY_HUMAN` findings, business rules, and requirements **must be preserved**, while purging unnecessary heavy source and AST data.
- **Minimum-Necessary Retention Specification (Two-Stage Snapshot Compaction)**:
  - **What Is Purged During Compaction**:
    1. All deterministic AST & technical tables for the compacted snapshot (`code_modules`, `code_files`, `code_symbols`, `code_imports`, `code_call_edges`, `code_type_hierarchies`, `code_symbol_references`, `db_schemas`, `api_services`, `infra_resources`).
    2. All unapproved (`DRAFT_AI`, `REJECTED`) findings, rules, requirements, and `knowledge_entities`/`knowledge_relationships` not linked to an approved item.
    3. All `document_chunks`, `artifact_embeddings`, and `artifact_versions` (including encrypted S3 blobs) that are **not** referenced by any remaining active snapshot or any pinned `evidence_anchor`.
  - **What Is Retained (Minimum Necessary Footprint)**:
    1. The lightweight `repository_snapshots` row (transitioned to `status = 'COMPACTED_EVIDENCE_ONLY'`) and `analysis_runs` header row (< 500 bytes each) so provenance foreign keys never dangle.
    2. All `APPROVED` and `MODIFIED_BY_HUMAN` rows in `findings`, `business_rules`, `requirements`, `modernization_recommendations`, and their `review_history`.
    3. The specific `evidence_anchors` rows linked via `finding_evidence_links` to those approved items (containing `start_line`, `end_line`, `snippet_sha256`, and the bounded `<= 2048` char `excerpt_text`), plus the `artifacts` and `artifact_versions` metadata row (`content_sha256`, `canonical_path`).

---

### `D3-PDEC-Q3` (`PROVISIONAL`): PostgreSQL RLS for Tenant Isolation + FastAPI Service-Layer Project RBAC
- **Decision Statement**:
  - PostgreSQL Row-Level Security (`RLS`) enforces **strict Organization/Tenant isolation (`tenant_id = app_current_tenant_id()`)** across all 64 `TENANT_DIRECT` tables.
  - Project-level access control (`project_memberships` and `roles`/`permissions`) is enforced in the FastAPI dependency injection and repository query layer initially.
- **Mandatory Safeguards & Verification Tests Required**:
  1. **Mandatory `ProjectAccessContext` Dependency**: Every project-, application-, or repository-scoped FastAPI endpoint and background task must require a resolved `ProjectAccessContext(tenant_id, user_id, project_id, granted_permissions)` injected by a single central security dependency before any repository method can be called.
  2. **Repository Signature Enforcement**: Repository methods for Domains B–H must accept `ctx: TenantProjectContext` and automatically append `.where(Model.tenant_id == ctx.tenant_id)` (plus `application_id` / `project_id` scoping).
  3. **Automated Negative Security Test Suite (CI Gate)**:
     - *Test Case 1 (Cross-Tenant RLS Gate)*: User in Tenant A attempts to read/write a UUID belonging to Tenant B $\to$ blocked by both PostgreSQL RLS and composite FKs.
     - *Test Case 2 (Intra-Tenant Cross-Project RBAC Gate)*: User in Tenant A who is a member of `Project_1` but **not** `Project_2` attempts to query `/api/v1/projects/{project_2_id}/...` or access an `application_id` / `snapshot_id` / `finding_id` belonging to `Project_2` $\to$ must return `HTTP 403/404`.

---

### `D3-PDEC-Q4` (`PROVISIONAL`): Synchronous Per-Tenant Tamper-Evident Audit Chaining
- **Decision Statement**:
  - `audit_logs` enforces synchronous per-tenant cryptographic hash chaining (`prev_audit_hash` $\to$ `entry_hash = sha256(tenant_id || prev_audit_hash || occurred_at || actor_type || action_code || target_resource_id || metadata_diff)`).
- **Concurrency Mechanism & Implications**:
  - **Serialization Mechanism**: A PostgreSQL `BEFORE INSERT` trigger on `audit_logs` acquires a transaction-scoped advisory lock keyed to the tenant (`PERFORM pg_advisory_xact_lock(hashtext('audit_chain:' || NEW.tenant_id::text))`), queries the latest `entry_hash` for `NEW.tenant_id` (`ORDER BY occurred_at DESC, id DESC LIMIT 1`), computes `NEW.entry_hash`, and inserts the row.
  - **Best-Practice Rule**: Application code must emit the `audit_logs` insert as the **final statement immediately before `COMMIT`** so the per-tenant advisory lock is held for `< 1 ms`.
  - **Throughput Envelope**: Supports `~250–500` concurrent audit-logged mutations per second *per individual tenant* (and scales linearly across different tenants because the lock is hashed per `tenant_id`).
  - **Documented Future Alternative**: If a single mega-tenant ever exceeds `500` audit events/second, switch to **Sub-Second Batch Merkle Checkpointing** (lock-free append into `audit_logs` + a background sealer computing a signed Merkle root every `10 seconds` into `audit_chain_checkpoints`).

---

### `D3-PDEC-Q5` (`APPROVED`): Phased, Dependency-Ordered Migration Waves
- **Decision Statement**:
  - Database schema implementation will roll out in **3 dependency-ordered Alembic migration waves** rather than a single monolithic 71-table migration (`33 + 21 + 17 = 71` canonical tables):
    - **Wave 1 (M1 — Identity, Tenancy, Ingestion, AST & Vector Foundation — 33 Tables)**:
      - Domain A (`8` tables): `organizations`, `users`, `organization_memberships`, `teams`, `team_memberships`, `roles`, `permissions`, `role_permissions`
      - Domain B (`6` tables): `workspaces`, `projects`, `project_memberships`, `applications`, `application_environments`, `analysis_scopes`
      - Domain C (`8` tables): `source_connectors`, `repositories`, `repository_branches`, `repository_commits`, `repository_snapshots`, `artifacts`, `artifact_versions`, `ingestion_jobs`
      - Domain D (`7` tables): `code_modules`, `code_files`, `code_symbols`, `code_imports`, `code_call_edges`, `code_type_hierarchies`, `code_symbol_references`
      - Domain I subset (`1` table): `analysis_runs` (required as the execution parent FK for `code_files`)
      - Domain J (`3` tables): `embedding_model_versions`, `document_chunks`, `artifact_embeddings`
      - *Subtotal*: $8 + 6 + 8 + 7 + 1 + 3 = 33$ tables.
    - **Wave 2 (M2 — Technical Intelligence, Unified Knowledge Graph, Evidence & AI Orchestration — 21 Tables)**:
      - Domain E (`9` tables), Domain F (`7` tables), remaining Domain I (`5` tables: `agent_runs`, `agent_task_dependencies`, `prompt_templates`, `model_invocations`, `agent_execution_events`).
      - *Subtotal*: $9 + 7 + 5 = 21$ tables.
    - **Wave 3 (M3+ — Business Rules, Requirements, Testing, Modernization & SaaS Governance — 17 Tables)**:
      - Domain G (`6` tables), Domain H (`5` tables), Domain K (`6` tables).
      - *Subtotal*: $6 + 5 + 6 = 17$ tables.
    - **Grand Total**: $33 + 21 + 17 = 71$ canonical tables.

---

## 3. Technical & Operational Design Resolutions (`D3-TECH-001` to `D3-TECH-006`)

| Resolution ID | Area | Technical Specification |
| :--- | :--- | :--- |
| **D3-TECH-001** | **Strict Tenant-Scoped Deduplication** | Content-addressed deduplication (`artifact_versions.content_sha256`, `document_chunks.chunk_text_sha256`, `evidence_anchors.snippet_sha256`) is strictly scoped **within a single `tenant_id`** (`UNIQUE (tenant_id, artifact_id, content_sha256)`). Cross-tenant deduplication is **prohibited** to prevent side-channel confirmation attacks ("does file SHA $X$ exist in another customer's account?") and to guarantee independent per-tenant KMS crypto-shredding. |
| **D3-TECH-002** | **Background Worker Tenant Context** | Every Redis queue job payload must carry a signed `TaskEnvelope(tenant_id, project_id, actor_user_id, trace_id, hmac_signature)`. Worker execution wrapper verifies the HMAC, opens a DB transaction, executes `SELECT set_config('app.current_tenant_id', :tenant_id, true)`, and refuses to run any task missing `tenant_id`. |
| **D3-TECH-003** | **Tenant-Aware Redis Cache Keys** | All Redis keys must follow the strict namespace pattern `lq:{env}:t:{tenant_id}:p:{project_id}:{domain}:{resource_id}`. Global un-namespaced cache keys for tenant data are forbidden. |
| **D3-TECH-004** | **Object Storage Authorization** | Clients and frontend browsers **never** receive direct S3/MinIO bucket access or long-lived presigned URLs for source blobs. All artifact reads flow through the FastAPI backend, which verifies tenant RLS + project RBAC in PostgreSQL before streaming or decrypting the blob using the tenant's KMS key. |
| **D3-TECH-005** | **Concurrent Analysis Run Guard** | A partial unique index `ux_active_analysis_run_per_snapshot ON analysis_runs(tenant_id, snapshot_id) WHERE status IN ('QUEUED', 'RUNNING_STATIC', 'RUNNING_EMBEDDINGS', 'RUNNING_AI_AGENTS')` prevents concurrent conflicting runs on the same snapshot. |
| **D3-TECH-006** | **Idempotent Job & Step Retries** | All worker writes use deterministic natural keys (`canonical_key`, `chunk_index`, `sequence_no`) with `INSERT ... ON CONFLICT DO UPDATE / DO NOTHING`, ensuring that retrying a failed `ingestion_job`, `analysis_run`, or `agent_run` is 100% idempotent and never creates duplicate entities or findings. |

