# LegacyIQ — Complete Entity-Relationship Diagrams (Design Phase D3)

**Document ID**: `D3-02`  
**Status**: Architecture Specification  

To maintain visual clarity and readability across all **71 tables**, the Entity-Relationship Diagrams (ERDs) are partitioned into **9 domain views** corresponding to Domains A through K.

> **Composite Tenant Foreign Key Convention**: Every tenant-scoped relationship enforces a composite foreign key `(tenant_id, <target>_id) REFERENCES <target_table>(tenant_id, id)` so that cross-tenant references are structurally rejected by PostgreSQL.

---

## 1. Domain A & B: Identity, Tenancy, Workspaces & Application Scope

Covers Organizations (Tenants), Users, Memberships, Teams, RBAC Roles/Permissions, Workspaces, Projects, Applications, Environments, and Analysis Scopes.

```mermaid
erDiagram
    organizations ||--o{ organization_memberships : "has members"
    users ||--o{ organization_memberships : "belongs to orgs"
    organizations ||--o{ teams : "owns"
    teams ||--o{ team_memberships : "includes"
    organization_memberships ||--o{ team_memberships : "assigned to"
    organizations ||--o{ roles : "defines custom or uses system"
    roles ||--o{ role_permissions : "grants"
    permissions ||--o{ role_permissions : "included in"
    roles ||--o{ organization_memberships : "assigned primary role"

    organizations ||--o{ workspaces : "owns"
    workspaces ||--o{ projects : "contains"
    projects ||--o{ project_memberships : "grants access"
    organization_memberships ||--o{ project_memberships : "member of project"
    roles ||--o{ project_memberships : "project role"

    projects ||--o{ applications : "manages"
    applications ||--o{ application_environments : "deployed in"
    applications ||--o{ analysis_scopes : "configures analysis"

    organizations {
        uuid id PK "Tenant Root ID"
        varchar slug UK "Unique URL slug"
        varchar display_name
        varchar tier "FREE | PRO | ENTERPRISE"
        varchar status "ACTIVE | SUSPENDED | PENDING_DELETION"
        uuid kms_key_id "Tenant encryption key ref"
        timestamptz created_at
    }

    users {
        uuid id PK "Global User ID"
        varchar email UK "Normalized lowercase email"
        varchar full_name
        varchar auth_provider "LOCAL | OIDC | SAML"
        varchar external_subject_id UK
        boolean is_system_admin
        timestamptz created_at
    }

    organization_memberships {
        uuid tenant_id PK,FK "organizations.id"
        uuid id PK
        uuid user_id FK "users.id (UK with tenant_id)"
        uuid role_id FK "roles.id"
        varchar status "INVITED | ACTIVE | REVOKED"
        timestamptz joined_at
    }

    teams {
        uuid tenant_id PK,FK
        uuid id PK
        varchar name "UK(tenant_id, name)"
        text description
    }

    team_memberships {
        uuid tenant_id PK,FK
        uuid id PK
        uuid team_id FK
        uuid org_membership_id FK "UK(tenant_id, team_id, org_membership_id)"
    }

    roles {
        uuid id PK
        uuid tenant_id FK "Nullable for global system roles"
        varchar code "UK(tenant_id, code)"
        varchar name
        boolean is_system_role
    }

    permissions {
        uuid id PK
        varchar code UK "e.g. repo:ingest, finding:approve"
        varchar category
        text description
    }

    role_permissions {
        uuid role_id PK,FK
        uuid permission_id PK,FK
    }

    workspaces {
        uuid tenant_id PK,FK
        uuid id PK
        varchar slug "UK(tenant_id, slug)"
        varchar name
        boolean is_default
    }

    projects {
        uuid tenant_id PK,FK
        uuid id PK
        uuid workspace_id FK
        varchar key "UK(tenant_id, workspace_id, key)"
        varchar name
        varchar lifecycle_status "ACTIVE | ARCHIVED"
    }

    project_memberships {
        uuid tenant_id PK,FK
        uuid id PK
        uuid project_id FK
        uuid org_membership_id FK "UK(tenant_id, project_id, org_membership_id)"
        uuid role_id FK
    }

    applications {
        uuid tenant_id PK,FK
        uuid id PK
        uuid project_id FK
        varchar code "UK(tenant_id, project_id, code)"
        varchar name
        varchar criticality_tier "TIER_1 | TIER_2 | TIER_3"
        jsonb primary_languages
    }

    application_environments {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        varchar env_name "UK(tenant_id, application_id, env_name)"
        varchar env_type "DEV | STAGING | PROD"
        jsonb metadata_config
    }

    analysis_scopes {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        varchar name "UK(tenant_id, application_id, name)"
        jsonb include_globs
        jsonb exclude_globs
        jsonb language_parsers_enabled
        boolean is_default
    }
```

---

## 2. Domain C: Source Connectors & Immutable Ingestion

Covers Source Connectors, Repositories, Branches, Commits, Immutable Snapshots, Content-Addressed Artifacts, Artifact Versions, and Ingestion Jobs.

