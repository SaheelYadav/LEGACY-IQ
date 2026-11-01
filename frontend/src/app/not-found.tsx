import Link from "next/link";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function NotFound() {
  return (
    <div className="flex items-center justify-center py-16">
      <Card className="max-w-md w-full text-center">
        <CardHeader className="items-center">
          <div className="h-10 w-10 rounded-full bg-slate-100 flex items-center justify-center mb-2">
            <Compass className="h-5 w-5 text-slate-700" />
          </div>
          <CardTitle>Route Not Found (404)</CardTitle>
          <CardDescription>
            The requested LegacyIQ workspace route does not exist.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/">
            <Button variant="default" size="sm">
              Return to Foundation Overview
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

