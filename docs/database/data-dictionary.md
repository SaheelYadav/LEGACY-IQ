# LegacyIQ — Canonical Data Dictionary (Design Phase D3)

**Document ID**: `D3-03`  
**Status**: Architecture Specification  
**Total Canonical Tables**: 71 across 11 Domains (A–K)

---

## Global Conventions Applied Across All Tables

1. **Primary Keys & Composite Tenant Keys**:
   - Global/system tables (`organizations`, `users`, `permissions`, `role_permissions`, `embedding_model_versions`) use `PRIMARY KEY (id)` (or `(role_id, permission_id)`).
   - Hybrid global/tenant catalog tables (`roles`, `prompt_templates`) use `PRIMARY KEY (id)` with nullable `tenant_id` enforced via a cross-tenant validation trigger.
   - All **64 strictly tenant-owned (`TENANT_DIRECT`) tables** enforce `PRIMARY KEY (tenant_id, id)` so every intra-tenant foreign key uses `(tenant_id, <fk_col>) REFERENCES <parent_table>(tenant_id, id)`.
2. **Audit Timestamps**:
   - Unless marked append-only/immutable, tables carry `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` and `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
3. **Identifier Generation**:
   - All `UUID` primary keys use time-ordered **UUIDv7** (`gen_random_uuid()` or PG17/app-generated UUIDv7) to preserve B-tree locality on high-insert tables.

---

## Domain A: Identity & Multi-Tenancy (8 Tables)

### A1. `organizations`
- **Purpose**: Root tenant entity representing an enterprise customer, consulting firm, or workspace organization.
- **Tenant Ownership**: **Tenant Root** (`id` *is* the `tenant_id` for all descendant tables).
- **Retention**: Retained for tenant lifetime; transitions to `PENDING_DELETION` then crypto-shredded + purged upon `deletion_requests` completion.
- **PK**: `(id)` | **UK**: `(slug)` | **Indexes**: `ix_organizations_status (status)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | NO | `PK` | Canonical Tenant ID (`tenant_id`). |
| `slug` | `VARCHAR(64)` | NO | `UNIQUE` | URL-safe organization handle. |
| `display_name` | `VARCHAR(255)` | NO | | Legal or display name of the organization. |
| `tier` | `VARCHAR(32)` | NO | `DEFAULT 'FREE'` | `'FREE' \| 'PRO' \| 'ENTERPRISE'`. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'ACTIVE'` | `'ACTIVE' \| 'SUSPENDED' \| 'PENDING_DELETION'`. |
| `kms_key_id` | `UUID` | YES | | Reference to tenant-specific envelope encryption key. |
| `settings_json` | `JSONB` | NO | `DEFAULT '{}'` | Tenant-wide security and AI policy flags. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Last update timestamp. |

### A2. `users`
- **Purpose**: Global user identity able to belong to one or more tenant `organizations` (critical for IT consulting firms operating across client tenants).
- **Tenant Ownership**: **Global Identity Table** (access mediated via `organization_memberships`).
- **Retention**: PII pseudonymized (`email`, `full_name` scrubbed) upon user erasure request while preserving `id` referential integrity in `review_history` and `audit_logs`.
- **PK**: `(id)` | **UK**: `(email)`, `(auth_provider, external_subject_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | NO | `PK` | Global user identifier. |
| `email` | `VARCHAR(320)` | NO | `UNIQUE` | Lowercase normalized email (**PII**). |
| `full_name` | `VARCHAR(255)` | NO | | Display name (**PII**). |
| `password_hash` | `TEXT` | YES | | Argon2id hash if `auth_provider = 'LOCAL'` (**Sensitive**). |
| `auth_provider` | `VARCHAR(32)` | NO | `DEFAULT 'LOCAL'` | `'LOCAL' \| 'OIDC' \| 'SAML'`. |
| `external_subject_id` | `VARCHAR(255)` | YES | `UK(auth_provider, external_subject_id)` | IdP subject identifier. |
| `is_system_admin` | `BOOLEAN` | NO | `DEFAULT false` | Platform operator flag (never bypasses tenant data without audit). |
| `last_login_at` | `TIMESTAMPTZ` | YES | | Last successful authentication. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### A3. `organization_memberships`
- **Purpose**: Binds a global `users.id` to a specific tenant `organizations.id` with a primary organization role.
- **Tenant Ownership**: Direct `tenant_id` (`FK -> organizations.id`).
- **Retention**: Purged on tenant deletion; soft-revoked (`status = 'REVOKED'`) when a member leaves an organization.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, user_id)` | **FK**: `tenant_id -> organizations(id)`, `user_id -> users(id)`, `role_id -> roles(id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Membership record ID. |
| `user_id` | `UUID` | NO | `FK, UK(tenant_id, user_id)` | Linked user. |
| `role_id` | `UUID` | NO | `FK` | Assigned organization-level RBAC role. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'ACTIVE'` | `'INVITED' \| 'ACTIVE' \| 'SUSPENDED' \| 'REVOKED'`. |
| `joined_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Membership activation timestamp. |

### A4. `teams`
- **Purpose**: Tenant-scoped engineering or consulting sub-teams for bulk project permission assignment.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: `ON DELETE CASCADE` with tenant.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, name)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Team ID. |
| `name` | `VARCHAR(128)` | NO | `UK(tenant_id, name)` | Team name within organization. |
| `description` | `TEXT` | YES | | Purpose of the team. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### A5. `team_memberships`
- **Purpose**: Many-to-many join between `teams` and `organization_memberships`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: `ON DELETE CASCADE` when team or org membership is removed.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, team_id, org_membership_id)` | **FK**: `(tenant_id, team_id) -> teams`, `(tenant_id, org_membership_id) -> organization_memberships`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Join ID. |
| `team_id` | `UUID` | NO | `FK` | Target team. |
| `org_membership_id` | `UUID` | NO | `FK` | Target organization member. |
| `added_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Assignment timestamp. |

### A6. `roles`
- **Purpose**: RBAC role definitions supporting built-in system roles (`tenant_id IS NULL`) and tenant-custom roles (`tenant_id IS NOT NULL`).
- **Tenant Ownership**: Hybrid Global (`tenant_id IS NULL`) + Tenant-Owned (`tenant_id IS NOT NULL`).
- **Retention**: Custom roles cascade on tenant deletion; system roles are immutable.
- **PK**: `(id)` | **UK**: ` COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'), code`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | NO | `PK` | Role ID. |
| `tenant_id` | `UUID` | YES | `FK -> organizations(id)` | `NULL` for built-in roles (`ORG_OWNER`, `ARCHITECT`, `REVIEWER`, `VIEWER`). |
| `code` | `VARCHAR(64)` | NO | | Machine role code. |
| `name` | `VARCHAR(128)` | NO | | Human-readable role title. |
| `is_system_role` | `BOOLEAN` | NO | `DEFAULT false` | True if seeded by platform. |

### A7. `permissions`
- **Purpose**: Global catalog of fine-grained capability permissions (e.g., `repo:ingest`, `analysis:run`, `finding:approve`, `tenant:delete`).
- **Tenant Ownership**: Global System Catalog (Read-only to tenants).
- **Retention**: Permanent system metadata.
- **PK**: `(id)` | **UK**: `(code)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | NO | `PK` | Permission ID. |
| `code` | `VARCHAR(96)` | NO | `UNIQUE` | Action code (`domain:action`). |
| `category` | `VARCHAR(64)` | NO | | Grouping category. |
| `description` | `TEXT` | NO | | Detailed capability description. |

### A8. `role_permissions`
- **Purpose**: Maps `roles` to granted `permissions`.
- **Tenant Ownership**: Inherited from `roles.tenant_id`.
- **Retention**: Cascades on `roles` deletion.
- **PK**: `(role_id, permission_id)` | **FK**: `role_id -> roles(id)`, `permission_id -> permissions(id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `role_id` | `UUID` | NO | `PK, FK` | Role reference. |
| `permission_id` | `UUID` | NO | `PK, FK` | Permission reference. |

---

## Domain B: Workspace, Project & Application Management (6 Tables)

### B1. `workspaces`
- **Purpose**: Logical business unit or client engagement boundary within an organization.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on tenant deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, slug)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Workspace ID. |
| `slug` | `VARCHAR(64)` | NO | `UK(tenant_id, slug)` | Workspace handle. |
| `name` | `VARCHAR(255)` | NO | | Display name. |
| `is_default` | `BOOLEAN` | NO | `DEFAULT false` | Default workspace flag. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### B2. `projects`
- **Purpose**: Modernization or discovery initiative grouping one or more legacy `applications`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Soft-archivable (`lifecycle_status = 'ARCHIVED'`); hard-deleted via `deletion_requests`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, workspace_id, key)` | **FK**: `(tenant_id, workspace_id) -> workspaces(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Project ID. |
| `workspace_id` | `UUID` | NO | `FK` | Parent workspace. |
| `key` | `VARCHAR(32)` | NO | `UK` | Short project code (e.g. `CORE-BANK`). |
| `name` | `VARCHAR(255)` | NO | | Full project name. |
| `description` | `TEXT` | YES | | Engagement summary. |
| `lifecycle_status` | `VARCHAR(32)` | NO | `DEFAULT 'ACTIVE'` | `'ACTIVE' \| 'ARCHIVED' \| 'PENDING_PURGE'`. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### B3. `project_memberships`
- **Purpose**: Project-level RBAC access control restricting which organization members or teams can view/edit a specific project.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on project deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, project_id, org_membership_id)` | **FK**: `(tenant_id, project_id) -> projects`, `(tenant_id, org_membership_id) -> organization_memberships`, `role_id -> roles(id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Project membership ID. |
| `project_id` | `UUID` | NO | `FK` | Target project. |
| `org_membership_id` | `UUID` | NO | `FK` | Granted organization member. |
| `role_id` | `UUID` | NO | `FK` | Project-level role override. |
| `granted_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Grant timestamp. |

### B4. `applications`
- **Purpose**: Represents a bounded legacy software system (monolith, microservice suite, or batch system) under analysis.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades with project purge.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, project_id, code)` | **FK**: `(tenant_id, project_id) -> projects(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Application ID. |
| `project_id` | `UUID` | NO | `FK` | Parent project. |
| `code` | `VARCHAR(64)` | NO | `UK` | Application short identifier. |
| `name` | `VARCHAR(255)` | NO | | Application name. |
| `architecture_style` | `VARCHAR(64)` | YES | | `'MONOLITH' \| 'MODULAR_MONOLITH' \| 'MICROSERVICES' \| 'BATCH_ETL'`. |
| `criticality_tier` | `VARCHAR(32)` | NO | `DEFAULT 'TIER_2'` | `'TIER_1' \| 'TIER_2' \| 'TIER_3'`. |
| `primary_languages` | `JSONB` | NO | `DEFAULT '[]'` | Detected/declared language list. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### B5. `application_environments`
- **Purpose**: Models deployment environments (`DEV`, `STAGING`, `PROD`) for correlating IaC configurations and runtime telemetry.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `applications` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, env_name)` | **FK**: `(tenant_id, application_id) -> applications`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Environment ID. |
| `application_id` | `UUID` | NO | `FK` | Parent application. |
| `env_name` | `VARCHAR(64)` | NO | `UK` | Environment name (e.g. `production-eu`). |
| `env_type` | `VARCHAR(32)` | NO | | `'DEV' \| 'TEST' \| 'STAGING' \| 'PROD'`. |
| `metadata_config` | `JSONB` | NO | `DEFAULT '{}'` | Non-secret environment topology metadata. |

### B6. `analysis_scopes`
- **Purpose**: Defines file inclusion/exclusion globs, enabled language parsers, maximum file size thresholds, and AI enrichment flags for an application.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Retained while referenced by any `analysis_runs`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, name)` | **FK**: `(tenant_id, application_id) -> applications`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Scope ID. |
| `application_id` | `UUID` | NO | `FK` | Parent application. |
| `name` | `VARCHAR(128)` | NO | `UK` | Scope profile name (e.g. `Default Full Scan`). |
| `include_globs` | `JSONB` | NO | `DEFAULT '["**/*"]'` | Glob patterns to include. |
| `exclude_globs` | `JSONB` | NO | `DEFAULT '["**/node_modules/**","**/vendor/**","**/.git/**"]'` | Excluded path globs. |
| `language_parsers_enabled` | `JSONB` | NO | `DEFAULT '["python","java","javascript","typescript","php"]'` | Active parser list. |
| `max_file_size_bytes` | `INTEGER` | NO | `DEFAULT 5242880` | Max single file size (default 5 MB). |
| `is_default` | `BOOLEAN` | NO | `DEFAULT true` | Default scope flag. |

---

## Domain C: Source Connectors & Immutable Ingestion (8 Tables)

### C1. `source_connectors`
- **Purpose**: Stores metadata and KMS/Vault references for external Git servers, issue trackers, or database metadata catalogs.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Purged on tenant deletion; credentials wiped immediately upon connector revocation.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, name)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Connector ID. |
| `name` | `VARCHAR(128)` | NO | `UK` | Connector label. |
| `provider_type` | `VARCHAR(32)` | NO | | `'GIT_LOCAL' \| 'GITHUB' \| 'GITLAB' \| 'BITBUCKET' \| 'ZIP_UPLOAD' \| 'DB_METADATA'`. |
| `endpoint_base_url` | `TEXT` | YES | | Base API/Git host URL. |
| `encrypted_credentials_ref` | `TEXT` | YES | | Envelope-encrypted token or KMS secret URI (**Sensitive**). |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'ACTIVE'` | `'ACTIVE' \| 'INVALID' \| 'REVOKED'`. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### C2. `repositories`
- **Purpose**: Represents a source code repository or uploaded archive stream linked to an `application`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: governed by `retention_policies` and `deletion_requests`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, name)` | **FK**: `(tenant_id, application_id) -> applications`, `(tenant_id, connector_id) -> source_connectors`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Repository ID. |
| `application_id` | `UUID` | NO | `FK` | Owning application. |
| `connector_id` | `UUID` | YES | `FK` | Nullable for direct ZIP uploads. |
| `name` | `VARCHAR(255)` | NO | `UK` | Repository name. |
| `source_type` | `VARCHAR(32)` | NO | | `'GIT' \| 'ZIP_ARCHIVE' \| 'DOC_BUNDLE'`. |
| `remote_url` | `TEXT` | YES | | Sanitized remote Git URL (never contains inline credentials). |
| `default_branch` | `VARCHAR(128)` | YES | `DEFAULT 'main'` | Default branch name. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'REGISTERED'` | `'REGISTERED' \| 'INGESTING' \| 'READY' \| 'FAILED' \| 'ARCHIVED'`. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Registration timestamp. |

