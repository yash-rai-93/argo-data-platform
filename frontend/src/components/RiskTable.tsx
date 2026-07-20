"use client";

import { AlertTriangle, Send } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchRiskList, type CustomerRisk } from "@/lib/api";

interface Toast {
  title: string;
  description: string;
}

const OUTREACH_TOAST: Toast = {
  title: "Demo action -- no message sent.",
  description:
    "In production this would hand the contributor's feature vector and SHAP attribution to the LLM to draft a maintainer check-in. The integration is not wired up.",
};

export default function RiskTable() {
  const [rows, setRows] = useState<CustomerRisk[]>([]);
  const [error, setError] = useState<string>("");
  const [toast, setToast] = useState<Toast | null>(null);

  useEffect(() => {
    fetchRiskList()
      .then(setRows)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load risk data"),
      );
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(timer);
  }, [toast]);

  return (
    <section className="glass-panel p-6">
      <div className="mb-4 flex items-center gap-2">
        <AlertTriangle className="h-5 w-5 text-red-400" />
        <h2 className="text-lg font-semibold text-slate-100">
          High-Value Contributors at Risk
        </h2>
      </div>
      <p className="mb-4 -mt-2 text-xs text-slate-500">
        Top contributors by event volume, ranked by live XGBoost churn score.
      </p>

      {error ? (
        <p className="text-sm text-red-300">{error}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr className="border-b border-white/10">
                <th className="py-2 pr-4 font-medium">Contributor</th>
                <th className="py-2 pr-4 font-medium">Primary Repo</th>
                <th className="py-2 pr-4 font-medium">Tenure (Days)</th>
                <th className="py-2 pr-4 font-medium">Total Events</th>
                <th className="py-2 pr-4 font-medium">Last Seen</th>
                <th className="py-2 pr-4 font-medium">Risk</th>
                <th className="py-2 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.contributor}
                  className="group h-16 border-b border-slate-800/50 transition-colors hover:bg-slate-800/20"
                >
                  <td className="pr-4 align-middle font-mono text-xs text-slate-300">
                    <span className="flex items-center gap-2">
                      <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 opacity-0 shadow-[0_0_8px_rgba(34,211,238,0.9)] transition-opacity group-hover:opacity-100" />
                      {r.contributor}
                    </span>
                  </td>
                  <td className="pr-4 align-middle font-mono text-xs text-slate-400">
                    {r.primary_repo}
                  </td>
                  <td className="pr-4 align-middle text-slate-300">
                    {r.tenure_days}d
                  </td>
                  <td className="pr-4 align-middle text-slate-300">
                    {r.total_events.toLocaleString()}
                  </td>
                  <td className="pr-4 align-middle text-slate-400">
                    {r.days_since_last_event}d ago
                  </td>
                  <td className="pr-4 align-middle">
                    <span
                      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                        r.risk_score >= 0.5
                          ? "border-red-500/40 bg-red-500/10 text-red-300 shadow-[0_0_12px_rgba(239,68,68,0.4)]"
                          : r.risk_score >= 0.25
                            ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                            : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                      }`}
                    >
                      {(r.risk_score * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="align-middle opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => setToast(OUTREACH_TOAST)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-white/5 px-3 py-1.5 text-xs font-medium text-cyan-300 transition-colors hover:border-cyan-400/70 hover:bg-cyan-400/10 hover:shadow-[0_0_14px_rgba(34,211,238,0.4)]"
                    >
                      <Send className="h-3.5 w-3.5" />
                      Preview outreach draft (demo)
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && !error && (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-500">
                    No contributors scored. Build the warehouse and train the
                    model first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm rounded-xl border border-cyan-400/30 bg-slate-900/90 p-4 text-sm text-slate-200 shadow-[0_0_30px_rgba(34,211,238,0.35)] backdrop-blur-xl">
          <div className="flex items-start gap-2">
            <Send className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" />
            <div>
              <p className="font-semibold text-slate-100">{toast.title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-400">
                {toast.description}
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
