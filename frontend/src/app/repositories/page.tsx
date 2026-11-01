"use client";

import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FolderGit2,
  Upload,
  Search,
  Code2,
  CheckCircle2,
  Clock,
  ShieldCheck,
  FileCode,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiClient, type HybridSearchHitItem } from "@/lib/api";

export default function RepositoriesPage() {
  const queryClient = useQueryClient();
  const [newRepoName, setNewRepoName] = useState("");
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [snapshotLabel, setSnapshotLabel] = useState("");
  const [uploadStatusMsg, setUploadStatusMsg] = useState<string | null>(null);
  const [uploadErrorMsg, setUploadErrorMsg] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<HybridSearchHitItem[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

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

  const jobsQuery = useQuery({
    queryKey: ["ingestion-jobs", projectId],
    queryFn: () => apiClient.listIngestionJobs(projectId!, auth!),
    enabled: Boolean(projectId && auth),
  });

  const symbolsQuery = useQuery({
    queryKey: ["code-symbols", projectId],
    queryFn: () => apiClient.listCodeSymbols(projectId!, auth!),
    enabled: Boolean(projectId && auth),
  });

  const activeRepoId =
    selectedRepoId ||
    reposQuery.data?.[0]?.id ||
    bootstrapQuery.data?.default_repository_id ||
    "";

  const activeSnapshotId =
    snapshotsQuery.data?.[0]?.id ||
    bootstrapQuery.data?.latest_snapshot_id ||
    "";

  const createRepoMutation = useMutation({
    mutationFn: (name: string) =>
      apiClient.createRepository(
        { project_id: projectId!, name, default_branch: "main" },
        auth!
      ),
    onSuccess: (created) => {
      setNewRepoName("");
      setSelectedRepoId(created.id);
      queryClient.invalidateQueries({ queryKey: ["repositories", projectId] });
    },
  });

  const uploadZipMutation = useMutation({
    mutationFn: () =>
      apiClient.uploadRepositoryZip(
        activeRepoId,
        selectedFile!,
        snapshotLabel || undefined,
        auth!
      ),
    onSuccess: (res) => {
      setUploadErrorMsg(null);
      setUploadStatusMsg(
        `Ingested ${res.files_processed} files (${res.total_bytes} bytes), indexed ${res.chunks_indexed} chunks into snapshot ${res.snapshot_id.slice(0, 8)} (tree SHA: ${res.tree_hash.slice(0, 12)}).`
      );
      setSelectedFile(null);
      setSnapshotLabel("");
      queryClient.invalidateQueries({ queryKey: ["snapshots", projectId] });
      queryClient.invalidateQueries({ queryKey: ["ingestion-jobs", projectId] });
      queryClient.invalidateQueries({ queryKey: ["code-symbols", projectId] });
      queryClient.invalidateQueries({ queryKey: ["code-summary", projectId] });
    },
    onError: (err: Error) => {
      setUploadStatusMsg(null);
      setUploadErrorMsg(err.message);
    },
  });

  async function handleHybridSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || !auth || !activeSnapshotId || !searchQuery.trim()) return;
    setIsSearching(true);
    setSearchError(null);
    try {
      const res = await apiClient.hybridSearch(
        {
          project_id: projectId,
          snapshot_id: activeSnapshotId,
          query: searchQuery.trim(),
          limit: 10,
        },
        auth
      );
      setSearchHits(res.hits);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Repositories &amp; Source Intelligence
            </h1>
            <Badge variant="success">Wave 1 Active</Badge>
          </div>
          <p className="text-sm text-slate-600 mt-1">
            Immutable ZIP snapshot ingestion, multi-language deterministic AST extraction, and hybrid RRF code search.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg">
          <ShieldCheck className="h-4 w-4 text-emerald-600 shrink-0" />
          <span>PostgreSQL RLS + Zip-Slip Guard Enforced</span>
        </div>
      </div>

      {/* Repository Registration & ZIP Upload Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <FolderGit2 className="h-4 w-4 text-slate-700" />
              Project Repositories ({reposQuery.data?.length ?? 0})
            </CardTitle>
            <CardDescription>
              Register a source repository inside project{" "}
              <span className="font-mono text-xs">
                {bootstrapQuery.data?.project_key || "CORE"}
              </span>
              .
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (newRepoName.trim() && projectId && auth) {
                  createRepoMutation.mutate(newRepoName.trim());
                }
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={newRepoName}
                onChange={(e) => setNewRepoName(e.target.value)}
                placeholder="e.g. billing-service-legacy"
                className="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
              <button
                type="submit"
                disabled={!newRepoName.trim() || createRepoMutation.isPending}
                className="rounded-md bg-slate-900 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              >
                {createRepoMutation.isPending ? "Creating..." : "Add Repository"}
              </button>
            </form>

            <div className="space-y-2 max-h-48 overflow-y-auto">
              {(reposQuery.data || []).map((repo) => (
                <div
                  key={repo.id}
                  onClick={() => setSelectedRepoId(repo.id)}
                  className={`cursor-pointer rounded-lg border px-3 py-2 flex items-center justify-between text-xs transition-colors ${
                    repo.id === activeRepoId
                      ? "border-slate-900 bg-slate-900/5"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <div>
                    <div className="font-semibold text-slate-900">{repo.name}</div>
                    <div className="font-mono text-[11px] text-slate-500">
                      Branch: {repo.default_branch} &bull; ID: {repo.id.slice(0, 8)}
                    </div>
                  </div>
                  <Badge variant={repo.id === activeRepoId ? "default" : "outline"}>
                    {repo.id === activeRepoId ? "Selected" : "Select"}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Upload className="h-4 w-4 text-slate-700" />
              Ingest Source Archive (.zip)
            </CardTitle>
            <CardDescription>
              Validates archive integrity, extracts deterministic AST symbols (Python, Java, TS, JS, PHP), and indexes 384-d embeddings.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <label className="block text-xs font-medium text-slate-700">
                Snapshot Label (optional)
              </label>
              <input
                type="text"
                value={snapshotLabel}
                onChange={(e) => setSnapshotLabel(e.target.value)}
                placeholder="e.g. release-2026-q4"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-slate-700">
                ZIP Archive File
              </label>
              <input
                type="file"
                accept=".zip,application/zip"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="w-full text-xs text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-800 hover:file:bg-slate-200"
              />
            </div>

            <button
              type="button"
              disabled={!selectedFile || !activeRepoId || uploadZipMutation.isPending}
              onClick={() => uploadZipMutation.mutate()}
              className="w-full rounded-md bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {uploadZipMutation.isPending
                ? "Validating, Parsing AST & Indexing Vectors..."
                : "Upload & Run Deterministic Discovery"}
            </button>

            {uploadStatusMsg && (
              <div className="rounded-md bg-emerald-50 border border-emerald-200 p-2.5 text-xs text-emerald-900 flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>{uploadStatusMsg}</span>
              </div>
            )}

            {uploadErrorMsg && (
              <div className="rounded-md bg-rose-50 border border-rose-200 p-2.5 text-xs text-rose-900">
                {uploadErrorMsg}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Snapshots & Ingestion Jobs */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Immutable Repository Snapshots ({snapshotsQuery.data?.length ?? 0})
            </CardTitle>
            <CardDescription>
              Content-addressed SHA-256 tree snapshots stored in tenant-isolated vault.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {(snapshotsQuery.data || []).length === 0 ? (
              <p className="text-xs text-slate-500">
                No snapshots captured yet. Upload a ZIP archive above to create your first immutable baseline.
              </p>
            ) : (
              <div className="space-y-2 max-h-56 overflow-y-auto">
                {(snapshotsQuery.data || []).map((snap) => (
                  <div
                    key={snap.id}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs flex items-center justify-between"
                  >
                    <div>
                      <div className="font-semibold text-slate-900">
                        {snap.snapshot_label || snap.id.slice(0, 8)}
                      </div>
                      <div className="font-mono text-[11px] text-slate-500">
                        Tree SHA: {snap.tree_hash.slice(0, 16)}... &bull;{" "}
                        {snap.file_count} files ({snap.total_bytes} B)
                      </div>
                    </div>
                    <Badge variant="success">{snap.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4 text-slate-700" />
              Ingestion &amp; Analysis Jobs ({jobsQuery.data?.length ?? 0})
            </CardTitle>
            <CardDescription>
              Execution telemetry across archive validation, static parsing, and vector indexing.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {(jobsQuery.data || []).length === 0 ? (
              <p className="text-xs text-slate-500">No ingestion jobs recorded yet.</p>
            ) : (
              <div className="space-y-2 max-h-56 overflow-y-auto">
                {(jobsQuery.data || []).map((job) => (
                  <div
                    key={job.id}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs flex items-center justify-between"
                  >
                    <div>
                      <div className="font-mono font-semibold text-slate-900">
                        {job.stage} ({job.progress_pct}%)
                      </div>
                      <div className="text-[11px] text-slate-500">
                        Processed {job.files_processed} files ({job.bytes_processed} bytes)
                      </div>
                    </div>
                    <Badge
                      variant={job.status === "COMPLETED" ? "success" : "warning"}
                    >
                      {job.status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Hybrid RRF Semantic + Lexical Search */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="h-4 w-4 text-slate-700" />
            Hybrid Reciprocal Rank Fusion (RRF) Codebase Search
          </CardTitle>
          <CardDescription>
            Combines 384-d <span className="font-mono text-xs">pgvector</span> HNSW cosine similarity with PostgreSQL{" "}
            <span className="font-mono text-xs">tsvector</span> full-text search, strictly scoped to active tenant and snapshot.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleHybridSearch} className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search business calculations, symbol names, or domain concepts..."
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={!activeSnapshotId || isSearching || !searchQuery.trim()}
              className="rounded-md bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {isSearching ? "Searching..." : "Run Hybrid Search"}
            </button>
          </form>

          {searchError && (
            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">
              {searchError}
            </div>
          )}

          {searchHits.length > 0 && (
            <div className="space-y-3">
              {searchHits.map((hit) => (
                <div
                  key={hit.chunk_id}
                  className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 space-y-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2 font-mono font-semibold text-slate-900">
                      <FileCode className="h-3.5 w-3.5 text-slate-600" />
                      <span>
                        {hit.relative_path}:{hit.start_line}-{hit.end_line}
                      </span>
                      {hit.symbol_qualified_name && (
                        <Badge variant="secondary" className="font-mono text-[10px]">
                          {hit.symbol_qualified_name} ({hit.symbol_kind})
                        </Badge>
                      )}
                    </div>
                    <div className="font-mono text-[11px] text-slate-600">
                      RRF: {hit.rrf_score} &bull; Vec:{" "}
                      {hit.vector_score ?? "N/A"} &bull; Lex:{" "}
                      {hit.lexical_score ?? "N/A"}
                    </div>
                  </div>
                  <pre className="rounded bg-slate-900 text-slate-100 p-3 text-xs font-mono overflow-x-auto">
                    {hit.chunk_text}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extracted AST Symbols Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Code2 className="h-4 w-4 text-slate-700" />
            Extracted Deterministic AST Symbols ({symbolsQuery.data?.length ?? 0})
          </CardTitle>
          <CardDescription>
            Classes, interfaces, functions, methods, and constants with line spans, cyclomatic complexity, and normalized AST SHA-256 hashes.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {(symbolsQuery.data || []).length === 0 ? (
            <p className="text-xs text-slate-500">
              No symbols extracted yet. Upload a repository archive above to populate deterministic code intelligence.
            </p>
          ) : (
            <div className="overflow-x-auto max-h-80">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    <th className="py-2 px-2">Qualified Symbol</th>
                    <th className="py-2 px-2">Kind</th>
                    <th className="py-2 px-2">Visibility</th>
                    <th className="py-2 px-2">Lines</th>
                    <th className="py-2 px-2">Complexity</th>
                    <th className="py-2 px-2">AST Hash</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {(symbolsQuery.data || []).map((sym) => (
                    <tr key={sym.id} className="hover:bg-slate-50">
                      <td className="py-2 px-2 font-semibold text-slate-900">
                        {sym.qualified_name}
                      </td>
                      <td className="py-2 px-2">
                        <Badge variant="outline" className="text-[10px]">
                          {sym.symbol_kind}
                        </Badge>
                      </td>
                      <td className="py-2 px-2 text-slate-600">{sym.visibility}</td>
                      <td className="py-2 px-2 text-slate-600">
                        L{sym.start_line}–L{sym.end_line}
                      </td>
                      <td className="py-2 px-2 text-slate-600">
                        {sym.cyclomatic_complexity ?? 1}
                      </td>
                      <td className="py-2 px-2 text-slate-400">
                        {sym.body_ast_hash.slice(0, 12)}...
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
