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
  access_token?: string | null;
  token_type?: string;
  expires_in_seconds?: number;
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

export interface Wave3EvidenceItem {
  link_id: string;
  anchor_id: string;
  evidence_role: string;
  relevance_weight: number;
  rationale_note: string | null;
  relative_path: string;
  locator_type: string;
  start_line: number;
  end_line: number;
  snippet_sha256: string;
  excerpt_text: string | null;
}

export interface BusinessDomainItem {
  id: string;
  code: string;
  name: string;
  description: string | null;
  origin_type: string;
  confidence_score: number;
  review_status: string;
}

export interface BusinessProcessItem {
  id: string;
  process_key: string;
  name: string;
  domain_code: string;
  workflow_summary: string;
  ordered_step_entity_ids: string[];
  origin_type: string;
  confidence_score: number;
  review_status: string;
}

export interface BusinessRuleItem {
  id: string;
  rule_code: string;
  rule_category: string;
  domain_code: string;
  domain_name: string;
  title: string;
  condition_expression: string;
  action_consequence: string;
  origin_type: string;
  is_confirmed_fact: boolean;
  confidence_score: number;
  review_status: string;
  version_no: number;
  knowledge_entity_id: string | null;
  evidence: Wave3EvidenceItem[];
}

export interface BusinessRulesResponse {
  snapshot_id: string;
  domains: BusinessDomainItem[];
  processes: BusinessProcessItem[];
  business_rules: BusinessRuleItem[];
}

export interface AcceptanceCriterionItem {
  id: string;
  criterion_order: number;
  given_clause: string;
  when_clause: string;
  then_clause: string;
  verification_method: string;
}

export interface RequirementItem {
  id: string;
  req_code: string;
  req_type: string;
  priority: string;
  domain_code: string;
  title: string;
  specification_statement: string;
  origin_type: string;
  is_confirmed_fact: boolean;
  confidence_score: number;
  review_status: string;
  version_no: number;
  actors: string[];
  inputs: string[];
  outputs: string[];
  preconditions: string;
  expected_outcomes: string;
  is_implicit: boolean;
  evidence_strength: string;
  acceptance_criteria: AcceptanceCriterionItem[];
  evidence: Wave3EvidenceItem[];
}

export interface RequirementsResponse {
  snapshot_id: string;
  requirements: RequirementItem[];
}

export interface ForwardTraceabilityEntry {
  requirement_id: string;
  req_code: string;
  req_type: string;
  priority: string;
  title: string;
  review_status: string;
  confidence_score: number;
  is_implicit: boolean;
  evidence_strength: string;
  business_rules: Array<{
    id: string;
    rule_code: string;
    title: string;
    rule_category: string;
  }>;
  code_symbols: Array<{
    id: string;
    name: string;
    qualified_name: string;
    symbol_kind: string;
  }>;
  knowledge_entities: Array<{
    id: string;
    entity_type: string;
    title: string;
    canonical_key: string;
  }>;
  evidence: Wave3EvidenceItem[];
}

export interface BackwardTraceabilityEntry {
  target_key: string;
  target_type: string;
  target_label: string;
  business_rules: Array<{
    id: string;
    rule_code: string;
    title: string;
    evidence: Wave3EvidenceItem[];
  }>;
  requirements: Array<{
    id: string;
    req_code: string;
    title: string;
    req_type: string;
    review_status: string;
  }>;
}

export interface TraceabilityResponse {
  snapshot_id: string;
  forward_traceability: ForwardTraceabilityEntry[];
  backward_traceability: BackwardTraceabilityEntry[];
  weak_or_missing_evidence: ForwardTraceabilityEntry[];
}

export interface ConflictsAndGapsResponse {
  snapshot_id: string;
  conflicts: Array<{
    id: string;
    conflict_type: string;
    status: string;
    primary_id: string;
    primary_label: string;
    conflicting_id: string;
    conflicting_label: string;
    primary_evidence: {
      anchor_id: string;
      start_line: number;
      end_line: number;
      snippet_sha256: string;
      excerpt_text: string | null;
    } | null;
    conflicting_evidence: {
      anchor_id: string;
      start_line: number;
      end_line: number;
      snippet_sha256: string;
      excerpt_text: string | null;
    } | null;
    resolution_notes: string | null;
  }>;
  overlapping_requirements: Array<{
    primary_req_code: string;
    primary_title: string;
    overlapping_req_code: string;
    overlapping_title: string;
    similarity_score: number;
    shared_terms: string[];
  }>;
  gaps_and_undocumented: Array<{
    gap_type: string;
    req_code: string | null;
    title: string;
    description: string;
  }>;
}

