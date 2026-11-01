# LegacyIQ — Wave 1 Pre-Implementation Audit & Preflight Report (Stage 0)

**Document ID**: `W1-00`  
**Status**: Completed & Verified (Zero Destructive Conflicts Detected)  
**Target Workspace**: `C:\LegacyIQ`  
**External Infrastructure**: `C:\LegacyIQ-infrastructure` (Preserved Untouched)

---

## 1. Existing Implementation Inventory (M0 Baseline)

### Backend (`C:\LegacyIQ\backend`)
- **Entry Point**: [`app/main.py`](file:///C:/LegacyIQ/backend/app/main.py) — FastAPI `0.162.0` application with lifespan logging, credential masking, and CORS middleware.
- **Configuration**: [`app/core/config.py`](file:///C:/LegacyIQ/backend/app/core/config.py) — Loads [`C:\LegacyIQ\.env.local`](file:///C:/LegacyIQ/.env.local) as the authoritative configuration file.
- **Database & Cache**:
  - [`app/db/base.py`](file:///C:/LegacyIQ/backend/app/db/base.py) — Defines SQLAlchemy 2.0 `Base`, `TimestampMixin`, and `TenantScopedMixin`.
  - [`app/db/session.py`](file:///C:/LegacyIQ/backend/app/db/session.py) — Defines `engine`, `SessionLocal`, `get_db()`, and `check_database_and_pgvector_health()`.
  - [`app/db/redis.py`](file:///C:/LegacyIQ/backend/app/db/redis.py) — Defines `get_redis_client()` and `check_redis_health()`.
- **Models & Migrations**:
  - [`app/models/__init__.py`](file:///C:/LegacyIQ/backend/app/models/__init__.py) — Exports `Base` (no domain models created yet).
  - [`alembic/env.py`](file:///C:/LegacyIQ/backend/alembic/env.py) — Wired to `settings.DATABASE_URL` and `Base.metadata`.
  - `alembic/versions/` — Empty (`.gitkeep` only).
- **Health Endpoints Verified Operational (`HTTP 200 OK`)**:
  - `GET /api/v1/health`
  - `GET /api/v1/health/database` (`latency_ms: 3084.79`, `pgvector: 0.8.7`)
  - `GET /api/v1/health/redis` (`latency_ms: 2051.10`, `ping: PONG`)
  - `GET /api/v1/health/ollama` (`latency_ms: 2329.44`, `model: qwen2.5-coder:3b`)

### Frontend (`C:\LegacyIQ\frontend`)
- Next.js `15.1.7` (App Router, TypeScript `5.7.3`, Tailwind CSS `3.4.17`, TanStack Query `5.66.0`, React Flow `@xyflow/react` `12.4.2`, Recharts `2.15.4`, React Hook Form `7.54.2`, Zod `3.24.2`).
- Existing routes preserved: `/`, `/dashboard`, `/repositories`, `/requirements`, `/architecture`, `/settings`.

---

## 2. Live PostgreSQL Database & Alembic Migration State

Read-only introspection executed against `localhost:5432/legacyiq`:
- **Existing Tables in `public` Schema**: `[]` (**0 tables** — completely clean database).
- **Existing `alembic_version` Table**: None (no migrations applied yet).
- **Installed PostgreSQL Extensions**:
  - `plpgsql` (`v1.0`)
  - `vector` (`v0.8.7` — `pgvector` confirmed active)
- **Existing Database Roles**:
  - `legacyiq_admin` (`rolsuper = True`, `rolbypassrls = True`).
  - *Security Note for Stage 1 & Stage 2*: Because `legacyiq_admin` is a superuser with `BYPASSRLS`, PostgreSQL will bypass RLS policies unless the transaction switches to a non-superuser, `NOBYPASSRLS` application runtime role. Stage 1 migration will create the `legacyiq_app` (`NOLOGIN NOBYPASSRLS NOSUPERUSER`) role and grant table permissions on `public`, and Stage 2's tenant-scoped session manager will execute `SET LOCAL ROLE legacyiq_app` alongside `SELECT set_config('app.current_tenant_id', :tenant_id, true)` on every tenant transaction.

---

## 3. Canonical Table Count Reconciliation (`33 + 21 + 17 = 71`)

### Root Cause of the `32 + 21 + 17 = 70` vs. `71` Discrepancy
In the earlier summary text of `d3-decisions-register.md` (`D3-PDEC-Q5`), Wave 1 was listed as:
> *"Domain A (8 tables), Domain B (6 tables), Domain C (8 tables), Domain D (7 tables), Domain J (3 tables), plus `analysis_runs` from Domain I (1 table)"*

Summing those exact domain counts yields:
$$8\text{ (Domain A)} + 6\text{ (Domain B)} + 8\text{ (Domain C)} + 7\text{ (Domain D)} + 3\text{ (Domain J)} + 1\text{ (\texttt{analysis\_runs})} = \mathbf{33\text{ tables}}$$
(not `32`).

### Reconciled Canonical Wave Breakdown (Matches 100% of `data-dictionary.md`, `complete-erd.md`, and `tenant-ownership-matrix.md`)

| Migration Wave | Domains Included | Table Count | Cumulative Total |
| :--- | :--- | :---: | :---: |
| **Wave 1 (Current Scope)** | Domain A (`8`) + Domain B (`6`) + Domain C (`8`) + Domain D (`7`) + Domain I `analysis_runs` (`1`) + Domain J (`3`) | **33** | 33 |
| **Wave 2 (Deferred to M2)** | Domain E (`9`) + Domain F (`7`) + Remaining Domain I (`5`) | **21** | 54 |
| **Wave 3 (Deferred to M3+)** | Domain G (`6`) + Domain H (`5`) + Domain K (`6`) | **17** | **71** |

Both [d3-decisions-register.md](file:///C:/LegacyIQ/docs/database/d3-decisions-register.md) and [d3-review-report.md](file:///C:/LegacyIQ/docs/database/d3-review-report.md) have been updated to reflect `33 + 21 + 17 = 71` and mark `D3-PDEC-Q1` through `D3-PDEC-Q5` as `APPROVED`.

---

## 4. Exact 33-Table Wave 1 Inventory

### Domain A: Identity & Multi-Tenancy (8 Tables)
1. `organizations` (`TENANT_ROOT`, PK `(id)`)
2. `users` (`GLOBAL_SYSTEM`, PK `(id)`)
3. `roles` (`HYBRID_CATALOG`, PK `(id)`)
4. `permissions` (`GLOBAL_SYSTEM`, PK `(id)`)
5. `role_permissions` (`GLOBAL_SYSTEM`, PK `(role_id, permission_id)`)
6. `organization_memberships` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
7. `teams` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
8. `team_memberships` (`TENANT_DIRECT`, PK `(tenant_id, id)`)

### Domain B: Workspace, Project & Application Scope (6 Tables)
9. `workspaces` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
10. `projects` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
11. `project_memberships` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
12. `applications` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
13. `application_environments` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
14. `analysis_scopes` (`TENANT_DIRECT`, PK `(tenant_id, id)`)

### Domain C: Source Connectors & Immutable Ingestion (8 Tables)
15. `source_connectors` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
16. `repositories` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
17. `repository_branches` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
18. `repository_commits` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
19. `repository_snapshots` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
20. `artifacts` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
21. `artifact_versions` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
22. `ingestion_jobs` (`TENANT_DIRECT`, PK `(tenant_id, id)`)

### Domain I (Wave 1 Foundation Anchor — 1 Table)
23. `analysis_runs` (`TENANT_DIRECT`, PK `(tenant_id, id)`)

### Domain D: Deterministic Code Intelligence (7 Tables)
24. `code_modules` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
25. `code_files` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
26. `code_symbols` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
27. `code_imports` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
28. `code_call_edges` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
29. `code_type_hierarchies` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
30. `code_symbol_references` (`TENANT_DIRECT`, PK `(tenant_id, id)`)

### Domain J: Retrieval & Vector Foundation (3 Tables)
31. `embedding_model_versions` (`GLOBAL_SYSTEM`, PK `(id)`)
32. `document_chunks` (`TENANT_DIRECT`, PK `(tenant_id, id)`)
33. `artifact_embeddings` (`TENANT_DIRECT`, PK `(tenant_id, id)`, `embedding vector(384)`)

*(Breakdown of the 33 Wave 1 tables by ownership class: `1 TENANT_ROOT`, `27 TENANT_DIRECT`, `1 HYBRID_CATALOG` [`roles`], `4 GLOBAL_SYSTEM` [`users`, `permissions`, `role_permissions`, `embedding_model_versions`].)*

---

## 5. Dependency Analysis & Ordered Alembic Migration Plan

Rather than one monolithic migration, Wave 1 DDL will be structured into **3 ordered, reversible Alembic migrations**:
1. **`0001_wave1_identity_and_projects`**:
   - Creates `app_current_tenant_id()` SQL function, `legacyiq_app` (`NOBYPASSRLS`) role, Domain A (`8` tables), and Domain B (`6` tables), plus the hybrid-catalog tenant validation trigger on `organization_memberships` and `project_memberships`.
2. **`0002_wave1_ingestion_and_code_intel`**:
   - Creates Domain C (`8` tables), `analysis_runs` (`1` table), and Domain D (`7` tables) with composite `(tenant_id, ...)` foreign keys, partial unique active-run index `ux_active_analysis_run_per_snapshot`, and `pg_trgm` symbol search index.
3. **`0003_wave1_retrieval_and_rls_security`**:
   - Creates Domain J (`3` tables: `embedding_model_versions`, `document_chunks` with generated `search_tsv` GIN index, `artifact_embeddings` with `vector(384)` HNSW cosine index), enables `ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on all tenant-owned tables, creates RLS policies for `legacyiq_app`, and seeds default RBAC roles/permissions and the `BAAI/bge-small-en-v1.5` (`384`-dim) embedding model record.

---

## 6. Risks, Blockers & Implementation Sequence

- **Destructive Schema/Migration Conflicts**: **None.** Database is empty (`PUBLIC_TABLES: []`) and ready for clean forward migration.
- **Local Embedding Dependency (`sentence-transformers`)**: Installed in host Python `3.10.6` (`C:\Users\Saheel\AppData\Local\Programs\Python\Python310`) with local HuggingFace cache present (`~/.cache/huggingface`). Enabling `include-system-site-packages = true` in `backend/.venv/pyvenv.cfg` (and installing `python-multipart` for FastAPI ZIP `UploadFile` handling) makes `sentence_transformers` and `torch` immediately available inside `backend/.venv` without downloading gigabytes of packages.
- **Execution Sequence**:
  - **Stage 1**: SQLAlchemy 2.0 Wave 1 models (33 tables) + 3 ordered Alembic migrations + schema & rollback verification.
  - **Stage 2**: Tenant security (`TenantContext`, `SET LOCAL ROLE legacyiq_app`, `SET LOCAL app.current_tenant_id`, project RBAC guards, Redis cache key namespacing, and negative isolation tests).
  - **Stage 3**: Tenant-isolated local blob storage adapter + ZIP repository upload & ingestion lifecycle service.
  - **Stage 4**: Multi-language deterministic parser registry (Python AST + regex/structural lexical parsers for Java, JS/TS, PHP) extracting modules, files, symbols, imports, call edges, type hierarchies, and symbol references.
  - **Stage 5**: AST-aware / sliding-window document chunking + `BAAI/bge-small-en-v1.5` (384-dim) vector embedding generation + hybrid RRF retrieval.
  - **Stage 6**: Versioned FastAPI `/api/v1` endpoints for organizations, workspaces, projects, applications, repository ZIP upload, snapshots, ingestion jobs, code discovery, and evidence-linked hybrid search.
  - **Stage 7**: Frontend integration across `/repositories`, `/dashboard`, `/architecture`, and search views.
  - **Stage 8 & 9**: Comprehensive test suite execution and Wave 1 implementation documentation.

