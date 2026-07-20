"use client";

import { CheckCircle2, Clock, Database, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchGovernanceHealth, type GovernanceHealth } from "@/lib/api";

function formatTimestamp(iso: string | undefined): string {
  if (!iso) return "unknown";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toUTCString();
}

function formatWindow(start: string, end: string): string {
  return `${start.slice(0, 10)} to ${end.slice(0, 10)}`;
}

export default function GovernancePanel() {
  const [health, setHealth] = useState<GovernanceHealth | null>(null);
  const [failed, setFailed] = useState<boolean>(false);

  useEffect(() => {
    fetchGovernanceHealth()
      .then(setHealth)
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <section className="glass-panel p-6">
        <h2 className="text-xl font-semibold">Data Governance</h2>
        <p className="mt-2 text-sm text-red-300">
          Governance endpoint unreachable. Is the API running?
        </p>
      </section>
    );
  }

  if (!health) {
    return <section className="glass-panel h-64 animate-pulse p-6" />;
  }

  if (!health.tests || !health.models || !health.source) {
    return (
      <section className="glass-panel p-6">
        <h2 className="text-xl font-semibold">Data Governance</h2>
        <p className="mt-2 text-sm text-slate-400">
          {health.detail ??
            "No dbt run ingested. Run etl/ingest_dbt_artifacts.py."}
        </p>
      </section>
    );
  }

  const allPassed: boolean = health.status === "pass";

  return (
    <section className="glass-panel p-6">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-cyan-400" />
          <h2 className="text-xl font-semibold">Data Governance</h2>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${
            allPassed
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-red-500/40 bg-red-500/10 text-red-300"
          }`}
        >
          {allPassed ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : (
            <XCircle className="h-3.5 w-3.5" />
          )}
          {health.tests_passed}/{health.tests_total} dbt tests passing
        </span>
      </div>
      <p className="mb-5 text-xs text-slate-500">
        Parsed from dbt&apos;s own run_results.json. Not hand-maintained, so it
        cannot drift from what the pipeline actually did.
      </p>

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[
          {
            label: "Last Build",
            value: formatTimestamp(health.run_at),
            icon: Clock,
          },
          {
            label: "Source Window",
            value: formatWindow(
              health.source.window_start,
              health.source.window_end,
            ),
            icon: Database,
          },
          {
            label: "Source Rows",
            value: health.source.row_count.toLocaleString(),
            icon: Database,
          },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="rounded-xl border border-slate-800/60 bg-slate-950/40 p-4"
            >
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </div>
              <p className="mt-1 font-mono text-sm text-slate-200">
                {item.value}
              </p>
            </div>
          );
        })}
      </div>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
        Schema Tests
      </h3>
      <div className="mb-6 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {health.tests.map((test) => {
          const passed: boolean = test.status === "pass";
          return (
            <div
              key={test.name}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
                passed
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-red-500/40 bg-red-500/10"
              }`}
            >
              {passed ? (
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
              ) : (
                <XCircle className="h-3.5 w-3.5 shrink-0 text-red-400" />
              )}
              <span className="truncate font-mono text-slate-300">
                {test.name}
              </span>
              {!passed && (
                <span className="ml-auto shrink-0 font-semibold text-red-300">
                  {test.failures} failed
                </span>
              )}
            </div>
          );
        })}
      </div>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
        Materialised Models
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left text-xs">
          <thead className="text-slate-500">
            <tr className="border-b border-white/10">
              <th className="pb-2 font-medium">Model</th>
              <th className="pb-2 font-medium">Type</th>
              <th className="pb-2 text-right font-medium">Rows</th>
              <th className="pb-2 text-right font-medium">Build</th>
              <th className="pb-2 text-right font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="font-mono text-slate-300">
            {health.models.map((model) => (
              <tr key={model.name} className="border-b border-white/5">
                <td className="py-2">{model.name}</td>
                <td className="py-2 text-slate-500">
                  {model.materialization ?? model.resource_type}
                </td>
                <td className="py-2 text-right">
                  {model.row_count < 0
                    ? "n/a"
                    : model.row_count.toLocaleString()}
                </td>
                <td className="py-2 text-right text-slate-400">
                  {model.execution_time.toFixed(3)}s
                </td>
                <td
                  className={`py-2 text-right ${
                    model.status === "success"
                      ? "text-emerald-400"
                      : "text-red-400"
                  }`}
                >
                  {model.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 border-t border-white/10 pt-3 text-[11px] text-slate-500">
        dbt {health.dbt_version} &middot; invocation{" "}
        {health.invocation_id?.slice(0, 8)} &middot; {health.elapsed_seconds}s
        total
      </p>
    </section>
  );
}
