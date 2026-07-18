"use client";

import { motion } from "framer-motion";
import { DollarSign, Sparkles, TrendingUp, Users } from "lucide-react";
import { useEffect, useState } from "react";

import ChurnWidget from "@/components/ChurnWidget";
import RevenueChart from "@/components/RevenueChart";
import RiskTable from "@/components/RiskTable";
import {
  fetchExecutiveMetrics,
  fetchIntelligenceSummary,
  type ExecutiveMetrics,
} from "@/lib/api";

export default function Home() {
  const [metrics, setMetrics] = useState<ExecutiveMetrics | null>(null);
  const [summary, setSummary] = useState<string>("");
  const [reasoning, setReasoning] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

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

  const cards = metrics
    ? [
        {
          label: "Monthly Revenue (MRR)",
          value: `$${metrics.mrr.toLocaleString()}`,
          desc: "Predictable recurring income stream",
          icon: DollarSign,
        },
        {
          label: "Annualized Growth Run-rate (ARR)",
          value: `$${metrics.arr.toLocaleString()}`,
          desc: "Projected yearly revenue at the current run-rate",
          icon: TrendingUp,
        },
        {
          label: "Daily Active Customers (DAU)",
          value: metrics.dau.toLocaleString(),
          desc: "Unique customers engaging with the product each day",
          icon: Users,
        },
      ]
    : [];

  return (
    <main className="mx-auto max-w-7xl p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold">ARGO Executive Command Suite</h1>
        <p className="mt-1 max-w-3xl text-slate-400">
          A product- and decision-intelligence platform that turns raw customer
          events into governed revenue metrics, churn predictions, and
          AI-generated strategy, so leaders can see what is happening and decide
          what to do next.
        </p>
      </header>

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
              {summary || "Summary unavailable (requires a configured API key)."}
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
    </main>
  );
}