### C3. `repository_branches`
- **Purpose**: Tracks branches discovered in a Git repository.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repositories` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, repository_id, branch_name)` | **FK**: `(tenant_id, repository_id) -> repositories`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Branch ID. |
| `repository_id` | `UUID` | NO | `FK` | Parent repository. |
| `branch_name` | `VARCHAR(255)` | NO | `UK` | Git branch ref name. |
| `head_commit_sha` | `VARCHAR(64)` | YES | | Latest observed commit hash. |
| `is_default` | `BOOLEAN` | NO | `DEFAULT false` | True if default branch. |

### C4. `repository_commits`
- **Purpose**: Immutable Git commit metadata associated with snapshots.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repositories` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, repository_id, commit_sha)` | **FK**: `(tenant_id, repository_id) -> repositories`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Commit record ID. |
| `repository_id` | `UUID` | NO | `FK` | Parent repository. |
| `commit_sha` | `VARCHAR(64)` | NO | `UK` | 40-char Git SHA-1 or 64-char SHA-256. |
| `author_name` | `VARCHAR(255)` | YES | | Commit author name (**PII**). |
| `author_email` | `VARCHAR(320)` | YES | | Commit author email (**PII**). |
| `committed_at` | `TIMESTAMPTZ` | YES | | Commit timestamp. |
| `commit_message` | `TEXT` | YES | | Commit message summary. |

### C5. `repository_snapshots`
- **Purpose**: **Immutable point-in-time freeze** of a repository tree or uploaded archive. Forms the foundational versioning anchor for all code intelligence, graph edges, and evidence.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: **Immutable once `status = 'READY'`**. Pruned only via explicit `retention_policies` (`max_snapshots_per_repo`) or `deletion_requests`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, repository_id, snapshot_number)` | **FK**: `(tenant_id, repository_id) -> repositories`, `(tenant_id, branch_id) -> repository_branches`, `(tenant_id, commit_id) -> repository_commits`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Snapshot ID. |
| `repository_id` | `UUID` | NO | `FK` | Parent repository. |
| `branch_id` | `UUID` | YES | `FK` | Optional branch reference. |
| `commit_id` | `UUID` | YES | `FK` | Optional commit reference. |
| `snapshot_number` | `INTEGER` | NO | `UK` | Monotonically increasing per repository (`1, 2, 3...`). |
| `tree_or_archive_sha256` | `CHAR(64)` | NO | | Merkle root / archive SHA-256 digest. |
| `total_files_count` | `BIGINT` | NO | `DEFAULT 0` | Count of indexed files in snapshot. |
| `total_bytes_size` | `BIGINT` | NO | `DEFAULT 0` | Uncompressed byte total. |
| `legal_hold_active` | `BOOLEAN` | NO | `DEFAULT false` | Blocks automated retention pruning and deletion while `true`. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'CREATING'` | `'CREATING' \| 'READY' \| 'COMPACTED_EVIDENCE_ONLY' \| 'SUPERSEDED' \| 'QUARANTINED'`. |
| `captured_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Immutable capture timestamp. |

### C6. `artifacts`
- **Purpose**: Logical identity of an ingested artifact path (source file, OpenAPI spec, DDL script, IaC file, or documentation file) across snapshots.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `applications` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, COALESCE(repository_id, '00000000-0000-0000-0000-000000000000'), canonical_path)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Logical artifact ID. |
| `application_id` | `UUID` | NO | `FK` | Owning application. |
| `repository_id` | `UUID` | YES | `FK` | Owning repository (nullable for standalone uploads). |
| `artifact_kind` | `VARCHAR(32)` | NO | | `'SOURCE_FILE' \| 'OPENAPI_SPEC' \| 'DDL_SCRIPT' \| 'IAC_FILE' \| 'DOC_FILE' \| 'LOG_ARCHIVE'`. |
| `canonical_path` | `TEXT` | NO | | Normalized POSIX-style relative path (`src/orders/service.py`). |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | First seen timestamp. |

### C7. `artifact_versions`
- **Purpose**: **Immutable content-addressed version** of an `artifact`. De-duplicates unchanged files across multiple `repository_snapshots`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: **Strictly Immutable**; garbage-collected only when zero `code_files`, `evidence_anchors`, or `doc_sections` reference it.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, artifact_id, content_sha256)` | **Indexes**: `ix_artifact_versions_sha256 (tenant_id, content_sha256)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Artifact version ID. |
| `artifact_id` | `UUID` | NO | `FK` | Parent logical artifact. |
| `content_sha256` | `CHAR(64)` | NO | `UK` | SHA-256 hex digest of normalized file bytes. |
| `byte_size` | `BIGINT` | NO | | Exact byte length. |
| `line_count` | `INTEGER` | YES | | Total newline count. |
| `encoding` | `VARCHAR(32)` | NO | `DEFAULT 'utf-8'` | Detected character encoding. |
| `mime_type` | `VARCHAR(128)` | NO | `DEFAULT 'text/plain'` | Detected MIME type. |
| `storage_object_uri` | `TEXT` | NO | | Tenant-isolated encrypted blob URI (**Sensitive Customer IP**). |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Immutable creation timestamp. |

### C8. `ingestion_jobs`
- **Purpose**: Tracks asynchronous background execution of repository cloning, archive validation, virus/zip-bomb scanning, and snapshot creation.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Retained for 90 days or per `retention_policies`.
- **PK**: `(tenant_id, id)` | **FK**: `(tenant_id, repository_id) -> repositories`, `(tenant_id, snapshot_id) -> repository_snapshots`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Job ID. |
| `repository_id` | `UUID` | NO | `FK` | Target repository. |
| `snapshot_id` | `UUID` | YES | `FK` | Resulting snapshot ID. |
| `triggered_by_user_id` | `UUID` | YES | `FK -> users(id)` | Initiating user. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'QUEUED'` | `'QUEUED' \| 'RUNNING' \| 'COMPLETED' \| 'FAILED' \| 'CANCELLED'`. |
| `stats_summary` | `JSONB` | NO | `DEFAULT '{}'` | Files scanned, skipped binary counts, duration metrics. |
| `error_message` | `TEXT` | YES | | Sanitized error diagnostic. |
| `started_at` | `TIMESTAMPTZ` | YES | | Execution start time. |
| `completed_at` | `TIMESTAMPTZ` | YES | | Execution end time. |

---

## Domain D: Deterministic Code Intelligence (7 Tables)

