# LegacyIQ — Wave 3 Implementation Report: Business Rules & Requirements Intelligence

## 1. Executive Summary

Wave 3 extends LegacyIQ from technical intelligence into **Business Rules & Requirements Intelligence (Domain G)**, transforming static AST entities, database constraints, API contracts, documentation sections, and unified knowledge graph relationships into structured, source-anchored business rules, functional/non-functional requirements, bidirectional traceability matrices, conflict/gap diagnostics, multi-hop impact analyses, and human review governance workflows.

---

## 2. Database Schema & Alembic Migration (`54 -> 60` Tables, `56` RLS-Forced Tables)

- **Alembic Revision**: `0005_wave3_biz_reqs` (`down_revision = "0004_wave2_tech_intel"`), implemented in `backend/alembic/versions/0005_wave3_business_rules_and_requirements.py`.
- **New Domain G Tables (6 Tables in `backend/app/models/business_intelligence.py`)**:
  1. `business_domains` (`BusinessDomain`): Bounded contexts (`ORDER_MANAGEMENT`, `BILLING_FINANCE`, `IDENTITY_SECURITY`, `DATA_GOVERNANCE`, `API_INTEGRATION`, `OPERATIONS_INFRA`, `CORE_DOMAIN`).
  2. `business_processes` (`BusinessProcess`): End-to-end reconstructed workflows linking API entrypoints through handler symbols and database tables (`ordered_step_entity_ids`).
  3. `business_rules` (`BusinessRule`): Extracted domain rules (`VALIDATION`, `CALCULATION`, `AUTHORIZATION`, `STATE_TRANSITION`, `INVARIANT`, `ROUTING`) with `condition_expression`, `action_consequence`, `origin_type`, `confidence_score`, `review_status`, and `version_no`.
  4. `requirements` (`Requirement`): Reconstructed functional and non-functional requirements (`FUNCTIONAL`, `NON_FUNCTIONAL_SECURITY`, `NON_FUNCTIONAL_PERFORMANCE`, `DATA_CONSTRAINT`, `INTEGRATION_CONTRACT`) with priority (`MUST`, `SHOULD`, `COULD`), normative `specification_statement`, `confidence_score`, `review_status`, and `version_no`.
  5. `requirement_acceptance_criteria` (`RequirementAcceptanceCriterion`): Testable Given/When/Then criteria (`given_clause`, `when_clause`, `then_clause`, `verification_method`).
  6. `requirement_traceability_links` (`RequirementTraceabilityLink`): Forward/backward Requirements Traceability Matrix (RTM) linking requirements to business rules, knowledge graph entities, and code symbols (`DERIVED_FROM_RULE`, `IMPLEMENTED_BY_CODE`, `CONSTRAINED_BY_SCHEMA`, `VERIFIED_BY_TEST`).
- **Evidence Foreign Keys & Row-Level Security**:
  - Added composite tenant-safe foreign keys `fk_finding_evidence_links_business_rule` and `fk_finding_evidence_links_requirement` on `finding_evidence_links`.
  - Enabled `ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on all 6 Domain G tables (`56` RLS-forced tables total across the 60-table schema).

---

## 3. Implemented Capabilities

1. **Deterministic + Hybrid Business Rule Discovery (`backend/app/analysis/business_rule_intelligence.py`)**:
   - Python AST and multi-language (Java, JS/TS, PHP) extraction of conditional validations, arithmetic financial/metric calculations, role/security guards, and lifecycle state transitions.
   - Database schema constraint (`NOT NULL`, `PRIMARY KEY`, `FOREIGN KEY`, PII column protection) and API authentication/contract rule synthesis.
   - Normative documentation rule extraction (`must`, `shall`, `required`, numeric thresholds) from `doc_sections`.
2. **Requirements Intelligence & Governance (`backend/app/services/requirements_intelligence_service.py`)**:
   - Synthesizes normative requirements with actors, inputs, outputs, preconditions, expected outcomes, and Given/When/Then acceptance criteria.
   - Detects **Implicit / Undocumented Behavior** (`is_implicit = True`) when code/DB rules lack documentation coverage.
   - Computes **Evidence Strength** (`STRONG`, `MODERATE`, `WEAK`, `MISSING`) and never silently marks unreviewed rules or AI-inferred conclusions as confirmed facts (`is_confirmed_fact` is `True` only when `review_status == 'APPROVED'`).
3. **Bidirectional Traceability Matrix**:
   - Forward traceability (`Requirement -> Business Rules -> Code Symbols / Knowledge Entities -> Evidence Anchors`) and backward traceability (`Code Symbol / DB Table / API Endpoint -> Business Rules -> Requirements`).
4. **Conflict & Gap Detection**:
   - Detects numeric threshold discrepancies between code rules and documentation rules (`CODE_VS_DOC`) and security policy contradictions (`REQUIREMENT_CONTRADICTION`), persisting both primary and conflicting `EvidenceAnchor` references in `KnowledgeConflict`.
   - Identifies duplicate/overlapping requirements via specification token Jaccard similarity and surfaces undocumented components.
5. **Multi-Hop Impact Analysis**:
   - Traces dependencies up to 3 hops across `RequirementTraceabilityLink` and `KnowledgeRelationship` to identify affected APIs, database tables, code symbols/modules, and infrastructure with blast-radius risk scoring (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
6. **Human Review Workflows**:
   - Supports `APPROVED`, `REJECTED`, `MODIFIED_BY_HUMAN` (with inline field edits), and `PENDING_REVIEW` (`Request Review`) across business rules and requirements, plus conflict resolution (`RESOLVED_KEEP_PRIMARY`, `RESOLVED_KEEP_CONFLICTING`, `DISMISSED`), recording every transition in the append-only `review_history` table.
7. **Frontend Workbench (`frontend/src/app/requirements/page.tsx`)**:
   - Interactive 5-tab workbench (**Business Rules**, **Requirements Catalog**, **Traceability Matrix**, **Conflicts & Gaps**, **Impact Analysis**) with source evidence anchor inspection and inline human review & curation controls.

---

## 4. Known Limitations

- Static business rule extraction for non-Python languages (Java, JS/TS, PHP) uses structured control-flow and annotation patterns alongside Tree-sitter symbol boundaries; complex cross-procedural dataflow value propagation is bounded to intraprocedural AST/statement scopes.
- Local LLM inference via Ollama (`business_rule_miner` and `requirements_synthesizer`) automatically falls back to deterministic evidence-grounded synthesis when Ollama is offline or times out, ensuring zero external paid API dependency.

