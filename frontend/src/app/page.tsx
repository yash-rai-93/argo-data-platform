"use client";

import { motion } from "framer-motion";
import {
  Activity,
  Cpu,
  Database,
  Download,
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
import PipelineLineage from "@/components/PipelineLineage";
import RevenueChart from "@/components/RevenueChart";
import RiskTable from "@/components/RiskTable";
import Sparkline from "@/components/Sparkline";
import TelemetryLog from "@/components/TelemetryLog";
import {
  fetchContributorTrend,
  fetchContributorsSparkline,
  fetchExecutiveMetrics,
  fetchIntelligenceSummary,
  fetchRetentionSparkline,
  fetchThroughputSparkline,
  type ExecutiveMetrics,
  type TrendMetric,
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

const SETTINGS = [
  { label: "API Base URL", value: "http://127.0.0.1:8000/api/v1" },
  { label: "Inference Model", value: "nvidia/nemotron-3-ultra-550b-a55b" },
  { label: "Churn Decision Threshold", value: "0.50" },
  { label: "Warehouse Engine", value: "DuckDB (dbt marts)" },
  { label: "Data Mode", value: "GitHub Archive via BigQuery (real events)" },
];

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
  const [trendData, setTrendData] = useState<TrendMetric[]>([]);
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
    fetchContributorTrend().then(setTrendData);
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
      <section className="space-y-8">
        <div className="glass-panel flex flex-wrap items-center gap-x-8 gap-y-3 px-6 py-4 text-sm">
          <span className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
            </span>
            <span className="font-medium text-slate-300">
              System Health &amp; Data Ingestion Pipeline
            </span>
          </span>
          <span className="flex items-center gap-2 text-slate-400">
            <Activity className="h-4 w-4 text-emerald-400" />
            Pipeline: <span className="text-emerald-300">Operational</span>
          </span>
          <span className="flex items-center gap-2 text-slate-400">
            <TrendingUp className="h-4 w-4 text-cyan-400" />
            Ingestion:{" "}
            <span className="font-mono text-cyan-300">
              {ingest.toLocaleString()} events/sec
            </span>
          </span>
          <span className="flex items-center gap-2 text-slate-400">
            <Database className="h-4 w-4 text-indigo-400" />
            Warehouse Nodes: <span className="text-indigo-300">Active</span>
          </span>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-red-300">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="glass-panel h-36 animate-pulse" />
              ))
            : cards.map((c) => {
                const Icon = c.icon;
                return (
                  <motion.div
                    key={c.label}
                    whileHover={{ y: -5 }}
                    className="glass-panel p-6"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-300">
                        {c.label}
                      </span>
                      <Icon className="h-5 w-5 shrink-0 text-indigo-400" />
                    </div>
                    <p className="mt-4 font-mono text-3xl font-semibold">
                      {c.value}
                    </p>
                    <div className="mt-3">
                      <Sparkline data={c.spark} color={c.color} />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">{c.desc}</p>
                  </motion.div>
                );
              })}
        </div>

        <RevenueChart />

        <ArgoBriefing />

        <section className="glass-panel p-6">
          <div className="mb-3 flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-400" />
            <h2 className="text-lg font-semibold">AI Intelligence Summary</h2>
          </div>
          {loading ? (
            <div className="h-16 animate-pulse rounded bg-white/10" />
          ) : (
            <>
              <p className="leading-relaxed text-slate-300">
                {summary ||
                  "Summary unavailable (requires a configured API key)."}
              </p>
              {reasoning && (
                <p className="mt-3 border-t border-white/10 pt-3 text-xs leading-relaxed text-slate-500">
                  {reasoning}
                </p>
              )}
            </>
          )}
        </section>
      </section>
    );
  }

  function renderRetention() {
    return (
      <section className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold">Retention Command Queue</h2>
          <p className="text-sm text-slate-400">
            Contributors flagged by the churn model, ranked by predicted risk,
            with a live simulator for probing any behavioural vector.
          </p>
        </div>
        <RiskTable />
        <ChurnWidget />
      </section>
    );
  }

  function renderMlEngine() {
    return (
      <section className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold">ML Engine</h2>
          <p className="text-sm text-slate-400">
            Warehouse lineage, model attribution, and the live event stream
            feeding the XGBoost churn classifier.
          </p>
        </div>
        <PipelineLineage />
        <TelemetryLog />
      </section>
    );
  }

  function renderSettings() {
    return (
      <section className="space-y-6">
        <GovernancePanel />
        <div className="glass-panel p-6">
          <h2 className="mb-4 text-xl font-semibold">Platform Parameters</h2>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {SETTINGS.map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-slate-800/60 bg-slate-950/40 p-4"
              >
                <dt className="text-xs text-slate-500">{s.label}</dt>
                <dd className="mt-1 font-mono text-sm text-slate-200">
                  {s.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
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
      <aside className="z-50 hidden h-[calc(100vh-2rem)] w-64 shrink-0 sticky top-4 m-4 flex-col rounded-3xl border border-white/10 bg-white/5 p-4 shadow-[0_25px_50px_-12px_rgba(0,0,0,0.7)] backdrop-blur-2xl md:flex">
        <div className="mb-6 flex items-center gap-2 px-2">
          <Sparkles className="h-6 w-6 text-cyan-400" />
          <span className="text-lg font-bold">ARGO</span>
        </div>

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
                        ? "bg-gradient-to-r from-cyan-500/20 to-transparent border-l-2 border-cyan-400 text-cyan-300 shadow-[inset_4px_0_10px_rgba(6,182,212,0.1)]"
                        : "border-transparent text-slate-400 hover:bg-white/5 hover:text-slate-200"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className="text-xs font-bold uppercase tracking-widest">
                      {n.label}
                    </span>
                    {"badge" in n && (
                      <span className="ml-auto rounded-full bg-cyan-400/20 px-2 py-0.5 text-[10px] font-bold text-cyan-300">
                        {n.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        <div className="mt-auto flex items-center gap-3 border-t border-white/10 pt-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-cyan-400 text-sm font-bold text-white">
            A
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-200">
              Aarush Udbhav
            </p>
            <p className="truncate text-xs text-slate-500">Lead AI Engineer</p>
          </div>
        </div>
      </aside>

      <main className="flex-1 p-6 lg:p-8">
        <div className="mx-auto max-w-6xl">
          <header className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold">ARGO Executive Command Suite</h1>
              <p className="mt-1 max-w-3xl text-slate-400">
                A product- and decision-intelligence platform that turns raw
                customer events into governed revenue metrics, churn
                predictions, and AI-generated strategy, so leaders can see what
                is happening and decide what to do next.
              </p>
            </div>
            <button
              type="button"
              onClick={handleExport}
              disabled={isExporting}
              className={`inline-flex shrink-0 items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-400 px-4 py-2.5 text-sm font-semibold text-white shadow-[0_0_20px_rgba(99,102,241,0.45)] transition-all hover:from-indigo-500 hover:to-indigo-300 hover:shadow-[0_0_28px_rgba(99,102,241,0.6)] ${
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
              {isExporting ? "Generating PDF..." : "Export Board Report (PDF)"}
            </button>
          </header>

          <div id="argo-workspace">{renderWorkspace()}</div>
        </div>
      </main>
      </div>
    </>
  );
}