### D1. `code_modules`
- **Purpose**: Represents language packages, namespaces, directories, or logical modules within a `repository_snapshot`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades when parent `repository_snapshots` is purged.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, snapshot_id, language, qualified_name)` | **FK**: `(tenant_id, snapshot_id) -> repository_snapshots`, `(tenant_id, parent_module_id) -> code_modules`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Module ID. |
| `snapshot_id` | `UUID` | NO | `FK` | Snapshot anchor. |
| `language` | `VARCHAR(32)` | NO | | `'python' \| 'java' \| 'javascript' \| 'typescript' \| 'php'`. |
| `module_kind` | `VARCHAR(32)` | NO | | `'PACKAGE' \| 'NAMESPACE' \| 'MODULE' \| 'DIRECTORY'`. |
| `qualified_name` | `TEXT` | NO | `UK` | Fully qualified module name (`com.acme.billing`). |
| `parent_module_id` | `UUID` | YES | `FK` | Enclosing module/package. |

### D2. `code_files`
- **Purpose**: Binds a file path inside a specific `repository_snapshot` to its immutable `artifact_version_id` and records deterministic file-level AST metrics.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades when parent `repository_snapshots` is purged.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, snapshot_id, relative_path)` | **FK**: `(tenant_id, snapshot_id) -> repository_snapshots`, `(tenant_id, artifact_version_id) -> artifact_versions`, `(tenant_id, module_id) -> code_modules`, `(tenant_id, analysis_run_id) -> analysis_runs`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Snapshot code file ID. |
| `snapshot_id` | `UUID` | NO | `FK` | Snapshot anchor. |
| `artifact_version_id` | `UUID` | NO | `FK` | Exact content-addressed blob version. |
| `module_id` | `UUID` | YES | `FK` | Enclosing module/package. |
| `analysis_run_id` | `UUID` | NO | `FK` | Parser analysis run ID. |
| `relative_path` | `TEXT` | NO | `UK` | Relative file path within snapshot. |
| `language` | `VARCHAR(32)` | NO | | Detected programming language. |
| `parser_name` | `VARCHAR(64)` | NO | | e.g., `'treesitter_java@0.23'`, `'python_ast@3.10'`. |
| `parse_status` | `VARCHAR(32)` | NO | | `'PARSED' \| 'PARTIAL_ERROR' \| 'SKIPPED_BINARY' \| 'SKIPPED_SIZE'`. |
| `loc_code` | `INTEGER` | NO | `DEFAULT 0` | Non-blank, non-comment lines of code. |
| `loc_comment` | `INTEGER` | NO | `DEFAULT 0` | Comment lines. |
| `ast_metrics` | `JSONB` | NO | `DEFAULT '{}'` | Halstead/complexity aggregates. |

### D3. `code_symbols`
- **Purpose**: Deterministic AST declaration table for classes, interfaces, traits, functions, methods, fields, constants, and enums.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_code_symbols_snapshot_qname (tenant_id, snapshot_id, qualified_name)`, `ix_code_symbols_file (tenant_id, code_file_id)`, `ix_code_symbols_body_hash (tenant_id, body_ast_hash)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Symbol ID. |
| `snapshot_id` | `UUID` | NO | `FK` | Snapshot anchor. |
| `code_file_id` | `UUID` | NO | `FK` | Declaring file. |
| `parent_symbol_id` | `UUID` | YES | `FK` | Enclosing symbol (e.g. class for a method). |
| `symbol_kind` | `VARCHAR(32)` | NO | | `'CLASS' \| 'INTERFACE' \| 'TRAIT' \| 'FUNCTION' \| 'METHOD' \| 'FIELD' \| 'CONSTANT' \| 'ENUM'`. |
| `name` | `VARCHAR(255)` | NO | | Unqualified identifier (`calculate_total`). |
| `qualified_name` | `TEXT` | NO | | Fully qualified name (`orders.service.OrderService.calculate_total`). |
| `signature_text` | `TEXT` | YES | | Normalized method/function signature including parameters & return types. |
| `visibility` | `VARCHAR(32)` | YES | | `'PUBLIC' \| 'PROTECTED' \| 'PRIVATE' \| 'INTERNAL'`. |
| `start_line` | `INTEGER` | NO | | 1-based start line in `code_file_id`. |
| `end_line` | `INTEGER` | NO | | 1-based inclusive end line. |
| `start_column` | `INTEGER` | NO | `DEFAULT 0` | 0-based start column. |
| `end_column` | `INTEGER` | NO | `DEFAULT 0` | 0-based end column. |
| `cyclomatic_complexity` | `INTEGER` | YES | | McCabe cyclomatic complexity. |
| `cognitive_complexity` | `INTEGER` | YES | | Cognitive complexity score. |
| `body_ast_hash` | `CHAR(64)` | YES | | SHA-256 of normalized AST tokens (enables rename/clone detection across snapshots). |
| `modifiers_and_annotations` | `JSONB` | NO | `DEFAULT '{}'` | Decorators, annotations (`@Transactional`, `@Route`), async/static flags. |