export interface ImpactAnalysisResponse {
  snapshot_id: string;
  target: {
    id: string;
    target_kind: string;
    code: string;
    title: string;
    review_status: string;
  };
  blast_radius_risk: string;
  impact_explanation: string;
  affected_apis: Array<{
    id: string;
    entity_type: string;
    canonical_key: string;
    title: string;
    hop_depth: number;
  }>;
  affected_database_tables: Array<{
    id: string;
    entity_type: string;
    canonical_key: string;
    title: string;
    hop_depth: number;
  }>;
  affected_code_components: Array<{
    id: string;
    entity_type: string;
    canonical_key: string;
    title: string;
    hop_depth: number;
  }>;
  affected_infrastructure: Array<{
    id: string;
    entity_type: string;
    canonical_key: string;
    title: string;
    hop_depth: number;
  }>;
  affected_business_rules: Array<{
    id: string;
    entity_type: string;
    canonical_key: string;
    title: string;
    hop_depth: number;
  }>;
  affected_requirements: Array<{
    id: string;
    entity_type: string;
    canonical_key: string;
    title: string;
    hop_depth: number;
  }>;
  dependency_edges: Array<{
    id: string;
    source: string;
    target: string;
    relationship_type: string;
    confidence_score: number;
  }>;
  evidence: Wave3EvidenceItem[];
}

export interface Wave3AnalyzeSummaryResponse {
  snapshot_id: string;
  analysis_run_id: string;
  business_domains_count: number;
  business_processes_count: number;
  business_rules_count: number;
  requirements_count: number;
  acceptance_criteria_count: number;
  traceability_links_count: number;
  conflicts_count: number;
}

export interface Wave4AnalyzeSummaryResponse {
  snapshot_id: string;
  analysis_run_id: string;
  discovered_test_suites_count: number;
  discovered_test_cases_count: number;
  generated_test_blueprints_count: number;
  coverage_links_count: number;
  risk_findings_count: number;
  technical_debt_items_count: number;
  modernization_recommendations_count: number;
}

export interface TestIntelligenceResponse {
  snapshot_id: string;
  summary: {
    total_suites: number;
    discovered_suites: number;
    generated_blueprint_suites: number;
    total_test_cases: number;
    discovered_test_cases: number;
    recommended_test_blueprints: number;
  };
  test_suites: Array<{
    id: string;
    suite_name: string;
    test_framework: string;
    suite_origin: string;
    is_discovered_in_repo: boolean;
  }>;
  test_cases: Array<{
    id: string;
    test_suite_id: string;
    suite_name: string;
    test_framework: string;
    suite_origin: string;
    is_discovered_in_repo: boolean;
    test_key: string;
    title: string;
    test_kind: string;
    scenario_description: string;
    generated_code_blueprint: string | null;
    last_observed_status: string;
    confidence_score: number;
    review_status: string;
    is_confirmed_fact: boolean;
    covered_targets: Array<{
      coverage_link_id: string;
      coverage_source: string;
      is_measured_coverage: boolean;
      confidence_score: number;
      symbol_qualified_name: string | null;
      rule_code: string | null;
      req_code: string | null;
    }>;
  }>;
}

export interface CoverageAndGapsResponse {
  snapshot_id: string;
  coverage_metrics: {
    total_requirements: number;
    requirements_covered_by_existing_tests: number;
    requirements_with_blueprint_recommendations: number;
    discovered_requirement_coverage_pct: number;
    total_production_symbols: number;
    symbols_covered_by_existing_tests: number;
    discovered_symbol_coverage_pct: number;
    measured_coverage_report_links: number;
    static_call_graph_links: number;
    inferred_blueprint_links: number;
  };
  untested_requirements: Array<{
    id: string;
    req_code: string;
    req_type: string;
    priority: string;
    title: string;
    has_generated_blueprint: boolean;
    coverage_state: string;
  }>;
  untested_critical_components: Array<{
    symbol_id: string;
    qualified_name: string;
    symbol_kind: string;
    relative_path: string;
    cyclomatic_complexity: number;
    cognitive_complexity: number;
  }>;
}

