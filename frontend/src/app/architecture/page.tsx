"use client";

import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiClient } from "@/lib/api";

const fallbackTopologyNodes: Node[] = [
  {
    id: "frontend",
    position: { x: 60, y: 100 },
    data: { label: "Next.js App Router (Wave 2 UI)" },
    style: {
      background: "#0f172a",
      color: "#f8fafc",
      borderRadius: "8px",
      padding: "10px",
      fontSize: "12px",
      fontFamily: "monospace",
    },
  },
  {
    id: "backend",
    position: { x: 320, y: 100 },
    data: { label: "FastAPI Backend (/api/v1)" },
    style: {
      background: "#1e293b",
      color: "#f8fafc",
      borderRadius: "8px",
      padding: "10px",
      fontSize: "12px",
      fontFamily: "monospace",
    },
  },
  {
    id: "postgres",
    position: { x: 600, y: 25 },
    data: { label: "PostgreSQL 17 + pgvector (:5432)" },
    style: {
      background: "#f8fafc",
      color: "#0f172a",
      border: "1px solid #cbd5e1",
      borderRadius: "8px",
      padding: "10px",
      fontSize: "12px",
      fontFamily: "monospace",
    },
  },
  {
    id: "redis",
    position: { x: 600, y: 100 },
    data: { label: "Redis 7 (:6380)" },
    style: {
      background: "#f8fafc",
      color: "#0f172a",
      border: "1px solid #cbd5e1",
      borderRadius: "8px",
      padding: "10px",
      fontSize: "12px",
      fontFamily: "monospace",
    },
  },
  {
    id: "ollama",
    position: { x: 600, y: 175 },
    data: { label: "Ollama qwen2.5-coder:3b (:11434)" },
    style: {
      background: "#f8fafc",
      color: "#0f172a",
      border: "1px solid #cbd5e1",
      borderRadius: "8px",
      padding: "10px",
      fontSize: "12px",
      fontFamily: "monospace",
    },
  },
];

const fallbackTopologyEdges: Edge[] = [
  { id: "e-fe-be", source: "frontend", target: "backend", animated: true },
  { id: "e-be-pg", source: "backend", target: "postgres" },
  { id: "e-be-rd", source: "backend", target: "redis" },
  { id: "e-be-ol", source: "backend", target: "ollama" },
];

type TabKey = "graph" | "database" | "apis" | "infra_docs" | "findings_agents";

