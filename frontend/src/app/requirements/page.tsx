import { FileCheck2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function RequirementsPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2.5">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Requirements Intelligence
          </h1>
          <Badge variant="warning">M0 Foundation Placeholder</Badge>
        </div>
        <p className="text-sm text-slate-600 mt-1">
          Evidence-backed functional and non-functional requirement discovery catalog.
        </p>
      </div>

      <Card className="border-dashed border-2 border-slate-300 bg-white">
        <CardHeader className="items-center text-center">
          <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center mb-2">
            <FileCheck2 className="h-6 w-6 text-slate-700" />
          </div>
          <CardTitle>No Requirements Extracted Yet (M0 Stage)</CardTitle>
          <CardDescription className="max-w-lg">
            Requirements extraction requires an indexed repository and AST/semantic analysis pipeline. No placeholder or synthetic requirements are fabricated in M0.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-center text-xs text-slate-500 font-mono">
          Planned Output: Functional Rules • Non-Functional Constraints • Source Code Evidence Citations
        </CardContent>
      </Card>
    </div>
  );
}

