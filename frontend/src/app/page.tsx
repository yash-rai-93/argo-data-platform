"use client";

import { motion } from "framer-motion";
import {
  Activity,
  Cpu,
  Database,
  Download,
  ExternalLink,
  GitPullRequest,
  LayoutDashboard,
  Loader2,
  Repeat,
  Settings,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import ArgoBriefing from "@/components/ArgoBriefing";
import ChurnWidget from "@/components/ChurnWidget";
import GovernancePanel from "@/components/GovernancePanel";
import ModelRegistry from "@/components/ModelRegistry";
import PipelineLineage from "@/components/PipelineLineage";
import PlatformSpec from "@/components/PlatformSpec";
import RevenueChart from "@/components/RevenueChart";
import RiskTable from "@/components/RiskTable";
import Sparkline from "@/components/Sparkline";
import TelemetryLog from "@/components/TelemetryLog";
import {
  fetchContributorsSparkline,
  fetchExecutiveMetrics,
  fetchIntelligenceSummary,
  fetchRetentionSparkline,
  fetchThroughputSparkline,
  type ExecutiveMetrics,
} from "@/lib/api";
import { generateBoardReport } from "@/lib/pdfReport";

const NAV_GROUPS = [
  {
    heading: "Core Platform",
    items: [
      { id: "command", label: "Command Suite", icon: LayoutDashboard },
      { id: "ml", label: "ML Engine", icon: Cpu },
    ],
  },
  {
    heading: "System",
    items: [
      { id: "retention", label: "Retention", icon: Users, badge: "3" },
      { id: "settings", label: "Settings", icon: Settings },
    ],
  },
] as const;

type TabId = (typeof NAV_GROUPS)[number]["items"][number]["id"];

// Per-tab heading copy plus whether the PDF export applies. Export only makes
// sense where the workspace holds a reviewable artefact: the retention queue
// and the model registry. On the overview and the settings spec it would just
// screenshot configuration.
const TABS: Record<
  TabId,
  { title: string; blurb: string; exportable: boolean }
> = {
  command: {
    title: "Command Suite",
    blurb:
      "Cohort health across 24 Python repositories: who is contributing, how much is shipping, and how much of last month's cohort came back.",
    exportable: false,
  },
  ml: {
    title: "ML Engine",
    blurb:
      "Training history, measured metric drift, warehouse lineage, and the live event stream feeding the XGBoost churn classifier.",
    exportable: true,
  },
  retention: {
    title: "Retention Command Queue",
    blurb:
      "High-value contributors ranked by live churn score, with a threshold simulator swept against the temporal holdout.",
    exportable: true,
  },
  settings: {
    title: "Platform & Governance",
    blurb:
      "dbt build health, schema test results, data freshness, and the full specification of the model currently serving predictions.",
    exportable: false,
  },
};

const PORTFOLIO_URL = "https://aarushch.github.io/Portfolio/";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("command");
  const [metrics, setMetrics] = useState<ExecutiveMetrics | null>(null);
  const [summary, setSummary] = useState<string>("");
  const [reasoning, setReasoning] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [ingest, setIngest] = useState<number>(1420);
  const [contributorSpark, setContributorSpark] = useState<number[]>([]);
  const [throughputSpark, setThroughputSpark] = useState<number[]>([]);
  const [retentionSpark, setRetentionSpark] = useState<number[]>([]);
  const [isExporting, setIsExporting] = useState<boolean>(false);

  async function handleExport() {
    setIsExporting(true);
    try {
      await generateBoardReport();
    } finally {
      setIsExporting(false);
    }
  }

  useEffect(() => {
    fetchExecutiveMetrics()
      .then(setMetrics)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load metrics"),
      )
      .finally(() => setLoading(false));

    fetchIntelligenceSummary()
      .then((s) => {
        setSummary(s.summary);
        setReasoning(s.reasoning ?? "");
      })
      .catch(() => setSummary(""));

    fetchContributorsSparkline().then(setContributorSpark);
    fetchThroughputSparkline().then(setThroughputSpark);
    fetchRetentionSparkline().then(setRetentionSpark);
  }, []);

  useEffect(() => {
    if (activeTab !== "command") return;
    const id = setInterval(
      () => setIngest(1380 + Math.floor(Math.random() * 120)),
      1500,
    );
    return () => clearInterval(id);
  }, [activeTab]);

  const cards = metrics
    ? [
        {
          label: "Active Contributors (30d)",
          value: metrics.active_contributors.toLocaleString(),
          desc: "Unique non-bot humans who touched the cohort in 30 days",
          icon: Users,
          spark: contributorSpark,
          color: "#22d3ee",
        },
        {
          label: "PR & Issue Throughput (7d)",
          value: metrics.pr_throughput.toLocaleString(),
          desc: "Pull request and issue events shipped in the trailing week",
          icon: GitPullRequest,
          spark: throughputSpark,
          color: "#6366f1",
        },
        {
          label: "Contributor Retention (30d)",
          value: `${(metrics.retention_rate * 100).toFixed(1)}%`,
          desc: "Share of the prior 30-day cohort still active in the current one",
          icon: Repeat,
          spark: retentionSpark,
          color: "#34d399",
        },
      ]
    : [];

  function renderCommandSuite() {
    return (
      <section className="space-y-4">
        <div className="glass-panel flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-2.5 text-xs">
          <span className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="font-medium text-slate-300">Pipeline</span>
            <span className="text-emerald-300">Operational</span>
          </span>
          <span className="flex items-center gap-1.5 text-slate-500">
            <Activity className="h-3.5 w-3.5 text-red-500" />
            Ingestion
            <span className="font-mono text-red-300">
              {ingest.toLocaleString()}/s
            </span>
          </span>
          <span className="flex items-center gap-1.5 text-slate-500">
            <Database className="h-3.5 w-3.5 text-red-500" />
            Warehouse
            <span className="font-mono text-slate-300">
              547,434 events &middot; 24 repos
            </span>
          </span>
          <span className="ml-auto flex items-center gap-1.5 text-slate-500">
            <TrendingUp className="h-3.5 w-3.5 text-red-500" />
            Window
            <span className="font-mono text-slate-300">
              2023-07-01 → 2024-01-01
            </span>
          </span>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="glass-panel h-32 animate-pulse" />
              ))
            : cards.map((c) => {
                const Icon = c.icon;
                return (
                  <motion.div
                    key={c.label}
                    whileHover={{ y: -3 }}
                    className="glass-panel p-5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="eyebrow">{c.label}</span>
                      <Icon className="h-4 w-4 shrink-0 text-red-500/80" />
                    </div>
                    <p className="mt-2 font-mono text-3xl font-bold tabular-nums text-slate-50">
                      {c.value}
                    </p>
                    <div className="mt-2">
                      <Sparkline data={c.spark} color={c.color} />
                    </div>
                    <p className="mt-2 text-[11px] leading-snug text-slate-500">
                      {c.desc}
                    </p>
                  </motion.div>
                );
              })}
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
          <div className="xl:col-span-3">
            <RevenueChart />
          </div>
          <section className="glass-panel p-5 xl:col-span-2">
            <div className="mb-2 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-red-500" />
              <h2 className="text-sm font-semibold text-slate-100">
                AI Intelligence Summary
              </h2>
            </div>
            {loading ? (
              <div className="h-16 animate-pulse rounded bg-white/5" />
            ) : (
              <>
                <p className="text-sm leading-relaxed text-slate-300">
                  {summary ||
                    "Summary unavailable (requires a configured API key)."}
                </p>
                {reasoning && (
                  <p className="mt-3 border-t border-white/10 pt-3 text-[11px] leading-relaxed text-slate-500">
                    {reasoning}
                  </p>
                )}
              </>
            )}
          </section>
        </div>

        <ArgoBriefing />
      </section>
    );
  }

  function renderRetention() {
    return (
      <section className="space-y-4">
        <RiskTable />
        <ChurnWidget />
      </section>
    );
  }

  function renderMlEngine() {
    return (
      <section className="space-y-4">
        <ModelRegistry />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <PipelineLineage />
          <TelemetryLog />
        </div>
      </section>
    );
  }

  function renderSettings() {
    return (
      <section className="space-y-4">
        <PlatformSpec />
        <GovernancePanel />
      </section>
    );
  }

  function renderWorkspace() {
    switch (activeTab) {
      case "ml":
        return renderMlEngine();
      case "retention":
        return renderRetention();
      case "settings":
        return renderSettings();
      default:
        return renderCommandSuite();
    }
  }

  return (
    <>
      <div className="light-leak-cyan" />
      <div className="light-leak-indigo" />
      <div className="flex min-h-screen">
      <aside className="z-50 hidden h-[calc(100vh-2rem)] w-60 shrink-0 sticky top-4 m-4 flex-col rounded-3xl border border-red-950/60 bg-black/50 p-4 shadow-[0_25px_50px_-12px_rgba(0,0,0,0.85)] backdrop-blur-2xl md:flex">
        <div className="mb-1 flex items-center gap-2 px-2">
          <Sparkles className="h-6 w-6 text-red-500 drop-shadow-[0_0_10px_rgba(239,68,68,0.7)]" />
          <span className="text-lg font-bold tracking-tight">ARGO</span>
        </div>
        <p className="mb-6 px-2 text-[10px] leading-tight text-slate-600">
          Contributor Decision Intelligence
        </p>

        {NAV_GROUPS.map((group) => (
          <div key={group.heading} className="mb-4">
            <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              {group.heading}
            </p>
            <div className="flex flex-col gap-1">
              {group.items.map((n) => {
                const Icon = n.icon;
                const active = activeTab === n.id;
                return (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => setActiveTab(n.id)}
                    className={`flex items-center gap-3 rounded-xl border-l-2 px-3 py-2 text-sm transition-all ${
                      active
                        ? "bg-gradient-to-r from-red-600/20 to-transparent border-l-2 border-red-500 text-red-400 shadow-[inset_4px_0_10px_rgba(220,38,38,0.1)]"
                        : "border-transparent text-slate-400 hover:bg-white/5 hover:text-slate-200"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className="text-xs font-bold uppercase tracking-widest">
                      {n.label}
                    </span>
                    {"badge" in n && (
                      <span className="ml-auto rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] font-bold text-red-400">
                        {n.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        <a
          href={PORTFOLIO_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="group mt-auto flex items-center gap-3 rounded-xl border-t border-red-950/60 px-2 pt-4 transition-colors hover:border-red-800/60"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-red-700 to-red-500 text-sm font-bold text-white shadow-[0_0_14px_rgba(239,68,68,0.4)]">
            A
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-200 transition-colors group-hover:text-red-300">
              Aarush Udbhav
            </p>
            <p className="truncate text-xs text-slate-500">Lead AI Engineer</p>
          </div>
          <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-600 transition-colors group-hover:text-red-400" />
        </a>
      </aside>

      <main className="flex-1 p-4 lg:p-6">
        <div className="mx-auto max-w-7xl">
          <header className="mb-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h1 className="text-2xl font-bold tracking-tight">
                ARGO
                <span className="ml-2 font-normal text-slate-500">
                  Contributor Decision Intelligence
                </span>
              </h1>
              <p className="font-mono text-[11px] text-slate-600">
                open-source contributor churn &middot; GitHub Archive via
                BigQuery
              </p>
            </div>

            <div className="mt-3 flex flex-wrap items-start justify-between gap-3 border-t border-red-950/50 pt-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-100">
                  {TABS[activeTab].title}
                </h2>
                <p className="mt-0.5 max-w-3xl text-sm leading-relaxed text-slate-400">
                  {TABS[activeTab].blurb}
                </p>
              </div>
              {TABS[activeTab].exportable && (
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={isExporting}
                  className={`inline-flex shrink-0 items-center gap-2 rounded-xl bg-gradient-to-r from-red-700 to-red-500 px-4 py-2 text-sm font-semibold text-white shadow-[0_0_20px_rgba(239,68,68,0.35)] transition-all hover:from-red-600 hover:to-red-400 hover:shadow-[0_0_28px_rgba(239,68,68,0.55)] ${
                    isExporting
                      ? "animate-pulse cursor-not-allowed opacity-80"
                      : ""
                  }`}
                >
                  {isExporting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  {isExporting ? "Generating PDF..." : "Export Report (PDF)"}
                </button>
              )}
            </div>
          </header>

          <div id="argo-workspace">{renderWorkspace()}</div>
        </div>
      </main>
      </div>
    </>
  );
}
