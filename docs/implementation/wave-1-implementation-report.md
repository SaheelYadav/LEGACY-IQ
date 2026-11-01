# LegacyIQ — Wave 1 Implementation Report
## Core Platform, Database Foundation & Source Intelligence

**Date**: 2026-11-01  
**Status**: Completed & Verified  
**Alembic Head Revision**: `0003_wave1_rls_vec`  
**Database Engine**: PostgreSQL 17 + `pgvector` `0.8.7` (`localhost:5432/legacyiq`)  
**Cache & Queue Engine**: Redis 7 (`localhost:6380/0`)  
**Local AI Runtime**: Ollama `qwen2.5-coder:3b` (`http://localhost:11434`) + `BAAI/bge-small-en-v1.5` (384 dimensions)

---

## 1. Executive Summary

Wave 1 transforms LegacyIQ from its M0 scaffold and D3 database specification into a live, multi-tenant enterprise discovery platform with:

1. **33 Canonical Wave 1 Tables** deployed via three dependency-ordered Alembic migrations (`0001_wave1_identity`, `0002_wave1_code_intel`, `0003_wave1_rls_vec`), reconciling the D3 wave breakdown ($33 + 21 + 17 = 71$ canonical tables).
2. **Non-Bypassable PostgreSQL Row-Level Security (RLS)** enforced via a dedicated non-superuser role (`legacyiq_app`) and transaction-scoped `SET LOCAL ROLE legacyiq_app` + `set_config('app.current_tenant_id', ...)` across all 29 tenant/hybrid-scoped tables, paired with composite `(tenant_id, id)` primary/foreign keys and cross-tenant role guard triggers.
3. **Hardened Source Archive Ingestion** supporting ZIP uploads with Zip-Slip path traversal defense, symlink rejection, per-file/total uncompressed byte limits, compression-ratio bomb guards, SHA-256 content addressing, and tenant-isolated blob storage (`backend/storage_vault/<tenant_id>/blobs/`).
4. **Deterministic Multi-Language Code Intelligence** extracting modules, files, symbols (with normalized AST SHA-256 hashes, line/column spans, and cyclomatic complexity), imports (with internal file resolution), static call edges, type hierarchies, and symbol references across **Python, Java, TypeScript, JavaScript, and PHP** without ever executing uploaded code.
5. **Hybrid Reciprocal Rank Fusion (RRF) Retrieval** combining 384-dimensional `pgvector` HNSW cosine similarity (`ix_artifact_embeddings_hnsw_cosine`) with PostgreSQL generated `tsvector` GIN full-text search (`ix_doc_chunks_search_tsv`), strictly scoped by `tenant_id` and `snapshot_id`.
6. **Versioned `/api/v1` Endpoints & Next.js Frontend Integration** wiring `/dashboard`, `/repositories`, and `/architecture` to live backend APIs while preserving all M0 health checks.

---

## 2. Reconciled Wave 1 Table Inventory (33 Canonical Tables)

| Domain | Count | Tables Implemented |
| :--- | :---: | :--- |
| **Domain A — Identity & Tenancy** | 8 | `organizations`, `users`, `roles`, `permissions`, `role_permissions`, `organization_memberships`, `teams`, `team_memberships` |
| **Domain B — Workspaces, Projects & Applications** | 6 | `workspaces`, `projects`, `project_memberships`, `applications`, `application_environments`, `analysis_scopes` |
| **Domain C — Source Connectors & Immutable Ingestion** | 8 | `source_connectors`, `repositories`, `repository_branches`, `repository_commits`, `repository_snapshots`, `artifacts`, `artifact_versions`, `ingestion_jobs` |
| **Domain D — Deterministic Code Intelligence** | 7 | `code_modules`, `code_files`, `code_symbols`, `code_imports`, `code_call_edges`, `code_type_hierarchies`, `code_symbol_references` |
| **Domain I (Wave 1 Subset) — Analysis Execution** | 1 | `analysis_runs` |
| **Domain J — Retrieval & Vector Indexing** | 3 | `embedding_model_versions`, `document_chunks`, `artifact_embeddings` |
| **Total Wave 1 Canonical Tables** | **33** | Plus `alembic_version` (schema tracking) |

---

## 3. Stage-by-Stage Implementation Summary

### Stage 0 — Pre-Implementation Audit
- Inspected existing backend/frontend codebase, D3 documentation suite, and live PostgreSQL/Redis/Ollama infrastructure.
- Documented baseline findings and reconciled the 33-table Wave 1 count in `docs/implementation/wave-1-preflight-report.md`, `docs/database/d3-decisions-register.md`, and `docs/database/d3-review-report.md`.

### Stage 1 — SQLAlchemy 2.0 Models & Alembic Migrations
- Implemented all 33 SQLAlchemy 2.0 models under `backend/app/models/`:
  - `identity.py`, `projects.py`, `ingestion.py`, `code_intelligence.py`, `retrieval.py`
- Created and applied 3 ordered Alembic migrations in `backend/alembic/versions/`:
  - `0001_wave1_identity_and_projects.py`
  - `0002_wave1_ingestion_and_code_intel.py`
  - `0003_wave1_retrieval_and_rls_security.py`

### Stage 2 — Tenant Security, RLS & Project RBAC
- Implemented `TenantContext`, `ProjectAccessContext`, `TaskEnvelope` (HMAC-SHA256 signed), `build_tenant_cache_key`, `verify_and_activate_tenant_context`, and `verify_project_access` in `backend/app/core/security.py`.
- Implemented `activate_tenant_rls`, `activate_unscoped_rls_role`, and `tenant_db_session` in `backend/app/db/session.py`.

### Stage 3 — Source Ingestion Foundation
- Implemented `TenantObjectStorage` in `backend/app/integrations/storage.py` storing content-addressed blobs under per-tenant directories (`storage_vault/<tenant_id>/blobs/<sha[:2]>/<sha>`).
- Implemented `IngestionService` in `backend/app/services/ingestion_service.py` with full ZIP archive safety validation and idempotent snapshot reuse.

### Stage 4 — Deterministic Code Intelligence
- Implemented `ParserRegistry`, `PythonAstParser`, and `BraceStructuralParser` in `backend/app/analysis/parser_registry.py`.
- Implemented `CodeIntelligenceService` in `backend/app/services/code_intelligence_service.py` populating all 7 Domain D tables.

### Stage 5 — Embedding & Retrieval Foundation
- Implemented `RetrievalService` in `backend/app/services/retrieval_service.py` supporting `AST_SYMBOL_WINDOW`, `MARKDOWN_SECTION`, and `SLIDING_WINDOW` chunking, 384-d `BAAI/bge-small-en-v1.5` embeddings, and Hybrid RRF search (`k=60`).

### Stage 6 & Stage 7 — FastAPI `/api/v1` Endpoints & Next.js Frontend
- Created Pydantic v2 schemas in `backend/app/schemas/platform.py` and FastAPI routers under `backend/app/api/v1/endpoints/`.
- Integrated live Wave 1 APIs into `frontend/src/lib/api.ts`, `/dashboard`, `/repositories`, and `/architecture`.

