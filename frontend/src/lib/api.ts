export interface ServiceHealthResponse {
  status: "healthy" | "unhealthy" | "unconfigured";
  service: string;
  latency_ms?: number | null;
  details?: Record<string, unknown>;
  error?: string | null;
}

export interface AppHealthResponse {
  status: "healthy";
  app_name: string;
  environment: string;
  version: string;
  milestone: string;
  timestamp: string;
}

export interface BootstrapContextResponse {
  tenant_id: string;
  organization_name: string;
  organization_slug: string;
  user_id: string;
  user_email: string;
  user_display_name: string;
  role_code: string;
  workspace_id: string;
  workspace_name: string;
  project_id: string;
  project_key: string;
  project_name: string;
  default_repository_id: string;
  default_repository_name: string;
  latest_snapshot_id: string | null;
}

export interface RepositoryItem {
  id: string;
  tenant_id: string;
  project_id: string;
  application_id: string | null;
  name: string;
  default_branch: string;
  clone_url: string | null;
  is_active: boolean;
  created_at: string;
}

export interface SnapshotItem {
  id: string;
  tenant_id: string;
  project_id: string;
  repository_id: string;
  snapshot_label: string | null;
  source_type: string;
  tree_hash: string;
  file_count: number;
  total_bytes: number;
  status: string;
  retention_class: string;
  legal_hold: boolean;
  created_at: string;
}

