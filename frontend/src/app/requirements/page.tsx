"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Code2,
  Database,
  Edit3,
  FileCheck2,
  GitBranch,
  Layers,
  Network,
  Play,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldAlert,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  apiClient,
  type BusinessRuleItem,
  type RequirementItem,
  type TenantAuthHeaders,
  type Wave3EvidenceItem,
} from "@/lib/api";

type ActiveTab =
  | "business-rules"
  | "requirements"
  | "traceability"
  | "conflicts"
  | "impact";

export default function RequirementsPage() {
  const queryClient = useQueryClient();
  const [auth, setAuth] = useState<TenantAuthHeaders | null>(null);
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("business-rules");

  // Filters
  const [ruleCategoryFilter, setRuleCategoryFilter] = useState<string>("ALL");
  const [reqTypeFilter, setReqTypeFilter] = useState<string>("ALL");
  const [traceDirection, setTraceDirection] = useState<"FORWARD" | "BACKWARD" | "WEAK">(
    "FORWARD"
  );

  // Impact target selector
  const [impactTargetId, setImpactTargetId] = useState<string>("");

  // Evidence Inspector Drawer state
  const [inspectedTitle, setInspectedTitle] = useState<string>("");
  const [inspectedEvidence, setInspectedEvidence] = useState<Wave3EvidenceItem[]>([]);

  // Inline Edit Modal state for Business Rule or Requirement
  const [editingRule, setEditingRule] = useState<BusinessRuleItem | null>(null);
  const [editRuleTitle, setEditRuleTitle] = useState<string>("");
  const [editRuleCond, setEditRuleCond] = useState<string>("");
  const [editRuleAction, setEditRuleAction] = useState<string>("");
  const [editRuleComment, setEditRuleComment] = useState<string>("");

  const [editingReq, setEditingReq] = useState<RequirementItem | null>(null);
  const [editReqTitle, setEditReqTitle] = useState<string>("");
  const [editReqSpec, setEditReqSpec] = useState<string>("");
  const [editReqPriority, setEditReqPriority] = useState<string>("MUST");
  const [editReqComment, setEditReqComment] = useState<string>("");

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap-context"],
    queryFn: () => apiClient.bootstrapContext(),
    retry: 1,
  });

  useEffect(() => {
    if (bootstrapQuery.data && !auth) {
      setAuth({
        tenantId: bootstrapQuery.data.tenant_id,
        userId: bootstrapQuery.data.user_id,
      });
      if (bootstrapQuery.data.default_repository_id) {
        setSelectedRepoId(bootstrapQuery.data.default_repository_id);
      }
      if (bootstrapQuery.data.latest_snapshot_id) {
        setSelectedSnapshotId(bootstrapQuery.data.latest_snapshot_id);
      }
    }
  }, [bootstrapQuery.data, auth]);

  const repositoriesQuery = useQuery({
    queryKey: [
      "repositories",
      bootstrapQuery.data?.project_id,
      auth?.tenantId,
    ],
    queryFn: () =>
      apiClient.listRepositories(bootstrapQuery.data!.project_id, auth!),
    enabled: Boolean(auth && bootstrapQuery.data?.project_id),
  });

  useEffect(() => {
    if (
      !selectedRepoId &&
      repositoriesQuery.data &&
      repositoriesQuery.data.length > 0
    ) {
      setSelectedRepoId(repositoriesQuery.data[0].id);
    }
  }, [repositoriesQuery.data, selectedRepoId]);

  const rulesQuery = useQuery({
    queryKey: ["wave3-rules", selectedSnapshotId, auth?.tenantId],
    queryFn: () => apiClient.getSnapshotBusinessRules(selectedSnapshotId, auth!),
    enabled: Boolean(auth && selectedSnapshotId),
  });

  const requirementsQuery = useQuery({
    queryKey: ["wave3-requirements", selectedSnapshotId, auth?.tenantId],
    queryFn: () => apiClient.getSnapshotRequirements(selectedSnapshotId, auth!),
    enabled: Boolean(auth && selectedSnapshotId),
  });

  const traceabilityQuery = useQuery({
    queryKey: ["wave3-traceability", selectedSnapshotId, auth?.tenantId],
    queryFn: () => apiClient.getSnapshotTraceability(selectedSnapshotId, auth!),
    enabled: Boolean(auth && selectedSnapshotId),
  });

  const conflictsQuery = useQuery({
    queryKey: ["wave3-conflicts", selectedSnapshotId, auth?.tenantId],
    queryFn: () =>
      apiClient.getSnapshotConflictsAndGaps(selectedSnapshotId, auth!),
    enabled: Boolean(auth && selectedSnapshotId),
  });

  useEffect(() => {
    if (!impactTargetId) {
      const firstReq = requirementsQuery.data?.requirements?.[0];
      const firstRule = rulesQuery.data?.business_rules?.[0];
      if (firstReq) {
        setImpactTargetId(firstReq.id);
      } else if (firstRule) {
        setImpactTargetId(firstRule.id);
      }
    }
  }, [requirementsQuery.data, rulesQuery.data, impactTargetId]);

  const impactQuery = useQuery({
    queryKey: [
      "wave3-impact",
      selectedSnapshotId,
      impactTargetId,
      auth?.tenantId,
    ],
    queryFn: () =>
      apiClient.getSnapshotImpactAnalysis(
        selectedSnapshotId,
        impactTargetId,
        auth!
      ),
    enabled: Boolean(auth && selectedSnapshotId && impactTargetId),
  });

  const invalidateWave3Queries = () => {
    queryClient.invalidateQueries({ queryKey: ["wave3-rules"] });
    queryClient.invalidateQueries({ queryKey: ["wave3-requirements"] });
    queryClient.invalidateQueries({ queryKey: ["wave3-traceability"] });
    queryClient.invalidateQueries({ queryKey: ["wave3-conflicts"] });
    queryClient.invalidateQueries({ queryKey: ["wave3-impact"] });
  };

  const analyzeWave3Mutation = useMutation({
    mutationFn: () => apiClient.analyzeSnapshotWave3(selectedSnapshotId, auth!),
    onSuccess: () => invalidateWave3Queries(),
  });

  const reviewRuleMutation = useMutation({
    mutationFn: (params: {
      ruleId: string;
      new_status: string;
      review_comment?: string;
      updated_title?: string;
      updated_condition_expression?: string;
      updated_action_consequence?: string;
    }) =>
      apiClient.reviewBusinessRule(
        params.ruleId,
        {
          new_status: params.new_status,
          review_comment: params.review_comment,
          updated_title: params.updated_title,
          updated_condition_expression: params.updated_condition_expression,
          updated_action_consequence: params.updated_action_consequence,
        },
        auth!
      ),
    onSuccess: () => {
      setEditingRule(null);
      invalidateWave3Queries();
    },
  });

  const reviewRequirementMutation = useMutation({
    mutationFn: (params: {
      requirementId: string;
      new_status: string;
      review_comment?: string;
      updated_title?: string;
      updated_specification_statement?: string;
      updated_priority?: string;
    }) =>
      apiClient.reviewRequirement(
        params.requirementId,
        {
          new_status: params.new_status,
          review_comment: params.review_comment,
          updated_title: params.updated_title,
          updated_specification_statement:
            params.updated_specification_statement,
          updated_priority: params.updated_priority,
        },
        auth!
      ),
    onSuccess: () => {
      setEditingReq(null);
      invalidateWave3Queries();
    },
  });

  const resolveConflictMutation = useMutation({
    mutationFn: (params: {
      conflictId: string;
      new_status: string;
      resolution_notes?: string;
    }) =>
      apiClient.resolveConflict(
        params.conflictId,
        {
          new_status: params.new_status,
          resolution_notes: params.resolution_notes,
        },
        auth!
      ),
    onSuccess: () => invalidateWave3Queries(),
  });

  const filteredRules = useMemo(() => {
    const all = rulesQuery.data?.business_rules ?? [];
    if (ruleCategoryFilter === "ALL") return all;
    return all.filter((r) => r.rule_category === ruleCategoryFilter);
  }, [rulesQuery.data, ruleCategoryFilter]);

  const filteredRequirements = useMemo(() => {
    const all = requirementsQuery.data?.requirements ?? [];
    if (reqTypeFilter === "ALL") return all;
    return all.filter((r) => r.req_type === reqTypeFilter);
  }, [requirementsQuery.data, reqTypeFilter]);

  const statusBadgeVariant = (status: string) => {
    if (status === "APPROVED" || status.startsWith("RESOLVED")) return "success";
    if (status === "REJECTED" || status === "DISMISSED") return "destructive";
    if (status === "MODIFIED_BY_HUMAN") return "secondary";
    return "warning";
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Business Rules &amp; Requirements Intelligence
            </h1>
            <Badge variant="success">Wave 3 Live</Badge>
          </div>
          <p className="text-sm text-slate-600 mt-1">
            Evidence-anchored business rule discovery, functional &amp; non-functional requirements, bidirectional traceability, conflict detection, impact analysis, and human review governance.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Select repository"
            value={selectedRepoId}
            onChange={(e) => setSelectedRepoId(e.target.value)}
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-medium text-slate-800"
          >
            {(repositoriesQuery.data ?? []).map((repo) => (
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
            className="h-9 w-64 rounded-md border border-slate-300 bg-white px-3 text-xs font-mono text-slate-800"
          />

          <Button
            size="sm"
            onClick={() => analyzeWave3Mutation.mutate()}
            disabled={!selectedSnapshotId || analyzeWave3Mutation.isPending}
          >
            {analyzeWave3Mutation.isPending ? (
              <RefreshCw className="h-3.5 w-3.5 mr-1.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5 mr-1.5" />
            )}
            Run Wave 3 Synthesis
          </Button>
        </div>
      </div>

      {/* Summary KPI Bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-slate-500">
              Business Domains
            </div>
            <div className="text-2xl font-bold text-slate-900 mt-1">
              {rulesQuery.data?.domains.length ?? 0}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">
              {rulesQuery.data?.processes.length ?? 0} workflows reconstructed
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-slate-500">
              Business Rules
            </div>
            <div className="text-2xl font-bold text-slate-900 mt-1">
              {rulesQuery.data?.business_rules.length ?? 0}
            </div>
            <div className="text-[11px] text-emerald-700 mt-0.5">
              {
                (rulesQuery.data?.business_rules ?? []).filter(
                  (r) => r.is_confirmed_fact
                ).length
              }{" "}
              human-confirmed facts
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-slate-500">
              Requirements
            </div>
            <div className="text-2xl font-bold text-slate-900 mt-1">
              {requirementsQuery.data?.requirements.length ?? 0}
            </div>
            <div className="text-[11px] text-amber-700 mt-0.5">
              {
                (requirementsQuery.data?.requirements ?? []).filter(
                  (r) => r.is_implicit
                ).length
              }{" "}
              implicit / undocumented
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-slate-500">
              Traceability Links
            </div>
            <div className="text-2xl font-bold text-slate-900 mt-1">
              {traceabilityQuery.data?.forward_traceability.length ?? 0}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">
              {traceabilityQuery.data?.backward_traceability.length ?? 0}{" "}
              technical targets traced
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="text-xs font-medium text-slate-500">
              Conflicts &amp; Gaps
            </div>
            <div className="text-2xl font-bold text-rose-700 mt-1">
              {(conflictsQuery.data?.conflicts.length ?? 0) +
                (conflictsQuery.data?.gaps_and_undocumented.length ?? 0)}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">
              {conflictsQuery.data?.conflicts.length ?? 0} contradictions •{" "}
              {conflictsQuery.data?.overlapping_requirements.length ?? 0}{" "}
              overlaps
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {(
          [
            {
              id: "business-rules",
              label: "1. Business Rules",
              icon: BookOpen,
              count: rulesQuery.data?.business_rules.length ?? 0,
            },
            {
              id: "requirements",
              label: "2. Requirements Catalog",
              icon: FileCheck2,
              count: requirementsQuery.data?.requirements.length ?? 0,
            },
            {
              id: "traceability",
              label: "3. Traceability Matrix",
              icon: GitBranch,
              count: traceabilityQuery.data?.forward_traceability.length ?? 0,
            },
            {
              id: "conflicts",
              label: "4. Conflicts & Gaps",
              icon: AlertTriangle,
              count:
                (conflictsQuery.data?.conflicts.length ?? 0) +
                (conflictsQuery.data?.gaps_and_undocumented.length ?? 0),
            },
            {
              id: "impact",
              label: "5. Impact Analysis",
              icon: Network,
              count:
                (impactQuery.data?.affected_apis.length ?? 0) +
                (impactQuery.data?.affected_database_tables.length ?? 0) +
                (impactQuery.data?.affected_code_components.length ?? 0),
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
              className={`inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-xs font-semibold transition ${
                active
                  ? "bg-slate-900 text-white shadow-sm"
                  : "bg-white text-slate-700 hover:bg-slate-100 border border-slate-200"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                  active
                    ? "bg-slate-700 text-slate-100"
                    : "bg-slate-100 text-slate-700"
                }`}
              >
                {tab.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Evidence Source Inspector Banner (when selected) */}
      {inspectedEvidence.length > 0 && (
        <Card className="border-indigo-300 bg-indigo-50/60">
          <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-sm text-indigo-950">
                Source Evidence Anchors: {inspectedTitle}
              </CardTitle>
              <CardDescription className="text-xs text-indigo-700">
                Immutable cryptographic SHA-256 snippet anchors linking this claim to the exact source lines.
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setInspectedEvidence([])}
            >
              Close Inspector
            </Button>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            {inspectedEvidence.map((ev) => (
              <div
                key={ev.link_id}
                className="rounded border border-indigo-200 bg-white p-3 text-xs space-y-1.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono font-semibold text-slate-900">
                    {ev.relative_path || "snapshot-artifact"} (L{ev.start_line}–L
                    {ev.end_line})
                  </span>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{ev.evidence_role}</Badge>
                    <span className="font-mono text-[10px] text-slate-500">
                      SHA256: {ev.snippet_sha256.slice(0, 16)}…
                    </span>
                  </div>
                </div>
                {ev.rationale_note && (
                  <p className="text-slate-600">{ev.rationale_note}</p>
                )}
                {ev.excerpt_text && (
                  <pre className="rounded bg-slate-900 text-slate-100 p-2.5 text-[11px] font-mono overflow-x-auto">
                    {ev.excerpt_text}
                  </pre>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* TAB 1: BUSINESS RULES */}
      {activeTab === "business-rules" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                "ALL",
                "VALIDATION",
                "CALCULATION",
                "AUTHORIZATION",
                "STATE_TRANSITION",
                "INVARIANT",
                "ROUTING",
              ].map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setRuleCategoryFilter(cat)}
                  className={`rounded px-2.5 py-1 text-xs font-medium ${
                    ruleCategoryFilter === cat
                      ? "bg-indigo-600 text-white"
                      : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
            <span className="text-xs text-slate-500">
              Showing {filteredRules.length} business rule(s)
            </span>
          </div>

          {editingRule && (
            <Card className="border-amber-300 bg-amber-50/50">
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm">
                  Edit &amp; Curate Business Rule: {editingRule.rule_code}
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-3 text-xs">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">
                    Title
                  </label>
                  <input
                    type="text"
                    value={editRuleTitle}
                    onChange={(e) => setEditRuleTitle(e.target.value)}
                    className="w-full rounded border border-slate-300 bg-white px-2.5 py-1.5"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="font-semibold text-slate-700 block mb-1">
                      Condition Expression (IF / WHEN)
                    </label>
                    <textarea
                      rows={2}
                      value={editRuleCond}
                      onChange={(e) => setEditRuleCond(e.target.value)}
                      className="w-full rounded border border-slate-300 bg-white p-2 font-mono"
                    />
                  </div>
                  <div>
                    <label className="font-semibold text-slate-700 block mb-1">
                      Enforced Action / Consequence (THEN)
                    </label>
                    <textarea
                      rows={2}
                      value={editRuleAction}
                      onChange={(e) => setEditRuleAction(e.target.value)}
                      className="w-full rounded border border-slate-300 bg-white p-2 font-mono"
                    />
                  </div>
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">
                    Reviewer Audit Note
                  </label>
                  <input
                    type="text"
                    value={editRuleComment}
                    onChange={(e) => setEditRuleComment(e.target.value)}
                    placeholder="Reason for human curation..."
                    className="w-full rounded border border-slate-300 bg-white px-2.5 py-1.5"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      reviewRuleMutation.mutate({
                        ruleId: editingRule.id,
                        new_status: "MODIFIED_BY_HUMAN",
                        updated_title: editRuleTitle,
                        updated_condition_expression: editRuleCond,
                        updated_action_consequence: editRuleAction,
                        review_comment:
                          editRuleComment || "Edited and curated by human reviewer.",
                      })
                    }
                  >
                    Save Human Edit (MODIFIED_BY_HUMAN)
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditingRule(null)}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 gap-3">
            {filteredRules.map((rule) => (
              <Card key={rule.id} className="bg-white">
                <CardContent className="p-4 space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
                          {rule.rule_code}
                        </span>
                        <Badge variant="secondary">{rule.rule_category}</Badge>
                        <Badge variant="outline">{rule.domain_code}</Badge>
                        <Badge variant={statusBadgeVariant(rule.review_status)}>
                          {rule.review_status} (v{rule.version_no})
                        </Badge>
                        {rule.is_confirmed_fact ? (
                          <Badge variant="success">Confirmed Fact</Badge>
                        ) : (
                          <Badge variant="warning">
                            {rule.origin_type === "DETERMINISTIC_RULE"
                              ? "Unconfirmed Static Rule"
                              : "AI-Inferred / Hybrid"}
                          </Badge>
                        )}
                      </div>
                      <h3 className="text-sm font-semibold text-slate-900">
                        {rule.title}
                      </h3>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-mono text-slate-600 mr-2">
                        Confidence: {(rule.confidence_score * 100).toFixed(0)}%
                      </span>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setInspectedTitle(`${rule.rule_code}: ${rule.title}`);
                          setInspectedEvidence(rule.evidence);
                        }}
                      >
                        <Code2 className="h-3.5 w-3.5 mr-1" />
                        Evidence ({rule.evidence.length})
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewRuleMutation.mutate({
                            ruleId: rule.id,
                            new_status: "APPROVED",
                            review_comment: "Confirmed business rule against source evidence.",
                          })
                        }
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1 text-emerald-600" />
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setEditingRule(rule);
                          setEditRuleTitle(rule.title);
                          setEditRuleCond(rule.condition_expression);
                          setEditRuleAction(rule.action_consequence);
                          setEditRuleComment("");
                        }}
                      >
                        <Edit3 className="h-3.5 w-3.5 mr-1" />
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewRuleMutation.mutate({
                            ruleId: rule.id,
                            new_status: "PENDING_REVIEW",
                            review_comment: "Requested secondary architect review.",
                          })
                        }
                      >
                        <RotateCcw className="h-3.5 w-3.5 mr-1 text-amber-600" />
                        Request Review
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewRuleMutation.mutate({
                            ruleId: rule.id,
                            new_status: "REJECTED",
                            review_comment: "Rejected during business rule review.",
                          })
                        }
                      >
                        <XCircle className="h-3.5 w-3.5 mr-1 text-rose-600" />
                        Reject
                      </Button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-xs">
                    <div className="rounded bg-slate-50 border border-slate-200 p-2.5">
                      <span className="font-semibold text-slate-600 block mb-0.5">
                        Condition / Trigger:
                      </span>
                      <code className="text-slate-900 font-mono break-words">
                        {rule.condition_expression}
                      </code>
                    </div>
                    <div className="rounded bg-slate-50 border border-slate-200 p-2.5">
                      <span className="font-semibold text-slate-600 block mb-0.5">
                        Action / Consequence:
                      </span>
                      <code className="text-slate-900 font-mono break-words">
                        {rule.action_consequence}
                      </code>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* TAB 2: REQUIREMENTS CATALOG */}
      {activeTab === "requirements" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                "ALL",
                "FUNCTIONAL",
                "NON_FUNCTIONAL_SECURITY",
                "DATA_CONSTRAINT",
                "INTEGRATION_CONTRACT",
              ].map((rt) => (
                <button
                  key={rt}
                  type="button"
                  onClick={() => setReqTypeFilter(rt)}
                  className={`rounded px-2.5 py-1 text-xs font-medium ${
                    reqTypeFilter === rt
                      ? "bg-indigo-600 text-white"
                      : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {rt}
                </button>
              ))}
            </div>
            <span className="text-xs text-slate-500">
              Showing {filteredRequirements.length} requirement(s)
            </span>
          </div>

          {editingReq && (
            <Card className="border-amber-300 bg-amber-50/50">
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm">
                  Edit Requirement Specification: {editingReq.req_code}
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-3 text-xs">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="md:col-span-3">
                    <label className="font-semibold text-slate-700 block mb-1">
                      Requirement Title
                    </label>
                    <input
                      type="text"
                      value={editReqTitle}
                      onChange={(e) => setEditReqTitle(e.target.value)}
                      className="w-full rounded border border-slate-300 bg-white px-2.5 py-1.5"
                    />
                  </div>
                  <div>
                    <label className="font-semibold text-slate-700 block mb-1">
                      Priority
                    </label>
                    <select
                      value={editReqPriority}
                      onChange={(e) => setEditReqPriority(e.target.value)}
                      className="w-full rounded border border-slate-300 bg-white px-2.5 py-1.5"
                    >
                      <option value="MUST">MUST</option>
                      <option value="SHOULD">SHOULD</option>
                      <option value="COULD">COULD</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">
                    Normative Specification Statement
                  </label>
                  <textarea
                    rows={3}
                    value={editReqSpec}
                    onChange={(e) => setEditReqSpec(e.target.value)}
                    className="w-full rounded border border-slate-300 bg-white p-2"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">
                    Reviewer Audit Note
                  </label>
                  <input
                    type="text"
                    value={editReqComment}
                    onChange={(e) => setEditReqComment(e.target.value)}
                    placeholder="Rationale for requirement modification..."
                    className="w-full rounded border border-slate-300 bg-white px-2.5 py-1.5"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      reviewRequirementMutation.mutate({
                        requirementId: editingReq.id,
                        new_status: "MODIFIED_BY_HUMAN",
                        updated_title: editReqTitle,
                        updated_specification_statement: editReqSpec,
                        updated_priority: editReqPriority,
                        review_comment:
                          editReqComment || "Curated requirement specification.",
                      })
                    }
                  >
                    Save Human Edit (MODIFIED_BY_HUMAN)
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditingReq(null)}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 gap-3">
            {filteredRequirements.map((req) => (
              <Card key={req.id} className="bg-white">
                <CardContent className="p-4 space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded">
                          {req.req_code}
                        </span>
                        <Badge variant="secondary">{req.req_type}</Badge>
                        <Badge variant="outline">Priority: {req.priority}</Badge>
                        <Badge
                          variant={
                            req.evidence_strength === "STRONG"
                              ? "success"
                              : req.evidence_strength === "MODERATE"
                              ? "secondary"
                              : "warning"
                          }
                        >
                          Evidence: {req.evidence_strength}
                        </Badge>
                        {req.is_implicit && (
                          <Badge variant="warning">
                            Implicit / Undocumented Behavior
                          </Badge>
                        )}
                        <Badge variant={statusBadgeVariant(req.review_status)}>
                          {req.review_status} (v{req.version_no})
                        </Badge>
                      </div>
                      <h3 className="text-sm font-semibold text-slate-900">
                        {req.title}
                      </h3>
                      <p className="text-xs text-slate-700">
                        {req.specification_statement}
                      </p>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setInspectedTitle(`${req.req_code}: ${req.title}`);
                          setInspectedEvidence(req.evidence);
                        }}
                      >
                        <Code2 className="h-3.5 w-3.5 mr-1" />
                        Evidence ({req.evidence.length})
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewRequirementMutation.mutate({
                            requirementId: req.id,
                            new_status: "APPROVED",
                            review_comment: "Requirement verified and approved.",
                          })
                        }
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1 text-emerald-600" />
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setEditingReq(req);
                          setEditReqTitle(req.title);
                          setEditReqSpec(req.specification_statement);
                          setEditReqPriority(req.priority);
                          setEditReqComment("");
                        }}
                      >
                        <Edit3 className="h-3.5 w-3.5 mr-1" />
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewRequirementMutation.mutate({
                            requirementId: req.id,
                            new_status: "PENDING_REVIEW",
                            review_comment: "Requested review.",
                          })
                        }
                      >
                        <RotateCcw className="h-3.5 w-3.5 mr-1 text-amber-600" />
                        Request Review
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          reviewRequirementMutation.mutate({
                            requirementId: req.id,
                            new_status: "REJECTED",
                            review_comment: "Requirement rejected.",
                          })
                        }
                      >
                        <XCircle className="h-3.5 w-3.5 mr-1 text-rose-600" />
                        Reject
                      </Button>
                    </div>
                  </div>

                  {/* Actors / Inputs / Outputs & Acceptance Criteria */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                    <div className="rounded bg-slate-50 p-2 border border-slate-200">
                      <span className="font-semibold text-slate-600">Actors: </span>
                      <span className="text-slate-800">
                        {req.actors.join(", ")}
                      </span>
                    </div>
                    <div className="rounded bg-slate-50 p-2 border border-slate-200">
                      <span className="font-semibold text-slate-600">
                        Preconditions:{" "}
                      </span>
                      <span className="text-slate-800 font-mono">
                        {req.preconditions}
                      </span>
                    </div>
                    <div className="rounded bg-slate-50 p-2 border border-slate-200">
                      <span className="font-semibold text-slate-600">
                        Expected Outcome:{" "}
                      </span>
                      <span className="text-slate-800 font-mono">
                        {req.expected_outcomes}
                      </span>
                    </div>
                  </div>

                  {req.acceptance_criteria.length > 0 && (
                    <div className="rounded border border-slate-200 bg-slate-50/70 p-2.5 text-xs space-y-1">
                      <div className="font-semibold text-slate-700">
                        Acceptance Criteria ({req.acceptance_criteria[0].verification_method}):
                      </div>
                      {req.acceptance_criteria.map((ac) => (
                        <div
                          key={ac.id}
                          className="grid grid-cols-1 md:grid-cols-3 gap-2 text-[11px] font-mono text-slate-800"
                        >
                          <div>• {ac.given_clause}</div>
                          <div>• {ac.when_clause}</div>
                          <div>• {ac.then_clause}</div>
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

      {/* TAB 3: TRACEABILITY MATRIX */}
      {activeTab === "traceability" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {(
              [
                {
                  id: "FORWARD",
                  label:
                    "Forward Traceability (Requirement → Rules → Code/DB/API → Evidence)",
                },
                {
                  id: "BACKWARD",
                  label:
                    "Backward Traceability (Code/DB/API → Business Rules → Requirements)",
                },
                {
                  id: "WEAK",
                  label: `Weak / Missing Evidence (${
                    traceabilityQuery.data?.weak_or_missing_evidence.length ?? 0
                  })`,
                },
              ] as const
            ).map((mode) => (
              <button
                key={mode.id}
                type="button"
                onClick={() => setTraceDirection(mode.id)}
                className={`rounded px-3 py-1.5 text-xs font-semibold ${
                  traceDirection === mode.id
                    ? "bg-indigo-600 text-white"
                    : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>

          {traceDirection !== "BACKWARD" ? (
            <div className="space-y-2.5">
              {(traceDirection === "WEAK"
                ? traceabilityQuery.data?.weak_or_missing_evidence ?? []
                : traceabilityQuery.data?.forward_traceability ?? []
              ).map((row) => (
                <Card key={row.requirement_id} className="bg-white">
                  <CardContent className="p-4 text-xs space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded">
                          {row.req_code}
                        </span>
                        <span className="font-semibold text-slate-900">
                          {row.title}
                        </span>
                        <Badge variant="secondary">{row.req_type}</Badge>
                        <Badge
                          variant={
                            row.evidence_strength === "STRONG"
                              ? "success"
                              : "warning"
                          }
                        >
                          Evidence: {row.evidence_strength} ({row.evidence.length})
                        </Badge>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setInspectedTitle(`${row.req_code}: ${row.title}`);
                          setInspectedEvidence(row.evidence);
                        }}
                      >
                        Inspect Anchor
                      </Button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 pt-1">
                      <div className="rounded bg-slate-50 border border-slate-200 p-2">
                        <div className="font-semibold text-slate-600 mb-1">
                          Derived From Business Rules ({row.business_rules.length})
                        </div>
                        {row.business_rules.map((br) => (
                          <div key={br.id} className="font-mono text-[11px]">
                            {br.rule_code}: {br.title}
                          </div>
                        ))}
                      </div>
                      <div className="rounded bg-slate-50 border border-slate-200 p-2">
                        <div className="font-semibold text-slate-600 mb-1">
                          Implementing Code Symbols ({row.code_symbols.length})
                        </div>
                        {row.code_symbols.length === 0 ? (
                          <span className="text-slate-400">
                            Schema / API / Doc level
                          </span>
                        ) : (
                          row.code_symbols.map((s) => (
                            <div key={s.id} className="font-mono text-[11px]">
                              {s.qualified_name} ({s.symbol_kind})
                            </div>
                          ))
                        )}
                      </div>
                      <div className="rounded bg-slate-50 border border-slate-200 p-2">
                        <div className="font-semibold text-slate-600 mb-1">
                          Linked Graph Entities ({row.knowledge_entities.length})
                        </div>
                        {row.knowledge_entities.map((ke) => (
                          <div key={ke.id} className="font-mono text-[11px]">
                            [{ke.entity_type}] {ke.title}
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <div className="space-y-2.5">
              {(traceabilityQuery.data?.backward_traceability ?? []).map(
                (bRow) => (
                  <Card key={bRow.target_key} className="bg-white">
                    <CardContent className="p-4 text-xs space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">{bRow.target_type}</Badge>
                        <span className="font-mono font-bold text-slate-900">
                          {bRow.target_label}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <div className="rounded bg-slate-50 border border-slate-200 p-2">
                          <div className="font-semibold text-slate-600 mb-1">
                            Enforces Business Rules ({bRow.business_rules.length})
                          </div>
                          {bRow.business_rules.map((br) => (
                            <div key={br.id} className="font-mono text-[11px]">
                              {br.rule_code}: {br.title}
                            </div>
                          ))}
                        </div>
                        <div className="rounded bg-slate-50 border border-slate-200 p-2">
                          <div className="font-semibold text-slate-600 mb-1">
                            Satisfies Requirements ({bRow.requirements.length})
                          </div>
                          {bRow.requirements.map((r) => (
                            <div key={r.id} className="font-mono text-[11px]">
                              {r.req_code}: {r.title} [{r.review_status}]
                            </div>
                          ))}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 4: CONFLICTS & GAPS */}
      {activeTab === "conflicts" && (
        <div className="space-y-6">
          {/* Section A: Contradictory Business Rules */}
          <Card className="bg-white">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-rose-600" />
                Conflicting Business Rules &amp; Code-vs-Documentation Contradictions (
                {conflictsQuery.data?.conflicts.length ?? 0})
              </CardTitle>
              <CardDescription>
                Side-by-side comparison of competing assertions with primary and conflicting source evidence anchors.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {(conflictsQuery.data?.conflicts ?? []).length === 0 ? (
                <p className="text-xs text-slate-500">
                  No open rule contradictions detected in this snapshot.
                </p>
              ) : (
                (conflictsQuery.data?.conflicts ?? []).map((conf) => (
                  <div
                    key={conf.id}
                    className="rounded-lg border border-rose-200 bg-rose-50/40 p-4 text-xs space-y-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="destructive">{conf.conflict_type}</Badge>
                        <Badge variant={statusBadgeVariant(conf.status)}>
                          {conf.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            resolveConflictMutation.mutate({
                              conflictId: conf.id,
                              new_status: "RESOLVED_KEEP_PRIMARY",
                              resolution_notes:
                                "Resolved in favor of primary source code rule.",
                            })
                          }
                        >
                          Keep Primary (Code)
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            resolveConflictMutation.mutate({
                              conflictId: conf.id,
                              new_status: "RESOLVED_KEEP_CONFLICTING",
                              resolution_notes:
                                "Resolved in favor of secondary specification.",
                            })
                          }
                        >
                          Keep Secondary
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            resolveConflictMutation.mutate({
                              conflictId: conf.id,
                              new_status: "DISMISSED",
                              resolution_notes: "Dismissed by reviewer.",
                            })
                          }
                        >
                          Dismiss
                        </Button>
                      </div>
                    </div>

                    {conf.resolution_notes && (
                      <p className="text-slate-800 font-medium">
                        {conf.resolution_notes}
                      </p>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="rounded bg-white border border-slate-200 p-3 space-y-1">
                        <div className="font-semibold text-slate-900">
                          Primary Assertion: {conf.primary_label}
                        </div>
                        {conf.primary_evidence && (
                          <pre className="rounded bg-slate-900 text-slate-100 p-2 text-[11px] font-mono overflow-x-auto">
                            {conf.primary_evidence.excerpt_text}
                          </pre>
                        )}
                      </div>
                      <div className="rounded bg-white border border-slate-200 p-3 space-y-1">
                        <div className="font-semibold text-slate-900">
                          Conflicting Assertion: {conf.conflicting_label}
                        </div>
                        {conf.conflicting_evidence && (
                          <pre className="rounded bg-slate-900 text-slate-100 p-2 text-[11px] font-mono overflow-x-auto">
                            {conf.conflicting_evidence.excerpt_text}
                          </pre>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {/* Section B: Duplicate & Overlapping Requirements */}
          <Card className="bg-white">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Layers className="h-4 w-4 text-amber-600" />
                Duplicate &amp; Overlapping Requirements (
                {conflictsQuery.data?.overlapping_requirements.length ?? 0})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              {(conflictsQuery.data?.overlapping_requirements ?? []).map(
                (ov, idx) => (
                  <div
                    key={`${ov.primary_req_code}-${ov.overlapping_req_code}-${idx}`}
                    className="rounded border border-slate-200 p-3 flex flex-wrap items-center justify-between gap-2"
                  >
                    <div>
                      <span className="font-mono font-bold text-indigo-700">
                        {ov.primary_req_code}
                      </span>{" "}
                      ({ov.primary_title}) ↔{" "}
                      <span className="font-mono font-bold text-indigo-700">
                        {ov.overlapping_req_code}
                      </span>{" "}
                      ({ov.overlapping_title})
                    </div>
                    <Badge variant="warning">
                      Similarity: {(ov.similarity_score * 100).toFixed(0)}% (
                      {ov.shared_terms.slice(0, 4).join(", ")})
                    </Badge>
                  </div>
                )
              )}
            </CardContent>
          </Card>

          {/* Section C: Undocumented Behavior & Missing Requirements */}
          <Card className="bg-white">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-indigo-600" />
                Undocumented Behavior &amp; Missing Documentation Coverage (
                {conflictsQuery.data?.gaps_and_undocumented.length ?? 0})
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-xs">
              {(conflictsQuery.data?.gaps_and_undocumented ?? []).map(
                (gap, idx) => (
                  <div
                    key={`${gap.title}-${idx}`}
                    className="rounded border border-slate-200 bg-slate-50 p-3 space-y-1"
                  >
                    <div className="flex items-center gap-2">
                      <Badge variant="warning">{gap.gap_type}</Badge>
                      {gap.req_code && (
                        <span className="font-mono font-bold text-slate-800">
                          {gap.req_code}
                        </span>
                      )}
                    </div>
                    <div className="font-semibold text-slate-900">
                      {gap.title}
                    </div>
                    <p className="text-slate-600">{gap.description}</p>
                  </div>
                )
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 5: IMPACT ANALYSIS */}
      {activeTab === "impact" && (
        <div className="space-y-4">
          <Card className="bg-white">
            <CardHeader className="pb-3">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                  <CardTitle className="text-base">
                    Multi-Hop Requirement &amp; Business Rule Impact Analyzer
                  </CardTitle>
                  <CardDescription>
                    Select any requirement or business rule to trace potentially affected APIs, database tables, code modules, and infrastructure.
                  </CardDescription>
                </div>
                <select
                  aria-label="Select impact analysis target"
                  value={impactTargetId}
                  onChange={(e) => setImpactTargetId(e.target.value)}
                  className="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-mono text-slate-900 min-w-[300px]"
                >
                  <optgroup label="Requirements">
                    {(requirementsQuery.data?.requirements ?? []).map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.req_code}: {r.title}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="Business Rules">
                    {(rulesQuery.data?.business_rules ?? []).map((br) => (
                      <option key={br.id} value={br.id}>
                        {br.rule_code}: {br.title}
                      </option>
                    ))}
                  </optgroup>
                </select>
              </div>
            </CardHeader>

            {impactQuery.data && (
              <CardContent className="space-y-4 text-xs">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="font-semibold text-slate-900">
                      {impactQuery.data.impact_explanation}
                    </span>
                  </div>
                  <Badge
                    variant={
                      impactQuery.data.blast_radius_risk === "CRITICAL" ||
                      impactQuery.data.blast_radius_risk === "HIGH"
                        ? "destructive"
                        : "warning"
                    }
                  >
                    Blast Radius: {impactQuery.data.blast_radius_risk}
                  </Badge>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="rounded border border-slate-200 p-3 space-y-1.5">
                    <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                      <Network className="h-3.5 w-3.5 text-indigo-600" />
                      Affected APIs ({impactQuery.data.affected_apis.length})
                    </div>
                    {impactQuery.data.affected_apis.map((n) => (
                      <div
                        key={n.id}
                        className="font-mono text-[11px] bg-slate-50 p-1.5 rounded"
                      >
                        {n.title} (hop {n.hop_depth})
                      </div>
                    ))}
                  </div>

                  <div className="rounded border border-slate-200 p-3 space-y-1.5">
                    <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                      <Database className="h-3.5 w-3.5 text-emerald-600" />
                      Affected DB Tables (
                      {impactQuery.data.affected_database_tables.length})
                    </div>
                    {impactQuery.data.affected_database_tables.map((n) => (
                      <div
                        key={n.id}
                        className="font-mono text-[11px] bg-slate-50 p-1.5 rounded"
                      >
                        {n.title} (hop {n.hop_depth})
                      </div>
                    ))}
                  </div>

                  <div className="rounded border border-slate-200 p-3 space-y-1.5">
                    <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                      <Code2 className="h-3.5 w-3.5 text-amber-600" />
                      Affected Code Symbols (
                      {impactQuery.data.affected_code_components.length})
                    </div>
                    {impactQuery.data.affected_code_components.map((n) => (
                      <div
                        key={n.id}
                        className="font-mono text-[11px] bg-slate-50 p-1.5 rounded"
                      >
                        [{n.entity_type}] {n.title} (hop {n.hop_depth})
                      </div>
                    ))}
                  </div>

                  <div className="rounded border border-slate-200 p-3 space-y-1.5">
                    <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                      <Server className="h-3.5 w-3.5 text-purple-600" />
                      Affected Infrastructure (
                      {impactQuery.data.affected_infrastructure.length})
                    </div>
                    {impactQuery.data.affected_infrastructure.map((n) => (
                      <div
                        key={n.id}
                        className="font-mono text-[11px] bg-slate-50 p-1.5 rounded"
                      >
                        {n.title} (hop {n.hop_depth})
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
