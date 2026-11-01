# LegacyIQ — Wave 1 API Inventory (`/api/v1`)

All tenant-scoped endpoints require headers:
- `X-Tenant-Id: <UUID>`
- `X-User-Id: <UUID>`

Every response includes `X-Correlation-Id: <UUID>` for distributed request tracing.

---

## 1. Infrastructure Health Endpoints (Preserved from M0)

| Method | Path | Auth Required | Summary |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/health` | No | Application liveness and version metadata |
| `GET` | `/api/v1/health/database` | No | Live PostgreSQL 17 & `pgvector` readiness probe |
| `GET` | `/api/v1/health/redis` | No | Live Redis 7 authenticated `PING` probe |
| `GET` | `/api/v1/health/ollama` | No | Live Ollama `qwen2.5-coder:3b` model availability probe |

---

## 2. Organizations, Memberships & Local-First Bootstrap (Domain A)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/bootstrap` | Public (Local Dev) | Idempotently provisions default tenant (`acme-enterprise`), owner user, workspace, project (`CORE`), application, and repository (`legacy-monolith`) |
| `POST` | `/api/v1/organizations` | Public | Creates a new organization tenant and binds the initial `ORG_OWNER` membership |
| `GET` | `/api/v1/organizations/current` | Active Member | Returns active organization details for the verified `TenantContext` |
| `GET` | `/api/v1/organizations/{tenant_id}/memberships` | Active Member | Lists organization memberships within the tenant |
| `POST` | `/api/v1/organizations/{tenant_id}/memberships` | `org:manage` | Adds a member with a role (`ORG_OWNER`, `ARCHITECT`, `REVIEWER`, `VIEWER`) |

---

## 3. Workspaces, Projects & Applications (Domain B)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/workspaces` | Active Member | Lists workspaces in the active tenant |
| `POST` | `/api/v1/workspaces` | `project:write` | Creates a workspace in the active tenant |
| `GET` | `/api/v1/projects` | Active Member | Lists projects accessible to the user in the active tenant |
| `POST` | `/api/v1/projects` | `project:write` | Creates a project and grants creator project membership |
| `GET` | `/api/v1/projects/{project_id}` | `project:read` | Returns project details (enforcing project-level RBAC) |
| `POST` | `/api/v1/projects/{project_id}/memberships` | `project:write` | Grants an organization member access to a project |
| `GET` | `/api/v1/applications` | `project:read` | Lists applications within a project (`?project_id=...`) |
| `POST` | `/api/v1/applications` | `project:write` | Creates an application within a project |

---

## 4. Repositories, ZIP Ingestion, Snapshots & Jobs (Domain C)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/repositories` | `project:read` | Lists repositories in a project (`?project_id=...`) |
| `POST` | `/api/v1/repositories` | `repo:ingest` | Registers a repository in a project |
| `POST` | `/api/v1/repositories/{repository_id}/upload-zip` | `repo:ingest` | Validates and ingests a `.zip` archive (`multipart/form-data`), creates an immutable `RepositorySnapshot`, runs static AST extraction, and indexes 384-d `pgvector` embeddings |
| `GET` | `/api/v1/repositories/{repository_id}/snapshots` | `project:read` | Lists immutable snapshots for a repository |
| `GET` | `/api/v1/snapshots` | `project:read` | Lists immutable snapshots across a project (`?project_id=...`) |
| `GET` | `/api/v1/ingestion-jobs` | `project:read` | Lists ingestion job telemetry for a project (`?project_id=...`) |
| `GET` | `/api/v1/ingestion-jobs/{job_id}` | `project:read` | Gets status, stage, and progress of a specific ingestion job |

---

## 5. Deterministic Code Intelligence (Domain D & Domain I)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/code/summary` | `project:read` | Aggregate counts of modules, files, LOC, symbols, imports, call edges, type hierarchies, references, and language/symbol-kind breakdowns |
| `GET` | `/api/v1/code/files` | `project:read` | Lists parsed `CodeFile` records with LOC, parser version, and parse status |
| `GET` | `/api/v1/code/symbols` | `project:read` | Lists extracted `CodeSymbol` declarations with line spans, complexity, and AST SHA-256 hash (`?q=...&symbol_kind=...`) |
| `GET` | `/api/v1/code/imports` | `project:read` | Lists static import/require/use statements and internal file resolution |
| `GET` | `/api/v1/code/call-edges` | `project:read` | Lists static caller-to-callee symbol edges and resolution confidence |
| `GET` | `/api/v1/code/type-hierarchies` | `project:read` | Lists class/interface `EXTENDS` and `IMPLEMENTS` relationships |
| `GET` | `/api/v1/code/references` | `project:read` | Lists cross-file symbol references with line and column coordinates |

---

## 6. Hybrid Vector & Lexical Retrieval (Domain J)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/search/hybrid` | `code:search` | Executes tenant- and snapshot-scoped Hybrid RRF search (`pgvector` cosine + PostgreSQL `tsvector` FTS) |
| `GET` | `/api/v1/search/hybrid` | `code:search` | Executes Hybrid RRF search via query parameters (`?project_id=...&snapshot_id=...&q=...`) |