### D4. `code_imports`
- **Purpose**: Captures file-level and scoped `import`, `require`, `use`, and `include` statements.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_code_imports_source (tenant_id, snapshot_id, source_file_id)`, `ix_code_imports_target (tenant_id, snapshot_id, resolved_target_file_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Import record ID. |
| `snapshot_id` | `UUID` | NO | `FK` | Snapshot anchor. |
| `source_file_id` | `UUID` | NO | `FK -> code_files` | File containing the import statement. |
| `resolved_target_file_id` | `UUID` | YES | `FK -> code_files` | Resolved internal file (`NULL` if third-party/stdlib). |
| `imported_module_expr` | `TEXT` | NO | | Raw module specifier string. |
| `imported_symbol_name` | `VARCHAR(255)` | YES | | Specific imported symbol (`*` or identifier). |
| `alias_name` | `VARCHAR(255)` | YES | | Local alias if renamed. |
| `is_external_package` | `BOOLEAN` | NO | `DEFAULT false` | True if external library dependency. |
| `line_number` | `INTEGER` | NO | | 1-based line number of import statement. |

### D5. `code_call_edges`
- **Purpose**: Static call graph edges between caller and callee `code_symbols`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_call_edges_caller (tenant_id, snapshot_id, caller_symbol_id)`, `ix_call_edges_callee (tenant_id, snapshot_id, callee_symbol_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Call edge ID. |
| `snapshot_id` | `UUID` | NO | `FK` | Snapshot anchor. |
| `caller_symbol_id` | `UUID` | NO | `FK -> code_symbols` | Invoking function/method/module symbol. |
| `callee_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Resolved internal target symbol (`NULL` if external/unresolved). |
| `unresolved_callee_expr` | `TEXT` | YES | | Receiver + method expression when `callee_symbol_id IS NULL`. |
| `resolution_certainty` | `VARCHAR(32)` | NO | | `'EXACT_STATIC' \| 'TYPE_INFERRED' \| 'DYNAMIC_AMBIGUOUS'`. |
| `call_site_line` | `INTEGER` | NO | | 1-based line number of invocation. |
| `call_site_column` | `INTEGER` | NO | `DEFAULT 0` | 0-based column of invocation. |

### D6. `code_type_hierarchies`
- **Purpose**: Tracks class inheritance (`EXTENDS`), interface realization (`IMPLEMENTS`), and PHP/Python mixin/trait composition.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_type_hier_sub (tenant_id, snapshot_id, sub_symbol_id)`, `ix_type_hier_super (tenant_id, snapshot_id, super_symbol_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Hierarchy edge ID. |
| `snapshot_id` | `UUID` | NO | `FK` | Snapshot anchor. |
| `sub_symbol_id` | `UUID` | NO | `FK -> code_symbols` | Subclass or implementing class. |
| `super_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Resolved base class/interface (`NULL` if external). |
| `unresolved_super_name` | `TEXT` | YES | | External base type name when `super_symbol_id IS NULL`. |
| `relation_kind` | `VARCHAR(32)` | NO | | `'EXTENDS' \| 'IMPLEMENTS' \| 'MIXIN' \| 'TRAIT_USE'`. |

### D7. `code_symbol_references`
- **Purpose**: Fine-grained cross-reference table recording reads, writes, instantiations, decorators, and type annotations referencing a `code_symbol`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_sym_refs_target (tenant_id, snapshot_id, referenced_symbol_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Reference ID. |
| `snapshot_id` | `UUID` | NO | `FK` | Snapshot anchor. |
| `referencing_file_id` | `UUID` | NO | `FK -> code_files` | File containing reference. |
| `enclosing_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Symbol scope where reference occurs. |
| `referenced_symbol_id` | `UUID` | NO | `FK -> code_symbols` | Target symbol being referenced. |
| `reference_kind` | `VARCHAR(32)` | NO | | `'READ' \| 'WRITE' \| 'INSTANTIATION' \| 'TYPE_ANNOTATION' \| 'DECORATOR'`. |
| `line_number` | `INTEGER` | NO | | 1-based line number. |
| `column_number` | `INTEGER` | NO | `DEFAULT 0` | 0-based column number. |

---

## Domain E: Technical, Data, API, Infrastructure & Runtime Intelligence (9 Tables)

### E1. `db_schemas`
- **Purpose**: Discovered relational/NoSQL database schemas extracted from SQL DDL scripts, Liquibase/Flyway/Alembic migrations, ORM models, or live catalog introspection.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, snapshot_id, schema_name)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | DB Schema ID. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `source_artifact_version_id` | `UUID` | YES | `FK -> artifact_versions` | Source DDL/migration file version. |
| `db_engine` | `VARCHAR(32)` | NO | | `'POSTGRESQL' \| 'MYSQL' \| 'ORACLE' \| 'MSSQL' \| 'SQLITE' \| 'MONGODB'`. |
| `schema_name` | `VARCHAR(128)` | NO | `UK` | Schema/database namespace name. |
| `discovery_source` | `VARCHAR(32)` | NO | | `'SQL_DDL' \| 'ORM_MODEL' \| 'MIGRATION_FILE' \| 'LIVE_CATALOG'`. |

### E2. `db_tables`
- **Purpose**: Discovered database tables, views, or collections within a `db_schema`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `db_schemas` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, db_schema_id, table_name)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | DB Table ID. |
| `db_schema_id` | `UUID` | NO | `FK -> db_schemas` | Parent schema. |
| `mapped_orm_symbol_id` | `UUID` | YES | `FK -> code_symbols` | ORM entity class mapped to this table. |
| `table_name` | `VARCHAR(255)` | NO | `UK` | Physical table/view name. |
| `table_kind` | `VARCHAR(32)` | NO | `DEFAULT 'TABLE'` | `'TABLE' \| 'VIEW' \| 'MATERIALIZED_VIEW' \| 'COLLECTION'`. |
| `comment_text` | `TEXT` | YES | | Extracted DDL table comment. |

### E3. `db_columns`
- **Purpose**: Columns belonging to a discovered `db_table`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `db_tables` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, db_table_id, column_name)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Column ID. |
| `db_table_id` | `UUID` | NO | `FK -> db_tables` | Parent table. |
| `column_name` | `VARCHAR(255)` | NO | `UK` | Column identifier. |
| `ordinal_position` | `INTEGER` | NO | | 1-based column order. |
| `data_type` | `VARCHAR(128)` | NO | | Declared SQL/ORM data type. |
| `is_nullable` | `BOOLEAN` | NO | `DEFAULT true` | Nullability flag. |
| `is_primary_key` | `BOOLEAN` | NO | `DEFAULT false` | PK membership flag. |
| `is_pii_candidate` | `BOOLEAN` | NO | `DEFAULT false` | Flagged by PII/sensitive data detector. |

### E4. `db_foreign_keys`
- **Purpose**: Explicit DDL foreign keys or ORM/naming-inferred table relationships in the analyzed legacy database.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `db_tables` deletion.
- **PK**: `(tenant_id, id)` | **FK**: `(tenant_id, source_table_id) -> db_tables`, `(tenant_id, target_table_id) -> db_tables`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Foreign key metadata ID. |
| `source_table_id` | `UUID` | NO | `FK` | Referencing child table. |
| `target_table_id` | `UUID` | NO | `FK` | Referenced parent table. |
| `constraint_name` | `VARCHAR(255)` | YES | | DDL constraint identifier. |
| `source_column_names` | `JSONB` | NO | | Ordered array of referencing column names. |
| `target_column_names` | `JSONB` | NO | | Ordered array of referenced column names. |
| `relation_origin` | `VARCHAR(32)` | NO | | `'EXPLICIT_DDL' \| 'ORM_RELATION' \| 'INFERRED_SQL_JOIN'`. |

### E5. `api_services`
- **Purpose**: Discovered HTTP/REST, GraphQL, gRPC, SOAP, or message consumer service boundaries.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, snapshot_id, service_name)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | API Service ID. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `service_name` | `VARCHAR(255)` | NO | `UK` | Service identifier. |
| `protocol` | `VARCHAR(32)` | NO | | `'REST' \| 'GRAPHQL' \| 'GRPC' \| 'SOAP' \| 'MESSAGE_CONSUMER'`. |
| `base_path` | `VARCHAR(255)` | YES | | Root URL prefix or queue namespace. |

### E6. `api_endpoints`
- **Purpose**: Individual API operations/routes discovered via OpenAPI specs or controller annotations (`@GetMapping`, `@app.post`, Express/Laravel routes).
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `api_services` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, api_service_id, http_method, route_pattern)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Endpoint ID. |
| `api_service_id` | `UUID` | NO | `FK -> api_services` | Parent API service. |
| `handler_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Controller/handler function symbol. |
| `http_method` | `VARCHAR(16)` | NO | | `'GET' \| 'POST' \| 'PUT' \| 'DELETE' \| 'PATCH' \| 'RPC' \| 'SUB'`. |
| `route_pattern` | `TEXT` | NO | `UK` | Normalized route path (`/api/v1/orders/{id}`). |
| `auth_required_inferred` | `BOOLEAN` | YES | | Whether middleware/decorator enforces auth. |
| `request_schema_json` | `JSONB` | YES | | Extracted payload schema. |
| `response_schema_json` | `JSONB` | YES | | Extracted response schema. |

### E7. `infra_resources`
- **Purpose**: Infrastructure-as-Code resources parsed from Dockerfiles, `docker-compose.yml`, Kubernetes manifests, Terraform, or CloudFormation.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Resource ID. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `source_artifact_version_id` | `UUID` | NO | `FK -> artifact_versions` | Source IaC file version. |
| `iac_tool` | `VARCHAR(32)` | NO | | `'DOCKERFILE' \| 'DOCKER_COMPOSE' \| 'KUBERNETES' \| 'TERRAFORM' \| 'CLOUDFORMATION'`. |
| `resource_type` | `VARCHAR(128)` | NO | | e.g., `aws_db_instance`, `k8s_deployment`. |
| `resource_name` | `VARCHAR(255)` | NO | | Declared resource identifier. |
| `configuration_attributes` | `JSONB` | NO | `DEFAULT '{}'` | Sanitized non-secret attributes (ports, images, replicas). |

### E8. `doc_sections`
- **Purpose**: Hierarchical sections parsed from Markdown, AsciiDoc, Sphinx/RST, or Javadoc/docstring manuals.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `artifact_versions` purge.
- **PK**: `(tenant_id, id)` | **FK**: `(tenant_id, artifact_version_id) -> artifact_versions`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Doc section ID. |
| `artifact_version_id` | `UUID` | NO | `FK` | Backing doc artifact version. |
| `parent_section_id` | `UUID` | YES | `FK -> doc_sections` | Parent section heading. |
| `heading_path` | `TEXT` | NO | | Breadcrumb heading path (`Architecture > Billing > Taxes`). |
| `heading_level` | `INTEGER` | NO | | Heading depth (`1..6`). |
| `start_line` | `INTEGER` | NO | | 1-based start line. |
| `end_line` | `INTEGER` | NO | | 1-based end line. |
| `content_markdown` | `TEXT` | NO | | Extracted section body text. |

### E9. `runtime_observations`
- **Purpose**: Optional ingested OpenTelemetry trace summaries, endpoint latency/error rates, or slow-query log patterns correlated to static entities.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Rolling retention (default 90 days) via `retention_policies`.
- **PK**: `(tenant_id, id)` | **FK**: `(tenant_id, application_id) -> applications`, `(tenant_id, environment_id) -> application_environments`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Observation ID. |
| `application_id` | `UUID` | NO | `FK` | Parent application. |
| `environment_id` | `UUID` | YES | `FK` | Source environment. |
| `linked_endpoint_id` | `UUID` | YES | `FK -> api_endpoints` | Correlated API endpoint. |
| `linked_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Correlated code symbol. |
| `observation_kind` | `VARCHAR(32)` | NO | | `'TRACE_SPAN' \| 'ERROR_RATE' \| 'LATENCY_P95' \| 'SLOW_QUERY' \| 'LOG_PATTERN'`. |
| `metric_payload` | `JSONB` | NO | | Aggregated telemetry metrics (PII-scrubbed). |
| `observed_window_start` | `TIMESTAMPTZ` | NO | | Start of telemetry window. |
| `observed_window_end` | `TIMESTAMPTZ` | NO | | End of telemetry window. |

---

## Domain F: Unified Knowledge Graph, Findings & Evidence (7 Tables)

### F1. `knowledge_entities`
- **Purpose**: Unified property-graph node table bridging deterministic code/DB/API artifacts and higher-level architectural components, business concepts, and external systems.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Versioned per `analysis_run_id`; historical versions preserved unless snapshot is purged.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, snapshot_id, analysis_run_id, entity_type, canonical_key)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Knowledge Entity ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing analysis run. |
| `source_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Populated when node represents a `code_symbol`. |
| `source_db_table_id` | `UUID` | YES | `FK -> db_tables` | Populated when node represents a `db_table`. |
| `source_api_endpoint_id` | `UUID` | YES | `FK -> api_endpoints` | Populated when node represents an `api_endpoint`. |
| `entity_type` | `VARCHAR(48)` | NO | | `'COMPONENT' \| 'SERVICE' \| 'MODULE' \| 'SYMBOL' \| 'DB_TABLE' \| 'API_ENDPOINT' \| 'INFRA_RESOURCE' \| 'BUSINESS_CONCEPT' \| 'EXTERNAL_SYSTEM'`. |
| `canonical_key` | `TEXT` | NO | `UK` | Deterministic natural key within run. |
| `title` | `VARCHAR(255)` | NO | | Human-readable node label. |
| `summary_description` | `TEXT` | YES | | Synthesized or extracted summary. |
| `origin_type` | `VARCHAR(32)` | NO | | `'DETERMINISTIC_PARSER' \| 'DETERMINISTIC_RULE' \| 'AI_INFERRED' \| 'HYBRID_AI_STATIC' \| 'HUMAN_AUTHORED'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | `DEFAULT 1.0000` | `0.0000` to `1.0000` (`CHECK (confidence_score BETWEEN 0 AND 1)`). |
| `review_status` | `VARCHAR(32)` | NO | `DEFAULT 'DRAFT_AI'` | `'DETERMINISTIC_FACT' \| 'DRAFT_AI' \| 'PENDING_REVIEW' \| 'APPROVED' \| 'MODIFIED_BY_HUMAN' \| 'REJECTED' \| 'SUPERSEDED'`. |
| `version_no` | `INTEGER` | NO | `DEFAULT 1` | Optimistic concurrency & revision counter. |
| `attributes_json` | `JSONB` | NO | `DEFAULT '{}'` | Computed graph centrality, PageRank, domain tags. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### F2. `knowledge_relationships`
- **Purpose**: Unified directed property-graph edge table connecting `knowledge_entities` across code, database, API, business rule, requirement, and test layers.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` or `analysis_runs` purge.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, analysis_run_id, source_entity_id, target_entity_id, relationship_type)` | **Indexes**: `ix_kr_source (tenant_id, snapshot_id, source_entity_id, relationship_type)`, `ix_kr_target (tenant_id, snapshot_id, target_entity_id, relationship_type)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Edge ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing analysis run. |
| `source_entity_id` | `UUID` | NO | `FK -> knowledge_entities` | Origin node. |
| `target_entity_id` | `UUID` | NO | `FK -> knowledge_entities` | Destination node. |
| `relationship_type` | `VARCHAR(48)` | NO | | Canonical verb (see `graph-relationship-catalogue.md`). |
| `origin_type` | `VARCHAR(32)` | NO | | `'DETERMINISTIC_PARSER' \| 'DETERMINISTIC_RULE' \| 'AI_INFERRED' \| 'HYBRID_AI_STATIC' \| 'HUMAN_AUTHORED'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | `DEFAULT 1.0000` | Confidence score (`0.0000`–`1.0000`). |
| `edge_weight` | `NUMERIC(8,4)` | NO | `DEFAULT 1.0000` | Coupling/call frequency weight for NetworkX projection. |
| `review_status` | `VARCHAR(32)` | NO | | Review lifecycle state. |
| `edge_metadata` | `JSONB` | NO | `DEFAULT '{}'` | Call counts, protocol details, CRUD flags. |

### F3. `findings`
- **Purpose**: First-class analytical assertions surfaced by LegacyIQ (architectural patterns, hidden risks, dead code, security flaws, or domain discoveries), each requiring source evidence links.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Preserved across runs with supersession lineage (`superseded_by_finding_id`).
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_findings_app_cat_status (tenant_id, application_id, finding_category, review_status)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Finding ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing analysis run. |
| `subject_entity_id` | `UUID` | YES | `FK -> knowledge_entities` | Primary subject node. |
| `producing_agent_run_id` | `UUID` | YES | `FK -> agent_runs` | Producing AI agent execution (`NULL` if deterministic rule). |
| `finding_category` | `VARCHAR(48)` | NO | | `'ARCHITECTURE' \| 'BUSINESS_RULE' \| 'REQUIREMENT' \| 'SECURITY_RISK' \| 'DEAD_CODE' \| 'PERFORMANCE' \| 'TECH_DEBT' \| 'MODERNIZATION'`. |
| `severity` | `VARCHAR(16)` | NO | `DEFAULT 'INFO'` | `'INFO' \| 'LOW' \| 'MEDIUM' \| 'HIGH' \| 'CRITICAL'`. |
| `title` | `VARCHAR(255)` | NO | | Concise finding headline. |
| `statement_markdown` | `TEXT` | NO | | Detailed analytical narrative. |
| `origin_type` | `VARCHAR(32)` | NO | | `'DETERMINISTIC_RULE' \| 'AI_INFERRED' \| 'HYBRID_AI_STATIC' \| 'HUMAN_AUTHORED'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | | Confidence score (`0.0000`–`1.0000`). |
| `review_status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING_REVIEW'` | `'DRAFT_AI' \| 'PENDING_REVIEW' \| 'APPROVED' \| 'MODIFIED_BY_HUMAN' \| 'REJECTED' \| 'SUPERSEDED'`. |
| `superseded_by_finding_id` | `UUID` | YES | `FK -> findings` | Points to newer finding version when superseded. |
| `version_no` | `INTEGER` | NO | `DEFAULT 1` | Revision counter. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### F4. `evidence_anchors`
- **Purpose**: **Immutable cryptographic pointer** to an exact span (file version, start/end lines, start/end columns, AST node path, and SHA-256 snippet hash) inside an `artifact_version`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: **Strictly Immutable**; retained as long as any finding, rule, requirement, or entity references it.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, artifact_version_id, locator_type, start_line, end_line, start_column, end_column, snippet_sha256)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Evidence Anchor ID. |
| `artifact_version_id` | `UUID` | NO | `FK -> artifact_versions` | Exact immutable file blob version. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot context where cited. |
| `locator_type` | `VARCHAR(32)` | NO | `DEFAULT 'LINE_RANGE'` | `'LINE_RANGE' \| 'BYTE_SPAN' \| 'AST_NODE_PATH' \| 'JSON_POINTER' \| 'DOC_HEADING'`. |
| `start_line` | `INTEGER` | NO | | 1-based inclusive start line. |
| `end_line` | `INTEGER` | NO | | 1-based inclusive end line (`CHECK (end_line >= start_line)`). |
| `start_column` | `INTEGER` | NO | `DEFAULT 0` | 0-based start column. |
| `end_column` | `INTEGER` | NO | `DEFAULT 0` | 0-based end column. |
| `ast_or_json_path` | `TEXT` | YES | | Optional structural selector (`ClassDef[OrderService]/FunctionDef[calculate_total]`). |
| `snippet_sha256` | `CHAR(64)` | NO | | SHA-256 hex digest of the exact cited source slice. |
| `excerpt_text` | `TEXT` | YES | | Bounded (`<= 2048 chars`), secret-redacted source excerpt (**Sensitive Customer IP**). |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Immutable creation timestamp. |

### F5. `finding_evidence_links`
- **Purpose**: Associates `evidence_anchors` with `findings`, `knowledge_entities`, `knowledge_relationships`, `business_rules`, or `requirements`, explaining *how* the source span supports or contradicts the claim.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades when the linked claim is purged.
- **PK**: `(tenant_id, id)` | **Constraint**: `CHECK (num_nonnulls(finding_id, knowledge_entity_id, knowledge_relationship_id, business_rule_id, requirement_id) >= 1)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Evidence Link ID. |
| `evidence_anchor_id` | `UUID` | NO | `FK -> evidence_anchors` | Cited immutable source span. |
| `finding_id` | `UUID` | YES | `FK -> findings` | Linked finding. |
| `knowledge_entity_id` | `UUID` | YES | `FK -> knowledge_entities` | Linked graph node. |
| `knowledge_relationship_id` | `UUID` | YES | `FK -> knowledge_relationships` | Linked graph edge. |
| `business_rule_id` | `UUID` | YES | `FK -> business_rules` | Linked business rule. |
| `requirement_id` | `UUID` | YES | `FK -> requirements` | Linked requirement. |
| `evidence_role` | `VARCHAR(32)` | NO | | `'PRIMARY_DEFINITION' \| 'CALL_SITE' \| 'CONFIG_BINDING' \| 'TEST_ASSERTION' \| 'DOC_CLAIM' \| 'CONTRADICTING_SOURCE'`. |
| `relevance_weight` | `NUMERIC(5,4)` | NO | `DEFAULT 1.0000` | Evidentiary weight (`0.0000`–`1.0000`). |
| `rationale_note` | `TEXT` | YES | | Why this span proves the claim. |

### F6. `knowledge_conflicts`
- **Purpose**: Explicit record of contradictions discovered between code and documentation, static vs. runtime behavior, or competing AI/human interpretations.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Preserved with audit resolution history.
- **PK**: `(tenant_id, id)` | **FK**: `(tenant_id, primary_evidence_anchor_id) -> evidence_anchors`, `(tenant_id, conflicting_evidence_anchor_id) -> evidence_anchors`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Conflict ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot context. |
| `conflict_type` | `VARCHAR(48)` | NO | | `'CODE_VS_DOC' \| 'AI_RUN_DIVERGENCE' \| 'STATIC_VS_RUNTIME' \| 'REQUIREMENT_CONTRADICTION'`. |
| `primary_entity_or_finding_id` | `UUID` | NO | | UUID of primary assertion. |
| `conflicting_entity_or_finding_id` | `UUID` | NO | | UUID of contradicting assertion. |
| `primary_evidence_anchor_id` | `UUID` | NO | `FK` | Anchor supporting primary claim (e.g. code). |
| `conflicting_evidence_anchor_id` | `UUID` | NO | `FK` | Anchor supporting conflicting claim (e.g. outdated doc). |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'OPEN'` | `'OPEN' \| 'RESOLVED_KEEP_PRIMARY' \| 'RESOLVED_KEEP_CONFLICTING' \| 'RESOLVED_MERGED' \| 'DISMISSED'`. |
| `resolved_by_user_id` | `UUID` | YES | `FK -> users(id)` | Human resolver. |
| `resolution_notes` | `TEXT` | YES | | Architect's rationale for resolution. |

### F7. `review_history`
- **Purpose**: **Append-only immutable audit log** of all human review state transitions (`APPROVE`, `MODIFY`, `REJECT`, `SUPERSEDE`) across findings, business rules, requirements, and entities.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: **Immutable** during project lifecycle; purged only on full project/tenant deletion.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_review_history_target (tenant_id, target_object_type, target_object_id, reviewed_at DESC)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Review history entry ID. |
| `target_object_type` | `VARCHAR(48)` | NO | | `'KNOWLEDGE_ENTITY' \| 'KNOWLEDGE_RELATIONSHIP' \| 'FINDING' \| 'BUSINESS_RULE' \| 'REQUIREMENT' \| 'MODERNIZATION_REC'`. |
| `target_object_id` | `UUID` | NO | | ID of reviewed record. |
| `reviewer_user_id` | `UUID` | NO | `FK -> users(id)` | Human reviewer. |
| `previous_status` | `VARCHAR(32)` | NO | | Prior `review_status`. |
| `new_status` | `VARCHAR(32)` | NO | | New `review_status`. |
| `previous_snapshot_json` | `JSONB` | NO | | Full serialized state before modification (preserves original AI output). |
| `updated_snapshot_json` | `JSONB` | NO | | Full serialized state after human review/edit. |
| `review_comment` | `TEXT` | YES | | Human rationale note. |
| `reviewed_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Immutable timestamp. |

---

## Domain G: Business Logic & Requirements Intelligence (6 Tables)

### G1. `business_domains`
- **Purpose**: High-level bounded contexts / functional business areas discovered or curated within an application (e.g., `Order Fulfillment`, `Tax & Invoicing`, `Customer Onboarding`).
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `applications` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, code)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Business domain ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `code` | `VARCHAR(64)` | NO | `UK` | Domain short key (`BILLING`). |
| `name` | `VARCHAR(255)` | NO | | Domain title. |
| `description` | `TEXT` | YES | | Bounded context responsibility summary. |
| `origin_type` | `VARCHAR(32)` | NO | | `'AI_INFERRED' \| 'HYBRID_AI_STATIC' \| 'HUMAN_AUTHORED'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | `DEFAULT 1.0000` | Confidence score. |
| `review_status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING_REVIEW'` | Review status. |

### G2. `business_processes`
- **Purpose**: End-to-end business workflows reconstructed from API entrypoints, batch jobs, and service call chains.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `applications` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, process_key)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Business process ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `business_domain_id` | `UUID` | YES | `FK -> business_domains` | Owning business domain. |
| `entry_entity_id` | `UUID` | YES | `FK -> knowledge_entities` | Triggering endpoint/job node. |
| `process_key` | `VARCHAR(96)` | NO | `UK` | Canonical workflow identifier. |
| `name` | `VARCHAR(255)` | NO | | Workflow name. |
| `workflow_summary` | `TEXT` | NO | | Step-by-step narrative description. |
| `ordered_step_entity_ids` | `JSONB` | NO | `DEFAULT '[]'` | Ordered list of `knowledge_entities.id` participating in the workflow. |
| `origin_type` | `VARCHAR(32)` | NO | | Origin classification. |
| `confidence_score` | `NUMERIC(5,4)` | NO | | Confidence score. |
| `review_status` | `VARCHAR(32)` | NO | | Review status. |

