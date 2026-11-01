"use client";

import { useEffect } from "react";
import { AlertOctagon, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Application route boundary caught error:", error);
  }, [error]);

  return (
    <div className="flex items-center justify-center py-16">
      <Card className="max-w-lg w-full border-rose-200">
        <CardHeader>
          <div className="flex items-center gap-2.5 text-rose-700">
            <AlertOctagon className="h-5 w-5" />
            <CardTitle>Application Route Error</CardTitle>
          </div>
          <CardDescription>
            An unexpected error occurred while rendering this LegacyIQ view.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md bg-slate-100 p-3 font-mono text-xs text-slate-700 break-all">
            {error.message || "Unknown client runtime exception"}
          </div>
          <Button onClick={reset} variant="default" size="sm">
            <RotateCcw className="h-3.5 w-3.5" />
            Retry View
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