export interface IngestionJobItem {
  id: string;
  tenant_id: string;
  project_id: string;
  repository_id: string;
  snapshot_id: string | null;
  status: string;
  stage: string;
  progress_pct: number;
  files_processed: number;
  bytes_processed: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ZipUploadResponse {
  repository_id: string;
  snapshot_id: string;
  ingestion_job_id: string;
  analysis_run_id: string | null;
  tree_hash: string;
  is_duplicate_snapshot: boolean;
  files_processed: number;
  total_bytes: number;
  chunks_indexed: number;
}

export interface CodeSummaryResponse {
  project_id: string;
  snapshot_id: string | null;
  analysis_run_id: string | null;
  total_modules: number;
  total_files: number;
  total_loc: number;
  total_symbols: number;
  total_imports: number;
  total_call_edges: number;
  total_type_hierarchies: number;
  total_references: number;
  language_breakdown: Record<string, number>;
  symbol_kind_breakdown: Record<string, number>;
}

export interface CodeFileItem {
  id: string;
  analysis_run_id: string;
  module_id: string | null;
  artifact_version_id: string;
  relative_path: string;
  language: string;
  loc_total: number;
  loc_code: number;
  parse_status: string;
  parser_version: string;
}

export interface CodeSymbolItem {
  id: string;
  analysis_run_id: string;
  code_file_id: string;
  parent_symbol_id: string | null;
  qualified_name: string;
  symbol_name: string;
  symbol_kind: string;
  visibility: string;
  signature_text: string | null;
  docstring_text: string | null;
  body_ast_hash: string;
  start_line: number;
  end_line: number;
  cyclomatic_complexity: number | null;
}

export interface CodeCallEdgeItem {
  id: string;
  analysis_run_id: string;
  caller_symbol_id: string;
  caller_qualified_name: string;
  callee_symbol_id: string;
  callee_qualified_name: string;
  call_site_line: number;
  resolution_confidence: number;
  is_dynamic_dispatch: boolean;
}

export interface HybridSearchHitItem {
  chunk_id: string;
  artifact_id: string;
  artifact_version_id: string;
  relative_path: string;
  detected_language: string | null;
  code_symbol_id: string | null;
  symbol_qualified_name: string | null;
  symbol_kind: string | null;
  chunk_strategy: string;
  start_line: number;
  end_line: number;
  chunk_text: string;
  chunk_sha256: string;
  rrf_score: number;
  vector_score: number | null;
  lexical_score: number | null;
}

export interface HybridSearchResponse {
  project_id: string;
  snapshot_id: string;
  query: string;
  total_hits: number;
  hits: HybridSearchHitItem[];
}

export interface Wave2AnalyzeSummaryResponse {
  snapshot_id: string;
  analysis_run_id: string;
  db_schemas_count: number;
  db_tables_count: number;
  db_columns_count: number;
  db_foreign_keys_count: number;
  api_services_count: number;
  api_endpoints_count: number;
  infra_resources_count: number;
  doc_sections_count: number;
  knowledge_entities_count: number;
  knowledge_relationships_count: number;
  evidence_anchors_count: number;
  findings_count: number;
  agent_runs_count: number;
}

export interface DbColumnItem {
  id: string;
  column_name: string;
  ordinal_position: number;
  data_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  is_pii_candidate: boolean;
}

export interface DbTableItem {
  id: string;
  db_schema_id: string;
  schema_name: string;
  table_name: string;
  table_kind: string;
  mapped_orm_symbol_id: string | null;
  comment_text: string | null;
  columns: DbColumnItem[];
}

export interface DbForeignKeyItem {
  id: string;
  source_table_id: string;
  source_table_name: string;
  target_table_id: string;
  target_table_name: string;
  constraint_name: string | null;
  source_column_names: string[];
  target_column_names: string[];
  relation_origin: string;
}

export interface DatabaseIntelResponse {
  snapshot_id: string;
  schemas: Array<{
    id: string;
    schema_name: string;
    db_engine: string;
    discovery_source: string;
  }>;
  tables: DbTableItem[];
  foreign_keys: DbForeignKeyItem[];
}

export interface ApiEndpointItem {
  id: string;
  api_service_id: string;
  service_name: string;
  protocol: string;
  handler_symbol_id: string | null;
  http_method: string;
  route_pattern: string;
  auth_required_inferred: boolean | null;
  request_schema_json: Record<string, unknown> | null;
  response_schema_json: Record<string, unknown> | null;
}

export interface ApiIntelResponse {
  snapshot_id: string;
  services: Array<{
    id: string;
    service_name: string;
    protocol: string;
    base_path: string | null;
  }>;
  endpoints: ApiEndpointItem[];
}

export interface InfraIntelResponse {
  snapshot_id: string;
  resources: Array<{
    id: string;
    iac_tool: string;
    resource_type: string;
    resource_name: string;
    source_artifact_version_id: string;
    configuration_attributes: Record<string, unknown>;
  }>;
}

export interface DocIntelResponse {
  snapshot_id: string;
  sections: Array<{
    id: string;
    artifact_version_id: string;
    canonical_path: string;
    parent_section_id: string | null;
    heading_path: string;
    heading_level: number;
    start_line: number;
    end_line: number;
    content_markdown: string;
  }>;
}

export interface KnowledgeEntityItem {
  id: string;
  entity_type: string;
  canonical_key: string;
  title: string;
  summary_description: string | null;
  origin_type: string;
  confidence_score: number;
  review_status: string;
  attributes_json: Record<string, unknown>;
}

export interface KnowledgeRelationshipItem {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: string;
  origin_type: string;
  confidence_score: number;
  edge_weight: number;
  review_status: string;
  edge_metadata: Record<string, unknown>;
}

export interface KnowledgeGraphResponse {
  snapshot_id: string;
  entity_counts_by_type: Record<string, number>;
  relationship_counts_by_type: Record<string, number>;
  entities: KnowledgeEntityItem[];
  relationships: KnowledgeRelationshipItem[];
}

export interface FindingEvidenceItem {
  link_id: string;
  evidence_anchor_id: string;
  artifact_version_id: string;
  locator_type: string;
  start_line: number;
  end_line: number;
  snippet_sha256: string;
  excerpt_text: string | null;
  evidence_role: string;
  relevance_weight: number;
  rationale_note: string | null;
}

export interface FindingItem {
  id: string;
  finding_category: string;
  severity: string;
  title: string;
  statement_markdown: string;
  origin_type: string;
  confidence_score: number;
  review_status: string;
  subject_entity_id: string | null;
  producing_agent_run_id: string | null;
  version_no: number;
  evidence: FindingEvidenceItem[];
}

export interface FindingsResponse {
  snapshot_id: string;
  findings: FindingItem[];
  conflicts: Array<{
    id: string;
    conflict_type: string;
    status: string;
    primary_entity_or_finding_id: string;
    conflicting_entity_or_finding_id: string;
    resolution_notes: string | null;
  }>;
}

export interface AgentOrchestrationResponse {
  snapshot_id: string;
  agent_runs: Array<{
    id: string;
    analysis_run_id: string;
    parent_agent_run_id: string | null;
    agent_name: string;
    agent_version: string;
    status: string;
    attempt_count: number;
    input_context_refs: Record<string, unknown>;
    output_summary_json: Record<string, unknown>;
    started_at: string | null;
    completed_at: string | null;
  }>;
  task_dependencies: Array<{
    id: string;
    upstream_agent_run_id: string;
    downstream_agent_run_id: string;
    dependency_kind: string;
  }>;
  model_invocations: Array<{
    id: string;
    agent_run_id: string;
    provider_name: string;
    model_identifier: string;
    is_fallback_invocation: boolean;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    latency_ms: number;
    status: string;
  }>;
  execution_events: Array<{
    id: string;
    agent_run_id: string;
    sequence_no: number;
    event_type: string;
    event_payload: Record<string, unknown>;
  }>;
}

export interface TenantAuthHeaders {
  tenantId: string;
  userId: string;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function fetchJson<T>(
  path: string,
  options?: RequestInit,
  auth?: TenantAuthHeaders
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options?.headers as Record<string, string> | undefined),
  };
  if (auth) {
    headers["X-Tenant-Id"] = auth.tenantId;
    headers["X-User-Id"] = auth.userId;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(detail);
  }
  return data as T;
}