### G3. `business_rules`
- **Purpose**: Explicit domain invariants, calculations, branching conditions, eligibility rules, and state transitions extracted from legacy source code and stored procedures.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Versioned per `analysis_run_id`; review history preserved in `review_history`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, snapshot_id, rule_code)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Business rule ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing analysis run. |
| `business_domain_id` | `UUID` | YES | `FK -> business_domains` | Domain classification. |
| `knowledge_entity_id` | `UUID` | YES | `FK -> knowledge_entities` | Mirror node in the unified knowledge graph. |
| `rule_code` | `VARCHAR(64)` | NO | `UK` | Stable identifier (e.g. `BR-ORD-0042`). |
| `rule_category` | `VARCHAR(32)` | NO | | `'VALIDATION' \| 'CALCULATION' \| 'AUTHORIZATION' \| 'STATE_TRANSITION' \| 'INVARIANT' \| 'ROUTING'`. |
| `title` | `VARCHAR(255)` | NO | | Business rule headline. |
| `condition_expression` | `TEXT` | NO | | Structured trigger/precondition (`IF order_total > 10000 AND customer_tier == 'GOLD'`). |
| `action_consequence` | `TEXT` | NO | | Enforced business outcome (`APPLY 7.5% discount and require manager approval`). |
| `origin_type` | `VARCHAR(32)` | NO | | `'DETERMINISTIC_RULE' \| 'AI_INFERRED' \| 'HYBRID_AI_STATIC' \| 'HUMAN_AUTHORED'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | | Confidence score (`0.0000`–`1.0000`). |
| `review_status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING_REVIEW'` | Review status. |
| `version_no` | `INTEGER` | NO | `DEFAULT 1` | Revision counter. |

### G4. `requirements`
- **Purpose**: Reconstructed Functional and Non-Functional Requirements synthesized from business rules, API contracts, data constraints, and documentation.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Versioned and preserved across runs; changes tracked in `review_history`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, snapshot_id, req_code)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Requirement ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing analysis run. |
| `business_domain_id` | `UUID` | YES | `FK -> business_domains` | Business domain. |
| `knowledge_entity_id` | `UUID` | YES | `FK -> knowledge_entities` | Mirror node in unified graph. |
| `req_code` | `VARCHAR(64)` | NO | `UK` | Requirement identifier (e.g. `REQ-FUNC-0108`). |
| `req_type` | `VARCHAR(48)` | NO | | `'FUNCTIONAL' \| 'NON_FUNCTIONAL_SECURITY' \| 'NON_FUNCTIONAL_PERFORMANCE' \| 'DATA_CONSTRAINT' \| 'INTEGRATION_CONTRACT'`. |
| `priority` | `VARCHAR(16)` | NO | `DEFAULT 'MUST'` | `'MUST' \| 'SHOULD' \| 'COULD'`. |
| `title` | `VARCHAR(255)` | NO | | Requirement title. |
| `specification_statement` | `TEXT` | NO | | Normative requirement specification ("The system shall..."). |
| `origin_type` | `VARCHAR(32)` | NO | | Origin classification. |
| `confidence_score` | `NUMERIC(5,4)` | NO | | Confidence score (`0.0000`–`1.0000`). |
| `review_status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING_REVIEW'` | Review status. |
| `version_no` | `INTEGER` | NO | `DEFAULT 1` | Revision counter. |