```mermaid
erDiagram
    applications ||--o{ repositories : "linked to"
    source_connectors ||--o{ repositories : "authenticates"
    repositories ||--o{ repository_branches : "tracks"
    repositories ||--o{ repository_commits : "records"
    repositories ||--o{ repository_snapshots : "captures point-in-time"
    repository_branches |o--o{ repository_snapshots : "branch context"
    repository_commits |o--o{ repository_snapshots : "commit context"
    repositories ||--o{ ingestion_jobs : "executes ingestion"
    repository_snapshots |o--o{ ingestion_jobs : "produces"
    applications ||--o{ artifacts : "owns logical artifact"
    artifacts ||--o{ artifact_versions : "immutable versions"

    source_connectors {
        uuid tenant_id PK,FK
        uuid id PK
        varchar name "UK(tenant_id, name)"
        varchar provider_type "GIT_LOCAL | GITHUB | GITLAB | BITBUCKET | ZIP_UPLOAD | DB_METADATA"
        text encrypted_credentials_ref "Vault/KMS secret reference"
        varchar status "ACTIVE | INVALID | REVOKED"
    }

    repositories {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid connector_id FK "Nullable for direct ZIP uploads"
        varchar name "UK(tenant_id, application_id, name)"
        varchar source_type "GIT | ZIP_ARCHIVE | DOC_BUNDLE"
        varchar remote_url
        varchar default_branch
        varchar status "REGISTERED | INGESTING | READY | FAILED | ARCHIVED"
    }

    repository_branches {
        uuid tenant_id PK,FK
        uuid id PK
        uuid repository_id FK
        varchar branch_name "UK(tenant_id, repository_id, branch_name)"
        varchar head_commit_sha
        boolean is_default
    }

    repository_commits {
        uuid tenant_id PK,FK
        uuid id PK
        uuid repository_id FK
        varchar commit_sha "UK(tenant_id, repository_id, commit_sha)"
        varchar author_name
        varchar author_email
        timestamptz committed_at
        text commit_message
    }

    repository_snapshots {
        uuid tenant_id PK,FK
        uuid id PK
        uuid repository_id FK
        uuid branch_id FK "Nullable for ZIP"
        uuid commit_id FK "Nullable for ZIP"
        integer snapshot_number "UK(tenant_id, repository_id, snapshot_number)"
        char_64 tree_or_archive_sha256 "Cryptographic root digest"
        bigint total_files_count
        bigint total_bytes_size
        boolean legal_hold_active "Blocks purge when true"
        varchar status "CREATING | READY | COMPACTED_EVIDENCE_ONLY | SUPERSEDED | QUARANTINED"
        timestamptz captured_at
    }

    artifacts {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid repository_id FK "Nullable for standalone docs/specs"
        varchar artifact_kind "SOURCE_FILE | OPENAPI_SPEC | DDL_SCRIPT | IAC_FILE | DOC_FILE | LOG_ARCHIVE"
        text canonical_path "UK(tenant_id, application_id, repository_id, canonical_path)"
    }

    artifact_versions {
        uuid tenant_id PK,FK
        uuid id PK
        uuid artifact_id FK
        char_64 content_sha256 "UK(tenant_id, artifact_id, content_sha256)"
        bigint byte_size
        integer line_count
        varchar encoding
        varchar mime_type
        text storage_object_uri "Encrypted blob URI"
        timestamptz created_at
    }

    ingestion_jobs {
        uuid tenant_id PK,FK
        uuid id PK
        uuid repository_id FK
        uuid snapshot_id FK "Nullable until created"
        uuid triggered_by_user_id FK
        varchar status "QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED"
        jsonb stats_summary
        text error_message
        timestamptz started_at
        timestamptz completed_at
    }
```

---

## 3. Domain D: Deterministic Code Intelligence (AST & Static Analysis)

Covers Snapshot-scoped Code Files, Modules/Packages, Symbols (Classes, Functions, Methods, Fields), Imports, Call Graph Edges, Type Hierarchies, and Symbol References.