---

## 7. Wave 2 Technical Intelligence, Unified Knowledge Graph & Agent Orchestration (Domains E, F, I)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/snapshots/{snapshot_id}/analyze-wave2` | Active Member | Runs Wave 2 Technical Intelligence, Knowledge Graph synthesis, and AI Agent Orchestration DAG |
| `GET` | `/api/v1/snapshots/{snapshot_id}/database` | Active Member | Returns discovered database schemas, tables, columns, PII candidates, and foreign keys |
| `GET` | `/api/v1/snapshots/{snapshot_id}/apis` | Active Member | Returns discovered API services and REST/GraphQL/OpenAPI endpoints |
| `GET` | `/api/v1/snapshots/{snapshot_id}/infrastructure` | Active Member | Returns discovered Docker, Compose, Kubernetes, Terraform, and CloudFormation resources |
| `GET` | `/api/v1/snapshots/{snapshot_id}/documentation` | Active Member | Returns extracted Markdown, HTML, DOCX, XLSX, and PDF documentation sections |
| `GET` | `/api/v1/snapshots/{snapshot_id}/graph` | Active Member | Returns Unified Knowledge Graph entities, relationships, PageRank, centrality, and Tarjan SCC metrics |
| `GET` | `/api/v1/snapshots/{snapshot_id}/graph/traverse` | Active Member | Executes cycle-safe PostgreSQL recursive CTE subgraph traversal (`OUTGOING`, `INCOMING`, `BOTH`) |
| `GET` | `/api/v1/snapshots/{snapshot_id}/findings` | Active Member | Returns evidence-anchored findings and open conflicts |
| `POST` | `/api/v1/findings/{finding_id}/review` | Active Member | Transitions finding review status and records an immutable `ReviewHistory` entry |
| `GET` | `/api/v1/snapshots/{snapshot_id}/agents` | Active Member | Returns AI Agent Orchestration runs, DAG task dependencies, model invocations, and execution events |

---

## 8. Wave 3 Business Rules & Requirements Intelligence (Domain G)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/snapshots/{snapshot_id}/requirements-intelligence/analyze` | Active Member | Runs or re-runs the Wave 3 Business Rules & Requirements Intelligence pipeline |
| `GET` | `/api/v1/snapshots/{snapshot_id}/business-rules` | Active Member | Returns discovered `BusinessDomain`, `BusinessProcess`, and `BusinessRule` records with `EvidenceAnchor` citations |
| `POST` | `/api/v1/business-rules/{rule_id}/review` | Active Member | Approves, rejects, edits (`MODIFIED_BY_HUMAN`), or requests review on a `BusinessRule` and appends `ReviewHistory` |
| `GET` | `/api/v1/snapshots/{snapshot_id}/requirements` | Active Member | Returns functional and non-functional `Requirement` records with Given/When/Then `RequirementAcceptanceCriterion` and evidence strength |
| `POST` | `/api/v1/requirements/{requirement_id}/review` | Active Member | Approves, rejects, edits (`MODIFIED_BY_HUMAN`), or requests review on a `Requirement` and appends `ReviewHistory` |
| `GET` | `/api/v1/snapshots/{snapshot_id}/traceability` | Active Member | Returns forward (`Requirement -> Rules -> Code/DB/API -> Evidence`) and backward traceability plus weak/missing evidence diagnostics |
| `GET` | `/api/v1/snapshots/{snapshot_id}/conflicts-and-gaps` | Active Member | Returns rule/doc contradictions (`CODE_VS_DOC`, `REQUIREMENT_CONTRADICTION`), overlapping requirements, and undocumented behavior gaps |
| `POST` | `/api/v1/conflicts/{conflict_id}/resolve` | Active Member | Resolves or dismisses a `KnowledgeConflict` and records an immutable `ReviewHistory` entry |
| `GET` | `/api/v1/snapshots/{snapshot_id}/impact-analysis` | Active Member | Traces multi-hop dependencies for any requirement, rule, or entity (`?target_id=...`) and returns blast-radius severity and affected components |

---