### G5. `requirement_acceptance_criteria`
- **Purpose**: Testable Given/When/Then acceptance criteria decomposing a `requirement`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `requirements` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, requirement_id, criterion_order)` | **FK**: `(tenant_id, requirement_id) -> requirements`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Criterion ID. |
| `requirement_id` | `UUID` | NO | `FK` | Parent requirement. |
| `criterion_order` | `INTEGER` | NO | `UK` | Display sequence (`1, 2, ...`). |
| `given_clause` | `TEXT` | NO | | Precondition state. |
| `when_clause` | `TEXT` | NO | | Triggering event/action. |
| `then_clause` | `TEXT` | NO | | Verifiable expected postcondition. |
| `verification_method` | `VARCHAR(32)` | NO | `DEFAULT 'UNIT_TEST'` | `'UNIT_TEST' \| 'INTEGRATION_TEST' \| 'STATIC_CHECK' \| 'MANUAL_INSPECTION'`. |

### G6. `requirement_traceability_links`
- **Purpose**: Explicit forward/backward Requirements Traceability Matrix (RTM) table linking `requirements` to `business_rules`, `knowledge_entities`, `code_symbols`, and `test_cases`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `requirements` deletion.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_rtm_req (tenant_id, requirement_id)`, `ix_rtm_rule (tenant_id, business_rule_id)`, `ix_rtm_symbol (tenant_id, code_symbol_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Traceability Link ID. |
| `requirement_id` | `UUID` | NO | `FK -> requirements` | Traced requirement. |
| `business_rule_id` | `UUID` | YES | `FK -> business_rules` | Underlying business rule. |
| `knowledge_entity_id` | `UUID` | YES | `FK -> knowledge_entities` | Implementing graph entity. |
| `code_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Implementing code symbol. |
| `test_case_id` | `UUID` | YES | `FK -> test_cases` | Verifying test case. |
| `link_type` | `VARCHAR(48)` | NO | | `'DERIVED_FROM_RULE' \| 'IMPLEMENTED_BY_CODE' \| 'VERIFIED_BY_TEST' \| 'CONSTRAINED_BY_SCHEMA'`. |
| `origin_type` | `VARCHAR(32)` | NO | | Origin classification. |
| `confidence_score` | `NUMERIC(5,4)` | NO | `DEFAULT 1.0000` | Confidence score. |

---

## Domain H: Testing, Coverage & Modernization (5 Tables)

### H1. `test_suites`
- **Purpose**: Catalogs either existing test suites discovered in the repository or AI-generated characterization test suites.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, snapshot_id, suite_name)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Test suite ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `suite_name` | `VARCHAR(255)` | NO | `UK` | Suite name or relative file path. |
| `test_framework` | `VARCHAR(32)` | NO | | `'PYTEST' \| 'JUNIT' \| 'JEST' \| 'VITEST' \| 'PHPUNIT' \| 'GENERATED_BLUEPRINT'`. |
| `suite_origin` | `VARCHAR(32)` | NO | | `'EXISTING_IN_REPO' \| 'AI_GENERATED_BLUEPRINT'`. |

### H2. `test_cases`
- **Purpose**: Individual discovered test methods or AI-generated characterization/regression test specifications.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `test_suites` deletion.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, test_suite_id, test_key)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Test case ID. |
| `test_suite_id` | `UUID` | NO | `FK -> test_suites` | Parent suite. |
| `test_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Populated if test exists in source code. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing analysis run. |
| `test_key` | `VARCHAR(255)` | NO | `UK` | Qualified test identifier. |
| `title` | `VARCHAR(255)` | NO | | Human-readable test scenario name. |
| `test_kind` | `VARCHAR(32)` | NO | | `'UNIT' \| 'INTEGRATION' \| 'CHARACTERIZATION' \| 'REGRESSION' \| 'CONTRACT'`. |
| `scenario_description` | `TEXT` | NO | | Behavioral objective of the test. |
| `generated_code_blueprint` | `TEXT` | YES | | Suggested test code skeleton (never auto-executed by LegacyIQ). |
| `last_observed_status` | `VARCHAR(32)` | NO | `DEFAULT 'UNKNOWN'` | `'UNKNOWN' \| 'PASSED' \| 'FAILED' \| 'SKIPPED' \| 'NOT_EXECUTED_BLUEPRINT'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | `DEFAULT 1.0000` | Confidence score. |
| `review_status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING_REVIEW'` | Review status. |

### H3. `test_coverage_links`
- **Purpose**: Maps `test_cases` to the `code_symbols`, `business_rules`, and `requirements` they verify (via static call-graph reachability, imported cobertura/lcov reports, or AI traceability).
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `test_cases` deletion.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_test_cov_symbol (tenant_id, target_symbol_id)`, `ix_test_cov_req (tenant_id, target_requirement_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Coverage link ID. |
| `test_case_id` | `UUID` | NO | `FK -> test_cases` | Verifying test case. |
| `target_symbol_id` | `UUID` | YES | `FK -> code_symbols` | Covered symbol. |
| `target_business_rule_id` | `UUID` | YES | `FK -> business_rules` | Covered business rule. |
| `target_requirement_id` | `UUID` | YES | `FK -> requirements` | Covered requirement. |
| `coverage_source` | `VARCHAR(32)` | NO | | `'STATIC_CALL_GRAPH' \| 'IMPORT_TRACE' \| 'COVERAGE_REPORT' \| 'AI_TRACEABILITY'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | `DEFAULT 1.0000` | Confidence score. |

### H4. `technical_debt_items`
- **Purpose**: Quantified structural, architectural, or maintainability debt items linked to specific `knowledge_entities` and `findings`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `repository_snapshots` purge.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Technical debt ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing run. |
| `affected_entity_id` | `UUID` | YES | `FK -> knowledge_entities` | Subject node. |
| `finding_id` | `UUID` | YES | `FK -> findings` | Backing finding. |
| `debt_category` | `VARCHAR(48)` | NO | | `'HIGH_COMPLEXITY' \| 'CIRCULAR_DEPENDENCY' \| 'GOD_CLASS' \| 'MISSING_TESTS' \| 'DEPRECATED_DEPENDENCY' \| 'SQL_COUPLED_UI'`. |
| `severity` | `VARCHAR(16)` | NO | | `'LOW' \| 'MEDIUM' \| 'HIGH' \| 'CRITICAL'`. |
| `estimated_remediation_hours` | `INTEGER` | YES | | Estimated engineering hours. |
| `description` | `TEXT` | NO | | Technical debt diagnostic. |

### H5. `modernization_recommendations`
- **Purpose**: Evidence-backed refactoring, decomposition, or migration blueprints addressing identified `technical_debt_items` and architectural bottlenecks.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Preserved across runs with review history in `review_history`.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Recommendation ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Parent application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot anchor. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Producing run. |
| `addressed_debt_id` | `UUID` | YES | `FK -> technical_debt_items` | Target debt item. |
| `strategy_pattern` | `VARCHAR(48)` | NO | | `'STRANGLER_FIG' \| 'EXTRACT_DOMAIN_SERVICE' \| 'REPLACE_RAW_SQL' \| 'INTRODUCE_CHARACTERIZATION_TESTS' \| 'UPGRADE_RUNTIME'`. |
| `title` | `VARCHAR(255)` | NO | | Recommendation title. |
| `current_state_summary` | `TEXT` | NO | | Evidence-backed current problem statement. |
| `target_state_architecture` | `TEXT` | NO | | Proposed target design. |
| `step_by_step_plan_markdown` | `TEXT` | NO | | Phased execution blueprint. |
| `risk_level` | `VARCHAR(16)` | NO | | `'LOW' \| 'MEDIUM' \| 'HIGH'`. |
| `effort_tshirt` | `VARCHAR(8)` | NO | | `'XS' \| 'S' \| 'M' \| 'L' \| 'XL'`. |
| `confidence_score` | `NUMERIC(5,4)` | NO | | Confidence score. |
| `review_status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING_REVIEW'` | Review status. |

---

## Domain I: AI Orchestration & Telemetry (6 Tables)

### I1. `analysis_runs`
- **Purpose**: Master versioned execution record coordinating static parsing, vector indexing, graph projection, and AI agent pipelines against a `repository_snapshot`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Retained alongside `repository_snapshots`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, application_id, run_number)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Analysis Run ID. |
| `application_id` | `UUID` | NO | `FK -> applications` | Target application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Analyzed snapshot. |
| `analysis_scope_id` | `UUID` | NO | `FK -> analysis_scopes` | Applied scope configuration. |
| `triggered_by_user_id` | `UUID` | YES | `FK -> users(id)` | Initiating user. |
| `run_number` | `INTEGER` | NO | `UK` | Sequential run number per application. |
| `run_mode` | `VARCHAR(32)` | NO | | `'FULL_DISCOVERY' \| 'INCREMENTAL_STATIC' \| 'AI_ENRICHMENT_ONLY'`. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'QUEUED'` | `'QUEUED' \| 'RUNNING_STATIC' \| 'RUNNING_EMBEDDINGS' \| 'RUNNING_AI_AGENTS' \| 'COMPLETED' \| 'FAILED' \| 'CANCELLED'`. |
| `pipeline_versions_manifest` | `JSONB` | NO | `DEFAULT '{}'` | Exact versions of parsers, models, and LegacyIQ worker build. |
| `started_at` | `TIMESTAMPTZ` | YES | | Start timestamp. |
| `completed_at` | `TIMESTAMPTZ` | YES | | Completion timestamp. |

### I2. `agent_runs`
- **Purpose**: Tracks execution of individual specialized AI agents (`repo_cartographer`, `rule_extractor`, `req_synthesizer`, `test_architect`, `modernization_advisor`) within an `analysis_run`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `analysis_runs` purge.
- **PK**: `(tenant_id, id)` | **FK**: `(tenant_id, analysis_run_id) -> analysis_runs`, `(tenant_id, parent_agent_run_id) -> agent_runs`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Agent Run ID. |
| `analysis_run_id` | `UUID` | NO | `FK` | Parent analysis run. |
| `parent_agent_run_id` | `UUID` | YES | `FK` | Parent orchestrator agent run. |
| `agent_name` | `VARCHAR(64)` | NO | | Canonical agent identifier. |
| `agent_version` | `VARCHAR(32)` | NO | | Semantic version of agent logic. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING'` | `'PENDING' \| 'RUNNING' \| 'COMPLETED' \| 'FAILED' \| 'RETRYING'`. |
| `attempt_count` | `INTEGER` | NO | `DEFAULT 1` | Retry counter. |
| `input_context_refs` | `JSONB` | NO | `DEFAULT '{}'` | IDs of chunks, symbols, and graph slices supplied as input. |
| `output_summary_json` | `JSONB` | NO | `DEFAULT '{}'` | Counts of entities/rules/findings emitted. |
| `started_at` | `TIMESTAMPTZ` | YES | | Start timestamp. |
| `completed_at` | `TIMESTAMPTZ` | YES | | End timestamp. |