```mermaid
erDiagram
    repository_snapshots ||--o{ code_files : "contains file at snapshot"
    artifact_versions ||--o{ code_files : "backed by immutable blob"
    analysis_runs ||--o{ code_files : "parsed in run"
    code_modules ||--o{ code_files : "groups"
    code_files ||--o{ code_symbols : "declares"
    code_symbols |o--o{ code_symbols : "parent_symbol_id (nesting)"
    code_files ||--o{ code_imports : "imports"
    code_symbols ||--o{ code_call_edges : "caller_symbol_id"
    code_symbols |o--o{ code_call_edges : "callee_symbol_id (nullable if external)"
    code_symbols ||--o{ code_type_hierarchies : "sub_symbol_id"
    code_symbols |o--o{ code_type_hierarchies : "super_symbol_id"
    code_symbols ||--o{ code_symbol_references : "referenced_symbol_id"
    code_files ||--o{ code_symbol_references : "referencing_file_id"

    code_modules {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        varchar language "python | java | javascript | typescript | php"
        varchar module_Kind "PACKAGE | NAMESPACE | MODULE | DIRECTORY"
        text qualified_name "UK(tenant_id, snapshot_id, language, qualified_name)"
        uuid parent_module_id FK
    }

    code_files {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid artifact_version_id FK
        uuid module_id FK
        uuid analysis_run_id FK
        text relative_path "UK(tenant_id, snapshot_id, relative_path)"
        varchar language
        varchar parser_name "treesitter | python_ast"
        varchar parse_status "PARSED | PARTIAL_ERROR | SKIPPED_BINARY | SKIPPED_SIZE"
        integer loc_code
        integer loc_comment
        jsonb ast_metrics
    }

    code_symbols {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid code_file_id FK
        uuid parent_symbol_id FK "Enclosing class/module symbol"
        varchar symbol_kind "CLASS | INTERFACE | FUNCTION | METHOD | FIELD | CONSTANT | ENUM"
        varchar name
        text qualified_name
        text signature_text
        varchar visibility "PUBLIC | PROTECTED | PRIVATE | INTERNAL"
        integer start_line
        integer end_line
        integer start_column
        integer end_column
        integer cyclomatic_complexity
        integer cognitive_complexity
        char_64 body_ast_hash "Structural hash ignoring whitespace"
        jsonb modifiers_and_annotations
    }

    code_imports {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid source_file_id FK
        uuid resolved_target_file_id FK "Nullable if third-party/stdlib"
        text imported_module_expr
        varchar imported_symbol_name
        varchar alias_name
        boolean is_external_package
        integer line_number
    }

    code_call_edges {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid caller_symbol_id FK
        uuid callee_symbol_id FK "Nullable when unresolved/external"
        text unresolved_callee_expr "Target expression when external/dynamic"
        varchar resolution_certainty "EXACT_STATIC | TYPE_INFERRED | DYNAMIC_AMBIGUOUS"
        integer call_site_line
        integer call_site_column
    }

    code_type_hierarchies {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid sub_symbol_id FK
        uuid super_symbol_id FK "Nullable if external base class"
        text unresolved_super_name
        varchar relation_kind "EXTENDS | IMPLEMENTS | MIXIN | TRAIT_USE"
    }

    code_symbol_references {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid referencing_file_id FK
        uuid enclosing_symbol_id FK
        uuid referenced_symbol_id FK
        varchar reference_kind "READ | WRITE | INSTANTIATION | TYPE_ANNOTATION | DECORATOR"
        integer line_number
        integer column_number
    }
```

---

## 4. Domain E: Technical, Data, API, Infrastructure & Runtime Intelligence

Covers extracted Database Schemas/Tables/Columns/Foreign Keys, API Services/Endpoints, Infrastructure Resources, Documentation Sections, and Runtime Observations.

```mermaid
erDiagram
    repository_snapshots ||--o{ db_schemas : "discovers DDL/ORM"
    db_schemas ||--o{ db_tables : "contains"
    db_tables ||--o{ db_columns : "has columns"
    db_tables ||--o{ db_foreign_keys : "source_table_id"
    db_tables ||--o{ db_foreign_keys : "target_table_id"

    repository_snapshots ||--o{ api_services : "discovers APIs"
    api_services ||--o{ api_endpoints : "exposes"
    code_symbols |o--o{ api_endpoints : "handler_symbol_id"

    repository_snapshots ||--o{ infra_resources : "discovers IaC"
    artifact_versions ||--o{ doc_sections : "parsed from doc"
    applications ||--o{ runtime_observations : "ingests telemetry"

    db_schemas {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid source_artifact_version_id FK
        varchar db_engine "POSTGRESQL | MYSQL | ORACLE | MSSQL | SQLITE | MONGODB"
        varchar schema_name "UK(tenant_id, snapshot_id, schema_name)"
        varchar discovery_source "SQL_DDL | ORM_MODEL | MIGRATION_FILE | LIVE_CATALOG"
    }

    db_tables {
        uuid tenant_id PK,FK
        uuid id PK
        uuid db_schema_id FK
        uuid mapped_orm_symbol_id FK "Nullable FK to code_symbols"
        varchar table_name "UK(tenant_id, db_schema_id, table_name)"
        varchar table_kind "TABLE | VIEW | MATERIALIZED_VIEW"
        text comment_text
    }

    db_columns {
        uuid tenant_id PK,FK
        uuid id PK
        uuid db_table_id FK
        varchar column_name "UK(tenant_id, db_table_id, column_name)"
        integer ordinal_position
        varchar data_type
        boolean is_nullable
        boolean is_primary_key
        boolean is_pii_candidate
    }

    db_foreign_keys {
        uuid tenant_id PK,FK
        uuid id PK
        uuid source_table_id FK
        uuid target_table_id FK
        varchar constraint_name
        jsonb source_column_names
        jsonb target_column_names
        varchar relation_origin "EXPLICIT_DDL | ORM_RELATION | INFERRED_NAMING"
    }

    api_services {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        varchar service_name "UK(tenant_id, snapshot_id, service_name)"
        varchar protocol "REST | GRAPHQL | GRPC | SOAP | MESSAGE_CONSUMER"
        varchar base_path
    }

    api_endpoints {
        uuid tenant_id PK,FK
        uuid id PK
        uuid api_service_id FK
        uuid handler_symbol_id FK "Nullable FK to code_symbols"
        varchar http_method "GET | POST | PUT | DELETE | PATCH | RPC | SUB"
        text route_pattern "UK(tenant_id, api_service_id, http_method, route_pattern)"
        boolean auth_required_inferred
        jsonb request_schema_json
        jsonb response_schema_json
    }

    infra_resources {
        uuid tenant_id PK,FK
        uuid id PK
        uuid snapshot_id FK
        uuid source_artifact_version_id FK
        varchar iac_tool "DOCKERFILE | DOCKER_COMPOSE | KUBERNETES | TERRAFORM | CLOUDFORMATION"
        varchar resource_type
        varchar resource_name
        jsonb configuration_attributes
    }

    doc_sections {
        uuid tenant_id PK,FK
        uuid id PK
        uuid artifact_version_id FK
        uuid parent_section_id FK
        text heading_path
        integer heading_level
        integer start_line
        integer end_line
        text content_markdown
    }

    runtime_observations {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid environment_id FK
        uuid linked_endpoint_id FK "Nullable FK to api_endpoints"
        uuid linked_symbol_id FK "Nullable FK to code_symbols"
        varchar observation_kind "TRACE_SPAN | ERROR_RATE | LATENCY_P95 | SLOW_QUERY | LOG_PATTERN"
        jsonb metric_payload
        timestamptz observed_window_start
        timestamptz observed_window_end
    }
```

