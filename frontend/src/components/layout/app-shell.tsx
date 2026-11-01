"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderGit2,
  FileCheck2,
  Network,
  Settings,
  Home,
  Menu,
  X,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  stage: string;
}

const navigation: NavItem[] = [
  { name: "Overview", href: "/", icon: Home, stage: "Wave 1 Live" },
  { name: "Intelligence Hub", href: "/dashboard", icon: LayoutDashboard, stage: "Wave 5 Live" },
  { name: "Repositories", href: "/repositories", icon: FolderGit2, stage: "Wave 1 Live" },
  { name: "Architecture", href: "/architecture", icon: Network, stage: "Wave 2 Live" },
  { name: "Requirements", href: "/requirements", icon: FileCheck2, stage: "Wave 3 Live" },
  { name: "Quality & Modernization", href: "/modernization", icon: ShieldCheck, stage: "Wave 4 Live" },
  { name: "Settings", href: "/settings", icon: Settings, stage: "Wave 1 Config" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50/70 text-slate-900 flex flex-col lg:flex-row">
      {/* Mobile Header */}
      <div className="lg:hidden flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 sticky top-0 z-30">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-slate-900 text-white flex items-center justify-center font-bold text-sm">
            LQ
          </div>
          <div>
            <span className="font-semibold tracking-tight text-slate-900">
              LegacyIQ
            </span>
            <span className="ml-2 text-xs text-slate-500 font-mono">M0</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="p-2 rounded-md text-slate-600 hover:bg-slate-100"
          aria-label="Toggle navigation menu"
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 border-r border-slate-200 bg-white flex flex-col justify-between transition-transform duration-200 ease-in-out lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div>
          {/* Brand Header */}
          <div className="h-16 px-6 border-b border-slate-200 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-lg bg-slate-900 text-white flex items-center justify-center font-bold text-sm shadow-sm">
                LQ
              </div>
              <div>
                <div className="font-semibold tracking-tight text-slate-900 leading-none">
                  LegacyIQ
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  Discovery &amp; Intelligence
                </div>
              </div>
            </Link>
            <Badge variant="outline" className="font-mono text-[10px] px-1.5 py-0">
              M0
            </Badge>
          </div>

          {/* Navigation Links */}
          <div className="px-3 py-4">
            <div className="px-3 mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Platform Navigation
            </div>
            <nav className="space-y-1">
              {navigation.map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname === item.href || pathname.startsWith(`${item.href}/`);

                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      "group flex items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    )}
                  >
                    <span className="flex items-center gap-3">
                      <Icon
                        className={cn(
                          "h-4 w-4 shrink-0",
                          isActive
                            ? "text-sky-400"
                            : "text-slate-400 group-hover:text-slate-700"
                        )}
                      />
                      {item.name}
                    </span>
                    <span
                      className={cn(
                        "text-[10px] font-mono rounded px-1.5 py-0.5",
                        isActive
                          ? "bg-slate-800 text-slate-300"
                          : "bg-slate-100 text-slate-500"
                      )}
                    >
                      {item.stage}
                    </span>
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>

        {/* Footer Info */}
        <div className="p-4 border-t border-slate-200 bg-slate-50/60 space-y-2.5">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-700">
            <ShieldCheck className="h-4 w-4 text-emerald-600 shrink-0" />
            <span>Local-First Static Mode</span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Zero-execution static analysis foundation. Connected to local{" "}
            <span className="font-mono text-slate-700">pgvector</span>,{" "}
            <span className="font-mono text-slate-700">Redis</span> &amp;{" "}
            <span className="font-mono text-slate-700">Ollama</span>.
          </p>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Utility Bar */}
        <header className="h-16 border-b border-slate-200 bg-white px-6 hidden lg:flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Badge variant="secondary" className="font-mono text-xs">
              Milestone M0 — Project Foundation
            </Badge>
            <span className="text-xs text-slate-500">
              No synthetic or fabricated repository metrics are displayed.
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-600 font-mono">
            <Terminal className="h-3.5 w-3.5 text-slate-400" />
            <span>API: {process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}</span>
          </div>
        </header>

        {/* Page Container */}
        <main className="flex-1 p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

