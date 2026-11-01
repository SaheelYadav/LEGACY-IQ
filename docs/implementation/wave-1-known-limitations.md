# LegacyIQ — Wave 1 Known Limitations & Wave 2/3 Roadmap

**Date**: 2026-11-01  
**Current Milestone**: Wave 1 (Core Platform, Database Foundation & Source Intelligence)

---

## 1. Intentional Scope Boundaries (Deferred to Wave 2 & Wave 3)

Per the approved D3 phased rollout plan, only the **33 Wave 1 canonical tables** and deterministic source intelligence capabilities are implemented in Wave 1:

1. **Wave 2 Tables Not Yet Provisioned (21 Tables)**:
   - Domain E (Database, API & External Interface Intelligence)
   - Domain F (Architecture Reconstruction & Graph Projections)
   - Domain G (Business Rules & Domain Logic Extraction)
   - Domain H (Requirements Intelligence & Traceability)
   - Remaining Domain I tables (`agent_task_executions`, `evidence_anchors`, `evidence_bundles`, `evidence_anchor_links`)
2. **Wave 3 Tables Not Yet Provisioned (17 Tables)**:
   - Domain K (Test Intelligence, Modernization Recommendations, Reports & Grounded Q&A)
   - Domain L (Human Review Workflows & Overrides)
   - Domain M (Tamper-Evident Hash-Chain Audit Logs, Retention Policies, Deletion Certificates, KMS Keys & Token Usage Ledgers)

---

## 2. Technical Limitations in Wave 1

1. **Structural Parser Coverage for Java, JS/TS, and PHP**:
   - Python files use Python's full `ast` module (`python-ast-1.0`).
   - Java, JavaScript, TypeScript, and PHP files use deterministic brace-and-signature structural parsers (`<lang>-structural-1.0`). While these accurately extract package/namespace declarations, imports, classes/interfaces, methods/functions, inheritance clauses, complexity estimates, and call expressions, deeply nested anonymous closures or macro constructs will be upgraded to full Tree-sitter grammar bindings in Wave 2.
2. **Synchronous Ingestion Pipeline Execution**:
   - In Wave 1, `POST /api/v1/repositories/{repository_id}/upload-zip` executes archive validation, deterministic static analysis, and chunk/vector indexing synchronously within the request transaction (recording stage telemetry in `ingestion_jobs`) and provides `TaskEnvelope` HMAC signing for Redis queue dispatch. Full asynchronous background worker consumer pools will be expanded in Wave 2 for multi-hundred-megabyte Git repositories.
3. **Header-Based Local Authentication**:
   - Wave 1 uses `X-Tenant-Id` and `X-User-Id` headers validated against PostgreSQL `users`, `organization_memberships`, and `project_memberships` (plus `/api/v1/bootstrap` for zero-friction local setup). OIDC/JWT token issuance and session cookies are scheduled for production hardening.