---

## 5. Domain F: Unified Knowledge Graph, Findings, Evidence & Review History

The core epistemological hub of LegacyIQ. Connects deterministic entities and AI-inferred domain abstractions via `knowledge_entities`, `knowledge_relationships`, `findings`, `evidence_anchors`, `finding_evidence_links`, `knowledge_conflicts`, and `review_history`.

```mermaid
erDiagram
    applications ||--o{ knowledge_entities : "scoped to app"
    repository_snapshots |o--o{ knowledge_entities : "introduced/observed in"
    analysis_runs ||--o{ knowledge_entities : "produced by run"
    code_symbols |o--o{ knowledge_entities : "bridges AST symbol"

    knowledge_entities ||--o{ knowledge_relationships : "source_entity_id"
    knowledge_entities ||--o{ knowledge_relationships : "target_entity_id"
    analysis_runs ||--o{ knowledge_relationships : "produced by run"

    applications ||--o{ findings : "surfaces finding"
    analysis_runs ||--o{ findings : "produced by run"
    knowledge_entities |o--o{ findings : "subject_entity_id"

    artifact_versions ||--o{ evidence_anchors : "pinned to immutable blob"
    findings ||--o{ finding_evidence_links : "backed by"
    knowledge_entities |o--o{ finding_evidence_links : "entity backed by"
    knowledge_relationships |o--o{ finding_evidence_links : "edge backed by"
    evidence_anchors ||--o{ finding_evidence_links : "provides anchor"

    knowledge_entities ||--o{ knowledge_conflicts : "conflicting subject"
    organizations ||--o{ review_history : "audits human review"

    knowledge_entities {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_run_id FK
        uuid source_symbol_id FK "Nullable bridge to code_symbols"
        uuid source_db_table_id FK "Nullable bridge to db_tables"
        uuid source_api_endpoint_id FK "Nullable bridge to api_endpoints"
        varchar entity_type "COMPONENT | SERVICE | MODULE | SYMBOL | DB_TABLE | API_ENDPOINT | BUSINESS_CONCEPT | EXTERNAL_SYSTEM"
        text canonical_key "UK(tenant_id, application_id, snapshot_id, entity_type, canonical_key)"
        varchar title
        text summary_description
        varchar origin_type "DETERMINISTIC_PARSER | DETERMINISTIC_RULE | AI_INFERRED | HYBRID_AI_STATIC | HUMAN_AUTHORED"
        numeric_5_4 confidence_score "0.0000 to 1.0000"
        varchar review_status "DRAFT_AI | PENDING_REVIEW | APPROVED | MODIFIED_BY_HUMAN | REJECTED | SUPERSEDED"
        integer version_no
        jsonb attributes_json
    }

    knowledge_relationships {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_run_id FK
        uuid source_entity_id FK
        uuid target_entity_id FK
        varchar relationship_type "CALLS | IMPORTS | READS_TABLE | WRITES_TABLE | EXPOSES_API | IMPLEMENTS_RULE | SATISFIES_REQ | TESTED_BY | DEPENDS_ON"
        varchar origin_type "DETERMINISTIC_PARSER | DETERMINISTIC_RULE | AI_INFERRED | HYBRID_AI_STATIC | HUMAN_AUTHORED"
        numeric_5_4 confidence_score
        numeric_8_4 edge_weight "Default 1.0000"
        varchar review_status "DRAFT_AI | PENDING_REVIEW | APPROVED | REJECTED"
        jsonb edge_metadata
    }

    findings {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_run_id FK
        uuid subject_entity_id FK "Nullable FK to knowledge_entities"
        uuid producing_agent_run_id FK "Nullable FK to agent_runs"
        varchar finding_category "ARCHITECTURE | BUSINESS_RULE | REQUIREMENT | SECURITY_RISK | DEAD_CODE | PERFORMANCE | TECH_DEBT | MODERNIZATION"
        varchar severity "INFO | LOW | MEDIUM | HIGH | CRITICAL"
        varchar title
        text statement_markdown
        varchar origin_type "DETERMINISTIC_RULE | AI_INFERRED | HYBRID_AI_STATIC | HUMAN_AUTHORED"
        numeric_5_4 confidence_score
        varchar review_status "DRAFT_AI | PENDING_REVIEW | APPROVED | MODIFIED_BY_HUMAN | REJECTED | SUPERSEDED"
        uuid superseded_by_finding_id FK
        integer version_no
        timestamptz created_at
    }

    evidence_anchors {
        uuid tenant_id PK,FK
        uuid id PK
        uuid artifact_version_id FK
        uuid snapshot_id FK
        varchar locator_type "LINE_RANGE | BYTE_SPAN | AST_NODE_PATH | JSON_POINTER | DOC_HEADING"
        integer start_line
        integer end_line
        integer start_column
        integer end_column
        char_64 snippet_sha256 "Hash of exact cited excerpt"
        text excerpt_text "Bounded redacted snippet <= 2048 chars"
        timestamptz created_at
    }

    finding_evidence_links {
        uuid tenant_id PK,FK
        uuid id PK
        uuid evidence_anchor_id FK
        uuid finding_id FK "Nullable (at least one target non-null)"
        uuid knowledge_entity_id FK "Nullable"
        uuid knowledge_relationship_id FK "Nullable"
        uuid business_rule_id FK "Nullable"
        uuid requirement_id FK "Nullable"
        varchar evidence_role "PRIMARY_DEFINITION | CALL_SITE | CONFIG_BINDING | TEST_ASSERTION | DOC_CLAIM | CONTRADICTING_SOURCE"
        numeric_5_4 relevance_weight
        text rationale_note
    }

    knowledge_conflicts {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        varchar conflict_type "CODE_VS_DOC | AI_RUN_DIVERGENCE | STATIC_VS_RUNTIME | REQUIREMENT_CONTRADICTION"
        uuid primary_entity_or_finding_id
        uuid conflicting_entity_or_finding_id
        uuid primary_evidence_anchor_id FK
        uuid conflicting_evidence_anchor_id FK
        varchar status "OPEN | RESOLVED_KEEP_PRIMARY | RESOLVED_KEEP_CONFLICTING | RESOLVED_MERGED | DISMISSED"
        uuid resolved_by_user_id FK
        text resolution_notes
    }

    review_history {
        uuid tenant_id PK,FK
        uuid id PK
        varchar target_object_type "KNOWLEDGE_ENTITY | KNOWLEDGE_RELATIONSHIP | FINDING | BUSINESS_RULE | REQUIREMENT | MODERNIZATION_REC"
        uuid target_object_id
        uuid reviewer_user_id FK
        varchar previous_status
        varchar new_status
        jsonb previous_snapshot_json "Immutable before-image"
        jsonb updated_snapshot_json "Immutable after-image"
        text review_comment
        timestamptz reviewed_at
    }
```

