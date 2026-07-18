"use client";

import { DollarSign, Sparkles, TrendingUp, Users } from "lucide-react";
import { useEffect, useState } from "react";

import ChurnWidget from "@/components/ChurnWidget";
import {
  fetchExecutiveMetrics,
  fetchIntelligenceSummary,
  type ExecutiveMetrics,
} from "@/lib/api";

export default function Home() {
  const [metrics, setMetrics] = useState<ExecutiveMetrics | null>(null);
  const [summary, setSummary] = useState<string>("");
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
      .then((s) => setSummary(s.summary))
      .catch(() => setSummary(""));
  }, []);

  const cards = metrics
    ? [
        {
          label: "MRR",
          value: `$${metrics.mrr.toLocaleString()}`,
          icon: DollarSign,
        },
        {
          label: "ARR",
          value: `$${metrics.arr.toLocaleString()}`,
          icon: TrendingUp,
        },
        { label: "DAU", value: metrics.dau.toLocaleString(), icon: Users },
      ]
    : [];

  return (
    <main className="min-h-screen bg-slate-950 p-8 text-slate-100">
      <header className="mb-8">
        <h1 className="text-3xl font-bold">ARGO Command Center</h1>
        <p className="text-slate-400">Product &amp; decision intelligence</p>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-red-300">
          {error}
        </div>
      )}

      <section className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {loading
          ? Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-32 animate-pulse rounded-xl bg-slate-900"
              />
            ))
          : cards.map((c) => {
              const Icon = c.icon;
              return (
                <div
                  key={c.label}
                  className="rounded-xl border border-slate-800 bg-slate-900 p-6"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">{c.label}</span>
                    <Icon className="h-5 w-5 text-indigo-400" />
                  </div>
                  <p className="mt-4 text-3xl font-semibold">{c.value}</p>
                </div>
              );
            })}
      </section>

      <section className="mt-8 rounded-xl border border-slate-800 bg-slate-900 p-6">
        <div className="mb-3 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-indigo-400" />
          <h2 className="text-lg font-semibold">AI Intelligence Summary</h2>
        </div>
        {loading ? (
          <div className="h-16 animate-pulse rounded bg-slate-800" />
        ) : (
          <p className="leading-relaxed text-slate-300">
            {summary || "Summary unavailable (requires a configured API key)."}
          </p>
        )}
      </section>

      <section className="mt-8">
        <ChurnWidget />
      </section>
    </main>
  );
}
