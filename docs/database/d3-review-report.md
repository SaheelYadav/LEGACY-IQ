# LegacyIQ — Design Phase D3 Comprehensive Architecture Review Report

**Document ID**: `D3-13`  
**Status**: Complete Architecture Audit & Baseline Readiness Report  
**Reviewed Corpus**: `docs/database/D3-01` through `D3-12`

---

## 1. Executive Summary & Baseline Readiness Determination

An exhaustive cross-document consistency and technical correctness review was conducted across all **10 core database specification documents** (`D3-01` through `D3-10`).

### Readiness Verdict: **READY AS PROVISIONAL BASELINE (Pending Final Product-Owner Sign-Off on `D3-PDEC-Q1`–`Q5`)**
- **12 issues** were identified during the audit (`1 CRITICAL`, `4 HIGH`, `4 MEDIUM`, `2 LOW`, `1 INFORMATIONAL`), cataloged in [d3-issue-register.md](file:///C:/LegacyIQ/docs/database/d3-issue-register.md).
- **All cross-document inconsistencies** (including the 64-vs-71 table count reconciliation, hybrid catalog FK trigger protection, `document_chunks` snapshot independence, `legal_hold_active` enforcement, and Two-Stage Snapshot Compaction for approved evidence preservation) have been **corrected directly in the D3 documentation set**.
- **All 5 Provisional Product-Owner Decisions (`Q1`–`Q5`)** have been integrated and marked `PROVISIONAL` in [d3-decisions-register.md](file:///C:/LegacyIQ/docs/database/d3-decisions-register.md) and [database-security-and-rls-design.md](file:///C:/LegacyIQ/docs/database/database-security-and-rls-design.md).

---

## 2. Documents Inspected & Cross-Document Reconciliation Matrix

| Doc ID | File | Inspected Scope | Audit Outcome |
| :---: | :--- | :--- | :--- |
| `D3-01` | [database-architecture.md](file:///C:/LegacyIQ/docs/database/database-architecture.md) | 12 decisions, 11-domain map, 2-stratum epistemology, T1–T5 transaction boundaries, scale design. | Reconciled table counts (`71` total: `E=9, G=6, I=6`); verified alignment with `D3-02`–`D3-10`. |
| `D3-02` | [complete-erd.md](file:///C:/LegacyIQ/docs/database/complete-erd.md) | 9 Mermaid ER diagrams covering all 71 tables, PKs, composite FKs, cardinalities, UKs. | Normalized `tree_or_archive_sha256`, added `legal_hold_active`, removed `code_symbol_id` from `document_chunks`. |
| `D3-03` | [data-dictionary.md](file:///C:/LegacyIQ/docs/database/data-dictionary.md) | Column-level dictionary for all 71 tables across Domains A–K. | Reconciled `71` tables (`64 TENANT_DIRECT`), normalized `ast_or_json_path`, updated `repository_snapshots` compaction status. |
| `D3-04` | [tenant-ownership-matrix.md](file:///C:/LegacyIQ/docs/database/tenant-ownership-matrix.md) | Ownership classes, composite FK rules, RLS flags, and deletion behavior across all 71 tables. | Reconciled `64 TENANT_DIRECT` count and documented hybrid catalog trigger guard (`D3-ISS-001`). |
| `D3-05` | [knowledge-model.md](file:///C:/LegacyIQ/docs/database/knowledge-model.md) | 10-step traceability chain from `Repository` to `EvidenceAnchor`. | Verified 100% FK and column alignment with `D3-02` and `D3-03`. |
| `D3-06` | [evidence-and-provenance-model.md](file:///C:/LegacyIQ/docs/database/evidence-and-provenance-model.md) | Cryptographic anchoring, citation verification gate, provenance lineage, confidence scoring, conflicts. | Verified alignment with `evidence_anchors`, `finding_evidence_links`, `knowledge_conflicts`, and `review_history`. |
| `D3-07` | [graph-relationship-catalogue.md](file:///C:/LegacyIQ/docs/database/graph-relationship-catalogue.md) | Node taxonomy, directed edge verbs, PG17 `CYCLE` recursive CTEs, NetworkX projection. | Verified index coverage against `D3-08`. |
| `D3-08` | [indexing-and-query-strategy.md](file:///C:/LegacyIQ/docs/database/indexing-and-query-strategy.md) | B-tree, covering, GIN (`tsvector`/`pg_trgm`/`jsonb_path_ops`), and `pgvector` HNSW indexes. | Verified query plans and `pgvector` `0.8.7` compatibility. |
| `D3-09` | [versioning-and-retention.md](file:///C:/LegacyIQ/docs/database/versioning-and-retention.md) | 5 versioning axes, carry-forward logic, sensitive data inventory, retention, crypto-shredding. | Integrated Two-Stage Snapshot Compaction (`COMPACTED_EVIDENCE_ONLY`) for Provisional Decision `Q2`. |
| `D3-10` | [database-security-and-rls-design.md](file:///C:/LegacyIQ/docs/database/database-security-and-rls-design.md) | Role separation (`legacyiq_app`), RLS DDL, `SET LOCAL` pooling, formal review. | Integrated Provisional Decisions `Q1`–`Q5`. |

---

## 3. Investigation of the 12 Critical Technical Questions

### Question 1: Does every tenant-owned foreign key correctly include `tenant_id`?
- **Finding**:
  - Across all **64 `TENANT_DIRECT` tables**, every foreign key referencing another `TENANT_DIRECT` table is a composite foreign key `(tenant_id, <target>_id) REFERENCES <target_table>(tenant_id, id)`.
  - **Edge Case Discovered & Resolved (`D3-ISS-001`)**: Three foreign keys on `TENANT_DIRECT` tables reference `HYBRID_CATALOG` tables (`organization_memberships.role_id -> roles.id`, `project_memberships.role_id -> roles.id`, and `model_invocations.prompt_template_id -> prompt_templates.id`) where `tenant_id` is `NULL` for built-in system entries and `NOT NULL` for custom tenant entries. Furthermore, five foreign keys reference `GLOBAL_SYSTEM` tables (`users.id` on memberships/jobs/reviews/audits, and `embedding_model_versions.id` on `artifact_embeddings`).
  - **Resolution**:
    1. References to `users(id)` and `embedding_model_versions(id)` intentionally omit `tenant_id` because those tables are global registries; user membership within the tenant is enforced via `organization_memberships (tenant_id, user_id)`.
    2. References to `roles(id)` and `prompt_templates(id)` are guarded by a mandatory `BEFORE INSERT OR UPDATE` trigger verifying `parent.tenant_id IS NULL OR parent.tenant_id = NEW.tenant_id`, closing the cross-tenant custom role/prompt reference vector.

---

### Question 2: Are composite primary keys compatible with all proposed foreign keys and SQLAlchemy ORM relationships?
- **Finding (`D3-ISS-004`)**:
  - **PostgreSQL DDL Compatibility**: 100% compatible, provided nullable composite foreign keys (e.g., `code_files.module_id NULL` in `FOREIGN KEY (tenant_id, module_id) REFERENCES code_modules(tenant_id, id)`) use PostgreSQL's default **`MATCH SIMPLE`** behavior. Under `MATCH SIMPLE`, if `module_id IS NULL`, PostgreSQL skips the foreign key check while `tenant_id` is still guaranteed valid by `NOT NULL` and the non-nullable parent FK `(tenant_id, snapshot_id)`. (`MATCH FULL` must **never** be used on nullable composite FKs.)
  - **SQLAlchemy 2.0 ORM Compatibility**: When a model has multiple `ForeignKeyConstraint` definitions that all include `tenant_id` as their first column, SQLAlchemy 2.0's mapper detects that multiple `relationship()` attributes write to the same `tenant_id` column and emits `SAWarning` unless configured properly.
  - **Mandatory SQLAlchemy 2.0 Pattern**:
    ```python
    class CodeFile(Base):
        __tablename__ = "code_files"
        __table_args__ = (
             PrimaryKeyConstraint("tenant_id", "id"),
            ForeignKeyConstraint(
                ["tenant_id", "snapshot_id"],
                ["repository_snapshots.tenant_id", "repository_snapshots.id"],
                ondelete="CASCADE",
            ),
            ForeignKeyConstraint(
                ["tenant_id", "artifact_version_id"],
                ["artifact_versions.tenant_id", "artifact_versions.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["tenant_id", "module_id"],
                ["code_modules.tenant_id", "code_modules.id"],
                match="SIMPLE",
                ondelete="SET NULL",
            ),
        )
        # Declare overlaps="snapshot,..." on sibling relationships sharing tenant_id
        snapshot: Mapped["RepositorySnapshot"] = relationship(
            foreign_keys="[CodeFile.tenant_id, CodeFile.snapshot_id]",
            overlaps="artifact_version,module",
        )
    ```

---

### Question 3: Does content-addressed deduplication preserve strict tenant isolation?
- **Finding (`D3-TECH-001`)**:
  - **Yes.** Content-addressed deduplication in `artifact_versions` (`UNIQUE (tenant_id, artifact_id, content_sha256)`), `document_chunks` (`UNIQUE (tenant_id, artifact_version_id, chunk_strategy, chunk_index)`), and `evidence_anchors` (`UNIQUE (tenant_id, artifact_version_id, ..., snippet_sha256)`) is **strictly scoped within a single `tenant_id`**.
  - **Why Global Cross-Tenant Deduplication Is Explicitly Rejected**:
    1. *Cryptographic Isolation*: Each tenant's object storage blobs are encrypted under a tenant-specific KMS key (`organizations.kms_key_id`) at `s3://<bucket>/<tenant_id>/blobs/<sha256>`.
    2. *Side-Channel Prevention*: Global deduplication would allow a malicious tenant to probe whether a proprietary file hash exists in another tenant's account.
    3. *Independent Offboarding*: Tenant A can be crypto-shredded and purged without reference-counting against Tenant B.

---

### Question 4: Can evidence anchors survive snapshot pruning without retaining unnecessary source data?
- **Finding (`D3-ISS-002` / Provisional Decision `Q2`)**:
  - **Yes, via Two-Stage Snapshot Compaction (`COMPACTED_EVIDENCE_ONLY`)**.
  - When a snapshot ages past `retention_policies.max_snapshots_per_repo`:
    1. All high-volume AST tables (`code_symbols`, `code_call_edges`, `code_symbol_references`, `code_imports`, `code_files`, `code_modules`) and unapproved `DRAFT_AI` findings for that snapshot are deleted (`> 98%` of DB rows for that snapshot).
    2. All `document_chunks`, `artifact_embeddings`, and `artifact_versions` (plus S3 blobs) **not** referenced by an active snapshot or a pinned `evidence_anchor` are garbage-collected.
    3. The `repository_snapshots` header row transitions to `status = 'COMPACTED_EVIDENCE_ONLY'`, and only the specific `evidence_anchors` (which carry `start_line`, `end_line`, `snippet_sha256`, and the bounded `<= 2048` char `excerpt_text`) and `artifact_versions` metadata rows cited by `APPROVED` / `MODIFIED_BY_HUMAN` findings, rules, and requirements are retained.

---

### Question 5: Are vector dimensions and HNSW indexes compatible with the selected `pgvector` version?
- **Finding (`D3-PDEC-Q1`)**:
  - **Yes.** The verified local infrastructure runs PostgreSQL 17 with **`pgvector` `0.8.7`**, which supports `vector` dimensions up to `2,000` for float32 HNSW indexes (and `4,000` for `halfvec`).
  - LegacyIQ's `vector(384)` (`BAAI/bge-small-en-v1.5`) is well within the `2,000`-dimension HNSW limit (`1,536 bytes` per vector) and natively supports `pgvector 0.8+` iterative HNSW scans (`SET LOCAL hnsw.iterative_scan = relaxed_order`).

---

### Question 6: Are graph traversal queries safe against cycles and tenant leakage?
- **Finding**:
  - **Cycle Safety**: Legacy codebases routinely contain mutual recursion and circular module imports (`A -> B -> A`). The recursive CTE in [graph-relationship-catalogue.md](file:///C:/LegacyIQ/docs/database/graph-relationship-catalogue.md) uses PostgreSQL's native `CYCLE source_entity_id, target_entity_id SET is_cycle USING traversal_path` clause combined with a hard `ig.hop_depth < :max_hops` (default `3`) and `LIMIT 1500` guard, guaranteeing termination in bounded time and memory.
  - **Tenant Leakage Safety**: Both the anchor member and recursive member join on `next_kr.tenant_id = ig.tenant_id` and execute under active RLS (`tenant_id = app_current_tenant_id()`), while composite FKs on `knowledge_relationships` guarantee `source_entity_id` and `target_entity_id` belong to the same `tenant_id`.

---

### Question 7: Are RLS policies compatible with SQLAlchemy connection pooling and transaction boundaries?
- **Finding**:
  - **Yes.** Because `SELECT set_config('app.current_tenant_id', :tenant_id, true)` uses `is_local = true` (`SET LOCAL`), the setting is bound exclusively to the current PostgreSQL transaction block and is automatically cleared by PostgreSQL the instant `COMMIT` or `ROLLBACK` executes.
  - **Interaction with Multi-Transaction Workflows (Boundary T4)**:
    - When a background worker releases its DB connection back to the SQLAlchemy `QueuePool` before calling Ollama (Step A $\to$ Step B in Boundary T4), the transaction ends and `app.current_tenant_id` resets.
    - When Step C checks out a new connection from the pool to persist the verified AI outputs, the session checkout wrapper automatically begins a new transaction and re-applies `set_config('app.current_tenant_id', :tenant_id, true)`.

---

### Question 8: Can project-level permissions be consistently enforced across every API and background worker?
- **Finding (`D3-PDEC-Q3`)**:
  - Under Provisional Decision `Q3`, PostgreSQL RLS enforces `tenant_id` isolation while FastAPI enforces project-level RBAC (`project_memberships`).
  - **Risk**: A developer could write a new endpoint or background job that filters by `tenant_id` (via RLS) but forgets to verify whether the current user is a member of the target `project_id` (allowing a user in Tenant A with access only to `Project_1` to view `Project_2` within Tenant A).
  - **Architectural Safeguard**:
    1. Every table in Domains B–H is rooted in `projects` (directly or via `applications -> project_id`).
    2. FastAPI endpoints do not inject a raw `Session`; they inject a `ScopedRepositoryFactory` constructed by a mandatory `require_project_permission(permission_code)` dependency that verifies `(tenant_id, project_id, user_id)` in `project_memberships` (or `ORG_OWNER` role in `organization_memberships`).
    3. Background jobs carry `(tenant_id, project_id, actor_user_id)` in their signed `TaskEnvelope` and re-verify project status before execution.

---

### Question 9: Are audit hash-chain concurrency and tamper-evidence guarantees technically sound?
- **Finding (`D3-ISS-006` / Provisional Decision `Q4`)**:
  - A naive `SELECT entry_hash ... ORDER BY occurred_at DESC LIMIT 1` without locking is vulnerable to race conditions under concurrent writes within the same tenant, producing a forked hash chain.
  - **Technical Resolution**: By acquiring a per-tenant transaction-scoped advisory lock (`pg_advisory_xact_lock(hashtext('audit_chain:' || NEW.tenant_id::text))`) inside a `BEFORE INSERT` trigger on `audit_logs` and requiring application services to insert into `audit_logs` as the last step before `COMMIT`, the hash chain is strictly linear per tenant, immune to race conditions, and holds the per-tenant lock for `< 1 ms`.
  - Furthermore, `UPDATE` and `DELETE` on `audit_logs` are blocked by the `prevent_immutable_ledger_mutation()` trigger, and periodic chain roots can be exported to external logs for off-database verification.

---

### Question 10: Are deletion, retention, legal holds and approved evidence preservation mutually consistent?
- **Finding (`D3-ISS-002` & `D3-ISS-007`)**:
  - Initially, there was a conflict between `ON DELETE CASCADE` on `repository_snapshots` and preserving approved evidence (`Q2`), as well as a missing legal hold flag.
  - With the addition of `legal_hold_active` and **Two-Stage Snapshot Compaction**, the precedence hierarchy is now deterministic and mutually consistent:
    $$\text{Legal Hold (\texttt{legal\_hold\_active = true})} \succ \text{Explicit Deletion Request (\texttt{FULL\_TENANT / PROJECT / REPO})} \succ \text{Approved Evidence Pinning (\texttt{Q2})} \succ \text{Automated Retention Compaction}$$
    1. If `legal_hold_active = true`, **all** automated compaction and manual deletions are blocked (`HTTP 409 Conflict`).
    2. If an authorized administrator executes an explicit `PROJECT` or `FULL_TENANT_OFFBOARDING` deletion (and `legal_hold_active = false`), all project/tenant data (including approved findings and evidence) is permanently purged and crypto-shredded.
    3. During routine `retention_policies` snapshot pruning (`max_snapshots_per_repo`), **Snapshot Compaction** purges heavy AST/vector data while preserving `APPROVED`/`MODIFIED_BY_HUMAN` findings, requirements, and their pinned `evidence_anchors`.

---

### Question 11: Are transaction boundaries consistent with asynchronous agent execution?
- **Finding**:
  - **Yes.** Transaction Boundary `T4` in [database-architecture.md](file:///C:/LegacyIQ/docs/database/database-architecture.md) explicitly prohibits holding an open PostgreSQL transaction or connection pool slot during asynchronous or synchronous LLM HTTP calls (`Ollama` or cloud fallback).
  - Each `agent_run` transitions through discrete, committed state checkpoints (`PENDING` $\to$ `RUNNING` $\to$ `COMPLETED` / `FAILED`) in short `< 100 ms` transactions, preventing idle-in-transaction timeouts, connection pool exhaustion, and lock contention.

---

### Question 12: Are indexes justified by actual query patterns rather than excessive speculative indexing?
- **Finding (`D3-ISS-011`)**:
  - Every index in [indexing-and-query-strategy.md](file:///C:/LegacyIQ/docs/database/indexing-and-query-strategy.md) maps to a concrete UI, API, ingestion, or graph traversal query pattern.
  - To prevent write amplification during high-speed AST ingestion (`code_symbols`, `code_call_edges`, `code_symbol_references`), redundant single-column `id` indexes are omitted (since `PRIMARY KEY (tenant_id, id)` already indexes `(tenant_id, id)`), and secondary indexes are restricted to `(tenant_id, snapshot_id, ...)` lookup paths.

---

## 4. Evaluation of the 10 Additional Architectural Checks

| # | Check Area | Risk Evaluated | Architectural Control in D3 Specification |
| :---: | :--- | :--- | :--- |
| **1** | **Cross-Tenant Deduplication Risks** | Side-channel file existence probing & shared KMS key entanglement if blobs/chunks were deduplicated globally across tenants. | **Strictly Prohibited (`D3-TECH-001`)**: Deduplication (`content_sha256`, `chunk_text_sha256`) is scoped strictly inside `tenant_id`. |
| **2** | **Data Leakage Through Embeddings & Retrieval** | `pgvector` HNSW index spans the table; a buggy vector query could return chunks from another tenant or wrong snapshot. | **Three-Layer Defense**: (1) RLS on `artifact_embeddings` and `document_chunks` enforces `tenant_id = app_current_tenant_id()`; (2) RRF query joins `code_files` on `(tenant_id, snapshot_id, artifact_version_id)`; (3) `pgvector 0.8.7` `hnsw.iterative_scan = relaxed_order` ensures post-RLS filtering never starves results. |
| **3** | **Tenant Context in Background Jobs** | Background worker processes jobs for multiple tenants sequentially and could forget to set or clear `app.current_tenant_id`. | **Signed TaskEnvelope + Context Manager (`D3-TECH-002`)**: Every worker task requires `TaskEnvelope(tenant_id, ...)` verified via HMAC; DB access is only available inside `with tenant_db_session(envelope.tenant_id):` which executes `SET LOCAL app.current_tenant_id` per transaction. |
| **4** | **Tenant-Aware Cache Keys** | Redis cache collisions or cross-tenant cache reads on port `6380`. | **Mandatory Key Prefix (`D3-TECH-003`)**: Redis wrapper enforces key prefix `lq:{env}:t:{tenant_id}:p:{project_id}:{domain}:{id}` and rejects un-scoped keys. |
| **5** | **Object Storage Authorization** | Direct bucket traversal or leaked presigned URLs exposing customer source files. | **Backend-Mediated Streaming & Per-Tenant Prefixes (`D3-TECH-004`)**: Blobs stored under `s3://<bucket>/<tenant_id>/blobs/<sha256>` encrypted with tenant KMS key `organizations.kms_key_id`; never exposed directly to browsers. |
| **6** | **Hard Deletion vs. Soft Deletion** | Orphaned heavy data from soft-deletes vs. accidental loss of audit trails from hard-deletes. | **Hybrid Policy**: Workspace/Project archival uses soft status (`lifecycle_status = 'ARCHIVED'`); Member removal uses `status = 'REVOKED'`; Snapshot compaction & `deletion_requests` perform verifiable **hard deletion + crypto-shredding** of source/AST/vector data while preserving immutable `audit_logs` and `deletion_requests` completion certificates. |
| **7** | **Reprocessing the Same Repository Snapshot** | Upgrading a parser or re-running AI extraction on an existing `snapshot_id` could duplicate symbols or overwrite human edits. | **Deterministic Upsert + Curated State Protection**: Domain D tables upsert idempotently on `(tenant_id, snapshot_id, relative_path)` / `canonical_key`; Domain F/G/H tables stamp outputs with the new `analysis_run_id` and carry forward `APPROVED` / `MODIFIED_BY_HUMAN` items without overwriting them. |
| **8** | **Concurrent Analysis Runs** | Two users clicking "Analyze" on the same snapshot simultaneously causing deadlocks or duplicate work. | **Partial Unique Index Guard (`D3-ISS-009` / `D3-TECH-005`)**: `ux_active_analysis_run_per_snapshot` guarantees at most one active `analysis_run` per `(tenant_id, snapshot_id)` at the PostgreSQL index level. |
| **9** | **Idempotency & Retry Behaviour** | Network timeout to Ollama or worker crash mid-batch causing duplicate rows on retry. | **Idempotent Natural Keys (`D3-TECH-006`)**: Every batch insert uses deterministic natural keys (`canonical_key`, `chunk_index`, `sequence_no`, `snippet_sha256`) with `ON CONFLICT DO NOTHING / DO UPDATE`. |
| **10** | **Schema Evolution & Backward Compatibility** | Adding new language parsers, node types, or agent metadata breaking existing tables. | **Extensible Enum/VARCHAR + Typed JSONB**: `entity_type`, `relationship_type`, and `finding_category` use constrained `VARCHAR` (avoiding rigid PostgreSQL `ENUM` type lock-in during `ALTER TYPE`) paired with schema-validated `attributes_json` / `edge_metadata` `JSONB` columns and `pipeline_versions_manifest`. |

---

## 5. Summary of Decisions Requiring Final Product-Owner Sign-Off

All 5 open architectural questions (`D3-PDEC-Q1` through `D3-PDEC-Q5` in [d3-decisions-register.md](file:///C:/LegacyIQ/docs/database/d3-decisions-register.md)) have been resolved with **PROVISIONAL** specifications:
1. **`D3-PDEC-Q1` (`PROVISIONAL`)**: Fixed `vector(384)` column with `embedding_model_versions` metadata and shadow-column/partition migration path for future dimensions.
2. **`D3-PDEC-Q2` (`PROVISIONAL`)**: Two-Stage Snapshot Compaction (`COMPACTED_EVIDENCE_ONLY`) preserving `APPROVED`/`MODIFIED_BY_HUMAN` findings, requirements, and their `evidence_anchors` when snapshots are pruned.
3. **`D3-PDEC-Q3` (`PROVISIONAL`)**: PostgreSQL RLS for strict `tenant_id` isolation + FastAPI `ProjectAccessContext` for project-level RBAC, backed by mandatory negative CI tests.
4. **`D3-PDEC-Q4` (`PROVISIONAL`)**: Synchronous per-tenant tamper-evident `audit_logs` hash chaining via transaction-end `pg_advisory_xact_lock`.
5. **`D3-PDEC-Q5` (`APPROVED`)**: Phased 3-wave Alembic migration rollout (Wave 1: 33 tables [Domains A=8, B=6, C=8, D=7, J=3, plus `analysis_runs`=1]; Wave 2: 21 tables [Domains E=9, F=7, remaining I=5]; Wave 3: 17 tables [Domains G=6, H=5, K=6]; total $33 + 21 + 17 = 71$ canonical tables).

Once you confirm approval of `D3-PDEC-Q1` through `D3-PDEC-Q5`, their status can be flipped from `PROVISIONAL` to `APPROVED`, locking **Design Phase D3** as the authoritative database baseline for LegacyIQ.

