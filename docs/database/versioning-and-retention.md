# LegacyIQ — Versioning, Immutability & Data Retention Architecture (Design Phase D3)

**Document ID**: `D3-09`  
**Status**: Architecture Specification  

---

## 1. Multi-Dimensional Versioning Model

LegacyIQ manages five independent axes of change over time without losing historical auditability or corrupting existing citations:

| Versioning Axis | Anchor Table | Key Identifier | Immutability Rule |
| :--- | :--- | :--- | :--- |
| **1. Source Repository State** | `repository_snapshots` | `(tenant_id, repository_id, snapshot_number)` + `tree_or_archive_sha256` | **Strictly Immutable** once `status = 'READY'`. New commits or ZIP uploads always create `snapshot_number + 1`. |
| **2. File / Blob Content** | `artifact_versions` | `(tenant_id, artifact_id, content_sha256)` | **Strictly Immutable** content-addressed record. Identical file content across snapshots reuses the same `artifact_version_id`. |
| **3. Execution & Parser Pipeline** | `analysis_runs` | `(tenant_id, application_id, run_number)` + `pipeline_versions_manifest` | **Immutable Execution Record**. Captures exact versions of Tree-sitter grammars, embedding models, and agent prompts used. |
| **4. Prompt & Embedding Models** | `prompt_templates`, `embedding_model_versions` | `(template_key, version_number)` / `(provider_name, model_name, model_revision)` | **Append-Only Registry**. Modifying a prompt creates `version_number + 1`. |
| **5. Human Curation & Review** | `findings`, `business_rules`, `requirements` + `review_history` | `version_no` + `superseded_by_finding_id` + `review_history.id` | In-place status transitions increment `version_no` and append an immutable before/after JSON snapshot to `review_history`. |

---

## 2. Preserving Human Reviews Across New Snapshots & Analysis Runs

When a customer ingests Snapshot #2 (or runs Analysis Run #2 on Snapshot #1), LegacyIQ must **carry forward human-approved knowledge** (`review_status IN ('APPROVED', 'MODIFIED_BY_HUMAN', 'REJECTED')`) rather than forcing architects to re-review 500 rules from scratch.

### Cross-Run Carry-Forward & Supersession Algorithm
1. **Deterministic Identity Matching**:
   - For `code_symbols`, matching uses `(qualified_name, body_ast_hash)`. If `body_ast_hash` is unchanged between Snapshot #1 and Snapshot #2, the symbol's behavioral semantics are guaranteed identical.
   - For `business_rules`, `requirements`, and `findings`, matching compares the cited `evidence_anchors.snippet_sha256` and `canonical_key`.
2. **Automatic Carry-Forward (Unchanged Evidence)**:
   - If all backing `evidence_anchors.snippet_sha256` hashes for an `APPROVED` or `MODIFIED_BY_HUMAN` rule/requirement still exist unchanged in Snapshot #2, the curated state is automatically linked to the new snapshot with `review_status` preserved.
3. **Drift Detection & Supersession (Modified Evidence)**:
   - If the underlying source code lines changed (`snippet_sha256` differs), the new analysis run generates a candidate record (`review_status = 'PENDING_REVIEW'`), links `superseded_by_finding_id`, and opens a `knowledge_conflicts` entry (`conflict_type = 'AI_RUN_DIVERGENCE'`) highlighting the exact code diff between the previously approved anchor and the new snapshot.

---

## 3. Sensitive Fields & Data Classification Inventory

To comply with enterprise security standards, GDPR, and SOC 2 requirements, all sensitive columns are explicitly classified:

| Classification Tier | Tables & Columns | Protection & Logging Policy |
| :--- | :--- | :--- |
| **Tier 1: Authentication Secrets & Keys** | `users.password_hash`, `source_connectors.encrypted_credentials_ref`, `organizations.kms_key_id` | Argon2id for passwords; envelope encryption via KMS/Vault for connector tokens. **Never logged, never returned in API responses.** |
| **Tier 2: Customer Intellectual Property (Source Code & Specs)** | `artifact_versions.storage_object_uri`, `evidence_anchors.excerpt_text`, `document_chunks.chunk_text`, `doc_sections.content_markdown`, `model_invocations.storage_payload_uri` | Encrypted at rest in object storage using tenant-specific DEK (`organizations.kms_key_id`). `excerpt_text` bounded to `<= 2048` chars and scanned by secret-redaction regex before DB insert. **Never sent to external cloud LLMs unless `tenant_subscriptions.allow_cloud_llm_providers = true`.** |
| **Tier 3: Personal Identifiable Information (PII)** | `users.email`, `users.full_name`, `repository_commits.author_name`, `repository_commits.author_email`, `audit_logs.client_ip` | Subject to GDPR Right-to-Erasure pseudonymization (`[REDACTED_USER_<hash>]`). |
| **Tier 4: Operational & Structural Metadata** | AST symbol names, line numbers, graph edge weights, token counts, latencies | Protected by tenant RLS; safe for internal structured application telemetry. |