export interface RiskRegisterResponse {
  snapshot_id: string;
  counts_by_severity: Record<string, number>;
  counts_by_category: Record<string, number>;
  risk_findings: Array<{
    id: string;
    finding_category: string;
    severity: string;
    likelihood: string;
    title: string;
    statement_markdown: string;
    origin_type: string;
    confidence_score: number;
    review_status: string;
    is_confirmed_fact: boolean;
    version_no: number;
    evidence: Array<{
      anchor_id: string;
      start_line: number;
      end_line: number;
      snippet_sha256: string;
      excerpt_text: string | null;
      rationale_note: string | null;
    }>;
  }>;
}

export interface TechnicalDebtResponse {
  snapshot_id: string;
  measured_vs_estimated_summary: {
    measured_metrics: {
      metric_nature: string;
      total_files: number;
      total_loc_code: number;
      total_symbols: number;
      max_cyclomatic_complexity: number;
      avg_cyclomatic_complexity: number;
      total_debt_items_detected: number;
    };
    heuristic_estimates: {
      metric_nature: string;
      total_estimated_remediation_hours: number;
      disclaimer: string;
    };
  };
  technical_debt_items: Array<{
    id: string;
    debt_category: string;
    severity: string;
    estimated_remediation_hours: number | null;
    is_effort_estimated: boolean;
    effort_nature: string;
    description: string;
    affected_entity_id: string | null;
    finding_id: string | null;
  }>;
}

export interface ModernizationAssessmentResponse {
  snapshot_id: string;
  microservices_recommended: boolean;
  dimensions: Array<{
    dimension: string;
    title: string;
    recommended_posture: string;
    microservices_recommended?: boolean;
    rationale: string;
  }>;
}

export interface ModernizationRoadmapResponse {
  snapshot_id: string;
  recommendations: Array<{
    id: string;
    strategy_pattern: string;
    roadmap_phase: number;
    title: string;
    current_state_summary: string;
    target_state_architecture: string;
    step_by_step_plan_markdown: string;
    risk_level: string;
    effort_tshirt: string;
    estimated_effort_range: string;
    is_effort_estimated: boolean;
    effort_nature: string;
    confidence_score: number;
    review_status: string;
    is_confirmed_fact: boolean;
    addressed_debt_category: string | null;
  }>;
  roadmap_phases: Array<{
    phase_number: number;
    phase_name: string;
    objective: string;
    prerequisites: string[];
    expected_benefits: string[];
    effort_nature: string;
    recommendations: Array<{
      id: string;
      strategy_pattern: string;
      roadmap_phase: number;
      title: string;
      current_state_summary: string;
      target_state_architecture: string;
      step_by_step_plan_markdown: string;
      risk_level: string;
      effort_tshirt: string;
      estimated_effort_range: string;
      is_effort_estimated: boolean;
      effort_nature: string;
      confidence_score: number;
      review_status: string;
      is_confirmed_fact: boolean;
      addressed_debt_category: string | null;
    }>;
  }>;
}

