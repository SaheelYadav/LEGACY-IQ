"use client";

import React, { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  Award,
  BookOpen,
  Bot,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  Lock,
  MessageSquare,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { InfrastructureStatusPanel } from "@/components/health/infrastructure-status-panel";
import { apiClient } from "@/lib/api";

type Wave5Tab =
  | "overview"
  | "assistant"
  | "reports"
  | "executive"
  | "exports";

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Wave5Tab>("overview");
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>("");

  // Q&A state
  const [selectedConversationId, setSelectedConversationId] =
    useState<string>("");
  const [questionInput, setQuestionInput] = useState<string>("");

  // Reports state
  const [selectedReportType, setSelectedReportType] = useState<string>(
    "COMPLETE_INTELLIGENCE"
  );
  const [selectedReportId, setSelectedReportId] = useState<string>("");
  const [selectedVersionNo, setSelectedVersionNo] = useState<
    number | undefined
  >(undefined);
  const [lifecycleComment, setLifecycleComment] = useState<string>("");
  const [editedSummaryInput, setEditedSummaryInput] = useState<string>("");

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

  const reposQuery = useQuery({
    queryKey: ["repositories", projectId],
    queryFn: () => apiClient.listRepositories(projectId!, auth!),
    enabled: Boolean(projectId && auth),
  });

  useEffect(() => {
    if (
      !selectedRepoId &&
      reposQuery.data &&
      reposQuery.data.length > 0 &&
      reposQuery.data[0]
    ) {
      setSelectedRepoId(reposQuery.data[0].id);
    }
  }, [reposQuery.data, selectedRepoId]);

  const snapshotsQuery = useQuery({
    queryKey: ["project-snapshots", projectId],
    queryFn: () => apiClient.listProjectSnapshots(projectId!, auth!),
    enabled: Boolean(projectId && auth),
  });

  const filteredSnapshots = (snapshotsQuery.data || []).filter(
    (s) => !selectedRepoId || s.repository_id === selectedRepoId
  );

  useEffect(() => {
    if (filteredSnapshots.length > 0 && filteredSnapshots[0]) {
      const exists = filteredSnapshots.some(
        (s) => s.id === selectedSnapshotId
      );
      if (!selectedSnapshotId || !exists) {
        setSelectedSnapshotId(filteredSnapshots[0].id);
      }
    }
  }, [filteredSnapshots, selectedSnapshotId]);

  const dashboardQuery = useQuery({
    queryKey: ["wave5-dashboard", selectedSnapshotId],
    queryFn: () =>
      apiClient.getApplicationIntelligenceDashboard(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const executiveQuery = useQuery({
    queryKey: ["wave5-executive", selectedSnapshotId],
    queryFn: () =>
      apiClient.getExecutiveInsights(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const conversationsQuery = useQuery({
    queryKey: ["wave5-qa-conversations", selectedSnapshotId],
    queryFn: () => apiClient.listQaConversations(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  useEffect(() => {
    const list = conversationsQuery.data?.conversations || [];
    if (list.length > 0 && list[0] && !selectedConversationId) {
      setSelectedConversationId(list[0].id);
    }
  }, [conversationsQuery.data, selectedConversationId]);

  const activeConversationQuery = useQuery({
    queryKey: ["wave5-qa-conversation", selectedConversationId],
    queryFn: () =>
      apiClient.getQaConversation(selectedConversationId, auth!),
    enabled: Boolean(selectedConversationId && auth),
  });

  const reportsListQuery = useQuery({
    queryKey: ["wave5-reports-list", selectedSnapshotId],
    queryFn: () => apiClient.listSnapshotReports(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  useEffect(() => {
    const reps = reportsListQuery.data?.reports || [];
    if (reps.length > 0 && reps[0]) {
      const exists = reps.some((r) => r.id === selectedReportId);
      if (!selectedReportId || !exists) {
        setSelectedReportId(reps[0].id);
        setSelectedVersionNo(undefined);
      }
    }
  }, [reportsListQuery.data, selectedReportId]);

  const activeReportQuery = useQuery({
    queryKey: ["wave5-report-detail", selectedReportId, selectedVersionNo],
    queryFn: () =>
      apiClient.getIntelligenceReport(
        selectedReportId,
        selectedVersionNo,
        auth!
      ),
    enabled: Boolean(selectedReportId && auth),
  });

  const exportsQuery = useQuery({
    queryKey: ["wave5-exports", selectedSnapshotId],
    queryFn: () => apiClient.listSnapshotExports(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const askQuestionMutation = useMutation({
    mutationFn: async (questionText: string) => {
      if (selectedConversationId) {
        return apiClient.askConversationQaQuestion(
          selectedConversationId,
          questionText,
          auth!
        );
      }
      return apiClient.askSnapshotQaQuestion(
        selectedSnapshotId,
        questionText,
        auth!
      );
    },
    onSuccess: (res) => {
      setSelectedConversationId(res.conversation_id);
      setQuestionInput("");
      queryClient.invalidateQueries({
        queryKey: ["wave5-qa-conversations", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave5-qa-conversation", res.conversation_id],
      });
    },
  });

  const generateReportMutation = useMutation({
    mutationFn: (reportType: string) =>
      apiClient.generateIntelligenceReport(
        selectedSnapshotId,
        { report_type: reportType, initial_status: "GENERATED" },
        auth!
      ),
    onSuccess: (rep) => {
      setSelectedReportId(rep.id);
      setSelectedVersionNo(rep.version_no);
      queryClient.invalidateQueries({
        queryKey: ["wave5-reports-list", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave5-report-detail", rep.id],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave5-exports", selectedSnapshotId],
      });
    },
  });

  const transitionLifecycleMutation = useMutation({
    mutationFn: (params: {
      reportId: string;
      targetStatus: string;
      comment?: string;
      updatedSummary?: string;
    }) =>
      apiClient.transitionReportLifecycle(
        params.reportId,
        {
          target_status: params.targetStatus,
          review_comment: params.comment || undefined,
          updated_executive_summary_markdown:
            params.updatedSummary || undefined,
        },
        auth!
      ),
    onSuccess: (rep) => {
      setSelectedVersionNo(rep.current_version_no);
      setLifecycleComment("");
      setEditedSummaryInput("");
      queryClient.invalidateQueries({
        queryKey: ["wave5-reports-list", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave5-report-detail", rep.id],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave5-exports", selectedSnapshotId],
      });
    },
  });

  const exportReportMutation = useMutation({
    mutationFn: (params: {
      reportId: string;
      format: string;
      versionNo?: number;
    }) =>
      apiClient.exportIntelligenceReport(
        params.reportId,
        {
          export_format: params.format,
          version_no: params.versionNo,
        },
        auth!
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["wave5-exports", selectedSnapshotId],
      });
    },
  });

  const dash = dashboardQuery.data;
  const exec = executiveQuery.data;
  const activeReport = activeReportQuery.data;
  const messages = activeConversationQuery.data?.messages || [];

  const langEntries = Object.entries(dash?.technology_stack.languages || {});
  const chartData =
    langEntries.length > 0
      ? langEntries.map(([lang, stats]) => ({
          language: lang.toUpperCase(),
          files: stats.files,
          loc: stats.loc,
        }))
      : [{ language: "NO FILES", files: 0, loc: 0 }];

  return (
    <div className="space-y-6">
      {/* Header & Snapshot Selector */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Application Intelligence Hub &amp; Governance
            </h1>
            <Badge variant="success">Wave 5 Live</Badge>
          </div>
          <p className="text-sm text-slate-600 mt-1">
            {bootstrapQuery.data ? (
              <>
                Tenant:{" "}
                <span className="font-semibold text-slate-800">
                  {bootstrapQuery.data.organization_name}
                </span>{" "}
                &bull; Project:{" "}
                <span className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">
                  {bootstrapQuery.data.project_key}
                </span>{" "}
                ({bootstrapQuery.data.project_name})
              </>
            ) : (
              "Unified Waves 1–5 Application Intelligence Dashboard, Semantic Q&A Assistant, 11-Type Report Engine & Controlled Export Governance."
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <select
            aria-label="Select Repository"
            value={selectedRepoId}
            onChange={(e) => {
              setSelectedRepoId(e.target.value);
              setSelectedSnapshotId("");
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 shadow-sm"
          >
            {(reposQuery.data || []).length === 0 ? (
              <option value="">No repositories ingested</option>
            ) : (
              (reposQuery.data || []).map((r) => (
                <option key={r.id} value={r.id}>
                  Repo: {r.name}
                </option>
              ))
            )}
          </select>

          <select
            aria-label="Select Snapshot"
            value={selectedSnapshotId}
            onChange={(e) => setSelectedSnapshotId(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 shadow-sm"
          >
            {filteredSnapshots.length === 0 ? (
              <option value="">No snapshots available</option>
            ) : (
              filteredSnapshots.map((s) => (
                <option key={s.id} value={s.id}>
                  Snapshot: {s.snapshot_label} ({s.source_type})
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {/* 5-Tab Navigation Bar */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {(
          [
            {
              id: "overview",
              label: "1. Application Overview (Waves 1–4)",
              icon: Sparkles,
            },
            {
              id: "assistant",
              label: "2. AI Intelligence Assistant (Q&A)",
              icon: Bot,
            },
            {
              id: "reports",
              label: "3. Reports & Documents (11 Types)",
              icon: FileText,
            },
            {
              id: "executive",
              label: "4. Executive Insights",
              icon: Award,
            },
            {
              id: "exports",
              label: "5. Export History & Audit Ledger",
              icon: Download,
            },
          ] as const
        ).map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold transition-colors ${
                active
                  ? "bg-slate-900 text-white shadow-sm"
                  : "bg-white text-slate-700 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* TAB 1: UNIFIED APPLICATION OVERVIEW */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Metric Basis Attribution Banner */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5 text-xs text-slate-700 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-900">
                Metric Provenance Discipline:
              </span>
              <Badge variant="outline" className="font-mono text-[10px]">
                MEASURED
              </Badge>
              <span>AST, SQL DDL, API &amp; coverage counts</span>
              <Badge variant="secondary" className="font-mono text-[10px]">
                HEURISTIC_ESTIMATE
              </Badge>
              <span>Effort hours &amp; T-shirt sizing</span>
              <Badge variant="warning" className="font-mono text-[10px]">
                INFERRED
              </Badge>
              <span>Extracted rules, requirements &amp; test blueprints</span>
            </div>
          </div>

          {dash ? (
            <>
              {/* Top 4 KPI Cards across Waves 1-4 */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardDescription>Source &amp; AST Inventory</CardDescription>
                      <Badge variant="outline" className="text-[10px] font-mono">
                        MEASURED
                      </Badge>
                    </div>
                    <CardTitle className="text-2xl font-mono">
                      {dash.technical_inventory.code_symbols_count} symbols
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-slate-500">
                      Files: {dash.snapshot_overview.total_files} &bull; LOC:{" "}
                      {dash.snapshot_overview.total_loc_code} &bull; Call Edges:{" "}
                      {dash.technical_inventory.call_edges_count}
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardDescription>DB, API &amp; Infra Assets</CardDescription>
                      <Badge variant="outline" className="text-[10px] font-mono">
                        MEASURED
                      </Badge>
                    </div>
                    <CardTitle className="text-2xl font-mono">
                      {dash.technical_inventory.db_tables_count} tables /{" "}
                      {dash.technical_inventory.api_endpoints_count} APIs
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-slate-500">
                      Infra: {dash.technical_inventory.infra_resources_count}{" "}
                      &bull; Graph Entities:{" "}
                      {dash.technical_inventory.knowledge_entities_count} &bull;{" "}
                      Anchors: {dash.technical_inventory.evidence_anchors_count}
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardDescription>
                        Business Rules &amp; Requirements
                      </CardDescription>
                      <Badge variant="warning" className="text-[10px] font-mono">
                        INFERRED
                      </Badge>
                    </div>
                    <CardTitle className="text-2xl font-mono">
                      {dash.business_and_requirements.business_rules_count}{" "}
                      rules / {dash.business_and_requirements.requirements_count}{" "}
                      reqs
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-slate-500">
                      Approved Rules:{" "}
                      {
                        dash.business_and_requirements
                          .approved_business_rules_count
                      }{" "}
                      &bull; Approved Reqs:{" "}
                      {
                        dash.business_and_requirements
                          .approved_requirements_count
                      }
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardDescription>
                        Risks, Debt &amp; Pending Reviews
                      </CardDescription>
                      <Badge
                        variant="secondary"
                        className="text-[10px] font-mono"
                      >
                        GOVERNED
                      </Badge>
                    </div>
                    <CardTitle className="text-2xl font-mono">
                      {dash.risk_and_technical_debt.total_risk_findings} risks
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-slate-500">
                      Pending Reviews:{" "}
                      {dash.governance_and_reviews.total_pending_human_reviews}{" "}
                      &bull; Open Conflicts:{" "}
                      {dash.governance_and_reviews.unresolved_conflicts_count}
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Stack, Testing & Modernization Summary Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">
                      Technology Stack &amp; Frameworks
                    </CardTitle>
                    <CardDescription>
                      Languages, detected frameworks, and IaC tooling
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2 text-xs">
                    <div>
                      <span className="font-semibold text-slate-700">
                        Frameworks:
                      </span>{" "}
                      {dash.technology_stack.frameworks.length > 0
                        ? dash.technology_stack.frameworks.join(", ")
                        : "Standard Library"}
                    </div>
                    <div>
                      <span className="font-semibold text-slate-700">
                        IaC &amp; Containers:
                      </span>{" "}
                      {dash.technology_stack.iac_and_container_tools.length > 0
                        ? dash.technology_stack.iac_and_container_tools.join(
                            ", "
                          )
                        : "None detected"}
                    </div>
                    <div>
                      <span className="font-semibold text-slate-700">
                        Business Domains (
                        {dash.business_and_requirements.domains_count}):
                      </span>{" "}
                      {dash.business_and_requirements.domains
                        .map((d) => d.name)
                        .join(", ") || "N/A"}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">
                      Test Discovery &amp; Coverage Posture
                    </CardTitle>
                    <CardDescription>
                      Discovered (`MEASURED`) vs. Blueprint (`INFERRED`)
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span>Discovered Test Suites / Cases:</span>
                      <span className="font-mono font-semibold">
                        {dash.testing_and_coverage.discovered_test_suites_count}{" "}
                        /{" "}
                        {dash.testing_and_coverage.discovered_test_cases_count}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Discovered Requirement Coverage:</span>
                      <span className="font-mono font-semibold">
                        {
                          dash.testing_and_coverage.coverage_metrics
                            .discovered_requirement_coverage_pct
                        }
                        %
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Recommended Test Blueprints:</span>
                      <span className="font-mono font-semibold text-amber-700">
                        {
                          dash.testing_and_coverage
                            .recommended_test_blueprints_count
                        }{" "}
                        (INFERRED)
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Untested Critical Symbols:</span>
                      <span className="font-mono font-semibold text-rose-700">
                        {
                          dash.testing_and_coverage
                            .untested_critical_components_count
                        }
                      </span>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">
                      Technical Debt &amp; Modernization
                    </CardTitle>
                    <CardDescription>
                      Measured debt items vs. heuristic effort hours
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span>Detected Technical Debt Items:</span>
                      <span className="font-mono font-semibold">
                        {
                          dash.risk_and_technical_debt.technical_debt_summary
                            .measured_metrics.total_debt_items_detected
                        }{" "}
                        (MEASURED)
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Estimated Remediation Effort:</span>
                      <span className="font-mono font-semibold text-sky-700">
                        {
                          dash.risk_and_technical_debt.technical_debt_summary
                            .heuristic_estimates
                            .total_estimated_remediation_hours
                        }
                        h (ESTIMATE)
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Modernization Recommendations:</span>
                      <span className="font-mono font-semibold">
                        {dash.modernization_posture.total_recommendations}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Microservices Recommended:</span>
                      <span className="font-mono font-semibold">
                        {dash.modernization_posture.microservices_recommended
                          ? "YES"
                          : "NO (Modular Monolith Preferred)"}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          ) : null}

          <InfrastructureStatusPanel />

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">
                    Parsed Source Files by Programming Language
                  </CardTitle>
                  <CardDescription>
                    Live deterministic parser breakdown from PostgreSQL{" "}
                    <span className="font-mono text-xs">code_files</span>.
                  </CardDescription>
                </div>
                <Badge variant="outline" className="font-mono text-xs">
                  MEASURED
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="language" fontSize={12} stroke="#475569" />
                    <YAxis
                      allowDecimals={false}
                      fontSize={12}
                      stroke="#475569"
                    />
                    <Tooltip />
                    <Bar
                      dataKey="files"
                      name="Parsed Source Files"
                      fill="#0f172a"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 2: AI INTELLIGENCE ASSISTANT (SEMANTIC Q&A) */}
      {activeTab === "assistant" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Suggested Questions & Conversation History */}
          <div className="lg:col-span-4 space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-sky-600" />
                  Specialized Intelligence Queries
                </CardTitle>
                <CardDescription className="text-xs">
                  Click any question to run Hybrid RRF retrieval + specialized
                  Wave 1–4 graph analysis.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {(dash?.suggested_qa_questions || []).map((sq, idx) => (
                  <button
                    key={idx}
                    type="button"
                    disabled={
                      !selectedSnapshotId || askQuestionMutation.isPending
                    }
                    onClick={() => askQuestionMutation.mutate(sq.question)}
                    className="w-full text-left rounded-md border border-slate-200 bg-slate-50/70 hover:bg-slate-100 px-2.5 py-2 text-xs text-slate-800 transition-colors"
                  >
                    <div className="font-mono text-[10px] text-sky-700 mb-0.5">
                      {sq.intent}
                    </div>
                    <div>{sq.question}</div>
                  </button>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-slate-600" />
                    Conversation History
                  </CardTitle>
                  <button
                    type="button"
                    onClick={() => setSelectedConversationId("")}
                    className="text-[11px] font-medium text-sky-700 hover:underline"
                  >
                    + New Session
                  </button>
                </div>
                <CardDescription className="text-xs">
                  Isolated by tenant and project RBAC
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {(conversationsQuery.data?.conversations || []).length === 0 ? (
                  <p className="text-xs text-slate-500">
                    No conversations yet for this snapshot.
                  </p>
                ) : (
                  (conversationsQuery.data?.conversations || []).map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setSelectedConversationId(c.id)}
                      className={`w-full text-left rounded-md px-2.5 py-2 text-xs transition-colors ${
                        selectedConversationId === c.id
                          ? "bg-slate-900 text-white"
                          : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <div className="font-medium truncate">{c.title}</div>
                      <div className="text-[10px] opacity-75 font-mono">
                        {c.conversation_status}
                      </div>
                    </button>
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Conversational Thread & Citations */}
          <div className="lg:col-span-8 space-y-4">
            <Card className="flex flex-col">
              <CardHeader className="pb-3 border-b border-slate-100">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">
                      Application Intelligence Assistant
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Every response separates direct codebase facts from
                      inferred explanations and cites exact source files and
                      line numbers.
                    </CardDescription>
                  </div>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    Zero-Hallucination Guard Active
                  </Badge>
                </div>
              </CardHeader>

              <CardContent className="py-4 space-y-4 max-h-[600px] overflow-y-auto">
                {messages.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center space-y-2">
                    <Bot className="h-8 w-8 text-slate-400 mx-auto" />
                    <p className="text-sm font-medium text-slate-700">
                      Ask a natural-language question about your analyzed
                      application
                    </p>
                    <p className="text-xs text-slate-500 max-w-md mx-auto">
                      Select one of the specialized intelligence queries on the
                      left or type your own question below. If evidence is not
                      found in the snapshot, the assistant will explicitly state
                      that evidence is insufficient.
                    </p>
                  </div>
                ) : (
                  messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`rounded-lg p-4 space-y-3 ${
                        msg.role === "USER"
                          ? "bg-slate-900 text-white ml-8"
                          : "bg-slate-50 border border-slate-200 text-slate-900 mr-4"
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold">
                          {msg.role === "USER"
                            ? "You"
                            : "LegacyIQ Intelligence Assistant"}
                        </span>
                        {msg.question_intent && (
                          <Badge
                            variant={
                              msg.role === "USER" ? "secondary" : "outline"
                            }
                            className="font-mono text-[10px]"
                          >
                            {msg.question_intent}
                          </Badge>
                        )}
                      </div>

                      {msg.role === "ASSISTANT" && msg.insufficient_evidence && (
                        <div className="rounded-md bg-amber-50 border border-amber-200 p-2.5 text-xs text-amber-900 flex items-center gap-2">
                          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
                          <span>
                            <strong>Insufficient Evidence:</strong> No matching
                            source code, database schema, or evidence anchor was
                            found in this snapshot for the requested topic.
                          </span>
                        </div>
                      )}

                      <div className="text-xs whitespace-pre-wrap leading-relaxed">
                        {msg.content_markdown}
                      </div>

                      {msg.role === "ASSISTANT" &&
                        msg.direct_facts &&
                        msg.direct_facts.length > 0 && (
                          <div className="space-y-1 pt-2 border-t border-slate-200">
                            <div className="text-[11px] font-semibold text-emerald-800 flex items-center gap-1.5">
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Direct Persisted Facts ({msg.direct_facts.length})
                            </div>
                            <ul className="list-disc pl-4 space-y-0.5 text-xs text-slate-700">
                              {msg.direct_facts.slice(0, 6).map((f, i) => (
                                <li key={i}>{f}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                      {msg.role === "ASSISTANT" &&
                        msg.inferred_explanations &&
                        msg.inferred_explanations.length > 0 && (
                          <div className="space-y-1 pt-2 border-t border-slate-200">
                            <div className="text-[11px] font-semibold text-amber-800">
                              Inferred Explanations &amp; Heuristics (
                              {msg.inferred_explanations.length})
                            </div>
                            <ul className="list-disc pl-4 space-y-0.5 text-xs text-slate-700">
                              {msg.inferred_explanations
                                .slice(0, 4)
                                .map((inf, i) => (
                                  <li key={i}>{inf}</li>
                                ))}
                            </ul>
                          </div>
                        )}

                      {msg.role === "ASSISTANT" &&
                        msg.citations &&
                        msg.citations.length > 0 && (
                          <div className="space-y-1.5 pt-2 border-t border-slate-200">
                            <div className="text-[11px] font-semibold text-slate-700 flex items-center gap-1.5">
                              <BookOpen className="h-3.5 w-3.5 text-sky-700" />
                              Source Evidence Citations ({msg.citations.length})
                            </div>
                            <div className="grid grid-cols-1 gap-1.5">
                              {msg.citations.slice(0, 5).map((cit) => (
                                <div
                                  key={cit.citation_id}
                                  className="rounded border border-slate-200 bg-white p-2 text-[11px]"
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-1 font-mono text-slate-800">
                                    <span>
                                      [{cit.citation_id}] {cit.relative_path}:L
                                      {cit.start_line}–L{cit.end_line}
                                    </span>
                                    <span className="text-[10px] text-slate-500">
                                      {cit.source_kind} &bull; sha256:
                                      {cit.snippet_sha256.slice(0, 10)}
                                    </span>
                                  </div>
                                  {cit.excerpt_text && (
                                    <pre className="mt-1 rounded bg-slate-900 text-slate-100 p-1.5 text-[10px] overflow-x-auto font-mono">
                                      {cit.excerpt_text.slice(0, 220)}
                                    </pre>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                    </div>
                  ))
                )}
              </CardContent>

              <div className="p-4 border-t border-slate-200 bg-white flex items-center gap-2">
                <input
                  type="text"
                  value={questionInput}
                  onChange={(e) => setQuestionInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      questionInput.trim() &&
                      !askQuestionMutation.isPending
                    ) {
                      askQuestionMutation.mutate(questionInput.trim());
                    }
                  }}
                  placeholder="Ask about architecture, business rules, API-DB dependencies, test gaps, security risks, or impact analysis..."
                  className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
                <button
                  type="button"
                  disabled={
                    !selectedSnapshotId ||
                    !questionInput.trim() ||
                    askQuestionMutation.isPending
                  }
                  onClick={() =>
                    askQuestionMutation.mutate(questionInput.trim())
                  }
                  className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  <Send className="h-3.5 w-3.5" />
                  {askQuestionMutation.isPending ? "Analyzing..." : "Ask"}
                </button>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* TAB 3: REPORTS & DOCUMENTS (11 TYPES + VERSIONING + LIFECYCLE + EXPORT) */}
      {activeTab === "reports" && (
        <div className="space-y-6">
          {/* Report Generator Bar */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <CardTitle className="text-base">
                    Structured Intelligence Report Generator (11 Report Types)
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Generate structured, evidence-anchored reports. Approved
                    report versions are strictly immutable; regenerating or
                    editing an approved report creates a new version (`v+1`).
                  </CardDescription>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    aria-label="Select Report Type"
                    value={selectedReportType}
                    onChange={(e) => setSelectedReportType(e.target.value)}
                    className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800"
                  >
                    {(
                      reportsListQuery.data?.available_report_types || [
                        {
                          report_type: "COMPLETE_INTELLIGENCE",
                          display_name:
                            "Complete Application Intelligence Report",
                        },
                      ]
                    ).map((rt) => (
                      <option key={rt.report_type} value={rt.report_type}>
                        {rt.display_name} ({rt.report_type})
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    disabled={
                      !selectedSnapshotId || generateReportMutation.isPending
                    }
                    onClick={() =>
                      generateReportMutation.mutate(selectedReportType)
                    }
                    className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    {generateReportMutation.isPending
                      ? "Generating..."
                      : "Generate Report"}
                  </button>
                </div>
              </div>
            </CardHeader>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Sidebar: Generated Reports List & Version History */}
            <div className="lg:col-span-4 space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    Generated Reports (
                    {(reportsListQuery.data?.reports || []).length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {(reportsListQuery.data?.reports || []).length === 0 ? (
                    <p className="text-xs text-slate-500">
                      No reports generated yet. Select a report type above and
                      click Generate Report.
                    </p>
                  ) : (
                    (reportsListQuery.data?.reports || []).map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => {
                          setSelectedReportId(r.id);
                          setSelectedVersionNo(undefined);
                        }}
                        className={`w-full text-left rounded-md p-2.5 text-xs transition-colors border ${
                          selectedReportId === r.id
                            ? "border-slate-900 bg-slate-900 text-white"
                            : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
                        }`}
                      >
                        <div className="font-semibold">
                          {r.report_type_display}
                        </div>
                        <div className="flex items-center justify-between mt-1 text-[10px] font-mono opacity-85">
                          <span>v{r.current_version_no}</span>
                          <span>{r.lifecycle_status}</span>
                        </div>
                      </button>
                    ))
                  )}
                </CardContent>
              </Card>

              {activeReport && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">
                      Version History ({activeReport.versions.length})
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Approved versions carry an immutable cryptographic hash
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-1.5">
                    {activeReport.versions.map((v) => (
                      <button
                        key={v.version_id}
                        type="button"
                        onClick={() => setSelectedVersionNo(v.version_no)}
                        className={`w-full text-left rounded border p-2 text-xs ${
                          activeReport.version_no === v.version_no
                            ? "border-sky-600 bg-sky-50/60 text-slate-900"
                            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between font-mono">
                          <span className="font-bold">
                            Version v{v.version_no}
                          </span>
                          <span className="flex items-center gap-1">
                            {v.is_immutable && (
                              <Lock className="h-3 w-3 text-emerald-700" />
                            )}
                            {v.lifecycle_status}
                          </span>
                        </div>
                        <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                          sha256: {v.content_sha256.slice(0, 16)}...
                        </div>
                      </button>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Right Area: Active Report Content, Lifecycle Controls & Export Actions */}
            <div className="lg:col-span-8 space-y-4">
              {activeReport ? (
                <>
                  <Card>
                    <CardHeader className="border-b border-slate-100 pb-4">
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <CardTitle className="text-lg">
                              {activeReport.title}
                            </CardTitle>
                            <Badge
                              variant={
                                activeReport.lifecycle_status === "APPROVED"
                                  ? "success"
                                  : "outline"
                              }
                              className="font-mono text-xs"
                            >
                              v{activeReport.version_no} &bull;{" "}
                              {activeReport.lifecycle_status}
                            </Badge>
                            {activeReport.is_immutable && (
                              <Badge
                                variant="secondary"
                                className="font-mono text-[10px] flex items-center gap-1"
                              >
                                <Lock className="h-3 w-3" /> IMMUTABLE
                              </Badge>
                            )}
                          </div>
                          <CardDescription className="text-xs mt-1 font-mono">
                            {activeReport.branding.organization_name} /{" "}
                            {activeReport.branding.project_name} (
                            {activeReport.branding.project_key}) &bull; SHA-256:{" "}
                            {activeReport.content_sha256.slice(0, 20)}...
                          </CardDescription>
                        </div>

                        {/* Export Format Triggers */}
                        <div className="flex flex-wrap items-center gap-1.5">
                          {(["PDF", "DOCX", "XLSX", "JSON"] as const).map(
                            (fmt) => (
                              <button
                                key={fmt}
                                type="button"
                                disabled={exportReportMutation.isPending}
                                onClick={() =>
                                  exportReportMutation.mutate({
                                    reportId: activeReport.id,
                                    format: fmt,
                                    versionNo: activeReport.version_no,
                                  })
                                }
                                className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-mono font-semibold text-slate-800 hover:bg-slate-100"
                              >
                                <FileSpreadsheet className="h-3 w-3 text-slate-600" />
                                Export {fmt}
                              </button>
                            )
                          )}
                        </div>
                      </div>
                    </CardHeader>

                    <CardContent className="py-4 space-y-5">
                      {/* Lifecycle & Approval Governance Bar */}
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-slate-900">
                            Report Lifecycle &amp; Sign-Off Governance
                          </span>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() =>
                                transitionLifecycleMutation.mutate({
                                  reportId: activeReport.id,
                                  targetStatus: "SUBMITTED_FOR_REVIEW",
                                  comment:
                                    lifecycleComment || "Submitted for review",
                                  updatedSummary:
                                    editedSummaryInput || undefined,
                                })
                              }
                              className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-800 hover:bg-slate-100"
                            >
                              Submit for Review
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                transitionLifecycleMutation.mutate({
                                  reportId: activeReport.id,
                                  targetStatus: "APPROVED",
                                  comment:
                                    lifecycleComment ||
                                    "Approved and locked as immutable version",
                                })
                              }
                              className="rounded bg-emerald-700 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-800"
                            >
                              Approve (Lock Immutable)
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                transitionLifecycleMutation.mutate({
                                  reportId: activeReport.id,
                                  targetStatus: "REJECTED",
                                  comment:
                                    lifecycleComment || "Rejected during review",
                                })
                              }
                              className="rounded bg-rose-700 px-2.5 py-1 text-xs font-semibold text-white hover:bg-rose-800"
                            >
                              Reject
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                transitionLifecycleMutation.mutate({
                                  reportId: activeReport.id,
                                  targetStatus: "DRAFT",
                                  comment:
                                    lifecycleComment ||
                                    "Created new mutable draft version",
                                  updatedSummary:
                                    editedSummaryInput || undefined,
                                })
                              }
                              className="rounded border border-sky-700 bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-900 hover:bg-sky-100"
                            >
                              {activeReport.is_immutable
                                ? "Create New Version (v+1) from Approved"
                                : "Save as Draft"}
                            </button>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            value={lifecycleComment}
                            onChange={(e) =>
                              setLifecycleComment(e.target.value)
                            }
                            placeholder="Review comment or approval rationale..."
                            className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
                          />
                          <input
                            type="text"
                            value={editedSummaryInput}
                            onChange={(e) =>
                              setEditedSummaryInput(e.target.value)
                            }
                            placeholder="Optional updated executive summary (creates v+1 if approved)..."
                            className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
                          />
                        </div>
                      </div>

                      {/* Executive Summary */}
                      <div className="space-y-1.5">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          1. Executive Summary
                        </h3>
                        <div className="rounded-md border border-slate-200 bg-white p-3 text-xs whitespace-pre-wrap leading-relaxed text-slate-800">
                          {activeReport.executive_summary_markdown}
                        </div>
                      </div>

                      {/* Scope & Methodology */}
                      <div className="space-y-1.5">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          2. Scope &amp; Methodology
                        </h3>
                        <div className="rounded-md border border-slate-200 bg-white p-3 text-xs whitespace-pre-wrap leading-relaxed text-slate-700">
                          {activeReport.scope_and_methodology_markdown}
                        </div>
                      </div>

                      {/* Report Sections */}
                      <div className="space-y-3">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          3. Detailed Intelligence Sections (
                          {activeReport.sections.length})
                        </h3>
                        {activeReport.sections.map((sec) => (
                          <div
                            key={sec.section_key}
                            className="rounded-md border border-slate-200 bg-white p-3 space-y-1.5"
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-slate-900">
                                {sec.title}
                              </span>
                              <div className="flex items-center gap-1.5">
                                <Badge
                                  variant="outline"
                                  className="font-mono text-[10px]"
                                >
                                  {sec.metric_basis}
                                </Badge>
                                <Badge
                                  variant="secondary"
                                  className="font-mono text-[10px]"
                                >
                                  {sec.review_posture}
                                </Badge>
                              </div>
                            </div>
                            <div className="text-xs text-slate-700 whitespace-pre-wrap">
                              {sec.content_markdown}
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Risks & Limitations */}
                      <div className="space-y-1.5">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          4. Risks, Assumptions &amp; Limitations
                        </h3>
                        <div className="rounded-md border border-amber-200 bg-amber-50/50 p-3 text-xs whitespace-pre-wrap text-slate-800">
                          {activeReport.risks_and_limitations_markdown}
                        </div>
                      </div>

                      {/* Evidence Citations */}
                      <div className="space-y-2">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                          5. Cryptographic Evidence References (
                          {activeReport.evidence_references.length})
                        </h3>
                        <div className="grid grid-cols-1 gap-1.5 max-h-56 overflow-y-auto">
                          {activeReport.evidence_references
                            .slice(0, 12)
                            .map((ev) => (
                              <div
                                key={ev.ref_id}
                                className="rounded border border-slate-200 bg-slate-50 p-2 text-[11px] font-mono"
                              >
                                <div className="flex justify-between">
                                  <span className="font-semibold text-slate-900">
                                    [{ev.ref_id}] {ev.title}
                                  </span>
                                  <span className="text-slate-600">
                                    {ev.relative_path}:L{ev.start_line}–L
                                    {ev.end_line}
                                  </span>
                                </div>
                                <div className="text-[10px] text-slate-500 truncate mt-0.5">
                                  sha256:{ev.snippet_sha256.slice(0, 16)} &bull;{" "}
                                  {ev.excerpt_text}
                                </div>
                              </div>
                            ))}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </>
              ) : (
                <Card>
                  <CardContent className="p-8 text-center text-xs text-slate-500">
                    Select or generate one of the 11 structured intelligence
                    reports to view, review, version, or export it.
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: EXECUTIVE INSIGHTS */}
      {activeTab === "executive" && exec && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardDescription>Overall Application Health</CardDescription>
                  <Badge variant="secondary" className="font-mono text-[10px]">
                    {exec.overall_application_health.metric_basis}
                  </Badge>
                </div>
                <CardTitle className="text-3xl font-mono">
                  {exec.overall_application_health.health_score} / 100 (Grade{" "}
                  {exec.overall_application_health.health_grade})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-slate-600">
                  {exec.overall_application_health.explanation}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardDescription>Architecture Complexity</CardDescription>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {exec.architecture_complexity.metric_basis}
                  </Badge>
                </div>
                <CardTitle className="text-2xl font-mono">
                  {exec.architecture_complexity.complexity_tier}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-slate-600 space-y-1">
                <div>
                  Max / Avg Cyclomatic:{" "}
                  <span className="font-mono font-semibold">
                    {exec.architecture_complexity.max_cyclomatic_complexity} /{" "}
                    {exec.architecture_complexity.avg_cyclomatic_complexity}
                  </span>
                </div>
                <div>
                  DB Tables: {exec.architecture_complexity.db_tables_count}{" "}
                  &bull; APIs:{" "}
                  {exec.architecture_complexity.api_endpoints_count} &bull;
                  Infra: {exec.architecture_complexity.infra_resources_count}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardDescription>Testing Maturity Tier</CardDescription>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {exec.testing_maturity.discovered_basis}
                  </Badge>
                </div>
                <CardTitle className="text-2xl font-mono">
                  {exec.testing_maturity.maturity_tier}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-slate-600 space-y-1">
                <div>
                  Requirement Coverage:{" "}
                  <span className="font-mono font-semibold">
                    {exec.testing_maturity.discovered_requirement_coverage_pct}%
                  </span>{" "}
                  &bull; Symbol Coverage:{" "}
                  <span className="font-mono font-semibold">
                    {exec.testing_maturity.discovered_symbol_coverage_pct}%
                  </span>
                </div>
                <div>
                  Recommended Blueprints:{" "}
                  {exec.testing_maturity.recommended_test_blueprints} (
                  {exec.testing_maturity.blueprint_basis})
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-rose-600" />
                  Critical Unresolved Issues &amp; Risk Distribution
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded border border-slate-200 p-2.5">
                    <div className="text-slate-500">
                      High / Critical Security &amp; Arch Risks
                    </div>
                    <div className="text-lg font-mono font-bold text-rose-700">
                      {
                        exec.critical_unresolved_issues
                          .high_or_critical_risks_count
                      }
                    </div>
                  </div>
                  <div className="rounded border border-slate-200 p-2.5">
                    <div className="text-slate-500">
                      Unresolved Knowledge Conflicts
                    </div>
                    <div className="text-lg font-mono font-bold text-amber-700">
                      {
                        exec.critical_unresolved_issues
                          .unresolved_conflicts_count
                      }
                    </div>
                  </div>
                  <div className="rounded border border-slate-200 p-2.5">
                    <div className="text-slate-500">Untested Requirements</div>
                    <div className="text-lg font-mono font-bold">
                      {
                        exec.critical_unresolved_issues
                          .untested_requirements_count
                      }
                    </div>
                  </div>
                  <div className="rounded border border-slate-200 p-2.5">
                    <div className="text-slate-500">Pending Human Reviews</div>
                    <div className="text-lg font-mono font-bold">
                      {
                        exec.critical_unresolved_issues
                          .pending_human_reviews_count
                      }
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">
                  Priority Modernization Recommendations &amp; Effort Estimates
                </CardTitle>
                <CardDescription className="text-xs">
                  {exec.estimated_modernization_effort.disclaimer}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                {exec.priority_recommendations.map((rec) => (
                  <div
                    key={rec.id}
                    className="rounded border border-slate-200 p-2.5 flex items-center justify-between"
                  >
                    <div>
                      <div className="font-semibold text-slate-900">
                        Phase {rec.roadmap_phase}: {rec.title}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        Strategy: {rec.strategy_pattern} &bull; Status:{" "}
                        {rec.review_status}
                      </div>
                    </div>
                    <Badge variant="secondary" className="font-mono text-[10px]">
                      {rec.effort_tshirt} ({rec.estimated_effort_range})
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* TAB 5: EXPORT HISTORY & TAMPER-EVIDENT AUDIT LEDGER */}
      {activeTab === "exports" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Controlled Report Exports (`PDF`, `DOCX`, `XLSX`, `JSON`)
              </CardTitle>
              <CardDescription className="text-xs">
                All export artifacts are stored in tenant-scoped object storage
                with SHA-256 verification and download tracking.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {(exportsQuery.data?.exports || []).length === 0 ? (
                <p className="text-xs text-slate-500">
                  No exports generated yet. Go to tab &ldquo;3. Reports &amp;
                  Documents&rdquo; and click Export PDF / DOCX / XLSX / JSON.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500">
                        <th className="py-2 pr-3">File Name</th>
                        <th className="py-2 px-3">Format</th>
                        <th className="py-2 px-3">Size (Bytes)</th>
                        <th className="py-2 px-3">SHA-256 Checksum</th>
                        <th className="py-2 px-3">Downloads</th>
                        <th className="py-2 pl-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {(exportsQuery.data?.exports || []).map((exp) => (
                        <tr key={exp.id}>
                          <td className="py-2.5 pr-3 font-mono font-medium text-slate-900">
                            {exp.file_name}
                          </td>
                          <td className="py-2.5 px-3">
                            <Badge
                              variant="outline"
                              className="font-mono text-[10px]"
                            >
                              {exp.export_format}
                            </Badge>
                          </td>
                          <td className="py-2.5 px-3 font-mono">
                            {exp.file_size_bytes}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-slate-500">
                            {exp.content_sha256.slice(0, 16)}...
                          </td>
                          <td className="py-2.5 px-3 font-mono">
                            {exp.download_count}
                          </td>
                          <td className="py-2.5 pl-3 text-right">
                            <button
                              type="button"
                              onClick={async () => {
                                if (!auth) return;
                                await apiClient.downloadReportExport(
                                  exp.id,
                                  exp.file_name,
                                  auth
                                );
                                queryClient.invalidateQueries({
                                  queryKey: [
                                    "wave5-exports",
                                    selectedSnapshotId,
                                  ],
                                });
                              }}
                              className="inline-flex items-center gap-1 rounded bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white hover:bg-slate-800"
                            >
                              <Download className="h-3 w-3" />
                              Download
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Tamper-Evident Governance Audit Ledger (`audit_logs`)
              </CardTitle>
              <CardDescription className="text-xs">
                Hash-chained (`previous_hash` &rarr; `record_hash`) audit trail
                for report generation, approvals, exports, and downloads.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-1.5 max-h-72 overflow-y-auto">
                {(exportsQuery.data?.audit_logs || []).map((log) => (
                  <div
                    key={log.id}
                    className="rounded border border-slate-200 bg-slate-50 p-2.5 text-xs font-mono flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1"
                  >
                    <div>
                      <span className="font-bold text-slate-900">
                        {log.action_code}
                      </span>{" "}
                      <span className="text-slate-600">
                        ({log.target_resource_type})
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-500">
                      prev:{(log.previous_hash || "GENESIS").slice(0, 10)}{" "}
                      &rarr; hash:{log.record_hash.slice(0, 12)}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
