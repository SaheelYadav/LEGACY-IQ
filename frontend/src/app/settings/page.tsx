"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Lock, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const workspacePreferenceSchema = z.object({
  defaultProvider: z.enum(["ollama", "openrouter", "gemini", "groq"]),
  ollamaModel: z.string().min(1, "Model identifier is required"),
  embeddingModel: z.string().min(1, "Embedding model is required"),
});

type WorkspacePreferenceValues = z.infer<typeof workspacePreferenceSchema>;

export default function SettingsPage() {
  const [savedBanner, setSavedBanner] = useState(false);

  const form = useForm<WorkspacePreferenceValues>({
    resolver: zodResolver(workspacePreferenceSchema),
    defaultValues: {
      defaultProvider: "ollama",
      ollamaModel: "qwen2.5-coder:3b",
      embeddingModel: "BAAI/bge-small-en-v1.5",
    },
  });

  const onSubmit = () => {
    setSavedBanner(true);
    setTimeout(() => setSavedBanner(false), 3000);
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2.5">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Settings &amp; Environment Configuration
          </h1>
          <Badge variant="outline" className="font-mono">
            M0 Configuration
          </Badge>
        </div>
        <p className="text-sm text-slate-600 mt-1">
          Inspect local runtime bindings. Secrets and database credentials are managed exclusively in <code className="font-mono text-xs">backend/.env</code> and never exposed to the browser.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              AI &amp; Embedding Provider Defaults (React Hook Form + Zod)
            </CardTitle>
            <CardDescription>
              Local-first configuration using Ollama and Sentence Transformers.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Default AI Inference Provider
                </label>
                <select
                  {...form.register("defaultProvider")}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-mono"
                >
                  <option value="ollama">ollama (Local Default)</option>
                  <option value="openrouter">openrouter (Fallback)</option>
                  <option value="gemini">gemini (Future Stub)</option>
                  <option value="groq">groq (Future Stub)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Ollama Model Identifier
                </label>
                <input
                  type="text"
                  {...form.register("ollamaModel")}
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-mono"
                />
                {form.formState.errors.ollamaModel && (
                  <p className="text-xs text-rose-600 mt-1">
                    {form.formState.errors.ollamaModel.message}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Local Embedding Model (384-dim)
                </label>
                <input
                  type="text"
                  readOnly
                  {...form.register("embeddingModel")}
                  className="w-full rounded-md border border-slate-200 bg-slate-100 px-3 py-2 text-sm font-mono text-slate-600"
                />
              </div>

              <div className="flex items-center justify-between pt-2">
                <Button type="submit" size="sm">
                  Validate Form Schema
                </Button>
                {savedBanner && (
                  <span className="text-xs text-emerald-700 flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Validated locally
                  </span>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Lock className="h-4 w-4 text-slate-700" />
              <CardTitle className="text-base">
                Backend Environment Security Policy
              </CardTitle>
            </div>
            <CardDescription>
              Required backend variables configured via <code className="font-mono text-xs">backend/.env</code>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs font-mono text-slate-700">
            <div className="rounded-lg bg-slate-900 text-slate-100 p-4 space-y-1.5 overflow-x-auto">
              <div>DATABASE_URL=postgresql+psycopg://legacyiq_admin:***@localhost:5432/legacyiq</div>
              <div>REDIS_URL=redis://:***@localhost:6380/0</div>
              <div>OLLAMA_BASE_URL=http://localhost:11434</div>
              <div>OLLAMA_MODEL=qwen2.5-coder:3b</div>
              <div>EMBEDDING_PROVIDER=sentence_transformers</div>
              <div>EMBEDDING_MODEL=BAAI/bge-small-en-v1.5</div>
              <div>EMBEDDING_DIMENSION=384</div>
            </div>
            <p className="font-sans text-slate-500 leading-relaxed">
              Credentials are never transmitted to the frontend client. Configure your actual passwords in <code className="font-mono">C:\LegacyIQ\backend\.env</code>.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