export interface ApplicationIntelligenceDashboardResponse {
  snapshot_overview: {
    snapshot_id: string;
    snapshot_label: string;
    repository_id: string;
    repository_name: string;
    application_id: string;
    application_name: string;
    project_id: string;
    project_name: string;
    project_key: string;
    organization_name: string;
    source_type: string;
    commit_sha: string | null;
    branch_name: string | null;
    total_files: number;
    total_loc_code: number;
    metric_basis: string;
  };
  technology_stack: {
    metric_basis: string;
    languages: Record<string, { files: number; loc: number }>;
    frameworks: string[];
    iac_and_container_tools: string[];
  };
  technical_inventory: {
    metric_basis: string;
    code_symbols_count: number;
    call_edges_count: number;
    db_tables_count: number;
    db_columns_count: number;
    db_foreign_keys_count: number;
    pii_columns_count: number;
    api_services_count: number;
    api_endpoints_count: number;
    infra_resources_count: number;
    knowledge_entities_count: number;
    knowledge_relationships_count: number;
    evidence_anchors_count: number;
    db_tables: Array<{ id: string; table_name: string; table_kind: string }>;
    api_endpoints: Array<{
      id: string;
      http_method: string;
      route_path: string;
      auth_scheme: string | null;
    }>;
    infra_resources: Array<{
      id: string;
      iac_tool: string;
      resource_type: string;
      resource_name: string;
    }>;
  };
  business_and_requirements: {
    metric_basis: string;
    domains_count: number;
    processes_count: number;
    business_rules_count: number;
    approved_business_rules_count: number;
    requirements_count: number;
    approved_requirements_count: number;
    domains: Array<{ id: string; domain_key: string; name: string }>;
    processes: Array<{ id: string; process_key: string; name: string }>;
  };
  testing_and_coverage: {
    discovered_test_suites_count: number;
    discovered_test_cases_count: number;
    recommended_test_blueprints_count: number;
    coverage_metrics: CoverageAndGapsResponse["coverage_metrics"];
    untested_requirements_count: number;
    untested_critical_components_count: number;
    discovered_coverage_basis: string;
    blueprint_coverage_basis: string;
  };
  risk_and_technical_debt: {
    total_risk_findings: number;
    risk_counts_by_severity: Record<string, number>;
    risk_counts_by_category: Record<string, number>;
    technical_debt_summary: TechnicalDebtResponse["measured_vs_estimated_summary"];
  };
  modernization_posture: {
    microservices_recommended: boolean;
    dimensions: ModernizationAssessmentResponse["dimensions"];
    total_recommendations: number;
    roadmap_phases: ModernizationRoadmapResponse["roadmap_phases"];
    effort_basis: string;
  };
  governance_and_reviews: {
    pending_business_rules_count: number;
    pending_requirements_count: number;
    pending_findings_count: number;
    pending_modernization_recs_count: number;
    total_pending_human_reviews: number;
    unresolved_conflicts_count: number;
    unresolved_conflicts: Array<{
      id: string;
      conflict_type: string;
      severity: string;
      resolution_status: string;
      description: string;
      confidence_score: number;
    }>;
  };
  metric_basis_legend: Record<string, string>;
  suggested_qa_questions: Array<{ intent: string; question: string }>;
}

export interface ExecutiveInsightsResponse {
  snapshot_id: string;
  application_name: string;
  organization_name: string;
  project_name: string;
  overall_application_health: {
    health_score: number;
    health_grade: string;
    metric_basis: string;
    explanation: string;
  };
  architecture_complexity: {
    metric_basis: string;
    total_files: number;
    total_loc_code: number;
    total_symbols: number;
    max_cyclomatic_complexity: number;
    avg_cyclomatic_complexity: number;
    complexity_tier: string;
    db_tables_count: number;
    api_endpoints_count: number;
    infra_resources_count: number;
  };
  risk_distribution: {
    metric_basis: string;
    total_risks: number;
    by_severity: Record<string, number>;
    by_category: Record<string, number>;
  };
  testing_maturity: {
    maturity_tier: string;
    discovered_test_suites: number;
    discovered_test_cases: number;
    discovered_requirement_coverage_pct: number;
    discovered_symbol_coverage_pct: number;
    recommended_test_blueprints: number;
    discovered_basis: string;
    blueprint_basis: string;
  };
  technical_debt_distribution: {
    total_debt_items: number;
    counts_by_category: Record<string, number>;
    measured_basis: string;
    estimated_remediation_hours: number;
    effort_basis: string;
  };
  modernization_readiness: {
    microservices_recommended: boolean;
    dimensions: ModernizationAssessmentResponse["dimensions"];
    metric_basis: string;
  };
  priority_recommendations: ModernizationRoadmapResponse["recommendations"];
  critical_unresolved_issues: {
    high_or_critical_risks_count: number;
    unresolved_conflicts_count: number;
    untested_requirements_count: number;
    pending_human_reviews_count: number;
  };
  estimated_modernization_effort: {
    metric_basis: string;
    total_technical_debt_remediation_hours: number;
    recommendation_effort_ranges: Array<{
      title: string;
      phase: number;
      tshirt: string;
      range: string;
    }>;
    disclaimer: string;
  };
}