---

## 6. Domain G: Business Logic & Requirements Intelligence

Covers Business Domains, Business Processes/Workflows, Extracted Business Rules, Functional & Non-Functional Requirements, Acceptance Criteria, and Traceability Links.

```mermaid
erDiagram
    applications ||--o{ business_domains : "partitioned into"
    business_domains ||--o{ business_processes : "orchestrates"
    business_domains |o--o{ business_rules : "categorizes"
    applications ||--o{ business_rules : "enforces"
    knowledge_entities |o--o{ business_rules : "represented as node"

    applications ||--o{ requirements : "specifies"
    business_domains |o--o{ requirements : "scoped to domain"
    requirements ||--o{ requirement_acceptance_criteria : "verified by"
    requirements ||--o{ requirement_traceability_links : "traces to"
    business_rules |o--o{ requirement_traceability_links : "derived from rule"
    knowledge_entities |o--o{ requirement_traceability_links : "implemented by entity"

    business_domains {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        varchar code "UK(tenant_id, application_id, code)"
        varchar name
        text description
        varchar origin_type
        numeric_5_4 confidence_score
        varchar review_status
    }

    business_processes {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid business_domain_id FK
        uuid entry_entity_id FK "Nullable FK to knowledge_entities"
        varchar process_key "UK(tenant_id, application_id, process_key)"
        varchar name
        text workflow_summary
        jsonb ordered_step_entity_ids
        varchar origin_type
        numeric_5_4 confidence_score
        varchar review_status
    }

    business_rules {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_run_id FK
        uuid business_domain_id FK
        uuid knowledge_entity_id FK "Bridge to unified graph node"
        varchar rule_code "UK(tenant_id, application_id, snapshot_id, rule_code)"
        varchar rule_category "VALIDATION | CALCULATION | AUTHORIZATION | STATE_TRANSITION | INVARIANT | ROUTING"
        varchar title
        text condition_expression "Given / Trigger condition"
        text action_consequence "Then / Enforced outcome"
        varchar origin_type
        numeric_5_4 confidence_score
        varchar review_status
        integer version_no
    }

    requirements {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_run_id FK
        uuid business_domain_id FK
        uuid knowledge_entity_id FK "Bridge to unified graph node"
        varchar req_code "UK(tenant_id, application_id, snapshot_id, req_code)"
        varchar req_type "FUNCTIONAL | NON_FUNCTIONAL_SECURITY | NON_FUNCTIONAL_PERFORMANCE | DATA_CONSTRAINT | INTEGRATION_CONTRACT"
        varchar priority "MUST | SHOULD | COULD"
        varchar title
        text specification_statement
        varchar origin_type
        numeric_5_4 confidence_score
        varchar review_status
        integer version_no
    }

    requirement_acceptance_criteria {
        uuid tenant_id PK,FK
        uuid id PK
        uuid requirement_id FK
        integer criterion_order "UK(tenant_id, requirement_id, criterion_order)"
        text given_clause
        text when_clause
        text then_clause
        varchar verification_method "UNIT_TEST | INTEGRATION_TEST | STATIC_CHECK | MANUAL_INSPECTION"
    }

    requirement_traceability_links {
        uuid tenant_id PK,FK
        uuid id PK
        uuid requirement_id FK
        uuid business_rule_id FK "Nullable"
        uuid knowledge_entity_id FK "Nullable"
        uuid code_symbol_id FK "Nullable"
        uuid test_case_id FK "Nullable"
        varchar link_type "DERIVED_FROM_RULE | IMPLEMENTED_BY_CODE | VERIFIED_BY_TEST | CONSTRAINED_BY_SCHEMA"
        varchar origin_type
        numeric_5_4 confidence_score
    }
```

