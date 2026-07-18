"use client";

import { AlertTriangle, Gauge, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  predictChurn,
  type ChurnFeatures,
  type ChurnPrediction,
} from "@/lib/api";

const FIELDS = [
  { key: "total_sessions", label: "Total Sessions" },
  { key: "avg_session_duration", label: "Avg Session Duration (s)" },
  { key: "account_age_days", label: "Account Age (days)" },
] as const;

type FieldKey = (typeof FIELDS)[number]["key"];

const SCENARIOS: { name: string; features: ChurnFeatures }[] = [
  {
    name: "Slipping Enterprise Customer",
    features: { total_sessions: 14, avg_session_duration: 95, account_age_days: 240 },
  },
  {
    name: "Healthy Power User",
    features: { total_sessions: 92, avg_session_duration: 330, account_age_days: 65 },
  },
  {
    name: "Inactive Trial User",
    features: { total_sessions: 1, avg_session_duration: 25, account_age_days: 18 },
  },
];

export default function ChurnWidget() {
  const [values, setValues] = useState<Record<FieldKey, string>>({
    total_sessions: "",
    avg_session_duration: "",
    account_age_days: "",
  });
  const [result, setResult] = useState<ChurnPrediction | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  const [sensitivity, setSensitivity] = useState<number>(50);
  const [learningRate, setLearningRate] = useState<number>(50);
  const [volatility, setVolatility] = useState<number>(30);

  const sliders = [
    { label: "Risk Sensitivity Threshold", value: sensitivity, set: setSensitivity },
    { label: "Model Learning Rate Simulation", value: learningRate, set: setLearningRate },
    { label: "Macro-Economic Volatility Buffer", value: volatility, set: setVolatility },
  ];

  const confidence = Math.round(
    Math.max(
      0,
      Math.min(100, 60 + sensitivity * 0.2 + learningRate * 0.2 - volatility * 0.3),
    ),
  );
  const confidenceColor =
    confidence >= 70
      ? "text-emerald-400"
      : confidence >= 45
        ? "text-cyan-400"
        : "text-red-400";

  async function runPrediction(features: ChurnFeatures) {
    setError("");
    setResult(null);
    setLoading(true);
    try {
      setResult(await predictChurn(features));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

  function loadScenario(features: ChurnFeatures) {
    setValues({
      total_sessions: String(features.total_sessions),
      avg_session_duration: String(features.avg_session_duration),
      account_age_days: String(features.account_age_days),
    });
    runPrediction(features);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    runPrediction({
      total_sessions: Number(values.total_sessions),
      avg_session_duration: Number(values.avg_session_duration),
      account_age_days: Number(values.account_age_days),
    });
  }

  const highRisk = result ? result.probability >= 0.5 : false;

  return (
    <section className="glass-panel p-6 transition-all focus-within:ring-1 focus-within:ring-cyan-400/40 focus-within:shadow-[0_0_30px_rgba(34,211,238,0.25)]">
      <div className="mb-4 flex items-center gap-2">
        <Gauge className="h-5 w-5 text-cyan-400" />
        <h2 className="text-lg font-semibold text-slate-100">
          Advanced Simulation Dashboard
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-4 flex flex-wrap gap-2">
            {SCENARIOS.map((s) => (
              <button
                key={s.name}
                type="button"
                onClick={() => loadScenario(s.features)}
                className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 transition-all hover:border-cyan-400/50 hover:text-cyan-300"
              >
                {s.name}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {FIELDS.map((f) => (
              <div key={f.key} className="relative">
                <input
                  id={f.key}
                  type="number"
                  required
                  placeholder=" "
                  value={values[f.key]}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [f.key]: e.target.value }))
                  }
                  className="peer w-full rounded-xl border border-white/10 bg-slate-900/40 px-4 pb-2 pt-5 text-white opacity-70 outline-none transition-all focus:border-cyan-400/70 focus:opacity-100 focus:ring-2 focus:ring-cyan-400/40"
                />
                <label
                  htmlFor={f.key}
                  className="pointer-events-none absolute left-4 top-4 text-sm text-slate-500 transition-all peer-focus:top-1.5 peer-focus:text-xs peer-focus:text-cyan-300 peer-[:not(:placeholder-shown)]:top-1.5 peer-[:not(:placeholder-shown)]:text-xs peer-[:not(:placeholder-shown)]:text-slate-400"
                >
                  {f.label}
                </label>
              </div>
            ))}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-indigo-500 to-cyan-400 text-white font-bold py-3 rounded-xl shadow-[0_0_20px_rgba(34,211,238,0.4)] hover:opacity-90 disabled:opacity-50 transition-all"
            >
              {loading ? "Scoring..." : "Predict Churn"}
            </button>
          </form>

          {error && (
            <div className="mt-4 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
              {error}
            </div>
          )}

          {result && (
            <div
              className={`mt-4 flex items-center justify-between rounded-xl border p-4 ${
                highRisk
                  ? "border-red-500/50 bg-red-500/10 shadow-[0_0_25px_rgba(239,68,68,0.55)]"
                  : "border-emerald-500/50 bg-emerald-500/10 shadow-[0_0_25px_rgba(16,185,129,0.55)]"
              }`}
            >
              <div className="flex items-center gap-2">
                {highRisk ? (
                  <AlertTriangle className="h-5 w-5 text-red-400 drop-shadow-[0_0_8px_rgba(239,68,68,0.9)]" />
                ) : (
                  <ShieldCheck className="h-5 w-5 text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.9)]" />
                )}
                <span
                  className={
                    highRisk
                      ? "text-red-300 drop-shadow-[0_0_8px_rgba(239,68,68,0.7)]"
                      : "text-emerald-300 drop-shadow-[0_0_8px_rgba(16,185,129,0.7)]"
                  }
                >
                  {highRisk ? "High risk" : "Low risk"}
                </span>
              </div>
              <span
                className={`text-2xl font-bold ${
                  highRisk
                    ? "text-red-400 drop-shadow-[0_0_12px_rgba(239,68,68,0.9)]"
                    : "text-emerald-400 drop-shadow-[0_0_12px_rgba(16,185,129,0.9)]"
                }`}
              >
                {(result.probability * 100).toFixed(1)}%
              </span>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-800/60 bg-slate-950/30 p-5">
          <div className="mb-4 flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-200">
              Model Simulation Tuner
            </h3>
          </div>

          <div className="space-y-5">
            {sliders.map((s) => (
              <div key={s.label}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-slate-400">{s.label}</span>
                  <span className="font-mono text-cyan-300">{s.value}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={s.value}
                  onChange={(e) => s.set(Number(e.target.value))}
                  className="w-full accent-cyan-400"
                />
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-xl border border-cyan-400/20 bg-slate-950/50 p-4 text-center">
            <p className="text-xs uppercase tracking-widest text-slate-500">
              Model Confidence Score
            </p>
            <p
              className={`mt-1 font-mono text-4xl font-bold transition-all ${confidenceColor} drop-shadow-[0_0_14px_rgba(34,211,238,0.4)]`}
            >
              {confidence}%
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