export default function ArchitecturePage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabKey>("graph");

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap-context"],
    queryFn: () => apiClient.bootstrapContext(),
    retry: 1,
  });

  const auth = bootstrapQuery.data
    ? {
        tenantId: bootstrapQuery.data.tenant_id,
        userId: bootstrapQuery.data.user_id,
      }
    : undefined;

  const projectId = bootstrapQuery.data?.project_id;
  const snapshotId = bootstrapQuery.data?.latest_snapshot_id;

  const graphQuery = useQuery({
    queryKey: ["wave2-graph", snapshotId],
    queryFn: () => apiClient.getSnapshotKnowledgeGraph(snapshotId!, auth!),
    enabled: Boolean(snapshotId && auth),
  });

  const dbIntelQuery = useQuery({
    queryKey: ["wave2-db", snapshotId],
    queryFn: () => apiClient.getSnapshotDatabaseIntel(snapshotId!, auth!),
    enabled: Boolean(snapshotId && auth),
  });

  const apiIntelQuery = useQuery({
    queryKey: ["wave2-apis", snapshotId],
    queryFn: () => apiClient.getSnapshotApiIntel(snapshotId!, auth!),
    enabled: Boolean(snapshotId && auth),
  });

  const infraIntelQuery = useQuery({
    queryKey: ["wave2-infra", snapshotId],
    queryFn: () => apiClient.getSnapshotInfraIntel(snapshotId!, auth!),
    enabled: Boolean(snapshotId && auth),
  });

  const docIntelQuery = useQuery({
    queryKey: ["wave2-docs", snapshotId],
    queryFn: () => apiClient.getSnapshotDocIntel(snapshotId!, auth!),
    enabled: Boolean(snapshotId && auth),
  });

  const findingsQuery = useQuery({
    queryKey: ["wave2-findings", snapshotId],
    queryFn: () => apiClient.getSnapshotFindings(snapshotId!, auth!),
    enabled: Boolean(snapshotId && auth),
  });

  const agentsQuery = useQuery({
    queryKey: ["wave2-agents", snapshotId],
    queryFn: () => apiClient.getSnapshotAgents(snapshotId!, auth!),
    enabled: Boolean(snapshotId && auth),
  });

  const symbolsQuery = useQuery({
    queryKey: ["code-symbols", projectId],
    queryFn: () => apiClient.listCodeSymbols(projectId!, auth!),
    enabled: Boolean(projectId && auth),
  });

  const analyzeWave2Mutation = useMutation({
    mutationFn: () => apiClient.analyzeSnapshotWave2(snapshotId!, auth!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wave2-graph", snapshotId] });
      queryClient.invalidateQueries({ queryKey: ["wave2-db", snapshotId] });
      queryClient.invalidateQueries({ queryKey: ["wave2-apis", snapshotId] });
      queryClient.invalidateQueries({ queryKey: ["wave2-infra", snapshotId] });
      queryClient.invalidateQueries({ queryKey: ["wave2-docs", snapshotId] });
      queryClient.invalidateQueries({ queryKey: ["wave2-findings", snapshotId] });
      queryClient.invalidateQueries({ queryKey: ["wave2-agents", snapshotId] });
    },
  });

  const reviewFindingMutation = useMutation({
    mutationFn: ({
      findingId,
      newStatus,
    }: {
      findingId: string;
      newStatus: string;
    }) =>
      apiClient.reviewFinding(
        findingId,
        {
          new_status: newStatus,
          review_comment: `Reviewed via Wave 2 Architecture Console (${newStatus})`,
        },
        auth!
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wave2-findings", snapshotId] });
    },
  });

  const { nodes, edges, isLiveKnowledgeGraph } = useMemo<{
    nodes: Node[];
    edges: Edge[];
    isLiveKnowledgeGraph: boolean;
  }>(() => {
    const kEntities = graphQuery.data?.entities || [];
    const kRels = graphQuery.data?.relationships || [];

    if (kEntities.length > 0) {
      const displayed = kEntities.slice(0, 28);
      const colorByType: Record<string, { bg: string; fg: string }> = {
        MODULE: { bg: "#0f172a", fg: "#f8fafc" },
        SYMBOL: { bg: "#ffffff", fg: "#0f172a" },
        DB_TABLE: { bg: "#ecfdf5", fg: "#065f46" },
        API_ENDPOINT: { bg: "#eff6ff", fg: "#1e40af" },
        SERVICE: { bg: "#1e3a8a", fg: "#f8fafc" },
        INFRA_RESOURCE: { bg: "#fef3c7", fg: "#92400e" },
      };

      const gNodes: Node[] = displayed.map((ent, idx) => {
        const col = idx % 4;
        const row = Math.floor(idx / 4);
        const palette = colorByType[ent.entity_type] || {
          bg: "#f8fafc",
          fg: "#0f172a",
        };
        return {
          id: ent.id,
          position: { x: 40 + col * 260, y: 40 + row * 100 },
          data: { label: `[${ent.entity_type}] ${ent.title}` },
          style: {
            background: palette.bg,
            color: palette.fg,
            border: "1px solid #cbd5e1",
            borderRadius: "8px",
            padding: "8px 10px",
            fontSize: "11px",
            fontFamily: "monospace",
          },
        };
      });

      const nodeSet = new Set(displayed.map((e) => e.id));
      const gEdges: Edge[] = kRels
        .filter(
          (r) => nodeSet.has(r.source_entity_id) && nodeSet.has(r.target_entity_id)
        )
        .map((r) => ({
          id: r.id,
          source: r.source_entity_id,
          target: r.target_entity_id,
          animated: true,
          label: r.relationship_type,
        }));

      return { nodes: gNodes, edges: gEdges, isLiveKnowledgeGraph: true };
    }

    const syms = symbolsQuery.data || [];
    if (syms.length > 0) {
      const displayedSyms = syms.slice(0, 20);
      return {
        nodes: displayedSyms.map((s, idx) => ({
          id: s.id,
          position: { x: 40 + (idx % 4) * 250, y: 40 + Math.floor(idx / 4) * 100 },
          data: { label: `${s.symbol_kind}: ${s.qualified_name}` },
          style: {
            background: "#ffffff",
            color: "#0f172a",
            border: "1px solid #cbd5e1",
            borderRadius: "8px",
            padding: "8px 10px",
            fontSize: "11px",
            fontFamily: "monospace",
          },
        })),
        edges: [],
        isLiveKnowledgeGraph: true,
      };
    }

    return {
      nodes: fallbackTopologyNodes,
      edges: fallbackTopologyEdges,
      isLiveKnowledgeGraph: false,
    };
  }, [graphQuery.data, symbolsQuery.data]);

  const entityCounts = graphQuery.data?.entity_counts_by_type || {};
  const dbTables = dbIntelQuery.data?.tables || [];
  const dbFks = dbIntelQuery.data?.foreign_keys || [];
  const apiEndpoints = apiIntelQuery.data?.endpoints || [];
  const infraResources = infraIntelQuery.data?.resources || [];
  const docSections = docIntelQuery.data?.sections || [];
  const findings = findingsQuery.data?.findings || [];
  const agentRuns = agentsQuery.data?.agent_runs || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Technical Intelligence &amp; Unified Knowledge Graph
            </h1>
            <Badge variant="success">
              {isLiveKnowledgeGraph ? "Wave 2 Live Graph" : "Wave 2 Ready"}
            </Badge>
          </div>
          <p className="text-sm text-slate-600 mt-1">
            Database schemas, REST/GraphQL APIs, Infrastructure-as-Code, Documentation sections, Provenance anchors, and AI Agent Orchestration.
          </p>
        </div>
        {snapshotId && (
          <Button
            size="sm"
            onClick={() => analyzeWave2Mutation.mutate()}
            disabled={analyzeWave2Mutation.isPending}
          >
            {analyzeWave2Mutation.isPending
              ? "Running Wave 2 Pipeline..."
              : "Run / Refresh Wave 2 Intelligence"}
          </Button>
        )}
      </div>

      {/* Summary KPI Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">Graph Entities</div>
            <div className="text-xl font-bold text-slate-900">
              {graphQuery.data?.entities.length ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">DB Tables / FKs</div>
            <div className="text-xl font-bold text-slate-900">
              {dbTables.length} / {dbFks.length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">API Endpoints</div>
            <div className="text-xl font-bold text-slate-900">
              {apiEndpoints.length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">Infra Resources</div>
            <div className="text-xl font-bold text-slate-900">
              {infraResources.length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">Doc Sections</div>
            <div className="text-xl font-bold text-slate-900">
              {docSections.length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">Findings &amp; Agents</div>
            <div className="text-xl font-bold text-slate-900">
              {findings.length} / {agentRuns.length}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {(
          [
            ["graph", "1. Unified Knowledge Graph"],
            ["database", `2. Database Intelligence (${dbTables.length})`],
            ["apis", `3. API Intelligence (${apiEndpoints.length})`],
            [
              "infra_docs",
              `4. Infra (${infraResources.length}) & Docs (${docSections.length})`,
            ],
            [
              "findings_agents",
              `5. Findings (${findings.length}) & AI Agents (${agentRuns.length})`,
            ],
          ] as Array<[TabKey, string]>
        ).map(([key, label]) => (
          <Button
            key={key}
            variant={activeTab === key ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab(key)}
          >
            {label}
          </Button>
        ))}
      </div>

      {activeTab === "graph" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Unified Knowledge Graph Canvas
            </CardTitle>
            <CardDescription>
              Connects Modules, Symbols, DB Tables, API Endpoints, and Infrastructure Resources with NetworkX PageRank &amp; SCC analysis.
              {Object.keys(entityCounts).length > 0 && (
                <span className="ml-2 font-mono text-xs text-slate-700">
                  {Object.entries(entityCounts)
                    .map(([k, v]) => `${k}:${v}`)
                    .join(" | ")}
                </span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[440px] w-full rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                fitView
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#cbd5e1" gap={18} />
                <Controls />
              </ReactFlow>
            </div>
          </CardContent>
        </Card>
      )}

      {activeTab === "database" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Discovered Tables &amp; Views ({dbTables.length})
              </CardTitle>
              <CardDescription>
                Extracted from SQL DDL scripts, migrations, and ORM entity mappings.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {dbTables.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No database tables discovered yet. Click &quot;Run / Refresh Wave 2 Intelligence&quot; or upload a repository containing SQL/ORM models.
                </p>
              ) : (
                dbTables.map((tbl) => (
                  <div
                    key={tbl.id}
                    className="rounded border border-slate-200 p-3 space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-semibold text-slate-900">
                        {tbl.schema_name}.{tbl.table_name}
                      </span>
                      <Badge variant="outline">{tbl.table_kind}</Badge>
                    </div>
                    {tbl.comment_text && (
                      <p className="text-xs text-slate-600">{tbl.comment_text}</p>
                    )}
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {tbl.columns.map((c) => (
                        <span
                          key={c.id}
                          className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${
                            c.is_pii_candidate
                              ? "bg-red-50 text-red-800 border border-red-200"
                              : c.is_primary_key
                              ? "bg-slate-900 text-white"
                              : "bg-slate-100 text-slate-700"
                          }`}
                        >
                          {c.column_name}: {c.data_type}
                          {c.is_primary_key ? " [PK]" : ""}
                          {c.is_pii_candidate ? " [PII]" : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Foreign-Key Relationships ({dbFks.length})
              </CardTitle>
              <CardDescription>
                Explicit DDL constraints and ORM `ForeignKey` relations.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {dbFks.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No foreign-key relationships discovered in this snapshot.
                </p>
              ) : (
                dbFks.map((fk) => (
                  <div
                    key={fk.id}
                    className="rounded border border-slate-200 p-2.5 text-xs font-mono flex items-center justify-between"
                  >
                    <span>
                      {fk.source_table_name}({fk.source_column_names.join(", ")}) &rarr;{" "}
                      {fk.target_table_name}({fk.target_column_names.join(", ")})
                    </span>
                    <Badge variant="outline">{fk.relation_origin}</Badge>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "apis" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Discovered REST, OpenAPI &amp; GraphQL Endpoints ({apiEndpoints.length})
            </CardTitle>
            <CardDescription>
              Extracted from OpenAPI/Swagger specs, GraphQL SDL schemas, and source route decorators.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {apiEndpoints.length === 0 ? (
              <p className="text-xs text-slate-500">
                No API endpoints discovered yet for this snapshot.
              </p>
            ) : (
              apiEndpoints.map((ep) => (
                <div
                  key={ep.id}
                  className="rounded border border-slate-200 p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <Badge variant="default" className="font-mono text-xs">
                        {ep.http_method}
                      </Badge>
                      <span className="font-mono text-xs font-semibold text-slate-900">
                        {ep.route_pattern}
                      </span>
                      <span className="text-xs text-slate-500">
                        ({ep.service_name} / {ep.protocol})
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        ep.auth_required_inferred ? "success" : "outline"
                      }
                    >
                      {ep.auth_required_inferred
                        ? "Auth Enforced"
                        : "Public / Unverified Auth"}
                    </Badge>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "infra_docs" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Infrastructure Resources ({infraResources.length})
              </CardTitle>
              <CardDescription>
                Parsed from Dockerfile, Docker Compose, Kubernetes, Terraform, and CloudFormation.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {infraResources.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No IaC manifests discovered in this snapshot.
                </p>
              ) : (
                infraResources.map((r) => (
                  <div
                    key={r.id}
                    className="rounded border border-slate-200 p-3 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-semibold text-slate-900">
                        {r.resource_name}
                      </span>
                      <Badge variant="outline">
                        {r.iac_tool} / {r.resource_type}
                      </Badge>
                    </div>
                    <pre className="text-[11px] font-mono bg-slate-50 p-2 rounded overflow-x-auto text-slate-700">
                      {JSON.stringify(r.configuration_attributes, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Documentation Sections ({docSections.length})
              </CardTitle>
              <CardDescription>
                Extracted from Markdown, HTML, DOCX, XLSX, and PDF documentation files.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {docSections.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No technical documentation sections extracted in this snapshot.
                </p>
              ) : (
                docSections.slice(0, 20).map((sec) => (
                  <div
                    key={sec.id}
                    className="rounded border border-slate-200 p-3 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-xs text-slate-900">
                        {sec.heading_path}
                      </span>
                      <span className="font-mono text-[11px] text-slate-500">
                        {sec.canonical_path} (L{sec.start_line}–L{sec.end_line})
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 line-clamp-3">
                      {sec.content_markdown}
                    </p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "findings_agents" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Evidence-Backed Findings &amp; Human Review ({findings.length})
              </CardTitle>
              <CardDescription>
                Every finding links to immutable SHA-256 `evidence_anchors` and supports audited review transitions.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {findings.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No findings generated yet. Run Wave 2 intelligence to synthesize evidence-backed findings.
                </p>
              ) : (
                findings.map((f) => (
                  <div
                    key={f.id}
                    className="rounded border border-slate-200 p-3 space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-xs text-slate-900">
                        {f.title}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <Badge variant="outline">{f.finding_category}</Badge>
                        <Badge
                          variant={
                            f.review_status === "APPROVED"
                              ? "success"
                              : "default"
                          }
                        >
                          {f.review_status}
                        </Badge>
                      </div>
                    </div>
                    <p className="text-xs text-slate-700">
                      {f.statement_markdown}
                    </p>
                    <div className="text-[11px] font-mono text-slate-500">
                      Origin: {f.origin_type} | Confidence:{" "}
                      {(f.confidence_score * 100).toFixed(0)}% | Evidence Anchors:{" "}
                      {f.evidence.length}
                    </div>
                    {f.evidence.map((ev) => (
                      <div
                        key={ev.link_id}
                        className="rounded bg-slate-50 p-2 text-[11px] font-mono text-slate-700 border border-slate-200"
                      >
                        [{ev.evidence_role}] L{ev.start_line}–L{ev.end_line} (SHA256:{" "}
                        {ev.snippet_sha256.slice(0, 12)}...): {ev.excerpt_text}
                      </div>
                    ))}
                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewFindingMutation.mutate({
                            findingId: f.id,
                            newStatus: "APPROVED",
                          })
                        }
                        disabled={reviewFindingMutation.isPending}
                      >
                        Approve Finding
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewFindingMutation.mutate({
                            findingId: f.id,
                            newStatus: "REJECTED",
                          })
                        }
                        disabled={reviewFindingMutation.isPending}
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                AI Agent Orchestration Runs ({agentRuns.length})
              </CardTitle>
              <CardDescription>
                Central orchestrator and specialized technical intelligence agents (`repo_cartographer`, `db_analyst`, `api_inspector`, `infra_auditor`, `doc_linker`).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {agentRuns.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No agent runs recorded for this snapshot yet.
                </p>
              ) : (
                agentRuns.map((ar) => (
                  <div
                    key={ar.id}
                    className="rounded border border-slate-200 p-3 flex items-center justify-between"
                  >
                    <div>
                      <div className="font-mono text-xs font-semibold text-slate-900">
                        {ar.agent_name} (v{ar.agent_version})
                      </div>
                      <div className="text-[11px] text-slate-500 font-mono">
                        Attempts: {ar.attempt_count} | Output:{" "}
                        {JSON.stringify(ar.output_summary_json)}
                      </div>
                    </div>
                    <Badge
                      variant={
                        ar.status === "COMPLETED" ? "success" : "outline"
                      }
                    >
                      {ar.status}
                    </Badge>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