---

## 7. Domain H: Testing, Coverage & Modernization Intelligence

Covers Discovered & Generated Test Suites, Test Cases, Test Coverage Links, Technical Debt Items, and Modernization Recommendations.

```mermaid
erDiagram
    applications ||--o{ test_suites : "has test suites"
    test_suites ||--o{ test_cases : "contains"
    test_cases ||--o{ test_coverage_links : "covers"
    code_symbols |o--o{ test_coverage_links : "target_symbol_id"
    requirements |o--o{ test_coverage_links : "target_requirement_id"
    business_rules |o--o{ test_coverage_links : "target_business_rule_id"

    applications ||--o{ technical_debt_items : "tracks debt"
    applications ||--o{ modernization_recommendations : "proposes modernization"
    technical_debt_items |o--o{ modernization_recommendations : "remediated by"

    test_suites {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        varchar suite_name "UK(tenant_id, application_id, snapshot_id, suite_name)"
        varchar test_framework "PYTEST | JUNIT | JEST | VITEST | PHPUNIT | GENERATED_BLUEPRINT"
        varchar suite_origin "EXISTING_IN_REPO | AI_GENERATED_BLUEPRINT"
    }

    test_cases {
        uuid tenant_id PK,FK
        uuid id PK
        uuid test_suite_id FK
        uuid test_symbol_id FK "Nullable FK to code_symbols if existing test"
        uuid analysis_run_id FK
        varchar test_key "UK(tenant_id, test_suite_id, test_key)"
        varchar title
        varchar test_kind "UNIT | INTEGRATION | CHARACTERIZATION | REGRESSION | CONTRACT"
        text scenario_description
        text generated_code_blueprint
        varchar last_observed_status "UNKNOWN | PASSED | FAILED | SKIPPED | NOT_EXECUTED_BLUEPRINT"
        numeric_5_4 confidence_score
        varchar review_status
    }

    test_coverage_links {
        uuid tenant_id PK,FK
        uuid id PK
        uuid test_case_id FK
        uuid target_symbol_id FK "Nullable"
        uuid target_business_rule_id FK "Nullable"
        uuid target_requirement_id FK "Nullable"
        varchar coverage_source "STATIC_CALL_GRAPH | IMPORT_TRACE | COVERAGE_REPORT | AI_TRACEABILITY"
        numeric_5_4 confidence_score
    }

    technical_debt_items {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_run_id FK
        uuid affected_entity_id FK "Nullable FK to knowledge_entities"
        uuid finding_id FK "Nullable FK to findings"
        varchar debt_category "HIGH_COMPLEXITY | CIRCULAR_DEPENDENCY | GOD_CLASS | MISSING_TESTS | DEPRECATED_DEPENDENCY | SQL_COUPLED_UI"
        varchar severity "LOW | MEDIUM | HIGH | CRITICAL"
        integer estimated_remediation_hours
        text description
    }

    modernization_recommendations {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_run_id FK
        uuid addressed_debt_id FK "Nullable FK to technical_debt_items"
        varchar strategy_pattern "STRANGLER_FIG | EXTRACT_DOMAIN_SERVICE | REPLACE_RAW_SQL | INTRODUCE_CHARACTERIZATION_TESTS | UPGRADE_RUNTIME"
        varchar title
        text current_state_summary
        text target_state_architecture
        text step_by_step_plan_markdown
        varchar risk_level "LOW | MEDIUM | HIGH"
        varchar effort_tshirt "XS | S | M | L | XL"
        numeric_5_4 confidence_score
        varchar review_status
    }
```

---

## 8. Domain I & J: AI Orchestration, Prompt Lineage & Vector Retrieval

Covers Analysis Runs, Agent Runs, Task Dependencies, Versioned Prompt Templates, Model Invocations, Execution Events, Embedding Model Versions, Document Chunks, and `pgvector` Artifact Embeddings.

