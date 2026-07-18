"use client";

import { motion } from "framer-motion";
import {
  Activity,
  Cpu,
  Database,
  DollarSign,
  LayoutDashboard,
  Settings,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import ChurnWidget from "@/components/ChurnWidget";
import RevenueChart from "@/components/RevenueChart";
import RiskTable from "@/components/RiskTable";
import Sparkline from "@/components/Sparkline";
import {
  fetchExecutiveMetrics,
  fetchIntelligenceSummary,
  type ExecutiveMetrics,
} from "@/lib/api";

const NAV = [
  { label: "Command Suite", icon: LayoutDashboard, active: true },
  { label: "ML Engine", icon: Cpu, active: false },
  { label: "Retention", icon: Users, active: false },
  { label: "Settings", icon: Settings, active: false },
];

export default function Home() {
  const [metrics, setMetrics] = useState<ExecutiveMetrics | null>(null);
  const [summary, setSummary] = useState<string>("");
  const [reasoning, setReasoning] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [ingest, setIngest] = useState<number>(1420);

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
  }, []);

  useEffect(() => {
    const id = setInterval(
      () => setIngest(1380 + Math.floor(Math.random() * 120)),
      1500,
    );
    return () => clearInterval(id);
  }, []);

  const cards = metrics
    ? [
        {
          label: "Monthly Revenue (MRR)",
          value: `$${metrics.mrr.toLocaleString()}`,
          desc: "Predictable recurring income stream",
          icon: DollarSign,
          spark: [420, 520, 610, 680, 740, 880],
          color: "#22d3ee",
        },
        {
          label: "Annualized Growth Run-rate (ARR)",
          value: `$${metrics.arr.toLocaleString()}`,
          desc: "Projected yearly revenue at the current run-rate",
          icon: TrendingUp,
          spark: [5040, 6240, 7320, 8160, 8880, 10560],
          color: "#6366f1",
        },
        {
          label: "Daily Active Customers (DAU)",
          value: metrics.dau.toLocaleString(),
          desc: "Unique customers engaging with the product each day",
          icon: Users,
          spark: [3, 5, 4, 6, 5, 7],
          color: "#34d399",
        },
      ]
    : [];

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-1 border-r border-white/10 bg-white/5 p-4 backdrop-blur-xl md:flex">
        <div className="mb-6 flex items-center gap-2 px-2">
          <Sparkles className="h-6 w-6 text-cyan-400" />
          <span className="text-lg font-bold">ARGO</span>
        </div>
        {NAV.map((n) => {
          const Icon = n.icon;
          return (
            <button
              key={n.label}
              type="button"
              className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-all ${
                n.active
                  ? "bg-white/10 text-white shadow-[0_0_14px_rgba(34,211,238,0.25)]"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
              }`}
            >
              <Icon className="h-4 w-4" />
              {n.label}
            </button>
          );
        })}
      </aside>

      <main className="flex-1 p-6 lg:p-8">
        <div className="mx-auto max-w-6xl">
          <header className="mb-6">
            <h1 className="text-3xl font-bold">ARGO Executive Command Suite</h1>
            <p className="mt-1 max-w-3xl text-slate-400">
              A product- and decision-intelligence platform that turns raw
              customer events into governed revenue metrics, churn predictions,
              and AI-generated strategy, so leaders can see what is happening and
              decide what to do next.
            </p>
          </header>

          <div className="glass-panel mb-8 flex flex-wrap items-center gap-x-8 gap-y-3 px-6 py-4 text-sm">
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
            <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-red-300">
              {error}
            </div>
          )}

          <section className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-3">
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
                      <p className="mt-4 text-3xl font-semibold">{c.value}</p>
                      <div className="mt-3">
                        <Sparkline data={c.spark} color={c.color} />
                      </div>
                      <p className="mt-2 text-xs text-slate-500">{c.desc}</p>
                    </motion.div>
                  );
                })}
          </section>

          <div className="mb-8">
            <RevenueChart />
          </div>

          <section className="glass-panel mb-8 p-6">
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

          <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <RiskTable />
            <ChurnWidget />
          </section>
        </div>
      </main>
    </div>
  );
}
