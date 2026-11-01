"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Database,
  Server,
  Cpu,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import { apiClient, type ServiceHealthResponse } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

function renderStatusBadge(
  isLoading: boolean,
  isError: boolean,
  data?: ServiceHealthResponse
) {
  if (isLoading) {
    return <Badge variant="secondary">Checking...</Badge>;
  }
  if (isError || !data) {
    return <Badge variant="destructive">Backend Offline</Badge>;
  }
  if (data.status === "healthy") {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" /> Healthy
      </Badge>
    );
  }
  if (data.status === "unconfigured") {
    return (
      <Badge variant="warning" className="gap-1">
        <AlertTriangle className="h-3 w-3" /> Credentials Required
      </Badge>
    );
  }
  return (
    <Badge variant="destructive" className="gap-1">
      <XCircle className="h-3 w-3" /> Unhealthy
    </Badge>
  );
}

export function InfrastructureStatusPanel() {
  const appHealth = useQuery({
    queryKey: ["health", "app"],
    queryFn: apiClient.getAppHealth,
  });

  const dbHealth = useQuery({
    queryKey: ["health", "database"],
    queryFn: apiClient.getDatabaseHealth,
  });

  const redisHealth = useQuery({
    queryKey: ["health", "redis"],
    queryFn: apiClient.getRedisHealth,
  });

  const ollamaHealth = useQuery({
    queryKey: ["health", "ollama"],
    queryFn: apiClient.getOllamaHealth,
  });

  const refreshAll = () => {
    appHealth.refetch();
    dbHealth.refetch();
    redisHealth.refetch();
    ollamaHealth.refetch();
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="text-base font-semibold">
            Live Infrastructure Connectivity (Truthful M0 Health Probes)
          </CardTitle>
          <CardDescription className="mt-1">
            Queries FastAPI health endpoints (<code className="font-mono text-xs">/api/v1/health/*</code>) against{" "}
            <code className="font-mono text-xs">C:\LegacyIQ-infrastructure</code>
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={refreshAll}>
          <RefreshCw className="h-3.5 w-3.5" />
          Re-probe Services
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {/* FastAPI Core */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4 flex flex-col justify-between space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium text-sm">
                <Activity className="h-4 w-4 text-slate-600" />
                <span>FastAPI Backend</span>
              </div>
              {appHealth.isLoading ? (
                <Badge variant="secondary">Checking...</Badge>
              ) : appHealth.isError || !appHealth.data ? (
                <Badge variant="destructive">Unreachable</Badge>
              ) : (
                <Badge variant="success" className="gap-1">
                  <CheckCircle2 className="h-3 w-3" /> Online
                </Badge>
              )}
            </div>
            <div className="text-xs text-slate-600 space-y-1 font-mono">
              <div>GET /api/v1/health</div>
              <div className="text-slate-500">
                {appHealth.data
                  ? `Env: ${appHealth.data.environment} (${appHealth.data.milestone})`
                  : "Start backend on port 8000"}
              </div>
            </div>
          </div>

          {/* PostgreSQL + pgvector */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4 flex flex-col justify-between space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium text-sm">
                <Database className="h-4 w-4 text-slate-600" />
                <span>PostgreSQL 17</span>
              </div>
              {renderStatusBadge(
                dbHealth.isLoading,
                dbHealth.isError,
                dbHealth.data
              )}
            </div>
            <div className="text-xs text-slate-600 space-y-1 font-mono">
              <div>localhost:5432 / legacyiq</div>
              <div className="text-slate-500 truncate">
                {dbHealth.data?.error
                  ? dbHealth.data.error
                  : dbHealth.data?.status === "healthy"
                  ? `pgvector: ${String(
                      dbHealth.data.details?.pgvector_installed ?? "checked"
                    )}`
                  : "Awaiting probe response"}
              </div>
            </div>
          </div>

          {/* Redis */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4 flex flex-col justify-between space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium text-sm">
                <Server className="h-4 w-4 text-slate-600" />
                <span>Redis 7</span>
              </div>
              {renderStatusBadge(
                redisHealth.isLoading,
                redisHealth.isError,
                redisHealth.data
              )}
            </div>
            <div className="text-xs text-slate-600 space-y-1 font-mono">
              <div>localhost:6380 (Container 6379)</div>
              <div className="text-slate-500 truncate">
                {redisHealth.data?.error
                  ? redisHealth.data.error
                  : redisHealth.data?.status === "healthy"
                  ? `Latency: ${redisHealth.data.latency_ms ?? 0} ms`
                  : "Awaiting probe response"}
              </div>
            </div>
          </div>

          {/* Ollama */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4 flex flex-col justify-between space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium text-sm">
                <Cpu className="h-4 w-4 text-slate-600" />
                <span>Ollama Local LLM</span>
              </div>
              {renderStatusBadge(
                ollamaHealth.isLoading,
                ollamaHealth.isError,
                ollamaHealth.data
              )}
            </div>
            <div className="text-xs text-slate-600 space-y-1 font-mono">
              <div>localhost:11434 (qwen2.5-coder:3b)</div>
              <div className="text-slate-500 truncate">
                {ollamaHealth.data?.error
                  ? ollamaHealth.data.error
                  : ollamaHealth.data?.status === "healthy"
                  ? `Model ready: ${String(
                      ollamaHealth.data.details?.configured_model_available ??
                        true
                    )}`
                  : "Awaiting probe response"}
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

