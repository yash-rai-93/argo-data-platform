"use client";

import { AlertTriangle, GitBranch } from "lucide-react";
import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchModelRegistry, type ModelVersion } from "@/lib/api";

interface ChartPoint {
  version: string;
  "Holdout ROC-AUC": number | null;
  "CV ROC-AUC": number | null;
  Precision: number | null;
  Recall: number | null;
}

function toChartPoints(versions: ModelVersion[]): ChartPoint[] {
  return versions
    .filter((v) => v.comparable)
    .map((v) => ({
      version: v.version.replace(/^v/, "").split("-")[0],
      "Holdout ROC-AUC": v.holdout_roc_auc,
      "CV ROC-AUC": v.cv_roc_auc,
      Precision: v.precision,
      Recall: v.recall,
    }));
}

function fmt(value: number | null): string {
  return value === null ? "—" : value.toFixed(4);
}

const SERIES = [
  { key: "Holdout ROC-AUC", color: "#22d3ee", width: 2.5 },
  { key: "CV ROC-AUC", color: "#6366f1", width: 1.5 },
  { key: "Precision", color: "#f59e0b", width: 1.5 },
  { key: "Recall", color: "#34d399", width: 1.5 },
] as const;

export default function ModelRegistry() {
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    fetchModelRegistry()
      .then(setVersions)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load registry"),
      );
  }, []);

  if (error) {
    return (
      <section className="glass-panel p-6">
        <h2 className="text-lg font-semibold">Model Registry</h2>
        <p className="mt-2 text-sm text-red-300">{error}</p>
      </section>
    );
  }

  const points: ChartPoint[] = toChartPoints(versions);
  const deployed: ModelVersion | undefined = versions
    .filter((v) => v.comparable)
    .at(-1);

  return (
    <section className="glass-panel p-6">
      <div className="mb-1 flex items-center gap-2">
        <GitBranch className="h-5 w-5 text-red-500" />
        <h2 className="text-lg font-semibold text-slate-100">
          Model Registry &amp; Metric Drift
        </h2>
      </div>
      <p className="mb-5 text-xs text-slate-500">
        Every training iteration, its measured metrics, and what changed.
        Appended by <span className="font-mono">ml/train_churn.py</span> on each
        run.
      </p>

      {points.length > 0 && (
        <div className="mb-6 h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={points}
              accessibilityLayer={false}
              margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.04)"
                vertical={false}
              />
              <XAxis
                dataKey="version"
                stroke="#64748b"
                tickLine={false}
                axisLine={false}
                fontSize={11}
              />
              <YAxis
                domain={[0.5, 1]}
                stroke="#64748b"
                tickLine={false}
                axisLine={false}
                width={40}
                fontSize={11}
              />
              <Tooltip
                contentStyle={{
                  background: "rgba(15,23,42,0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: "0.5rem",
                  fontSize: "0.75rem",
                }}
                labelStyle={{ color: "#94a3b8" }}
              />
              <Legend wrapperStyle={{ fontSize: "0.7rem" }} />
              {SERIES.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={s.width}
                  dot={{ r: 3, fill: s.color }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="space-y-3">
        {versions.map((v) => {
          const isDeployed: boolean = v.version === deployed?.version;
          return (
            <div
              key={v.version}
              className={`rounded-xl border p-4 transition-all ${
                isDeployed
                  ? "border-red-500/40 bg-red-500/5"
                  : v.comparable
                    ? "border-slate-800/60 bg-slate-950/30"
                    : "border-amber-500/30 bg-amber-500/5"
              }`}
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-semibold text-slate-100">
                  {v.version}
                </span>
                {isDeployed && (
                  <span className="rounded-full border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-red-400">
                    deployed
                  </span>
                )}
                {!v.comparable && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
                    <AlertTriangle className="h-3 w-3" />
                    not comparable
                  </span>
                )}
                <span className="ml-auto font-mono text-[11px] text-slate-500">
                  {v.n_features}f &middot; {v.n_rows.toLocaleString()} rows
                </span>
              </div>

              <div className="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  { label: "Holdout AUC", value: v.holdout_roc_auc, accent: true },
                  { label: "CV AUC", value: v.cv_roc_auc, accent: false },
                  { label: "Precision", value: v.precision, accent: false },
                  { label: "Recall", value: v.recall, accent: false },
                ].map((m) => (
                  <div key={m.label}>
                    <p className="text-[10px] uppercase tracking-widest text-slate-500">
                      {m.label}
                    </p>
                    <p
                      className={`font-mono text-lg font-bold ${
                        m.accent ? "text-red-400" : "text-slate-300"
                      }`}
                    >
                      {fmt(m.value)}
                    </p>
                  </div>
                ))}
              </div>

              <p className="text-xs leading-relaxed text-slate-400">
                {v.change_summary}
              </p>
              <p className="mt-2 border-t border-white/5 pt-2 font-mono text-[10px] text-slate-600">
                {v.dataset} &middot; {v.split_strategy} &middot; {v.best_params}
              </p>
            </div>
          );
        })}
      </div>

      <p className="mt-4 border-t border-white/10 pt-3 text-[11px] leading-relaxed text-slate-500">
        The synthetic baseline scored 0.97 on data generated by rules the model
        then rediscovered. Real GitHub events scored 0.66. That drop is not a
        regression &mdash; it is the first honest measurement in this table.
      </p>
    </section>
  );
}