---

## 4. Lifecycle, Retention Policies & Garbage Collection

Each tenant configures retention windows in `retention_policies` (`artifact_category`, `retain_days`, `max_snapshots_per_repo`, `auto_purge_enabled`):

| `artifact_category` | Default Retention | Purge / Compaction Mechanism |
| :--- | :--- | :--- |
| **`RAW_SOURCE_BLOBS`** | Active snapshots + `max_snapshots_per_repo` (default last `10` snapshots) | When an old `repository_snapshot` is compacted (`status = 'COMPACTED_EVIDENCE_ONLY'`), any `artifact_versions` not referenced by an active snapshot or by an `evidence_anchor` depending on retention policy are garbage-collected (blocked if `legal_hold_active = true`). |
| **`SNAPSHOT_AST`** | Tied to active `repository_snapshots` (`max_snapshots_per_repo = 10`) | Compacting an expired `repository_snapshot` deletes its heavy AST/graph rows (`code_modules`, `code_files`, `code_symbols`, `code_imports`, `code_call_edges`, `code_type_hierarchies`, `code_symbol_references`) and unapproved `DRAFT_AI` findings, while keeping the lightweight `repository_snapshots` header row (`status = 'COMPACTED_EVIDENCE_ONLY'`) so `APPROVED` / `MODIFIED_BY_HUMAN` findings, rules, requirements, and their `evidence_anchors` preserve intact foreign keys and provenance (**Provisional Decision Q2**). |
| **`AI_INVOCATION_LOGS`** | `90 days` (`model_invocations.storage_payload_uri` & `agent_execution_events`) | Raw prompt/completion blobs in object storage and step events in `agent_execution_events` expire after 90 days; summary token counts and provenance IDs in `model_invocations` are retained. |
| **`RUNTIME_OBSERVATIONS`** | `90 days` | Time-windowed delete on `runtime_observations.observed_window_end < now() - interval '90 days'`. |
| **`AUDIT_LOGS`** | `365 days` (Pro) / `2555 days` (7 Years Enterprise) | Append-only in PostgreSQL; cold-archived to immutable WORM object storage prior to partition drop. |

---

## 5. Verifiable Deletion & Crypto-Shredding Workflow (`deletion_requests`)

When a tenant administrator initiates a deletion (`SINGLE_SNAPSHOT`, `REPOSITORY`, `PROJECT`, or `FULL_TENANT_OFFBOARDING`):

1. **Request & Approval Gate**:
   - Creates a row in `deletion_requests` (`status = 'REQUESTED'`) and requires dual-authorization via `approval_requests` (`request_type = 'DATA_PURGE_APPROVAL'`) for `PROJECT` or `FULL_TENANT_OFFBOARDING`.
2. **Crypto-Shredding (Immediate Irreversible Revocation for Full Tenant Offboarding)**:
   - For `FULL_TENANT_OFFBOARDING`, the worker first destroys the tenant's Data Encryption Key (`organizations.kms_key_id`) in the KMS/Vault (`status = 'CRYPTO_SHREDDED'`), immediately rendering all encrypted object storage blobs and backups undecipherable.
3. **Ordered Relational & Blob Purge**:
   - Deletes tenant object storage prefix `s3://<bucket>/<tenant_id>/`.
   - Deletes relational rows in leaf-to-root order (or partition detach + drop) within bounded batch transactions.
4. **Completion Certificate**:
   - Generates a signed cryptographic digest (`completion_certificate_sha256`) over the purge manifest and records the final timestamp in `deletion_requests.completed_at` (`status = 'COMPLETED'`).

