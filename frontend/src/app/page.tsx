import Link from "next/link";
import {
  ArrowRight,
  Code2,
  FileSearch,
  GitBranch,
  Layers,
  Shield,
  Sparkles,
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
import { InfrastructureStatusPanel } from "@/components/health/infrastructure-status-panel";

const capabilities = [
  {
    title: "Automated Repository Discovery",
    description:
      "Static language inventory, entrypoint detection, and framework profiling for Python, Java, JS/TS, and PHP.",
    icon: GitBranch,
    milestone: "Wave 1 Active",
  },
  {
    title: "Requirements & Business Logic Extraction",
    description:
      "Evidence-linked reconstruction of functional and non-functional requirements directly from AST and call graphs.",
    icon: FileSearch,
    milestone: "Wave 3 Active",
  },
  {
    title: "Architecture & Dependency Mapping",
    description:
      "Structural decomposition powered by Tree-sitter, Python AST, NetworkX, and interactive React Flow canvases.",
    icon: Layers,
    milestone: "Wave 2 Active",
  },
  {
    title: "Local Semantic Code Intelligence",
    description:
      "384-dimension local embeddings (BAAI/bge-small-en-v1.5) indexed in PostgreSQL 17 pgvector with Ollama inference.",
    icon: Sparkles,
    milestone: "Waves 1–5 Active",
  },
  {
    title: "Characterization Test Blueprints",
    description:
      "Automated test specification generation to lock down legacy behavior prior to refactoring.",
    icon: Code2,
    milestone: "Wave 4 Active",
  },
  {
    title: "Zero-Execution Security Posture",
    description:
      "Customer source code is never executed. Credentials remain isolated on local infrastructure.",
    icon: Shield,
    milestone: "Enforced M0–W6",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="max-w-3xl space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="default">Waves 1–6 Integrated Platform</Badge>
            <Badge variant="outline" className="font-mono">
              Local-First Architecture
            </Badge>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            LegacyIQ — Legacy Application Discovery &amp; Requirements Intelligence
          </h1>
          <p className="text-base text-slate-600 leading-relaxed">
            Foundation workspace initialized and wired to local PostgreSQL 17 (
            <code className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">
              pgvector
            </code>
            ), Redis 7, Sentence Transformers (
            <code className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">
              BAAI/bge-small-en-v1.5
            </code>
            ), and Ollama (
            <code className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">
              qwen2.5-coder:3b
            </code>
            ).
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link href="/dashboard">
              <Button size="lg">
                Open Workspace Dashboard
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/settings">
              <Button variant="outline" size="lg">
                Inspect Environment &amp; Providers
              </Button>
            </Link>
          </div>
        </div>
      </div>

      {/* Live Infrastructure Probe */}
      <InfrastructureStatusPanel />

      {/* Capabilities Grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Platform Capability Matrix
            </h2>
            <p className="text-sm text-slate-500">
              Architectural modules scaffolded in M0 and scheduled across upcoming milestones.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {capabilities.map((cap) => {
            const Icon = cap.icon;
            return (
              <Card key={cap.title} className="flex flex-col justify-between">
                <CardHeader>
                  <div className="flex items-center justify-between mb-2">
                    <div className="h-9 w-9 rounded-lg bg-slate-100 flex items-center justify-center">
                      <Icon className="h-4 w-4 text-slate-800" />
                    </div>
                    <Badge variant="secondary" className="font-mono text-[11px]">
                      {cap.milestone}
                    </Badge>
                  </div>
                  <CardTitle className="text-base">{cap.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-slate-600 leading-relaxed">
                    {cap.description}
                  </CardDescription>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}