export interface QaCitationItem {
  citation_id: string;
  source_kind: string;
  title: string;
  relative_path: string;
  start_line: number;
  end_line: number;
  snippet_sha256: string;
  excerpt_text: string;
  confidence_score: number;
}

export interface QaMessageItem {
  id: string;
  conversation_id: string;
  sequence_no: number;
  role: "USER" | "ASSISTANT";
  question_intent: string | null;
  content_markdown: string;
  direct_facts: string[];
  inferred_explanations: string[];
  citations: QaCitationItem[];
  insufficient_evidence: boolean;
  confidence_score: number | null;
  agent_run_id: string | null;
  created_at: string | null;
}

export interface QaConversationSummary {
  id: string;
  tenant_id: string;
  project_id: string;
  application_id: string;
  snapshot_id: string;
  title: string;
  conversation_status: string;
  created_at: string | null;
  updated_at: string | null;
  messages?: QaMessageItem[];
}

export interface QaAskResponse {
  conversation_id: string;
  snapshot_id: string;
  question_intent: string;
  user_message: QaMessageItem;
  assistant_message: QaMessageItem;
}

export interface IntelligenceReportResponse {
  id: string;
  tenant_id: string;
  project_id: string;
  application_id: string;
  snapshot_id: string;
  branding: {
    organization_name: string;
    organization_slug: string;
    project_name: string;
    project_key: string;
    application_name: string;
    repository_name: string;
    snapshot_label: string;
  };
  report_type: string;
  report_type_display: string;
  title: string;
  current_version_no: number;
  version_no: number;
  version_id: string;
  lifecycle_status: string;
  report_lifecycle_status: string;
  is_immutable: boolean;
  executive_summary_markdown: string;
  scope_and_methodology_markdown: string;
  sections: Array<{
    section_key: string;
    title: string;
    metric_basis: string;
    review_posture: string;
    content_markdown: string;
  }>;
  evidence_references: Array<{
    ref_id: string;
    category: string;
    title: string;
    relative_path: string;
    start_line: number;
    end_line: number;
    snippet_sha256: string;
    excerpt_text: string;
  }>;
  risks_and_limitations_markdown: string;
  recommendations: ModernizationRoadmapResponse["recommendations"];
  metrics_summary: {
    measured: Record<string, number>;
    heuristic_estimates: Record<string, number>;
    inferred: Record<string, number>;
  };
  content_sha256: string;
  review_comment: string | null;
  reviewer_user_id: string | null;
  generated_at: string | null;
  reviewed_at: string | null;
  versions: Array<{
    version_id: string;
    version_no: number;
    lifecycle_status: string;
    is_immutable: boolean;
    content_sha256: string;
    review_comment: string | null;
    reviewer_user_id: string | null;
    created_at: string | null;
    reviewed_at: string | null;
  }>;
}

export interface ReportListResponse {
  snapshot_id: string;
  available_report_types: Array<{ report_type: string; display_name: string }>;
  reports: Array<{
    id: string;
    project_id: string;
    application_id: string;
    snapshot_id: string;
    report_type: string;
    report_type_display: string;
    title: string;
    current_version_no: number;
    lifecycle_status: string;
    is_approved: boolean;
    approved_at: string | null;
    created_at: string | null;
    updated_at: string | null;
  }>;
}

export interface ReportExportItem {
  id: string;
  tenant_id: string;
  project_id: string;
  report_id: string;
  report_version_id: string;
  export_format: string;
  status: string;
  file_name: string;
  mime_type: string;
  file_size_bytes: number;
  content_sha256: string;
  storage_object_uri: string;
  branding: Record<string, string>;
  requested_by_user_id: string | null;
  audit_log_id: string | null;
  download_count: number;
  created_at: string | null;
}