```mermaid
erDiagram
    applications ||--o{ analysis_runs : "executes analysis"
    repository_snapshots ||--o{ analysis_runs : "analyzes snapshot"
    analysis_scopes ||--o{ analysis_runs : "uses scope"

    analysis_runs ||--o{ agent_runs : "spawns agents"
    agent_runs ||--o{ agent_task_dependencies : "depends on"
    agent_runs ||--o{ model_invocations : "invokes LLM"
    prompt_templates ||--o{ model_invocations : "renders template"
    agent_runs ||--o{ agent_execution_events : "emits telemetry"

    artifact_versions ||--o{ document_chunks : "segmented into"
    document_chunks ||--o{ artifact_embeddings : "embedded as"
    embedding_model_versions ||--o{ artifact_embeddings : "encoded by model"

    analysis_runs {
        uuid tenant_id PK,FK
        uuid id PK
        uuid application_id FK
        uuid snapshot_id FK
        uuid analysis_scope_id FK
        uuid triggered_by_user_id FK
        integer run_number "UK(tenant_id, application_id, run_number)"
        varchar run_mode "FULL_DISCOVERY | INCREMENTAL_STATIC | AI_ENRICHMENT_ONLY"
        varchar status "QUEUED | RUNNING_STATIC | RUNNING_EMBEDDINGS | RUNNING_AI_AGENTS | COMPLETED | FAILED | CANCELLED"
        jsonb pipeline_versions_manifest
        timestamptz started_at
        timestamptz completed_at
    }

    agent_runs {
        uuid tenant_id PK,FK
        uuid id PK
        uuid analysis_run_id FK
        uuid parent_agent_run_id FK "Nullable for root coordinator"
        varchar agent_name "repo_cartographer | rule_extractor | req_synthesizer | test_architect | modernization_advisor"
        varchar agent_version
        varchar status "PENDING | RUNNING | COMPLETED | FAILED | RETRYING"
        integer attempt_count
        jsonb input_context_refs
        jsonb output_summary_json
        timestamptz started_at
        timestamptz completed_at
    }

    agent_task_dependencies {
        uuid tenant_id PK,FK
        uuid id PK
        uuid analysis_run_id FK
        uuid upstream_agent_run_id FK
        uuid downstream_agent_run_id FK "UK(tenant_id, upstream_agent_run_id, downstream_agent_run_id)"
        varchar dependency_kind "DATA_PREREQUISITE | VERIFICATION_GATE"
    }

    prompt_templates {
        uuid id PK
        uuid tenant_id FK "Nullable for global system prompts"
        varchar template_key "UK(tenant_id, template_key, version_number)"
        integer version_number
        varchar target_agent_name
        char_64 template_sha256
        text system_prompt_text
        text user_prompt_template
        jsonb output_json_schema
        timestamptz created_at
    }

    model_invocations {
        uuid tenant_id PK,FK
        uuid id PK
        uuid agent_run_id FK
        uuid prompt_template_id FK
        varchar provider_name "ollama | openrouter | gemini | groq"
        varchar model_identifier "qwen2.5-coder:3b | cohere/north-mini-code:free"
        boolean is_fallback_invocation
        char_64 rendered_prompt_sha256
        text storage_payload_uri "Optional object storage URI for raw prompt/completion"
        integer prompt_tokens
        integer completion_tokens
        integer total_tokens
        integer latency_ms
        varchar status "SUCCESS | SCHEMA_VALIDATION_ERROR | TIMEOUT | PROVIDER_ERROR"
        timestamptz invoked_at
    }

    agent_execution_events {
        uuid tenant_id PK,FK
        uuid id PK
        uuid agent_run_id FK
        integer sequence_no
        varchar event_type "STEP_STARTED | TOOL_CALLED | EVIDENCE_VERIFIED | HALLUCINATION_REJECTED | STEP_COMPLETED"
        jsonb event_payload
        timestamptz occurred_at
    }

    embedding_model_versions {
        uuid id PK
        varchar provider_name "sentence_transformers | ollama | openai_compatible"
        varchar model_name "BAAI/bge-small-en-v1.5"
        varchar model_revision "UK(provider_name, model_name, model_revision)"
        integer vector_dimension "384"
        varchar distance_metric "COSINE | L2 | INNER_PRODUCT"
        boolean is_active_default
    }

    document_chunks {
        uuid tenant_id PK,FK
        uuid id PK
        uuid artifact_version_id FK
        varchar chunk_strategy "AST_SYMBOL_WINDOW | MARKDOWN_SECTION | SLIDING_TOKEN_WINDOW"
        integer chunk_index "UK(tenant_id, artifact_version_id, chunk_strategy, chunk_index)"
        integer start_line
        integer end_line
        integer token_count
        char_64 chunk_text_sha256
        text chunk_text
        jsonb metadata_tags "Includes symbol_qualified_name, symbol_kind, body_ast_hash"
    }

    artifact_embeddings {
        uuid tenant_id PK,FK
        uuid id PK
        uuid document_chunk_id FK
        uuid embedding_model_version_id FK "UK(tenant_id, document_chunk_id, embedding_model_version_id)"
        vector_384 embedding "pgvector vector(384)"
        timestamptz created_at
    }
```

---

## 9. Domain K: Governance, Audit, Retention & SaaS Commercials

Covers Immutable Audit Logs, Governance Approval Requests, Data Retention Policies, Right-to-Erasure/Deletion Requests, Tenant Subscriptions, and Usage Quotas.

