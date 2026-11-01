# LegacyIQ — Wave 1 Test & Verification Report

**Date**: 2026-11-01  
**Backend Test Runner**: `pytest 8.4.2` (`C:\LegacyIQ\backend\.venv\Scripts\pytest.exe`)  
**Frontend Verification**: `tsc --noEmit`, `next lint`, `next build`

---

## 1. Backend Test Suite Results (`17 passed in 7.09s`)

| Test Module | Test Case | Category | Status |
| :--- | :--- | :--- | :---: |
| `tests/test_health.py` | `test_fastapi_app_routes_registered` | M0 Regression | **PASSED** |
| `tests/test_health.py` | `test_app_health_endpoint_handler` | M0 Regression | **PASSED** |
| `tests/test_health.py` | `test_unconfigured_db_and_redis_report_truthfully` | M0 Regression | **PASSED** |
| `tests/test_health.py` | `test_url_masking_never_exposes_password` | Security | **PASSED** |
| `tests/test_health.py` | `test_static_ast_analyzer_and_graph_builder` | M0 Regression | **PASSED** |
| `tests/test_health.py` | `test_zip_slip_path_traversal_guard` | Security | **PASSED** |
| `tests/test_wave1_unit.py` | `test_wave1_33_canonical_models_and_mappers` | Schema / ORM | **PASSED** |
| `tests/test_wave1_unit.py` | `test_wave1_api_v1_routes_registered` | API Contract | **PASSED** |
| `tests/test_wave1_unit.py` | `test_tenant_cache_key_and_signed_task_envelope` | Security / Queue | **PASSED** |
| `tests/test_wave1_unit.py` | `test_tenant_object_storage_isolation` | Storage Isolation | **PASSED** |
| `tests/test_wave1_unit.py` | `test_multi_language_parsers_python_java_js_ts_php` | Code Intelligence | **PASSED** |
| `tests/test_wave1_unit.py` | `test_python_parser_syntax_error_handled_gracefully` | Parser Resilience | **PASSED** |
| `tests/test_wave1_unit.py` | `test_zip_ingestion_security_guards` | Archive Security | **PASSED** |
| `tests/test_wave1_unit.py` | `test_deterministic_384d_embedding_properties` | Vector Indexing | **PASSED** |
| `tests/test_wave1_integration_db.py` | `test_postgres_33_tables_indexes_triggers_and_rls_enabled` | Live DB & RLS | **PASSED** |
| `tests/test_wave1_integration_db.py` | `test_negative_tenant_isolation_and_project_rbac` | Negative Security | **PASSED** |
| `tests/test_wave1_integration_db.py` | `test_end_to_end_zip_ingestion_code_intelligence_and_hybrid_rrf_search` | End-to-End Pipeline | **PASSED** |

---

## 2. Detailed Verification of Mandatory Wave 1 Requirements

### 2.1 Database Migrations & Schema Integrity
- **Alembic Revision**: `0003_wave1_rls_vec` verified in `alembic_version`.
- **Canonical Table Count**: All 33 Wave 1 tables verified in `pg_tables`.
- **Key Indexes Verified**:
  - `ux_active_analysis_run_per_snapshot` (partial unique index on `analysis_runs`)
  - `ix_doc_chunks_search_tsv` (GIN index on generated `tsvector` column in `document_chunks`)
  - `ix_artifact_embeddings_hnsw_cosine` (`pgvector` HNSW `vector_cosine_ops` index on `artifact_embeddings.embedding` with `m=16, ef_construction=64`)
- **Database Triggers Verified**:
  - `trg_org_memberships_role_tenant_guard`
  - `trg_project_memberships_role_tenant_guard`

### 2.2 Mandatory Negative Tenant Security Tests (`test_negative_tenant_isolation_and_project_rbac`)
1. **Cross-Tenant SELECT**: Tenant B querying Tenant A's `Project` by ID returns `None` (`0` rows).
2. **Cross-Tenant UPDATE**: Tenant B executing `UPDATE projects SET name = ... WHERE id = <tenant_a_project>` affects `0` rows; Tenant A's record remains intact.
3. **Cross-Tenant DELETE**: Tenant B executing `DELETE FROM projects WHERE id = <tenant_a_project>` affects `0` rows.
4. **Cross-Tenant Foreign Key Injection**: Tenant B attempting to insert a `Project` referencing Tenant A's `workspace_id` fails with a database integrity/RLS error.
5. **Unauthorized Project Access**: A user with `VIEWER` organization membership in Tenant A who lacks a `ProjectMembership` row for `Secret Project A` is rejected with `SecurityViolationError`.
6. **Missing Tenant Context Fail-Closed**: Switching to `legacyiq_app` with an empty `app.current_tenant_id` returns `0` rows across `organizations` and `projects`.
7. **Connection Pool Context Reset**: Subsequent sessions checked out from `SessionLocal` after a `tenant_db_session` block confirm `current_setting('app.current_tenant_id', true)` is reset to `''`.

### 2.3 Frontend Build & Quality Checks
- `npm run typecheck` (`tsc --noEmit`): **0 errors**
- `npm run lint` (`next lint`): **✔ No ESLint warnings or errors**
- `npm run build` (`next build`): **Production build succeeded** across `/`, `/dashboard`, `/repositories`, `/requirements`, `/architecture`, and `/settings`.

