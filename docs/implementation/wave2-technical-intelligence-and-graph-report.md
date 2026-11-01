# LegacyIQ — Wave 2 Implementation Report: Technical Intelligence, Unified Knowledge Graph & AI Orchestration

## 1. Executive Summary

Wave 2 extends the LegacyIQ platform from deterministic source-code parsing (Wave 1) into full **Technical Intelligence (Domain E)**, the **Unified Knowledge Graph & Provenance Engine (Domain F)**, and **AI Agent Orchestration (Domain I)**:

- **Database Schema Expansion**: Applied Alembic migration `0004_wave2_tech_intel` adding **21 canonical tables** (`Domain E = 9`, `Domain F = 7`, `Domain I remaining = 5`), bringing the live PostgreSQL 17 database from **33 to 54 tables** and **29 to 50 Row-Level Security (RLS) enforced tables**.
- **Database Intelligence (`backend/app/analysis/database_intelligence.py`)**: Deterministic discovery of SQL schemas (`db_schemas`), tables/views/materialized views (`db_tables`), columns with primary-key and PII candidate detection (`db_columns`), explicit and ORM foreign-key relationships (`db_foreign_keys`), indexes, stored procedures, functions, triggers, and code-to-table access lineage (`MAPS_TO_TABLE`, `READS_TABLE`, `WRITES_TABLE`).
- **API Intelligence (`backend/app/analysis/api_intelligence.py`)**: Deterministic extraction of REST, OpenAPI 3.x / Swagger 2.0 (`.json`/`.yaml`), and GraphQL SDL (`.graphql`/`.gql`) services (`api_services`) and endpoints (`api_endpoints`), including HTTP methods, normalized route patterns, controller handler symbol resolution (`handler_symbol_id`), request/response JSON schemas, and authentication inference (`auth_required_inferred`).
- **Infrastructure Intelligence (`backend/app/analysis/infra_intelligence.py`)**: Deterministic extraction of `infra_resources` across `Dockerfile`, `docker-compose.yml`, Kubernetes manifests (`Deployment`, `StatefulSet`, `Service`, `Ingress`, `ConfigMap`), Terraform HCL (`.tf`), and AWS CloudFormation (`Resources:`), with inter-resource dependency edges (`DEPENDS_ON`) and automatic secret value redaction.
- **Documentation Intelligence (`backend/app/analysis/doc_intelligence.py`)**: Hierarchical section extraction (`doc_sections`) across Markdown (`.md`), RST/AsciiDoc/Text, HTML (`.html`/`.htm`), Microsoft Word OpenXML (`.docx`), Microsoft Excel OpenXML (`.xlsx`), and PDF (`.pdf`), cross-referencing mentioned identifiers against discovered code symbols, database tables, API endpoints, and infrastructure resources.
- **Unified Knowledge Graph & Provenance (`backend/app/services/knowledge_graph_service.py`)**:
  - Connects `MODULE`, `SYMBOL`, `DB_TABLE`, `API_ENDPOINT`, `SERVICE`, `INFRA_RESOURCE`, and `COMPONENT` nodes in `knowledge_entities` via canonical directed edges (`CONTAINS`, `IMPORTS`, `CALLS`, `INHERITS_FROM`, `IMPLEMENTS_INTERFACE`, `MAPS_TO_TABLE`, `READS_TABLE`, `WRITES_TABLE`, `REFERENCES_TABLE_FK`, `EXPOSES_API`, `HANDLES_ENDPOINT`, `DEPENDS_ON`) in `knowledge_relationships`.
  - Anchors every claim to immutable cryptographic `evidence_anchors` (1-based line ranges, SHA-256 snippet digests, and secret-scrubbed excerpts) via `finding_evidence_links`.
  - Projects the relational graph into NetworkX (`nx.MultiDiGraph`) to compute PageRank, in/out degree, betweenness centrality, and Tarjan Strongly Connected Components (circular dependency detection).
  - Supports cycle-safe PostgreSQL recursive CTE graph traversal (`GET /api/v1/snapshots/{id}/graph/traverse`) and audited human review state transitions (`POST /api/v1/findings/{id}/review` -> `review_history`).
- **AI Agent Orchestration (`backend/app/services/agent_orchestrator.py`)**:
  - Central orchestrator (`TechnicalIntelligenceOrchestrator`) managing the topological DAG of 5 specialized technical intelligence agents (`repo_cartographer` -> `db_analyst`, `api_inspector`, `infra_auditor` -> `doc_linker`).
  - Enforces typed Pydantic input/output contracts (`AgentInputContext`, `AgentFindingsPayload`, `AgentFindingClaim`), tracks `agent_runs`, `agent_task_dependencies`, `prompt_templates`, `model_invocations`, and `agent_execution_events`, and rejects any hallucinated/ungrounded anchor reference with `HALLUCINATION_REJECTED`.

---

## 2. Wave 2 Database Tables & RLS Matrix (21 New Tables -> 54 Total)

| Domain | Table | Ownership Class | Primary Key | RLS Policy |
| :--- | :--- | :--- | :--- | :--- |
| **Domain E** | `db_schemas` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `db_tables` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `db_columns` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `db_foreign_keys` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `api_services` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `api_endpoints` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `infra_resources` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `doc_sections` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain E** | `runtime_observations` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain F** | `knowledge_entities` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain F** | `knowledge_relationships` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain F** | `findings` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain F** | `evidence_anchors` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain F** | `finding_evidence_links` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain F** | `knowledge_conflicts` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain F** | `review_history` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain I** | `agent_runs` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain I** | `agent_task_dependencies` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain I** | `prompt_templates` | `HYBRID_CATALOG` | `(id)` | `prompt_templates_select_policy` + `prompt_templates_write_policy` + `trg_model_invocations_prompt_tenant_guard` |
| **Domain I** | `model_invocations` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |
| **Domain I** | `agent_execution_events` | `TENANT_DIRECT` | `(tenant_id, id)` | `tenant_isolation_policy` |

---

## 3. FastAPI `/api/v1` Wave 2 Endpoints

- `POST /api/v1/snapshots/{snapshot_id}/analyze-wave2` — Executes/refreshes the full Wave 2 pipeline on an ingested snapshot.
- `GET /api/v1/snapshots/{snapshot_id}/database` — Returns `db_schemas`, `db_tables`, `db_columns`, and `db_foreign_keys`.
- `GET /api/v1/snapshots/{snapshot_id}/apis` — Returns `api_services` and `api_endpoints`.
- `GET /api/v1/snapshots/{snapshot_id}/infrastructure` — Returns `infra_resources`.
- `GET /api/v1/snapshots/{snapshot_id}/documentation` — Returns hierarchical `doc_sections`.
- `GET /api/v1/snapshots/{snapshot_id}/graph` — Returns `knowledge_entities`, `knowledge_relationships`, and type breakdowns.
- `GET /api/v1/snapshots/{snapshot_id}/graph/traverse` — Cycle-safe recursive CTE traversal from `root_entity_id`.
- `GET /api/v1/snapshots/{snapshot_id}/findings` — Returns `findings` with linked `evidence_anchors` and `knowledge_conflicts`.
- `POST /api/v1/findings/{finding_id}/review` — Transitions finding review state (`APPROVED`, `REJECTED`, `MODIFIED_BY_HUMAN`) and appends an immutable `review_history` record.
- `GET /api/v1/snapshots/{snapshot_id}/agents` — Returns `agent_runs`, `agent_task_dependencies`, `model_invocations`, and `agent_execution_events`.