```mermaid
erDiagram
    organizations ||--o{ audit_logs : "records immutable audit trail"
    organizations ||--o{ approval_requests : "governs sensitive actions"
    organizations ||--o{ retention_policies : "configures retention"
    organizations ||--o{ deletion_requests : "tracks erasure workflows"
    organizations ||--|| tenant_subscriptions : "subscribed plan"
    organizations ||--o{ tenant_usage_quotas : "meters period usage"
    projects ||--o{ qa_conversations : "hosts Q&A sessions"
    qa_conversations ||--o{ qa_messages : "contains messages"
    projects ||--o{ intelligence_reports : "generates reports"
    intelligence_reports ||--o{ intelligence_report_versions : "versions (APPROVED immutable)"
    intelligence_report_versions ||--o{ report_exports : "exports PDF/DOCX/XLSX/JSON"

    audit_logs {
        uuid tenant_id PK,FK
        uuid id PK
        uuid actor_user_id FK "Nullable for system/worker events"
        varchar actor_type "USER | SYSTEM_WORKER | API_KEY | ADMIN_SUPPORT"
        varchar action_code "REPO_INGESTED | ANALYSIS_STARTED | FINDING_APPROVED | EXPORT_GENERATED | RLS_POLICY_VERIFIED"
        varchar target_resource_type
        uuid target_resource_id
        inet client_ip
        char_64 prev_audit_hash "Tamper-evident hash chain per tenant"
        char_64 entry_hash
        jsonb metadata_diff
        timestamptz occurred_at
    }

    approval_requests {
        uuid tenant_id PK,FK
        uuid id PK
        uuid project_id FK
        uuid requested_by_user_id FK
        uuid decided_by_user_id FK
        varchar request_type "BASELINE_REQUIREMENTS_SIGN_OFF | EXTERNAL_LLM_FALLBACK_OPT_IN | DATA_PURGE_APPROVAL"
        varchar status "PENDING | APPROVED | REJECTED | EXPIRED"
        jsonb request_payload
        text decision_reason
        timestamptz requested_at
        timestamptz decided_at
    }

    retention_policies {
        uuid tenant_id PK,FK
        uuid id PK
        varchar artifact_category "RAW_SOURCE_BLOBS | SNAPSHOT_AST | AI_INVOCATION_LOGS | AUDIT_LOGS"
        integer retain_days
        integer max_snapshots_per_repo
        boolean auto_purge_enabled
        timestamptz updated_at
    }

    deletion_requests {
        uuid tenant_id PK,FK
        uuid id PK
        uuid requested_by_user_id FK
        varchar deletion_scope "SINGLE_SNAPSHOT | REPOSITORY | PROJECT | FULL_TENANT_OFFBOARDING"
        uuid target_scope_id
        varchar status "REQUESTED | APPROVED | IN_PROGRESS | CRYPTO_SHREDDED | COMPLETED | FAILED"
        char_64 completion_certificate_sha256
        timestamptz requested_at
        timestamptz completed_at
    }

    tenant_subscriptions {
        uuid tenant_id PK,FK
        uuid id PK
        varchar plan_code "LOCAL_COMMUNITY | CONSULTING_TEAM | ENTERPRISE_SAAS"
        varchar billing_status "ACTIVE | TRIALING | PAST_DUE | CANCELLED"
        integer max_repositories_allowed
        bigint max_loc_allowed
        boolean allow_cloud_llm_providers
        timestamptz current_period_start
        timestamptz current_period_end
    }

    tenant_usage_quotas {
        uuid tenant_id PK,FK
        uuid id PK
        date billing_month "UK(tenant_id, billing_month)"
        integer repositories_count
        bigint analyzed_loc_count
        bigint vector_chunks_stored
        bigint local_llm_tokens_used
        bigint cloud_llm_tokens_used
        bigint object_storage_bytes_used
        timestamptz updated_at
    }

    qa_conversations {
        uuid tenant_id PK,FK
        uuid id PK
        uuid project_id FK
        uuid application_id FK
        uuid snapshot_id FK
        uuid created_by_user_id FK
        varchar title
        varchar conversation_status "ACTIVE | ARCHIVED"
        timestamptz created_at
        timestamptz updated_at
    }

    qa_messages {
        uuid tenant_id PK,FK
        uuid id PK
        uuid conversation_id FK
        uuid snapshot_id FK
        integer sequence_no "UK(tenant_id, conversation_id, sequence_no)"
        varchar role "USER | ASSISTANT"
        varchar question_intent
        text content_markdown
        jsonb direct_facts_json
        jsonb inferred_explanations_json
        jsonb citations_json
        boolean insufficient_evidence
        numeric_5_4 confidence_score
        timestamptz created_at
    }

    intelligence_reports {
        uuid tenant_id PK,FK
        uuid id PK
        uuid project_id FK
        uuid application_id FK
        uuid snapshot_id FK
        varchar report_type "11 canonical report types"
        varchar title
        integer current_version_no
        varchar lifecycle_status "DRAFT | GENERATED | SUBMITTED_FOR_REVIEW | APPROVED | REJECTED | ARCHIVED"
        timestamptz created_at
        timestamptz updated_at
    }

    intelligence_report_versions {
        uuid tenant_id PK,FK
        uuid id PK
        uuid report_id FK
        uuid snapshot_id FK
        integer version_no "UK(tenant_id, report_id, version_no)"
        varchar lifecycle_status
        boolean is_immutable "true once APPROVED"
        text executive_summary_markdown
        jsonb sections_json
        jsonb evidence_refs_json
        char_64 content_sha256
        timestamptz created_at
    }

    report_exports {
        uuid tenant_id PK,FK
        uuid id PK
        uuid project_id FK
        uuid report_id FK
        uuid report_version_id FK
        varchar export_format "PDF | DOCX | XLSX | JSON"
        varchar file_name
        bigint file_size_bytes
        char_64 content_sha256
        text storage_object_uri
        integer download_count
        timestamptz created_at
    }
```