export interface AuditLogItem {
  id: string;
  tenant_id: string;
  actor_user_id: string | null;
  action_code: string;
  target_resource_type: string;
  target_resource_id: string | null;
  metadata_diff: Record<string, unknown>;
  previous_hash: string | null;
  record_hash: string;
  occurred_at: string | null;
}

export interface SnapshotExportsResponse {
  snapshot_id: string;
  exports: ReportExportItem[];
  audit_logs: AuditLogItem[];
}

export interface TenantAuthHeaders {
  tenantId: string;
  userId: string;
  accessToken?: string | null;
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
    if (auth.accessToken) {
      headers["Authorization"] = `Bearer ${auth.accessToken}`;
    }
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

  analyzeSnapshotWave3: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<Wave3AnalyzeSummaryResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/requirements-intelligence/analyze`,
      { method: "POST" },
      auth
    ),

  getSnapshotBusinessRules: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<BusinessRulesResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/business-rules`,
      { method: "GET" },
      auth
    ),

  reviewBusinessRule: (
    ruleId: string,
    payload: {
      new_status: string;
      review_comment?: string;
      updated_title?: string;
      updated_condition_expression?: string;
      updated_action_consequence?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<{
      id: string;
      rule_code: string;
      review_status: string;
      is_confirmed_fact: boolean;
      version_no: number;
    }>(
      `/api/v1/business-rules/${encodeURIComponent(ruleId)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  getSnapshotRequirements: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<RequirementsResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/requirements`,
      { method: "GET" },
      auth
    ),

  reviewRequirement: (
    requirementId: string,
    payload: {
      new_status: string;
      review_comment?: string;
      updated_title?: string;
      updated_specification_statement?: string;
      updated_priority?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<{
      id: string;
      req_code: string;
      review_status: string;
      is_confirmed_fact: boolean;
      version_no: number;
    }>(
      `/api/v1/requirements/${encodeURIComponent(requirementId)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  getSnapshotTraceability: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<TraceabilityResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/traceability`,
      { method: "GET" },
      auth
    ),

  getSnapshotConflictsAndGaps: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<ConflictsAndGapsResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/conflicts-and-gaps`,
      { method: "GET" },
      auth
    ),

  resolveConflict: (
    conflictId: string,
    payload: {
      new_status: string;
      resolution_notes?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<{ id: string; status: string; resolution_notes: string | null }>(
      `/api/v1/conflicts/${encodeURIComponent(conflictId)}/resolve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  getSnapshotImpactAnalysis: (
    snapshotId: string,
    targetId: string,
    auth: TenantAuthHeaders
  ) =>
    fetchJson<ImpactAnalysisResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/impact-analysis?target_id=${encodeURIComponent(targetId)}`,
      { method: "GET" },
      auth
    ),

  analyzeSnapshotWave4: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<Wave4AnalyzeSummaryResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/testing-modernization/analyze`,
      { method: "POST" },
      auth
    ),

  getSnapshotTestIntelligence: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<TestIntelligenceResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/test-intelligence`,
      { method: "GET" },
      auth
    ),

  getSnapshotCoverageAndGaps: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<CoverageAndGapsResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/coverage-and-gaps`,
      { method: "GET" },
      auth
    ),

  getSnapshotRiskRegister: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<RiskRegisterResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/risk-register`,
      { method: "GET" },
      auth
    ),

  getSnapshotTechnicalDebt: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<TechnicalDebtResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/technical-debt`,
      { method: "GET" },
      auth
    ),

  getSnapshotModernizationAssessment: (
    snapshotId: string,
    auth: TenantAuthHeaders
  ) =>
    fetchJson<ModernizationAssessmentResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/modernization-assessment`,
      { method: "GET" },
      auth
    ),

  getSnapshotModernizationRoadmap: (
    snapshotId: string,
    auth: TenantAuthHeaders
  ) =>
    fetchJson<ModernizationRoadmapResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/modernization-roadmap`,
      { method: "GET" },
      auth
    ),

  reviewModernizationRecommendation: (
    recommendationId: string,
    payload: {
      new_status: string;
      review_comment?: string;
      updated_title?: string;
      updated_target_state_architecture?: string;
      updated_effort_tshirt?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<{
      id: string;
      title: string;
      review_status: string;
      is_confirmed_fact: boolean;
    }>(
      `/api/v1/modernization-recommendations/${encodeURIComponent(recommendationId)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  reviewTestCase: (
    testCaseId: string,
    payload: {
      new_status: string;
      review_comment?: string;
      updated_generated_code_blueprint?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<{
      id: string;
      test_key: string;
      review_status: string;
      is_confirmed_fact: boolean;
    }>(
      `/api/v1/test-cases/${encodeURIComponent(testCaseId)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  // Wave 5: Unified Application Intelligence Dashboard, Semantic Q&A, Reports & Export Governance
  getApplicationIntelligenceDashboard: (
    snapshotId: string,
    auth: TenantAuthHeaders
  ) =>
    fetchJson<ApplicationIntelligenceDashboardResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/intelligence-dashboard`,
      { method: "GET" },
      auth
    ),

  getExecutiveInsights: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<ExecutiveInsightsResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/executive-insights`,
      { method: "GET" },
      auth
    ),

  listQaConversations: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<{ conversations: QaConversationSummary[] }>(
      `/api/v1/qa/conversations?snapshot_id=${encodeURIComponent(snapshotId)}`,
      { method: "GET" },
      auth
    ),

  getQaConversation: (conversationId: string, auth: TenantAuthHeaders) =>
    fetchJson<QaConversationSummary>(
      `/api/v1/qa/conversations/${encodeURIComponent(conversationId)}`,
      { method: "GET" },
      auth
    ),

  askSnapshotQaQuestion: (
    snapshotId: string,
    question: string,
    auth: TenantAuthHeaders
  ) =>
    fetchJson<QaAskResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/qa/ask`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      },
      auth
    ),

  askConversationQaQuestion: (
    conversationId: string,
    question: string,
    auth: TenantAuthHeaders
  ) =>
    fetchJson<QaAskResponse>(
      `/api/v1/qa/conversations/${encodeURIComponent(conversationId)}/ask`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      },
      auth
    ),

  listSnapshotReports: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<ReportListResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/reports`,
      { method: "GET" },
      auth
    ),

  generateIntelligenceReport: (
    snapshotId: string,
    payload: {
      report_type: string;
      initial_status?: string;
      custom_title?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<IntelligenceReportResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/reports/generate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  getIntelligenceReport: (
    reportId: string,
    versionNo: number | undefined,
    auth: TenantAuthHeaders
  ) => {
    const q = versionNo ? `?version_no=${versionNo}` : "";
    return fetchJson<IntelligenceReportResponse>(
      `/api/v1/reports/${encodeURIComponent(reportId)}${q}`,
      { method: "GET" },
      auth
    );
  },

  transitionReportLifecycle: (
    reportId: string,
    payload: {
      target_status: string;
      review_comment?: string;
      updated_title?: string;
      updated_executive_summary_markdown?: string;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<IntelligenceReportResponse>(
      `/api/v1/reports/${encodeURIComponent(reportId)}/lifecycle`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  exportIntelligenceReport: (
    reportId: string,
    payload: {
      export_format: string;
      version_no?: number;
      custom_branding?: Record<string, string>;
    },
    auth: TenantAuthHeaders
  ) =>
    fetchJson<ReportExportItem>(
      `/api/v1/reports/${encodeURIComponent(reportId)}/exports`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      auth
    ),

  listSnapshotExports: (snapshotId: string, auth: TenantAuthHeaders) =>
    fetchJson<SnapshotExportsResponse>(
      `/api/v1/snapshots/${encodeURIComponent(snapshotId)}/exports`,
      { method: "GET" },
      auth
    ),

  downloadReportExport: async (
    exportId: string,
    fallbackFileName: string,
    auth: TenantAuthHeaders
  ): Promise<void> => {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/exports/${encodeURIComponent(exportId)}/download`,
      {
        method: "GET",
        headers: {
          "X-Tenant-Id": auth.tenantId,
          "X-User-Id": auth.userId,
        },
        cache: "no-store",
      }
    );
    if (!response.ok) {
      throw new Error(`Download failed with HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fallbackFileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },
};
