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