export const apiClient = {
  baseUrl: API_BASE_URL,
  getAppHealth: () => fetchJson<AppHealthResponse>("/api/v1/health"),
  getDatabaseHealth: () =>
    fetchJson<ServiceHealthResponse>("/api/v1/health/database"),
  getRedisHealth: () =>
    fetchJson<ServiceHealthResponse>("/api/v1/health/redis"),
  getOllamaHealth: () =>
    fetchJson<ServiceHealthResponse>("/api/v1/health/ollama"),

  bootstrapContext: () =>
    fetchJson<BootstrapContextResponse>("/api/v1/bootstrap", {
      method: "POST",
    }),

  listRepositories: (projectId: string, auth: TenantAuthHeaders) =>
    fetchJson<RepositoryItem[]>(
      `/api/v1/repositories?project_id=${encodeURIComponent(projectId)}`,
      { method: "GET" },
      auth
    ),

  createRepository: (
    payload: { project_id: string; name: string; default_branch?: string },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<RepositoryItem>(
      "/api/v1/repositories",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  uploadRepositoryZip: async (
    repositoryId: string,
    file: File,
    snapshotLabel: string | undefined,
    auth: TenantAuthHeaders
  ): Promise<ZipUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    if (snapshotLabel) {
      formData.append("snapshot_label", snapshotLabel);
    }
    const response = await fetch(
      `${API_BASE_URL}/api/v1/repositories/${encodeURIComponent(repositoryId)}/upload-zip`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Tenant-Id": auth.tenantId,
          "X-User-Id": auth.userId,
        },
        body: formData,
      }
    );
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail =
        data && typeof data === "object" && "detail" in data
          ? String((data as { detail: unknown }).detail)
          : `HTTP ${response.status}: ${response.statusText}`;
      throw new Error(detail);
    }
    return data as ZipUploadResponse;
  },

  listProjectSnapshots: (projectId: string, auth: TenantAuthHeaders) =>
    fetchJson<SnapshotItem[]>(
      `/api/v1/snapshots?project_id=${encodeURIComponent(projectId)}`,
      { method: "GET" },
      auth
    ),

  listIngestionJobs: (projectId: string, auth: TenantAuthHeaders) =>
    fetchJson<IngestionJobItem[]>(
      `/api/v1/ingestion-jobs?project_id=${encodeURIComponent(projectId)}`,
      { method: "GET" },
      auth
    ),

  getCodeSummary: (
    projectId: string,
    auth: TenantAuthHeaders,
    snapshotId?: string | null
  ) => {
    const qs = new URLSearchParams({ project_id: projectId });
    if (snapshotId) qs.set("snapshot_id", snapshotId);
    return fetchJson<CodeSummaryResponse>(
      `/api/v1/code/summary?${qs.toString()}`,
      { method: "GET" },
      auth
    );
  },

  listCodeFiles: (
    projectId: string,
    auth: TenantAuthHeaders,
    snapshotId?: string | null
  ) => {
    const qs = new URLSearchParams({ project_id: projectId, limit: "100" });
    if (snapshotId) qs.set("snapshot_id", snapshotId);
    return fetchJson<CodeFileItem[]>(
      `/api/v1/code/files?${qs.toString()}`,
      { method: "GET" },
      auth
    );
  },

  listCodeSymbols: (
    projectId: string,
    auth: TenantAuthHeaders,
    options?: { snapshotId?: string | null; q?: string; symbolKind?: string }
  ) => {
    const qs = new URLSearchParams({ project_id: projectId, limit: "100" });
    if (options?.snapshotId) qs.set("snapshot_id", options.snapshotId);
    if (options?.q) qs.set("q", options.q);
    if (options?.symbolKind) qs.set("symbol_kind", options.symbolKind);
    return fetchJson<CodeSymbolItem[]>(
      `/api/v1/code/symbols?${qs.toString()}`,
      { method: "GET" },
      auth
    );
  },

  listCodeCallEdges: (
    projectId: string,
    auth: TenantAuthHeaders,
    snapshotId?: string | null
  ) => {
    const qs = new URLSearchParams({ project_id: projectId, limit: "100" });
    if (snapshotId) qs.set("snapshot_id", snapshotId);
    return fetchJson<CodeCallEdgeItem[]>(
      `/api/v1/code/call-edges?${qs.toString()}`,
      { method: "GET" },
      auth
    );
  },

  hybridSearch: (
    payload: {
      project_id: string;
      snapshot_id: string;
      query: string;
      limit?: number;
      language?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<HybridSearchResponse>(
      "/api/v1/search/hybrid",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  analyzeSnapshotWave2: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<Wave2AnalyzeSummaryResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/analyze-wave2`,
      { method: "POST" },
      auth
    ),

  getSnapshotDatabaseIntel: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<DatabaseIntelResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/database`,
      { method: "GET" },
      auth
    ),

  getSnapshotApiIntel: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<ApiIntelResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/apis`,
      { method: "GET" },
      auth
    ),

  getSnapshotInfraIntel: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<InfraIntelResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/infrastructure`,
      { method: "GET" },
      auth
    ),

  getSnapshotDocIntel: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<DocIntelResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/documentation`,
      { method: "GET" },
      auth
    ),

  getSnapshotKnowledgeGraph: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<KnowledgeGraphResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/graph`,
      { method: "GET" },
      auth
    ),

  getSnapshotFindings: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<FindingsResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/findings`,
      { method: "GET" },
      auth
    ),

  reviewFinding: (
    findingId: string,
    payload: {
      new_status: string;
      review_comment?: string;
      updated_title?: string;
      updated_statement_markdown?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<{ id: string; review_status: string; version_no: number }>(
      `/api/v1/findings/${encodeURIComponent(findingId)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  getSnapshotAgents: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<AgentOrchestrationResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/agents`,
      { method: "GET" },
      auth
    ),
};