## 9. Wave 4 Testing, Risk, Technical Debt & Modernization Intelligence (Domain H)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/snapshots/{snapshot_id}/testing-modernization/analyze` | Active Member | Runs or re-runs the Wave 4 Testing, Risk, Technical Debt & Modernization Intelligence pipeline |
| `GET` | `/api/v1/snapshots/{snapshot_id}/test-intelligence` | Active Member | Returns discovered repository `TestSuite` / `TestCase` records (`DISCOVERED_IN_REPO`), generated characterization blueprints (`AI_GENERATED_BLUEPRINT`), and `TestCoverageLink` mappings |
| `GET` | `/api/v1/snapshots/{snapshot_id}/coverage-and-gaps` | Active Member | Returns discovered vs. blueprint-estimated coverage percentages, Cobertura/LCOV line coverage metrics, untested requirements, and untested critical components |
| `GET` | `/api/v1/snapshots/{snapshot_id}/risk-register` | Active Member | Returns classified security (`CWE-798`, `CWE-89`, `CWE-78`, `CWE-502`, `CWE-306`), dependency (`CVE` / `EOL`), architectural, SPOF, data integrity, performance, and operational risk findings with `EvidenceAnchor` citations |
| `GET` | `/api/v1/snapshots/{snapshot_id}/technical-debt` | Active Member | Returns quantified `TechnicalDebtItem` records separating measured static metrics (`MEASURED`) from heuristic remediation effort estimates (`HEURISTIC_ESTIMATE`) |
| `GET` | `/api/v1/snapshots/{snapshot_id}/modernization-assessment` | Active Member | Returns 7-dimension modernization readiness posture and evidence-grounded architecture target pattern evaluation (`CONSOLIDATE_MODULAR_MONOLITH` vs. `SELECTIVE_SERVICE_EXTRACTION`) |
| `GET` | `/api/v1/snapshots/{snapshot_id}/modernization-roadmap` | Active Member | Returns prioritized `ModernizationRecommendation` records organized into a 4-phase modernization roadmap (`PHASE_1` through `PHASE_4`) |
| `POST` | `/api/v1/modernization-recommendations/{recommendation_id}/review` | Active Member | Approves, rejects, edits (`MODIFIED_BY_HUMAN`), or requests review on a `ModernizationRecommendation` and appends `ReviewHistory` |
| `POST` | `/api/v1/test-cases/{test_case_id}/review` | Active Member | Approves, rejects, edits (`MODIFIED_BY_HUMAN`), or requests review on a discovered or generated `TestCase` and appends `ReviewHistory` |

---

## 10. Wave 5 Reporting, Semantic Q&A & Export Governance (Domain K)

| Method | Path | Permission | Summary |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/snapshots/{snapshot_id}/intelligence-dashboard` | `project:read` | Returns the unified Waves 1–4 Application Intelligence Dashboard with `MEASURED`, `HEURISTIC_ESTIMATE`, and `INFERRED` attribution |
| `GET` | `/api/v1/snapshots/{snapshot_id}/executive-insights` | `project:read` | Returns management-level Executive Reporting insights (health score & grade, complexity, risk distribution, testing maturity, tech debt, modernization readiness, effort) |
| `POST` | `/api/v1/qa/conversations` | `project:read` | Creates a tenant- and project-isolated Semantic Q&A conversation session |
| `GET` | `/api/v1/qa/conversations` | `project:read` | Lists Semantic Q&A conversations accessible to the caller (`?project_id=...&snapshot_id=...`) |
| `GET` | `/api/v1/qa/conversations/{conversation_id}` | `project:read` | Returns a Semantic Q&A conversation and its full message & citation history |
| `POST` | `/api/v1/qa/conversations/{conversation_id}/ask` | `project:read` | Executes a codebase-grounded Semantic Q&A turn in an existing conversation using Hybrid RRF search + Wave 1–4 intelligence services + local Ollama inference |
| `POST` | `/api/v1/snapshots/{snapshot_id}/qa/ask` | `project:read` | Executes a codebase-grounded Semantic Q&A turn directly against a snapshot |
| `POST` | `/api/v1/snapshots/{snapshot_id}/reports/generate` | `project:read` | Generates or regenerates one of the 11 structured intelligence reports (preserving immutable `APPROVED` versions by creating `v+1`) |
| `GET` | `/api/v1/snapshots/{snapshot_id}/reports` | `project:read` | Lists all intelligence reports generated for a snapshot along with the 11 available report types |
| `GET` | `/api/v1/reports/{report_id}` | `project:read` | Retrieves a structured intelligence report (`?version_no=...`) and its full version list |
| `GET` | `/api/v1/reports/{report_id}/versions` | `project:read` | Lists all historical and current versions of an intelligence report |
| `POST` | `/api/v1/reports/{report_id}/lifecycle` | `project:read` | Transitions report lifecycle (`DRAFT`, `GENERATED`, `SUBMITTED_FOR_REVIEW`, `APPROVED`, `REJECTED`, `ARCHIVED`) while enforcing strict immutability on `APPROVED` versions |
| `POST` | `/api/v1/reports/{report_id}/exports` | `project:read` | Generates a controlled export (`PDF`, `DOCX`, `XLSX`, `JSON`) in tenant-scoped storage and records a hash-chained `AuditLog` (`EXPORT_GENERATED`) |
| `GET` | `/api/v1/snapshots/{snapshot_id}/exports` | `project:read` | Lists controlled report exports and tamper-evident `AuditLog` entries for a snapshot |
| `GET` | `/api/v1/exports/{export_id}/download` | `project:read` | Safely streams a generated report export binary (`PDF`, `DOCX`, `XLSX`, `JSON`), increments `download_count`, and records an `EXPORT_DOWNLOADED` audit event |
| `GET` | `/api/v1/organizations/{tenant_id}/audit-logs` | Active Member | Lists hash-chained tamper-evident `AuditLog` entries for the active tenant |




