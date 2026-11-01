"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
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

export default function DashboardPage() {
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

  const snapshotsQuery = useQuery({
    queryKey: ["snapshots", projectId],
    queryFn: () => apiClient.listProjectSnapshots(projectId!, auth!),
    enabled: Boolean(projectId && auth),
  });

  const summaryQuery = useQuery({
    queryKey: ["code-summary", projectId],
    queryFn: () => apiClient.getCodeSummary(projectId!, auth!),
    enabled: Boolean(projectId && auth),
  });

  const summary = summaryQuery.data;
  const langBreakdown = summary?.language_breakdown || {};

  const chartData = [
    { language: "Python", files: langBreakdown.python || 0 },
    { language: "Java", files: langBreakdown.java || 0 },
    { language: "TypeScript", files: langBreakdown.typescript || 0 },
    { language: "JavaScript", files: langBreakdown.javascript || 0 },
    { language: "PHP", files: langBreakdown.php || 0 },
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Platform Dashboard
            </h1>
            <Badge variant="success">Wave 1 Active</Badge>
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
              "Multi-tenant workspace telemetry, deterministic code intelligence, and infrastructure readiness."
            )}
          </p>
        </div>
      </div>

      {/* Live Wave 1 Metrics Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Registered Repositories</CardDescription>
            <CardTitle className="text-2xl font-mono">
              {reposQuery.data?.length ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-500">
              Immutable Snapshots: {snapshotsQuery.data?.length ?? 0}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Extracted AST Symbols</CardDescription>
            <CardTitle className="text-2xl font-mono">
              {summary?.total_symbols ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-500">
              Parsed Files: {summary?.total_files ?? 0} ({summary?.total_loc ?? 0} LOC)
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Static Call Graph Edges</CardDescription>
            <CardTitle className="text-2xl font-mono">
              {summary?.total_call_edges ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-500">
              Imports: {summary?.total_imports ?? 0} &bull; Hierarchies:{" "}
              {summary?.total_type_hierarchies ?? 0}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Hybrid Retrieval Index</CardDescription>
            <CardTitle className="text-lg font-mono pt-1">
              vector(384) + FTS
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-500 font-mono">
              BAAI/bge-small-en-v1.5 (RRF k=60)
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Live Infrastructure Health */}
      <InfrastructureStatusPanel />

      {/* Recharts Language Breakdown */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">
                Parsed Source Files by Programming Language
              </CardTitle>
              <CardDescription>
                Live deterministic parser breakdown from PostgreSQL{" "}
                <span className="font-mono text-xs">code_files</span> across the active project baseline.
              </CardDescription>
            </div>
            <Badge variant="outline" className="font-mono text-xs">
              Wave 1 Telemetry
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="language" fontSize={12} stroke="#475569" />
                <YAxis allowDecimals={false} fontSize={12} stroke="#475569" />
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
  );
}
