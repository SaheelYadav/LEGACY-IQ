"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Compass,
  FileSearch,
  FlaskConical,
  Gauge,
  Layers,
  Play,
  RefreshCw,
  ShieldAlert,
  Wrench,
  XCircle,
} from "lucide-react";
import { apiClient, TenantAuthHeaders } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type TabKey =
  | "test-intelligence"
  | "coverage-gaps"
  | "risk-register"
  | "technical-debt"
  | "modernization-assessment"
  | "roadmap";

export default function ModernizationWorkbenchPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabKey>("test-intelligence");
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>("");

  // Filters
  const [suiteOriginFilter, setSuiteOriginFilter] = useState<string>("ALL");
  const [riskSeverityFilter, setRiskSeverityFilter] = useState<string>("ALL");
  const [riskCategoryFilter, setRiskCategoryFilter] = useState<string>("ALL");
  const [debtCategoryFilter, setDebtCategoryFilter] = useState<string>("ALL");
  const [expandedEvidenceIds, setExpandedEvidenceIds] = useState<
    Record<string, boolean>
  >({});

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap-context-wave4"],
    queryFn: () => apiClient.bootstrapContext(),
  });

  const auth: TenantAuthHeaders | null = useMemo(() => {
    if (!bootstrapQuery.data) return null;
    return {
      tenantId: bootstrapQuery.data.tenant_id,
      userId: bootstrapQuery.data.user_id,
    };
  }, [bootstrapQuery.data]);

  useEffect(() => {
    if (bootstrapQuery.data) {
      if (!selectedRepoId && bootstrapQuery.data.default_repository_id) {
        setSelectedRepoId(bootstrapQuery.data.default_repository_id);
      }
      if (!selectedSnapshotId && bootstrapQuery.data.latest_snapshot_id) {
        setSelectedSnapshotId(bootstrapQuery.data.latest_snapshot_id);
      }
    }
  }, [bootstrapQuery.data, selectedRepoId, selectedSnapshotId]);

  const reposQuery = useQuery({
    queryKey: ["repositories-wave4", bootstrapQuery.data?.project_id],
    queryFn: () =>
      apiClient.listRepositories(bootstrapQuery.data!.project_id, auth!),
    enabled: Boolean(bootstrapQuery.data?.project_id && auth),
  });

  useEffect(() => {
    if (!selectedRepoId && reposQuery.data && reposQuery.data.length > 0) {
      setSelectedRepoId(reposQuery.data[0].id);
    }
  }, [reposQuery.data, selectedRepoId]);

  const testIntelQuery = useQuery({
    queryKey: ["wave4-test-intel", selectedSnapshotId],
    queryFn: () =>
      apiClient.getSnapshotTestIntelligence(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const coverageQuery = useQuery({
    queryKey: ["wave4-coverage", selectedSnapshotId],
    queryFn: () =>
      apiClient.getSnapshotCoverageAndGaps(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const riskQuery = useQuery({
    queryKey: ["wave4-risk", selectedSnapshotId],
    queryFn: () => apiClient.getSnapshotRiskRegister(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const debtQuery = useQuery({
    queryKey: ["wave4-debt", selectedSnapshotId],
    queryFn: () =>
      apiClient.getSnapshotTechnicalDebt(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const assessmentQuery = useQuery({
    queryKey: ["wave4-assessment", selectedSnapshotId],
    queryFn: () =>
      apiClient.getSnapshotModernizationAssessment(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const roadmapQuery = useQuery({
    queryKey: ["wave4-roadmap", selectedSnapshotId],
    queryFn: () =>
      apiClient.getSnapshotModernizationRoadmap(selectedSnapshotId, auth!),
    enabled: Boolean(selectedSnapshotId && auth),
  });

  const analyzeMutation = useMutation({
    mutationFn: () =>
      apiClient.analyzeSnapshotWave4(selectedSnapshotId, auth!),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["wave4-test-intel", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave4-coverage", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave4-risk", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave4-debt", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave4-assessment", selectedSnapshotId],
      });
      queryClient.invalidateQueries({
        queryKey: ["wave4-roadmap", selectedSnapshotId],
      });
    },
  });

  const reviewRecMutation = useMutation({
    mutationFn: (vars: { id: string; new_status: string; comment?: string }) =>
      apiClient.reviewModernizationRecommendation(
        vars.id,
        { new_status: vars.new_status, review_comment: vars.comment },
        auth!
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["wave4-roadmap", selectedSnapshotId],
      });
    },
  });

  const reviewTestCaseMutation = useMutation({
    mutationFn: (vars: { id: string; new_status: string; comment?: string }) =>
      apiClient.reviewTestCase(
        vars.id,
        { new_status: vars.new_status, review_comment: vars.comment },
        auth!
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["wave4-test-intel", selectedSnapshotId],
      });
    },
  });

  const reviewFindingMutation = useMutation({
    mutationFn: (vars: { id: string; new_status: string; comment?: string }) =>
      apiClient.reviewFinding(
        vars.id,
        { new_status: vars.new_status, review_comment: vars.comment },
        auth!
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["wave4-risk", selectedSnapshotId],
      });
    },
  });

  const filteredTests = useMemo(() => {
    const list = testIntelQuery.data?.test_cases || [];
    if (suiteOriginFilter === "ALL") return list;
    return list.filter((tc) => tc.suite_origin === suiteOriginFilter);
  }, [testIntelQuery.data, suiteOriginFilter]);

  const filteredRisks = useMemo(() => {
    const list = riskQuery.data?.risk_findings || [];
    return list.filter((rf) => {
      if (riskSeverityFilter !== "ALL" && rf.severity !== riskSeverityFilter)
        return false;
      if (
        riskCategoryFilter !== "ALL" &&
        rf.finding_category !== riskCategoryFilter
      )
        return false;
      return true;
    });
  }, [riskQuery.data, riskSeverityFilter, riskCategoryFilter]);

  const filteredDebt = useMemo(() => {
    const list = debtQuery.data?.technical_debt_items || [];
    if (debtCategoryFilter === "ALL") return list;
    return list.filter((d) => d.debt_category === debtCategoryFilter);
  }, [debtQuery.data, debtCategoryFilter]);

  const toggleEvidence = (id: string) => {
    setExpandedEvidenceIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Badge className="bg-indigo-600 text-white hover:bg-indigo-700">
              Wave 4 Live
            </Badge>
            <span className="text-xs font-mono text-slate-500">
              Domain H — Testing, Risk, Debt &amp; Modernization
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1">
            Testing, Risk &amp; Modernization Intelligence
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Evidence-anchored test coverage, CWE/CVE risk register, measured vs.
            estimated technical debt, and 4-phase modernization roadmap.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            aria-label="Select repository"
            value={selectedRepoId}
            onChange={(e) => setSelectedRepoId(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-800 shadow-sm"
          >
            {(reposQuery.data ?? []).map((repo) => (
              <option key={repo.id} value={repo.id}>
                Repo: {repo.name}
              </option>
            ))}
          </select>

          <input
            aria-label="Active snapshot ID"
            type="text"
            value={selectedSnapshotId}
            onChange={(e) => setSelectedSnapshotId(e.target.value)}
            placeholder="Snapshot UUID..."
            className="w-60 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm"
          />

          <button
            type="button"
            disabled={!selectedSnapshotId || analyzeMutation.isPending}
            onClick={() => analyzeMutation.mutate()}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {analyzeMutation.isPending ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            Run Wave 4 Analysis
          </button>
        </div>
      </div>

      {/* Top KPI Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">
              Discovered Tests vs. Blueprints
            </CardDescription>
            <CardTitle className="text-xl flex items-baseline gap-2">
              <span>
                {testIntelQuery.data?.summary.discovered_test_cases ?? 0}
              </span>
              <span className="text-xs font-normal text-slate-500">
                discovered /{" "}
                {testIntelQuery.data?.summary.recommended_test_blueprints ?? 0}{" "}
                blueprints
              </span>
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">
              Discovered Req Coverage
            </CardDescription>
            <CardTitle className="text-xl flex items-baseline gap-2">
              <span>
                {coverageQuery.data?.coverage_metrics
                  .discovered_requirement_coverage_pct ?? 0}
                %
              </span>
              <span className="text-xs font-normal text-slate-500">
                (
                {coverageQuery.data?.coverage_metrics
                  .requirements_covered_by_existing_tests ?? 0}
                /{coverageQuery.data?.coverage_metrics.total_requirements ?? 0})
              </span>
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">
              Risk Register Findings
            </CardDescription>
            <CardTitle className="text-xl flex items-baseline gap-2">
              <span>{riskQuery.data?.risk_findings.length ?? 0}</span>
              <span className="text-xs font-normal text-rose-600">
                {(riskQuery.data?.counts_by_severity?.CRITICAL ?? 0) +
                  (riskQuery.data?.counts_by_severity?.HIGH ?? 0)}{" "}
                High/Critical
              </span>
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">
              Technical Debt Items
            </CardDescription>
            <CardTitle className="text-xl flex items-baseline gap-2">
              <span>{debtQuery.data?.technical_debt_items.length ?? 0}</span>
              <span className="text-xs font-normal text-amber-700">
                ~
                {debtQuery.data?.measured_vs_estimated_summary
                  .heuristic_estimates.total_estimated_remediation_hours ?? 0}
                h (Est.)
              </span>
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs">
              Modernization Posture
            </CardDescription>
            <CardTitle className="text-sm font-mono text-indigo-700 pt-1">
              {assessmentQuery.data?.microservices_recommended
                ? "SELECTIVE_DECOMPOSITION"
                : "MODULAR_MONOLITH"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* 6-Tab Navigation */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {[
          {
            key: "test-intelligence",
            label: "1. Test Intelligence",
            icon: FlaskConical,
          },
          {
            key: "coverage-gaps",
            label: "2. Coverage & Gaps",
            icon: Gauge,
          },
          {
            key: "risk-register",
            label: "3. Risk Register",
            icon: ShieldAlert,
          },
          {
            key: "technical-debt",
            label: "4. Technical Debt",
            icon: Wrench,
          },
          {
            key: "modernization-assessment",
            label: "5. Modernization Assessment",
            icon: Compass,
          },
          {
            key: "roadmap",
            label: "6. Recommendations & Roadmap",
            icon: Layers,
          },
        ].map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key as TabKey)}
              className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-semibold transition-colors ${
                active
                  ? "bg-slate-900 text-white shadow-sm"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* TAB 1: TEST INTELLIGENCE */}
      {activeTab === "test-intelligence" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-600">
                Origin Filter:
              </span>
              {["ALL", "EXISTING_IN_REPO", "AI_GENERATED_BLUEPRINT"].map(
                (orig) => (
                  <button
                    key={orig}
                    type="button"
                    onClick={() => setSuiteOriginFilter(orig)}
                    className={`rounded-md px-2.5 py-1 text-xs font-mono ${
                      suiteOriginFilter === orig
                        ? "bg-slate-900 text-white"
                        : "bg-white border border-slate-200 text-slate-700"
                    }`}
                  >
                    {orig}
                  </button>
                )
              )}
            </div>
            <div className="text-xs text-slate-500">
              Clearly separates{" "}
              <span className="font-mono font-semibold text-emerald-700">
                EXISTING_IN_REPO
              </span>{" "}
              tests from{" "}
              <span className="font-mono font-semibold text-indigo-700">
                AI_GENERATED_BLUEPRINT
              </span>{" "}
              recommendations.
            </div>
          </div>

          <div className="space-y-3">
            {filteredTests.map((tc) => (
              <Card key={tc.id} className="border-slate-200">
                <CardContent className="p-4 space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          className={
                            tc.is_discovered_in_repo
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-indigo-100 text-indigo-800"
                          }
                        >
                          {tc.suite_origin}
                        </Badge>
                        <Badge variant="outline" className="font-mono text-xs">
                          {tc.test_framework}
                        </Badge>
                        <Badge variant="outline" className="font-mono text-xs">
                          {tc.test_kind}
                        </Badge>
                        <Badge variant="outline" className="font-mono text-xs">
                          {tc.review_status}
                        </Badge>
                      </div>
                      <h3 className="text-sm font-semibold text-slate-900 mt-1.5">
                        {tc.title}
                      </h3>
                      <p className="text-xs font-mono text-slate-500">
                        {tc.test_key}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() =>
                          reviewTestCaseMutation.mutate({
                            id: tc.id,
                            new_status: "APPROVED",
                            comment: "Approved in Wave 4 Test Workbench",
                          })
                        }
                        className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          reviewTestCaseMutation.mutate({
                            id: tc.id,
                            new_status: "REJECTED",
                            comment: "Rejected in Wave 4 Test Workbench",
                          })
                        }
                        className="inline-flex items-center gap-1 rounded border border-rose-300 bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-800 hover:bg-rose-100"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        Reject
                      </button>
                    </div>
                  </div>

                  <p className="text-xs text-slate-700">
                    {tc.scenario_description}
                  </p>

                  {tc.covered_targets.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <span className="text-[11px] font-semibold text-slate-500">
                        Coverage Targets:
                      </span>
                      {tc.covered_targets.map((ct) => (
                        <span
                          key={ct.coverage_link_id}
                          className="inline-flex items-center gap-1.5 rounded bg-slate-100 px-2 py-0.5 text-[11px] font-mono text-slate-800"
                        >
                          <span className="text-indigo-700 font-semibold">
                            [{ct.coverage_source}]
                          </span>
                          {ct.req_code ||
                            ct.rule_code ||
                            ct.symbol_qualified_name}
                        </span>
                      ))}
                    </div>
                  )}

                  {tc.generated_code_blueprint && (
                    <pre className="rounded-lg bg-slate-900 p-3 text-xs font-mono text-slate-100 overflow-x-auto">
                      {tc.generated_code_blueprint}
                    </pre>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* TAB 2: COVERAGE & GAPS */}
      {activeTab === "coverage-gaps" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Discovered vs. Inferred Coverage Provenance
              </CardTitle>
              <CardDescription className="text-xs">
                Distinguishes measured coverage reports (`COVERAGE_REPORT`) and
                static call-graph links (`STATIC_CALL_GRAPH`) from AI-generated
                characterization blueprints (`AI_TRACEABILITY`).
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4">
                <div className="text-xs font-mono text-emerald-800">
                  COVERAGE_REPORT (Measured)
                </div>
                <div className="text-2xl font-bold text-emerald-900 mt-1">
                  {coverageQuery.data?.coverage_metrics
                    .measured_coverage_report_links ?? 0}{" "}
                  links
                </div>
                <p className="text-xs text-emerald-700 mt-1">
                  Backed by uploaded Cobertura XML or LCOV line execution data.
                </p>
              </div>

              <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-4">
                <div className="text-xs font-mono text-blue-800">
                  STATIC_CALL_GRAPH (Discovered Repo Tests)
                </div>
                <div className="text-2xl font-bold text-blue-900 mt-1">
                  {coverageQuery.data?.coverage_metrics
                    .static_call_graph_links ?? 0}{" "}
                  links
                </div>
                <p className="text-xs text-blue-700 mt-1">
                  Deterministically traced from existing repository test calls
                  to symbols, rules, and requirements.
                </p>
              </div>

              <div className="rounded-lg border border-indigo-200 bg-indigo-50/60 p-4">
                <div className="text-xs font-mono text-indigo-800">
                  AI_TRACEABILITY (Recommended Blueprints)
                </div>
                <div className="text-2xl font-bold text-indigo-900 mt-1">
                  {coverageQuery.data?.coverage_metrics
                    .inferred_blueprint_links ?? 0}{" "}
                  links
                </div>
                <p className="text-xs text-indigo-700 mt-1">
                  Unexecuted characterization test blueprints recommended for
                  untested requirements.
                </p>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Untested Requirements (
                  {coverageQuery.data?.untested_requirements.length ?? 0})
                </CardTitle>
                <CardDescription className="text-xs">
                  Requirements with zero `EXISTING_IN_REPO` test coverage.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {(coverageQuery.data?.untested_requirements || []).map((ur) => (
                  <div
                    key={ur.id}
                    className="rounded-lg border border-slate-200 p-3 flex items-center justify-between gap-2"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-slate-900">
                          {ur.req_code}
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          {ur.priority}
                        </Badge>
                        <Badge variant="outline" className="text-[10px]">
                          {ur.req_type}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-700 mt-1">{ur.title}</p>
                    </div>
                    <Badge className="bg-amber-100 text-amber-800 font-mono text-[10px]">
                      {ur.coverage_state}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Untested Critical Components (
                  {coverageQuery.data?.untested_critical_components.length ?? 0}
                  )
                </CardTitle>
                <CardDescription className="text-xs">
                  Classes and higher-complexity functions lacking discovered
                  unit/integration tests.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {(coverageQuery.data?.untested_critical_components || []).map(
                  (uc) => (
                    <div
                      key={uc.symbol_id}
                      className="rounded-lg border border-slate-200 p-3 flex items-center justify-between gap-2"
                    >
                      <div>
                        <div className="font-mono text-xs font-semibold text-slate-900">
                          {uc.qualified_name}
                        </div>
                        <div className="text-[11px] font-mono text-slate-500">
                          {uc.relative_path} ({uc.symbol_kind})
                        </div>
                      </div>
                      <div className="text-right font-mono text-xs text-rose-700">
                        CC={uc.cyclomatic_complexity} | Cog=
                        {uc.cognitive_complexity}
                      </div>
                    </div>
                  )
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* TAB 3: RISK REGISTER */}
      {activeTab === "risk-register" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-medium text-slate-600">
              Severity:
            </span>
            {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((sev) => (
              <button
                key={sev}
                type="button"
                onClick={() => setRiskSeverityFilter(sev)}
                className={`rounded-md px-2.5 py-1 text-xs font-mono ${
                  riskSeverityFilter === sev
                    ? "bg-slate-900 text-white"
                    : "bg-white border border-slate-200 text-slate-700"
                }`}
              >
                {sev}
              </button>
            ))}

            <span className="text-xs font-medium text-slate-600 ml-3">
              Category:
            </span>
            <select
              aria-label="Filter by risk category"
              value={riskCategoryFilter}
              onChange={(e) => setRiskCategoryFilter(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-mono"
            >
              <option value="ALL">ALL CATEGORIES</option>
              <option value="RISK_SECURITY">RISK_SECURITY</option>
              <option value="RISK_DEPENDENCY">RISK_DEPENDENCY</option>
              <option value="RISK_SPOF">RISK_SPOF</option>
              <option value="RISK_DATA_INTEGRITY">RISK_DATA_INTEGRITY</option>
              <option value="RISK_PERFORMANCE">RISK_PERFORMANCE</option>
              <option value="RISK_OPERATIONAL">RISK_OPERATIONAL</option>
              <option value="RISK_ARCHITECTURE">RISK_ARCHITECTURE</option>
            </select>
          </div>

          <div className="space-y-3">
            {filteredRisks.map((rf) => (
              <Card key={rf.id} className="border-slate-200">
                <CardContent className="p-4 space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          className={
                            rf.severity === "CRITICAL"
                              ? "bg-rose-600 text-white"
                              : rf.severity === "HIGH"
                                ? "bg-amber-600 text-white"
                                : "bg-slate-200 text-slate-800"
                          }
                        >
                          {rf.severity}
                        </Badge>
                        <Badge variant="outline" className="font-mono text-xs">
                          {rf.finding_category}
                        </Badge>
                        <Badge variant="outline" className="font-mono text-xs">
                          Likelihood: {rf.likelihood}
                        </Badge>
                        <Badge variant="outline" className="font-mono text-xs">
                          Confidence: {(rf.confidence_score * 100).toFixed(0)}%
                        </Badge>
                        <Badge variant="outline" className="font-mono text-xs">
                          {rf.review_status}
                        </Badge>
                      </div>
                      <h3 className="text-sm font-semibold text-slate-900 mt-1.5">
                        {rf.title}
                      </h3>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => toggleEvidence(rf.id)}
                        className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        <FileSearch className="h-3.5 w-3.5" />
                        Evidence ({rf.evidence.length})
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          reviewFindingMutation.mutate({
                            id: rf.id,
                            new_status: "APPROVED",
                            comment: "Confirmed in Wave 4 Risk Register",
                          })
                        }
                        className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Confirm Risk
                      </button>
                    </div>
                  </div>

                  <div className="text-xs text-slate-700 whitespace-pre-line rounded-lg bg-slate-50 p-3 border border-slate-200/80">
                    {rf.statement_markdown}
                  </div>

                  {expandedEvidenceIds[rf.id] && rf.evidence.length > 0 && (
                    <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-3 space-y-2">
                      <div className="text-xs font-semibold text-indigo-950">
                        Immutable Source Evidence Anchors
                      </div>
                      {rf.evidence.map((ev) => (
                        <div
                          key={ev.anchor_id}
                          className="rounded bg-slate-900 p-2.5 text-xs font-mono text-slate-100"
                        >
                          <div className="text-indigo-300">
                            Lines {ev.start_line}–{ev.end_line} | sha256:{" "}
                            {ev.snippet_sha256.slice(0, 16)}...
                          </div>
                          {ev.excerpt_text && (
                            <pre className="mt-1 text-slate-200 overflow-x-auto">
                              {ev.excerpt_text}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* TAB 4: TECHNICAL DEBT */}
      {activeTab === "technical-debt" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="border-emerald-200 bg-emerald-50/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-mono text-emerald-900">
                  MEASURED STATIC &amp; GRAPH METRICS (Deterministic Fact)
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-3 gap-3 text-xs font-mono">
                <div>
                  <div className="text-slate-500">Total LOC</div>
                  <div className="text-lg font-bold text-slate-900">
                    {debtQuery.data?.measured_vs_estimated_summary
                      .measured_metrics.total_loc_code ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Max Cyclomatic</div>
                  <div className="text-lg font-bold text-slate-900">
                    {debtQuery.data?.measured_vs_estimated_summary
                      .measured_metrics.max_cyclomatic_complexity ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Avg Cyclomatic</div>
                  <div className="text-lg font-bold text-slate-900">
                    {debtQuery.data?.measured_vs_estimated_summary
                      .measured_metrics.avg_cyclomatic_complexity ?? 0}
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-amber-200 bg-amber-50/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-mono text-amber-900">
                  HEURISTIC REMEDIATION ESTIMATES (Labeled Estimate)
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs">
                <div className="text-lg font-bold font-mono text-amber-950">
                  ~
                  {debtQuery.data?.measured_vs_estimated_summary
                    .heuristic_estimates.total_estimated_remediation_hours ?? 0}{" "}
                  engineering hours (Estimated)
                </div>
                <p className="text-amber-800 mt-1">
                  {
                    debtQuery.data?.measured_vs_estimated_summary
                      .heuristic_estimates.disclaimer
                  }
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {[
              "ALL",
              "HIGH_COMPLEXITY",
              "DUPLICATED_CODE",
              "DEAD_CODE",
              "CIRCULAR_DEPENDENCY",
              "GOD_CLASS",
              "SQL_COUPLED_UI",
              "MISSING_TESTS",
              "DEPRECATED_DEPENDENCY",
            ].map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setDebtCategoryFilter(cat)}
                className={`rounded-md px-2.5 py-1 text-xs font-mono ${
                  debtCategoryFilter === cat
                    ? "bg-slate-900 text-white"
                    : "bg-white border border-slate-200 text-slate-700"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            {filteredDebt.map((item) => (
              <Card key={item.id}>
                <CardContent className="p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="font-mono text-xs">
                        {item.debt_category}
                      </Badge>
                      <Badge
                        className={
                          item.severity === "HIGH" ||
                          item.severity === "CRITICAL"
                            ? "bg-amber-600 text-white"
                            : "bg-slate-200 text-slate-800"
                        }
                      >
                        {item.severity}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-800 font-mono">
                      {item.description}
                    </p>
                  </div>
                  <Badge className="bg-amber-100 text-amber-900 font-mono text-xs shrink-0">
                    ~{item.estimated_remediation_hours ?? 0}h (
                    {item.effort_nature})
                  </Badge>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* TAB 5: MODERNIZATION ASSESSMENT */}
      {activeTab === "modernization-assessment" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(assessmentQuery.data?.dimensions || []).map((dim) => (
            <Card key={dim.dimension} className="border-slate-200">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <Badge variant="outline" className="font-mono text-xs">
                    {dim.dimension}
                  </Badge>
                  <Badge className="bg-indigo-100 text-indigo-900 font-mono text-xs">
                    {dim.recommended_posture}
                  </Badge>
                </div>
                <CardTitle className="text-base mt-2">{dim.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-slate-700 leading-relaxed">
                  {dim.rationale}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* TAB 6: RECOMMENDATIONS & 4-PHASE ROADMAP */}
      {activeTab === "roadmap" && (
        <div className="space-y-6">
          {(roadmapQuery.data?.roadmap_phases || []).map((phase) => (
            <Card key={phase.phase_number} className="border-slate-300">
              <CardHeader className="bg-slate-50 border-b border-slate-200">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-base">{phase.phase_name}</CardTitle>
                  <Badge className="bg-amber-100 text-amber-900 font-mono text-xs">
                    Effort Labels: {phase.effort_nature}
                  </Badge>
                </div>
                <CardDescription className="text-xs text-slate-700">
                  {phase.objective}
                </CardDescription>
                <div className="flex flex-wrap gap-4 pt-1 text-[11px] text-slate-600">
                  <div>
                    <span className="font-semibold">Prerequisites:</span>{" "}
                    {phase.prerequisites.join(", ")}
                  </div>
                  <div>
                    <span className="font-semibold">Expected Benefits:</span>{" "}
                    {phase.expected_benefits.join(", ")}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-4 space-y-3">
                {phase.recommendations.length === 0 ? (
                  <div className="text-xs text-slate-500 font-mono">
                    No active recommendations assigned to this phase.
                  </div>
                ) : (
                  phase.recommendations.map((rec) => (
                    <div
                      key={rec.id}
                      className="rounded-lg border border-slate-200 p-4 space-y-2.5"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge className="bg-indigo-600 text-white font-mono text-xs">
                              {rec.strategy_pattern}
                            </Badge>
                            <Badge
                              variant="outline"
                              className="font-mono text-xs"
                            >
                              Risk: {rec.risk_level}
                            </Badge>
                            <Badge className="bg-amber-100 text-amber-900 font-mono text-xs">
                              Effort: {rec.effort_tshirt} (
                              {rec.estimated_effort_range})
                            </Badge>
                            <Badge
                              variant="outline"
                              className="font-mono text-xs"
                            >
                              {rec.review_status}
                            </Badge>
                          </div>
                          <h4 className="text-sm font-semibold text-slate-900 mt-1.5">
                            {rec.title}
                          </h4>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              reviewRecMutation.mutate({
                                id: rec.id,
                                new_status: "APPROVED",
                                comment: "Approved in Wave 4 Roadmap",
                              })
                            }
                            className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100"
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              reviewRecMutation.mutate({
                                id: rec.id,
                                new_status: "REJECTED",
                                comment: "Rejected in Wave 4 Roadmap",
                              })
                            }
                            className="inline-flex items-center gap-1 rounded border border-rose-300 bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-800 hover:bg-rose-100"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            Reject
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                        <div className="rounded bg-slate-50 p-2.5 border border-slate-200/70">
                          <div className="font-semibold text-slate-900">
                            Current State (Evidence-Backed)
                          </div>
                          <p className="text-slate-700 mt-0.5">
                            {rec.current_state_summary}
                          </p>
                        </div>
                        <div className="rounded bg-indigo-50/40 p-2.5 border border-indigo-200/70">
                          <div className="font-semibold text-indigo-950">
                            Target State Architecture
                          </div>
                          <p className="text-slate-700 mt-0.5">
                            {rec.target_state_architecture}
                          </p>
                        </div>
                      </div>

                      <div className="text-xs text-slate-700 whitespace-pre-line font-mono bg-slate-50 p-2.5 rounded border border-slate-200/60">
                        {rec.step_by_step_plan_markdown}
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
