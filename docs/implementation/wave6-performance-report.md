# LegacyIQ — Wave 6 Performance Validation Report

**Phase:** Wave 6 — System Integration & End-to-End Validation (Phase F)  
**Date:** 2026-11-01  
**Status:** All Latency Targets Met (`11/11` Operations Within SLA)

---

## 1. Measurement Methodology

All performance measurements were captured against the live PostgreSQL 17.11 + `pgvector 0.8.7` database (`localhost:5432`) and local object storage during the execution of [`test_wave6_phases_b_c_d_e_f_complete_system_integration`](file:///C:/LegacyIQ/backend/tests/test_wave6_system_integration.py) using `time.perf_counter()` high-resolution timers.

- **Test Workload**: Multi-language enterprise legacy archive (`Python` FastAPI service, `Java` Spring Boot controller, `TypeScript` gateway, `PostgreSQL` DDL schema with tables/FKs/views/triggers, `OpenAPI 3.0.3` spec, `GraphQL` schema, `Dockerfile`, `docker-compose.yml`, `Kubernetes` Deployment, `Terraform` RDS/S3 config, `Markdown` architecture handbook, `pytest` suite, and `coverage.xml` Cobertura report).
- **Database Conditions**: Full `FORCE ROW LEVEL SECURITY` active across all `72` tenant-owned tables (`SET LOCAL app.current_tenant_id` enforced on every transaction), HNSW vector index (`vector_cosine_ops`, `m=16`, `ef_construction=64`) and GIN full-text search index active on `artifact_chunks`.

---

## 2. Recorded Latency Measurements

| Operation | Component / Method | Measured Latency (`ms`) | Target Threshold (`ms`) | Status |
| :--- | :--- | :---: | :---: | :---: |
| **1. Deterministic Static AST Parse (Single Module)** | [`PythonAstParser.parse`](file:///C:/LegacyIQ/backend/app/services/code_intelligence_service.py) | **`0.28 ms`** | `< 1,000 ms` | **PASS** |
| **2. End-to-End Repository Ingestion + Waves 1–4 Pipeline** | [`IngestionService.ingest_zip_archive`](file:///C:/LegacyIQ/backend/app/services/ingestion_service.py) (ZIP validation, SHA-256 deduplication, AST, DB/API/Infra/Doc extraction, Knowledge Graph, Business Rules, Requirements, RTM, Conflicts, Tests, Risks, Debt, Modernization Roadmap) | **`1,355.16 ms`** | `< 10,000 ms` | **PASS** |
| **3. Unified Application Intelligence Dashboard Query** | [`ReportingQaExportService.get_application_intelligence_dashboard`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) | **`397.39 ms`** | `< 5,000 ms` | **PASS** |
| **4. Knowledge Graph Multi-Hop Impact Traversal** | [`RequirementsIntelligenceService.analyze_impact`](file:///C:/LegacyIQ/backend/app/services/requirements_intelligence_service.py) | **`17.79 ms`** | `< 2,000 ms` | **PASS** |
| **5. Hybrid RRF Retrieval (`pgvector` HNSW + FTS GIN)** | [`RetrievalService.hybrid_search`](file:///C:/LegacyIQ/backend/app/services/retrieval_service.py) (`k = 60`) | **`28.09 ms`** | `< 5,000 ms` | **PASS** |
| **6. Semantic Q&A Turn (Intent + Retrieval + Grounded Synthesis + Persistence)** | [`ReportingQaExportService.ask_question`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) | **`630.48 ms`** | `< 5,000 ms` | **PASS** |
| **7. Complete Intelligence Report Generation (`9` Sections + SHA-256 Versioning)** | [`ReportingQaExportService.generate_report`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) (`COMPLETE_INTELLIGENCE`) | **`1,317.06 ms`** | `< 5,000 ms` | **PASS** |
| **8. Controlled PDF Export + Object Storage + AuditLog Hash Chain** | [`ReportingQaExportService.export_report`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) (`PDF`) | **`41.15 ms`** | `< 2,000 ms` | **PASS** |
| **9. Controlled DOCX Export + Object Storage + AuditLog Hash Chain** | [`ReportingQaExportService.export_report`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) (`DOCX`) | **`45.01 ms`** | `< 2,000 ms` | **PASS** |
| **10. Controlled XLSX Export + Object Storage + AuditLog Hash Chain** | [`ReportingQaExportService.export_report`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) (`XLSX`) | **`40.32 ms`** | `< 2,000 ms` | **PASS** |
| **11. Controlled JSON Export + Object Storage + AuditLog Hash Chain** | [`ReportingQaExportService.export_report`](file:///C:/LegacyIQ/backend/app/services/reporting_qa_export_service.py) (`JSON`) | **`46.28 ms`** | `< 2,000 ms` | **PASS** |

---

## 3. Bottleneck Analysis & Targeted Recommendations

1. **Report Generation (`1,317.06 ms`) & Dashboard Aggregation (`397.39 ms`)**:
   - **Observation**: `_build_report_content_bundle` aggregates data across Waves 1–4 (`get_application_intelligence_dashboard`, `get_executive_insights`, `get_snapshot_business_rules`, `get_snapshot_requirements`, `get_discovered_tests`, `get_coverage_and_gaps`, `get_risk_intelligence`, `get_technical_debt`, and `get_recommendations_and_roadmap`). Because several of those helper methods independently query `RepositorySnapshot` and `EvidenceAnchor`, there is minor repeated SQL query overhead during `COMPLETE_INTELLIGENCE` report compilation.
   - **Recommendation (Future Optimization)**: Pass pre-fetched snapshot/anchor maps between internal Wave 5 bundle builders or cache immutable snapshot read models in Redis using `build_tenant_cache_key(tenant_id, "snapshot_bundle", str(snapshot_id))` to reduce `COMPLETE_INTELLIGENCE` generation below `400 ms` on large enterprise monorepos.
2. **Hybrid RRF Search (`28.09 ms`) & Graph Traversal (`17.79 ms`)**:
   - **Observation**: Both `pgvector` HNSW cosine similarity + PostgreSQL GIN full-text search RRF fusion (`28.09 ms`) and cycle-safe graph impact analysis (`17.79 ms`) execute well under `30 ms` with RLS active. No changes required.
3. **Multi-Format Export Rendering (`40.32 ms – 46.28 ms`)**:
   - **Observation**: Binary rendering for `PDF` (`reportlab`), `DOCX` (`python-docx`), `XLSX` (`openpyxl`), and `JSON`, combined with tenant-isolated SHA-256 blob persistence and `AuditLog` hash-chain insertion, completes in `~43 ms` per export.

