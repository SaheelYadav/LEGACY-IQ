# LegacyIQ — Wave 6 End-to-End Test Report

**Phase:** Wave 6 — System Integration & End-to-End Validation (Phases B, C, D)  
**Date:** 2026-11-01  
**Test Suite:** `C:\LegacyIQ\backend\tests` (`46` Tests across M0 + Waves 1–6)  
**Status:** All `24` End-to-End Workflow Steps & Cross-Wave Consistency Checks Verified

---

## 1. Phase B — 24-Step End-to-End Application Workflow Verification

Tested against live PostgreSQL 17.11 (`pgvector 0.8.7`) using a realistic multi-language enterprise legacy repository (`_build_wave6_enterprise_legacy_zip` in [`test_wave6_system_integration.py`](file:///C:/LegacyIQ/backend/tests/test_wave6_system_integration.py)) containing Python billing/account logic (`src/billing_engine.py`), SQL DDL (`schema/billing_core.sql`), OpenAPI 3.0.3 (`api/openapi.yaml`), `Dockerfile`, `requirements.txt`, `pytest` unit tests (`tests/test_billing_engine.py`), and Markdown documentation (`docs/billing_specification.md`).

| Step | Workflow Stage | Persisted Tables & Services Verified | Result |
| :---: | :--- | :--- | :---: |
| **1** | Repository creation & project access | `organizations`, `projects`, `project_memberships`, `applications`, `repositories`, `verify_project_access` | **PASS** |
| **2** | ZIP repository upload & ingestion | `IngestionService.ingest_zip_archive`, `TenantObjectStorage`, `ingestion_jobs` | **PASS** |
| **3** | Snapshot creation & file processing | `repository_snapshots`, `artifacts`, `artifact_versions` (SHA-256 tree hash & deduplication) | **PASS** |
| **4** | Language & framework detection | `detect_language_and_kind`, `code_files`, `get_application_intelligence_dashboard` (`python`, `sql`, `yaml`, `dockerfile`, `markdown`) | **PASS** |
| **5** | Code intelligence extraction | `code_files`, `code_symbols`, `code_imports`, `code_call_edges`, `document_chunks`, `artifact_embeddings` (`384`-d) | **PASS** |
| **6** | Database schema extraction | `db_schemas`, `db_tables` (`customer_accounts`, `invoice_ledgers`), `db_columns` (`tax_ssn` PII candidate), `db_foreign_keys` | **PASS** |
| **7** | API discovery | `api_services`, `api_endpoints` (`POST /api/v1/accounts/{account_id}/deactivate`, `POST /api/v1/invoices/settle`) | **PASS** |
| **8** | Infrastructure discovery | `infra_resources` (`Dockerfile` base image `python:3.9-slim`, `requirements.txt` dependencies) | **PASS** |
| **9** | Documentation extraction | `doc_sections` (`docs/billing_specification.md` heading & rule extraction) | **PASS** |
| **10** | Evidence anchor generation | `evidence_anchors` (`start_line`, `end_line`, `snippet_sha256`, `excerpt_text` linked to `artifact_versions`) | **PASS** |
| **11** | Knowledge graph construction | `knowledge_entities`, `knowledge_relationships`, `KnowledgeGraphService.traverse_subgraph` | **PASS** |
| **12** | Business rule extraction | `business_domains`, `business_processes`, `business_rules` (validation, calculation, authorization rules) | **PASS** |
| **13** | Functional & NFR synthesis | `requirements` (`FUNCTIONAL` and `NON_FUNCTIONAL` requirements with actors, preconditions, outcomes) | **PASS** |
| **14** | Acceptance criteria generation | `requirement_acceptance_criteria` (Given / When / Then structured scenarios) | **PASS** |
| **15** | Requirements traceability | `requirement_traceability_links` (forward & backward RTM across rules, symbols, DB tables, APIs, tests) | **PASS** |
| **16** | Conflict & ambiguity detection | `knowledge_conflicts` (detects `15%` code discount vs `20%` documentation discount discrepancy) | **PASS** |
| **17** | Test discovery & coverage analysis | `test_suites`, `test_cases` (`EXISTING_IN_REPO` vs `AI_GENERATED_BLUEPRINT`), `test_coverage_links` | **PASS** |
| **18** | Security & technical debt analysis | `findings` (`SECURITY_VULNERABILITY` MD5 CWE-328, outdated dependencies), `technical_debt_items` | **PASS** |
| **19** | Modernization recommendations | `modernization_recommendations` (4-phase roadmap with T-shirt effort ranges and supporting `evidence` anchors) | **PASS** |
| **20** | Unified intelligence dashboard | `ReportingQaExportService.get_application_intelligence_dashboard` & `get_executive_insights` (`MEASURED` vs `HEURISTIC_ESTIMATE` vs `INFERRED`) | **PASS** |
| **21** | Semantic Q&A with persisted citations | `qa_conversations`, `qa_messages`, `citations_json` (`relative_path`, `start_line`, `end_line`, `snippet_sha256`) | **PASS** |
| **22** | Report generation & lifecycle transitions | `intelligence_reports`, `intelligence_report_versions` (all `11` report types; `DRAFT -> GENERATED -> SUBMITTED_FOR_REVIEW -> APPROVED`; strict `is_immutable = True` on `v1` when `v2` is created) | **PASS** |
| **23** | PDF, DOCX, XLSX & JSON export | `report_exports` (`build_pdf_export`, `build_docx_export`, `build_xlsx_export`, `build_json_export`) | **PASS** |
| **24** | Export download & audit logging | `get_export_download_payload` (SHA-256 checksum verified) + hash-chained `audit_logs` (`EXPORT_GENERATED`, `EXPORT_DOWNLOADED`) | **PASS** |

---

## 2. Phase C — Cross-Wave Referential & Governance Consistency Verification

All cross-wave invariants were verified against persisted PostgreSQL records in [`test_wave6_system_integration.py`](file:///C:/LegacyIQ/backend/tests/test_wave6_system_integration.py):
1. **Findings -> Evidence**: Every `Finding` has at least one `FindingEvidenceLink` pointing to an existing `EvidenceAnchor` in the same tenant and snapshot.
2. **Requirements -> Business Rules & Evidence**: Every `Requirement` has `FindingEvidenceLink` rows (`requirement_id -> evidence_anchor_id`) and `RequirementAcceptanceCriterion` rows.
3. **Traceability Integrity**: Every `RequirementTraceabilityLink` references valid `Requirement`, `BusinessRule`, `CodeSymbol`, `KnowledgeEntity`, and `TestCase` IDs.
4. **Knowledge Graph Integrity**: Every `KnowledgeRelationship` (`source_entity_id`, `target_entity_id`) points to valid `KnowledgeEntity` nodes.
5. **Modernization Recommendation Evidence (`DEF-W6-002`)**: Every recommendation returned by `get_recommendations_and_roadmap` includes a non-empty `evidence` array with valid `anchor_id` and `64`-char `snippet_sha256`.
6. **Review Status Governance (`DEF-W6-001`)**: Transitioning a `BusinessRule` to `REJECTED` immediately excludes it from active dashboard counts, active report sections, executive priority lists, and Q&A answers, and increments `rejected_items_count`.
7. **Immutable Approved Report Versions**: Editing an `APPROVED` report (`v1`) creates `version_no = 2` (`DRAFT`) while preserving `v1` with `lifecycle_status == "APPROVED"` and `is_immutable == True`.

---

## 3. Phase D — AI & Evidence Validation

1. **All 12 Specialized Q&A Intents**: Verified in `test_question_intent_classification_all_specialized_queries` ([`test_wave5_unit.py`](file:///C:/LegacyIQ/backend/tests/test_wave5_unit.py)) and live Q&A execution in [`test_wave6_system_integration.py`](file:///C:/LegacyIQ/backend/tests/test_wave6_system_integration.py).
2. **Fact vs. Inference Separation**: Directly observed AST/DDL/test-coverage facts are returned in `direct_facts`; unapproved business rules, requirements, and risk findings (`PENDING_REVIEW` / `MODIFIED_BY_HUMAN`) are returned in `inferred_explanations` with explicit `review_status` and `confidence_score`.
3. **Insufficient-Evidence Guard**: Querying for non-existent functionality (`"zxqv_nonexistent_mars_orbital_telemetry_xyz987"`) sets `insufficient_evidence = True` and refuses to fabricate claims.
4. **Hallucination Rejection Gate**: `TechnicalIntelligenceOrchestrator.validate_and_persist_agent_claims` rejects any AI claim whose file/line anchor does not match a persisted `EvidenceAnchor` (`HALLUCINATION_REJECTED`).