### I3. `agent_task_dependencies`
- **Purpose**: DAG edge table enforcing execution order and verification gates between upstream and downstream `agent_runs`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `analysis_runs` purge.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, upstream_agent_run_id, downstream_agent_run_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Dependency ID. |
| `analysis_run_id` | `UUID` | NO | `FK -> analysis_runs` | Parent analysis run. |
| `upstream_agent_run_id` | `UUID` | NO | `FK -> agent_runs` | Prerequisite agent run. |
| `downstream_agent_run_id` | `UUID` | NO | `FK -> agent_runs` | Dependent agent run. |
| `dependency_kind` | `VARCHAR(32)` | NO | `DEFAULT 'DATA_PREREQUISITE'` | `'DATA_PREREQUISITE' \| 'VERIFICATION_GATE'`. |

### I4. `prompt_templates`
- **Purpose**: Immutable versioned registry of system and user prompt templates and expected Pydantic/JSON output schemas used by AI agents.
- **Tenant Ownership**: Hybrid Global (`tenant_id IS NULL`) + Tenant-Customizable (`tenant_id IS NOT NULL`).
- **Retention**: Immutable once referenced by `model_invocations`.
- **PK**: `(id)` | **UK**: `(COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'), template_key, version_number)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | NO | `PK` | Prompt Template ID. |
| `tenant_id` | `UUID` | YES | `FK -> organizations(id)` | `NULL` for built-in platform prompts. |
| `template_key` | `VARCHAR(96)` | NO | | Logical prompt name (`extract_business_rules_v1`). |
| `version_number` | `INTEGER` | NO | | Monotonic version (`1, 2...`). |
| `target_agent_name` | `VARCHAR(64)` | NO | | Associated agent. |
| `template_sha256` | `CHAR(64)` | NO | | SHA-256 of system + user prompt template text. |
| `system_prompt_text` | `TEXT` | NO | | System instructions enforcing citation rules. |
| `user_prompt_template` | `TEXT` | NO | | Parameterized prompt template. |
| `output_json_schema` | `JSONB` | NO | | Enforced structured output JSON schema. |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Creation timestamp. |

### I5. `model_invocations`
- **Purpose**: Records every individual LLM call (local Ollama `qwen2.5-coder:3b` or fallback OpenRouter/Gemini/Groq), capturing latency, token usage, prompt digest, and schema validation outcome.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Governed by `retention_policies` (`AI_INVOCATION_LOGS`).
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_model_inv_agent (tenant_id, agent_run_id)`, `ix_model_inv_time (tenant_id, invoked_at DESC)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Invocation ID. |
| `agent_run_id` | `UUID` | NO | `FK -> agent_runs` | Parent agent run. |
| `prompt_template_id` | `UUID` | NO | `FK -> prompt_templates(id)` | Prompt template version used. |
| `provider_name` | `VARCHAR(32)` | NO | | `'ollama' \| 'openrouter' \| 'gemini' \| 'groq'`. |
| `model_identifier` | `VARCHAR(128)` | NO | | e.g., `'qwen2.5-coder:3b'`. |
| `is_fallback_invocation` | `BOOLEAN` | NO | `DEFAULT false` | True if routed to fallback provider. |
| `rendered_prompt_sha256` | `CHAR(64)` | NO | | SHA-256 of rendered input prompt. |
| `storage_payload_uri` | `TEXT` | YES | | Optional encrypted blob URI storing full prompt/completion (**Sensitive**). |
| `prompt_tokens` | `INTEGER` | NO | `DEFAULT 0` | Input token count. |
| `completion_tokens` | `INTEGER` | NO | `DEFAULT 0` | Output token count. |
| `total_tokens` | `INTEGER` | NO | `DEFAULT 0` | Total tokens consumed. |
| `latency_ms` | `INTEGER` | NO | | End-to-end inference duration in milliseconds. |
| `status` | `VARCHAR(32)` | NO | | `'SUCCESS' \| 'SCHEMA_VALIDATION_ERROR' \| 'HALLUCINATION_REJECTED' \| 'TIMEOUT' \| 'PROVIDER_ERROR'`. |
| `invoked_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Invocation timestamp. |

### I6. `agent_execution_events`
- **Purpose**: Fine-grained step telemetry emitted during `agent_runs` (tool calls, citation verification checks, hallucination rejections).
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Rolling 30–90 day retention via `retention_policies`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, agent_run_id, sequence_no)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Event ID. |
| `agent_run_id` | `UUID` | NO | `FK -> agent_runs` | Parent agent run. |
| `sequence_no` | `INTEGER` | NO | `UK` | Monotonic step index (`1, 2...`). |
| `event_type` | `VARCHAR(48)` | NO | | `'STEP_STARTED' \| 'TOOL_CALLED' \| 'EVIDENCE_VERIFIED' \| 'HALLUCINATION_REJECTED' \| 'STEP_COMPLETED'`. |
| `event_payload` | `JSONB` | NO | `DEFAULT '{}'` | Structured diagnostic metadata. |
| `occurred_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Event timestamp. |

---

## Domain J: Retrieval & Vector Indexing (3 Tables)

### J1. `embedding_model_versions`
- **Purpose**: Global catalog of embedding models and their vector dimensionality (defaulting to `sentence_transformers` / `BAAI/bge-small-en-v1.5` at `384` dimensions).
- **Tenant Ownership**: Global System Catalog (Read-only to tenants).
- **Retention**: Permanent system metadata.
- **PK**: `(id)` | **UK**: `(provider_name, model_name, model_revision)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | NO | `PK` | Embedding Model Version ID. |
| `provider_name` | `VARCHAR(64)` | NO | | `'sentence_transformers' \| 'ollama' \| 'openai_compatible'`. |
| `model_name` | `VARCHAR(128)` | NO | | `'BAAI/bge-small-en-v1.5'`. |
| `model_revision` | `VARCHAR(64)` | NO | `DEFAULT 'main'` | Model weights revision/hash. |
| `vector_dimension` | `INTEGER` | NO | `DEFAULT 384` | Embedding dimensionality (`384`). |
| `distance_metric` | `VARCHAR(32)` | NO | `DEFAULT 'COSINE'` | `'COSINE' \| 'L2' \| 'INNER_PRODUCT'`. |
| `is_active_default` | `BOOLEAN` | NO | `DEFAULT true` | Active default flag. |

### J2. `document_chunks`
- **Purpose**: Deterministic AST-aligned or section-aligned text segments extracted from `artifact_versions` for hybrid full-text and semantic vector retrieval.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Keyed to `artifact_version_id`; deduplicated across snapshots and purged only when `artifact_versions` is purged.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, artifact_version_id, chunk_strategy, chunk_index)` | **Indexes**: GIN `to_tsvector('english', chunk_text)` for hybrid lexical+vector search

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Document Chunk ID. |
| `artifact_version_id` | `UUID` | NO | `FK -> artifact_versions` | Exact immutable source artifact version. |
| `chunk_strategy` | `VARCHAR(48)` | NO | | `'AST_SYMBOL_WINDOW' \| 'MARKDOWN_SECTION' \| 'SLIDING_TOKEN_WINDOW'`. |
| `chunk_index` | `INTEGER` | NO | `UK` | 0-based index within `artifact_version_id`. |
| `start_line` | `INTEGER` | NO | | 1-based start line in `artifact_version_id`. |
| `end_line` | `INTEGER` | NO | | 1-based inclusive end line. |
| `token_count` | `INTEGER` | NO | | Token count of chunk. |
| `chunk_text_sha256` | `CHAR(64)` | NO | | SHA-256 of chunk text. |
| `chunk_text` | `TEXT` | NO | | Chunk content (**Sensitive Customer IP**). |
| `metadata_tags` | `JSONB` | NO | `DEFAULT '{}'` | Language, symbol kind, qualified name header, and `body_ast_hash` (snapshot-independent). |

### J3. `artifact_embeddings`
- **Purpose**: Stores `pgvector` embeddings (`vector(384)`) linked to `document_chunks` and `embedding_model_versions`.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Cascades on `document_chunks` deletion; can be rebuilt deterministically at any time.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, document_chunk_id, embedding_model_version_id)` | **Indexes**: HNSW `(embedding vector_cosine_ops)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Embedding ID. |
| `document_chunk_id` | `UUID` | NO | `FK -> document_chunks` | Source chunk. |
| `embedding_model_version_id` | `UUID` | NO | `FK -> embedding_model_versions(id)` | Model version that produced the vector. |
| `embedding` | `vector(384)` | NO | | 384-dimensional float32 vector (`pgvector`). |
| `created_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Generation timestamp. |

---

## Domain K: Reporting, Semantic Q&A, Export Governance, Audit & SaaS Commercials (11 Tables)

### K1. `audit_logs`
- **Purpose**: **Tamper-evident, append-only compliance ledger** recording security-sensitive and governance actions across the tenant.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Retained per regulatory/enterprise policy (default 365–2555 days); protected against `UPDATE`/`DELETE` via PostgreSQL trigger.
- **PK**: `(tenant_id, id)` | **Indexes**: `ix_audit_logs_tenant_time (tenant_id, occurred_at DESC)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Audit entry ID. |
| `actor_user_id` | `UUID` | YES | `FK -> users(id)` | Acting human user (`NULL` for system worker). |
| `actor_type` | `VARCHAR(32)` | NO | | `'USER' \| 'SYSTEM_WORKER' \| 'API_KEY' \| 'ADMIN_SUPPORT'`. |
| `action_code` | `VARCHAR(64)` | NO | | e.g., `'REPO_INGESTED'`, `'FINDING_APPROVED'`, `'DELETION_EXECUTED'`. |
| `target_resource_type` | `VARCHAR(64)` | NO | | Target entity table/domain. |
| `target_resource_id` | `UUID` | YES | | Target entity UUID. |
| `client_ip` | `INET` | YES | | Originating IP address (**PII**). |
| `prev_audit_hash` | `CHAR(64)` | YES | | SHA-256 of preceding audit row for this tenant. |
| `entry_hash` | `CHAR(64)` | NO | | SHA-256 chaining `prev_audit_hash + action + timestamp + payload`. |
| `metadata_diff` | `JSONB` | NO | `DEFAULT '{}'` | Redacted action metadata (never contains secrets/code). |
| `occurred_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Immutable event timestamp. |

