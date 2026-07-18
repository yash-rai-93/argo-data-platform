"use client";

import { AlertTriangle, Gauge, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";

import { predictChurn, type ChurnPrediction } from "@/lib/api";

const FIELDS = [
  { key: "total_sessions", label: "Total Sessions" },
  { key: "avg_session_duration", label: "Avg Session Duration (s)" },
  { key: "account_age_days", label: "Account Age (days)" },
] as const;

type FieldKey = (typeof FIELDS)[number]["key"];

export default function ChurnWidget() {
  const [values, setValues] = useState<Record<FieldKey, string>>({
    total_sessions: "",
    avg_session_duration: "",
    account_age_days: "",
  });
  const [result, setResult] = useState<ChurnPrediction | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const prediction = await predictChurn({
        total_sessions: Number(values.total_sessions),
        avg_session_duration: Number(values.avg_session_duration),
        account_age_days: Number(values.account_age_days),
      });
      setResult(prediction);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

  const highRisk = result ? result.probability >= 0.5 : false;

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-4 flex items-center gap-2">
        <Gauge className="h-5 w-5 text-indigo-400" />
        <h2 className="text-lg font-semibold text-slate-100">
          Churn Risk Predictor
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {FIELDS.map((f) => (
          <div key={f.key} className="flex flex-col gap-1">
            <label htmlFor={f.key} className="text-sm text-slate-400">
              {f.label}
            </label>
            <input
              id={f.key}
              type="number"
              required
              value={values[f.key]}
              onChange={(e) =>
                setValues((v) => ({ ...v, [f.key]: e.target.value }))
              }
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-indigo-400"
            />
          </div>
        ))}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-indigo-500 px-4 py-2 font-medium text-white transition-colors hover:bg-indigo-400 disabled:opacity-50"
        >
          {loading ? "Scoring..." : "Predict Churn"}
        </button>
      </form>

      {error && (
        <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {result && (
        <div
          className={`mt-4 flex items-center justify-between rounded-lg border p-4 ${
            highRisk
              ? "border-red-500/40 bg-red-500/10"
              : "border-emerald-500/40 bg-emerald-500/10"
          }`}
        >
          <div className="flex items-center gap-2">
            {highRisk ? (
              <AlertTriangle className="h-5 w-5 text-red-400" />
            ) : (
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
            )}
            <span className={highRisk ? "text-red-300" : "text-emerald-300"}>
              {highRisk ? "High risk" : "Low risk"}
            </span>
          </div>
          <span className="text-2xl font-semibold text-slate-100">
            {(result.probability * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </section>
  );
}