### K2. `approval_requests`
- **Purpose**: Tracks formal sign-off workflows (e.g., approving baseline requirements for export, enabling external cloud LLM fallback, or authorizing repository purge).
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Retained alongside `audit_logs`.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Approval request ID. |
| `project_id` | `UUID` | YES | `FK -> projects` | Scoped project. |
| `requested_by_user_id` | `UUID` | NO | `FK -> users(id)` | Requesting user. |
| `decided_by_user_id` | `UUID` | YES | `FK -> users(id)` | Approving/rejecting user. |
| `request_type` | `VARCHAR(64)` | NO | | `'BASELINE_REQUIREMENTS_SIGN_OFF' \| 'EXTERNAL_LLM_FALLBACK_OPT_IN' \| 'DATA_PURGE_APPROVAL'`. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'PENDING'` | `'PENDING' \| 'APPROVED' \| 'REJECTED' \| 'EXPIRED'`. |
| `request_payload` | `JSONB` | NO | `DEFAULT '{}'` | Scope and parameters of request. |
| `decision_reason` | `TEXT` | YES | | Approver rationale. |
| `requested_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Request timestamp. |
| `decided_at` | `TIMESTAMPTZ` | YES | | Decision timestamp. |

### K3. `retention_policies`
- **Purpose**: Tenant-configurable data lifecycle rules per artifact category.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Active for tenant lifetime.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, artifact_category)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Policy ID. |
| `artifact_category` | `VARCHAR(48)` | NO | `UK` | `'RAW_SOURCE_BLOBS' \| 'SNAPSHOT_AST' \| 'AI_INVOCATION_LOGS' \| 'RUNTIME_OBSERVATIONS' \| 'AUDIT_LOGS'`. |
| `retain_days` | `INTEGER` | NO | | Retention window in days. |
| `max_snapshots_per_repo` | `INTEGER` | YES | | Maximum retained snapshots per repository. |
| `auto_purge_enabled` | `BOOLEAN` | NO | `DEFAULT false` | Whether background janitor purges expired items automatically. |
| `updated_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Last modified timestamp. |

### K4. `deletion_requests`
- **Purpose**: Tracks verifiable data erasure and crypto-shredding workflows for snapshots, repositories, projects, or full tenant offboarding.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Tombstone certificate record retained in compliance log after target data is purged.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Deletion request ID. |
| `requested_by_user_id` | `UUID` | NO | `FK -> users(id)` | Initiating administrator. |
| `deletion_scope` | `VARCHAR(32)` | NO | | `'SINGLE_SNAPSHOT' \| 'REPOSITORY' \| 'PROJECT' \| 'FULL_TENANT_OFFBOARDING'`. |
| `target_scope_id` | `UUID` | NO | | UUID of snapshot, repository, project, or tenant. |
| `status` | `VARCHAR(32)` | NO | `DEFAULT 'REQUESTED'` | `'REQUESTED' \| 'APPROVED' \| 'IN_PROGRESS' \| 'CRYPTO_SHREDDED' \| 'COMPLETED' \| 'FAILED'`. |
| `completion_certificate_sha256` | `CHAR(64)` | YES | | Signed hash of deletion manifest. |
| `requested_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Request timestamp. |
| `completed_at` | `TIMESTAMPTZ` | YES | | Completion timestamp. |

### K5. `tenant_subscriptions`
- **Purpose**: Commercial plan entitlements, LOC limits, and cloud AI provider opt-in gates for a tenant.
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Retained for billing/compliance lifecycle.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK, UK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Subscription ID. |
| `plan_code` | `VARCHAR(48)` | NO | `DEFAULT 'LOCAL_COMMUNITY'` | `'LOCAL_COMMUNITY' \| 'CONSULTING_TEAM' \| 'ENTERPRISE_SAAS'`. |
| `billing_status` | `VARCHAR(32)` | NO | `DEFAULT 'ACTIVE'` | `'ACTIVE' \| 'TRIALING' \| 'PAST_DUE' \| 'CANCELLED'`. |
| `max_repositories_allowed` | `INTEGER` | NO | `DEFAULT 10` | Repository quota limit. |
| `max_loc_allowed` | `BIGINT` | NO | `DEFAULT 5000000` | Maximum analyzed lines of code. |
| `allow_cloud_llm_providers` | `BOOLEAN` | NO | `DEFAULT false` | Must be explicitly `true` before any code snippet leaves local Ollama. |
| `current_period_start` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Billing period start. |
| `current_period_end` | `TIMESTAMPTZ` | YES | | Billing period end. |

### K6. `tenant_usage_quotas`
- **Purpose**: Monthly metered resource consumption (analyzed LOC, stored vector chunks, local vs. cloud LLM tokens, object storage bytes).
- **Tenant Ownership**: Direct `tenant_id`.
- **Retention**: Retained for billing history.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, billing_month)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Meter record ID. |
| `billing_month` | `DATE` | NO | `UK` | First day of billing month (`2026-11-01`). |
| `repositories_count` | `INTEGER` | NO | `DEFAULT 0` | Active repositories count. |
| `analyzed_loc_count` | `BIGINT` | NO | `DEFAULT 0` | Cumulative LOC analyzed in period. |
| `vector_chunks_stored` | `BIGINT` | NO | `DEFAULT 0` | Active vector embeddings stored. |
| `local_llm_tokens_used` | `BIGINT` | NO | `DEFAULT 0` | Tokens processed via local Ollama. |
| `cloud_llm_tokens_used` | `BIGINT` | NO | `DEFAULT 0` | Tokens processed via cloud providers. |
| `object_storage_bytes_used` | `BIGINT` | NO | `DEFAULT 0` | Encrypted blob storage footprint. |
| `updated_at` | `TIMESTAMPTZ` | NO | `DEFAULT now()` | Last meter update timestamp. |

### K7. `qa_conversations`
- **Purpose**: Tenant-, project-, and snapshot-scoped conversational Semantic Q&A sessions.
- **Tenant Ownership**: Direct `tenant_id`.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Conversation ID. |
| `project_id` | `UUID` | NO | `FK -> projects` | Project RBAC boundary. |
| `application_id` | `UUID` | NO | `FK -> applications` | Target application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Grounded repository snapshot. |
| `created_by_user_id` | `UUID` | YES | `FK -> users(id)` | Creator user. |
| `title` | `VARCHAR(255)` | NO | | Session title. |
| `conversation_status` | `VARCHAR(32)` | NO | `DEFAULT 'ACTIVE'` | `'ACTIVE' \| 'ARCHIVED'`. |

### K8. `qa_messages`
- **Purpose**: User questions and assistant responses within a `qa_conversations` session, separating `direct_facts_json` from `inferred_explanations_json` and storing source `citations_json`.
- **Tenant Ownership**: Direct `tenant_id`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, conversation_id, sequence_no)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Message ID. |
| `conversation_id` | `UUID` | NO | `FK -> qa_conversations` | Parent conversation. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Snapshot context. |
| `sequence_no` | `INTEGER` | NO | `UK` | 1-based message order. |
| `role` | `VARCHAR(32)` | NO | | `'USER' \| 'ASSISTANT'`. |
| `question_intent` | `VARCHAR(64)` | YES | | Classified query intent (`ARCHITECTURE_DISCOVERY`, etc.). |
| `content_markdown` | `TEXT` | NO | | Grounded markdown message. |
| `direct_facts_json` | `JSONB` | NO | `DEFAULT '[]'` | Persisted facts separated from inference. |
| `inferred_explanations_json` | `JSONB` | NO | `DEFAULT '[]'` | Inferred explanations and review posture. |
| `citations_json` | `JSONB` | NO | `DEFAULT '[]'` | File path, line range, SHA-256, and excerpt citations. |
| `insufficient_evidence` | `BOOLEAN` | NO | `DEFAULT false` | `true` when snapshot lacks supporting evidence. |

### K9. `intelligence_reports`
- **Purpose**: Master record for any of the 11 structured application intelligence report types.
- **Tenant Ownership**: Direct `tenant_id`.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Report ID. |
| `project_id` | `UUID` | NO | `FK -> projects` | Project RBAC boundary. |
| `application_id` | `UUID` | NO | `FK -> applications` | Target application. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Target snapshot. |
| `report_type` | `VARCHAR(64)` | NO | | One of the 11 canonical `REPORT_TYPE_CATALOG` keys. |
| `title` | `VARCHAR(255)` | NO | | Report title. |
| `current_version_no` | `INTEGER` | NO | `DEFAULT 1` | Active version number. |
| `lifecycle_status` | `VARCHAR(32)` | NO | `DEFAULT 'GENERATED'` | `'DRAFT' \| 'GENERATED' \| 'SUBMITTED_FOR_REVIEW' \| 'APPROVED' \| 'REJECTED' \| 'ARCHIVED'`. |

### K10. `intelligence_report_versions`
- **Purpose**: Versioned report payloads. Once `lifecycle_status = 'APPROVED'`, `is_immutable = true` is permanently locked; subsequent edits create `version_no + 1`.
- **Tenant Ownership**: Direct `tenant_id`.
- **PK**: `(tenant_id, id)` | **UK**: `(tenant_id, report_id, version_no)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Report Version ID. |
| `report_id` | `UUID` | NO | `FK -> intelligence_reports` | Parent report. |
| `snapshot_id` | `UUID` | NO | `FK -> repository_snapshots` | Source snapshot. |
| `version_no` | `INTEGER` | NO | `UK` | Monotonic version number (`1, 2, ...`). |
| `lifecycle_status` | `VARCHAR(32)` | NO | | Version lifecycle status. |
| `is_immutable` | `BOOLEAN` | NO | `DEFAULT false` | `true` for `APPROVED` versions (never overwritten). |
| `executive_summary_markdown` | `TEXT` | NO | | Executive summary. |
| `sections_json` | `JSONB` | NO | `DEFAULT '[]'` | Structured report sections. |
| `evidence_refs_json` | `JSONB` | NO | `DEFAULT '[]'` | Evidence anchor citations. |
| `content_sha256` | `CHAR(64)` | NO | | Cryptographic digest of canonical report content. |

### K11. `report_exports`
- **Purpose**: Controlled multi-format export artifacts (`PDF`, `DOCX`, `XLSX`, `JSON`) with tenant storage isolation, download tracking, and `AuditLog` linkage.
- **Tenant Ownership**: Direct `tenant_id`.
- **PK**: `(tenant_id, id)`

| Column | Type | Null | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenant_id` | `UUID` | NO | `PK, FK` | Owning organization. |
| `id` | `UUID` | NO | `PK` | Export ID. |
| `project_id` | `UUID` | NO | `FK -> projects` | Project RBAC boundary. |
| `report_id` | `UUID` | NO | `FK -> intelligence_reports` | Exported report. |
| `report_version_id` | `UUID` | NO | `FK -> intelligence_report_versions` | Exact exported report version. |
| `export_format` | `VARCHAR(16)` | NO | | `'PDF' \| 'DOCX' \| 'XLSX' \| 'JSON'`. |
| `file_name` | `VARCHAR(255)` | NO | | Generated attachment filename. |
| `file_size_bytes` | `BIGINT` | NO | | Export artifact byte size. |
| `content_sha256` | `CHAR(64)` | NO | | SHA-256 of exported binary. |
| `storage_object_uri` | `TEXT` | NO | | Tenant-isolated blob URI. |
| `download_count` | `INTEGER` | NO | `DEFAULT 0` | Metered download counter. |


