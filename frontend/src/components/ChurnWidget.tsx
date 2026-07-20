"use client";

import { AlertTriangle, Gauge, ShieldCheck, Sigma, SlidersHorizontal } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import ShapExplanation from "@/components/ShapExplanation";
import {
  fetchThresholdHoldout,
  predictChurn,
  type ChurnFeatures,
  type ChurnPrediction,
  type ThresholdHoldout,
} from "@/lib/api";

interface ConfusionMatrix {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  precision: number;
  recall: number;
  accuracy: number;
  f1: number;
}

const EMPTY_MATRIX: ConfusionMatrix = {
  tp: 0,
  fp: 0,
  tn: 0,
  fn: 0,
  precision: 0,
  recall: 0,
  accuracy: 0,
  f1: 0,
};

// Sweeps the cached holdout at a given cutoff. O(n) over ~600 rows, so this is
// cheap enough to run on every slider frame with no debounce.
function computeMatrix(
  holdout: ThresholdHoldout | null,
  threshold: number,
): ConfusionMatrix {
  if (!holdout || holdout.n === 0) return EMPTY_MATRIX;

  let tp = 0;
  let fp = 0;
  let tn = 0;
  let fn = 0;
  for (let i = 0; i < holdout.n; i += 1) {
    const predicted: boolean = holdout.y_prob[i] >= threshold;
    const actual: boolean = holdout.y_true[i] === 1;
    if (predicted && actual) tp += 1;
    else if (predicted && !actual) fp += 1;
    else if (!predicted && actual) fn += 1;
    else tn += 1;
  }

  const precision: number = tp + fp === 0 ? 0 : tp / (tp + fp);
  const recall: number = tp + fn === 0 ? 0 : tp / (tp + fn);
  return {
    tp,
    fp,
    tn,
    fn,
    precision,
    recall,
    accuracy: (tp + tn) / holdout.n,
    f1:
      precision + recall === 0
        ? 0
        : (2 * precision * recall) / (precision + recall),
  };
}

type FieldKey = keyof ChurnFeatures;

interface Field {
  key: FieldKey;
  label: string;
  step: string;
  min: string;
}

interface Scenario {
  name: string;
  features: ChurnFeatures;
}

const FIELDS: readonly Field[] = [
  { key: "total_events", label: "Total Events", step: "1", min: "0" },
  { key: "distinct_repos", label: "Distinct Repos", step: "1", min: "0" },
  { key: "active_days", label: "Active Days", step: "1", min: "0" },
  { key: "commit_events", label: "Commit Events", step: "1", min: "0" },
  { key: "pull_request_events", label: "Pull Request Events", step: "1", min: "0" },
  { key: "issue_events", label: "Issue Events", step: "1", min: "0" },
  { key: "comment_events", label: "Comment Events", step: "1", min: "0" },
  { key: "engagement_events", label: "Engagement Events", step: "1", min: "0" },
  { key: "release_events", label: "Release Events", step: "1", min: "0" },
  { key: "weekend_ratio", label: "Weekend Ratio (0-1)", step: "0.01", min: "0" },
  {
    key: "events_per_active_day",
    label: "Events per Active Day",
    step: "0.1",
    min: "0",
  },
  { key: "tenure_days", label: "Tenure (days)", step: "1", min: "0" },
  {
    key: "days_since_last_event",
    label: "Days Since Last Event",
    step: "1",
    min: "0",
  },
  { key: "velocity_30d", label: "30-Day Velocity (0-1)", step: "0.01", min: "0" },
  {
    key: "deceleration_score",
    label: "Deceleration (raw delta)",
    step: "1",
    min: "",
  },
  {
    key: "deceleration_ratio",
    label: "Deceleration Ratio (-1 to 1)",
    step: "0.01",
    min: "-1",
  },
];

type FormState = Record<FieldKey, string>;

const EMPTY_FORM: FormState = FIELDS.reduce(
  (accumulator, field) => ({ ...accumulator, [field.key]: "" }),
  {} as FormState,
);

const SCENARIOS: readonly Scenario[] = [
  {
    name: "Fading Core Maintainer",
    features: {
      total_events: 41,
      distinct_repos: 2,
      active_days: 12,
      commit_events: 18,
      pull_request_events: 9,
      issue_events: 7,
      comment_events: 5,
      engagement_events: 2,
      release_events: 0,
      weekend_ratio: 0.08,
      events_per_active_day: 3.4,
      tenure_days: 96,
      days_since_last_event: 34,
      // 3 of 41 events in the final 30 days; 30 in the first half vs 11 in the
      // second. Sharp, unambiguous decay.
      velocity_30d: 0.07,
      deceleration_score: 19,
      deceleration_ratio: 0.46,
    },
  },
  {
    name: "Thriving Contributor",
    features: {
      total_events: 412,
      distinct_repos: 7,
      active_days: 78,
      commit_events: 190,
      pull_request_events: 84,
      issue_events: 62,
      comment_events: 58,
      engagement_events: 14,
      release_events: 4,
      weekend_ratio: 0.24,
      events_per_active_day: 5.3,
      tenure_days: 118,
      days_since_last_event: 1,
      // 120 of 412 events in the final 30 days; 180 in the first half vs 232
      // in the second. Accelerating, not decaying.
      velocity_30d: 0.29,
      deceleration_score: -52,
      deceleration_ratio: -0.13,
    },
  },
  {
    name: "Drive-by First-Timer",
    features: {
      total_events: 3,
      distinct_repos: 1,
      active_days: 1,
      commit_events: 1,
      pull_request_events: 1,
      issue_events: 1,
      comment_events: 0,
      engagement_events: 0,
      release_events: 0,
      weekend_ratio: 1.0,
      events_per_active_day: 3.0,
      tenure_days: 4,
      days_since_last_event: 87,
      // All 3 events landed in the first half and none in the final 30 days.
      velocity_30d: 0.0,
      deceleration_score: 3,
      deceleration_ratio: 1.0,
    },
  },
];

function toFormState(features: ChurnFeatures): FormState {
  return FIELDS.reduce(
    (accumulator, field) => ({
      ...accumulator,
      [field.key]: String(features[field.key]),
    }),
    {} as FormState,
  );
}

function toFeatures(values: FormState): ChurnFeatures {
  return FIELDS.reduce(
    (accumulator, field) => ({
      ...accumulator,
      [field.key]: Number(values[field.key]),
    }),
    {} as ChurnFeatures,
  );
}

export default function ChurnWidget() {
  const [values, setValues] = useState<FormState>(EMPTY_FORM);
  const [result, setResult] = useState<ChurnPrediction | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [holdout, setHoldout] = useState<ThresholdHoldout | null>(null);
  const [threshold, setThreshold] = useState<number>(0.5);

  useEffect(() => {
    fetchThresholdHoldout()
      .then(setHoldout)
      .catch(() => setHoldout(null));
  }, []);

  const matrix: ConfusionMatrix = useMemo(
    () => computeMatrix(holdout, threshold),
    [holdout, threshold],
  );

  async function runPrediction(features: ChurnFeatures): Promise<void> {
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

  function loadScenario(features: ChurnFeatures): void {
    setValues(toFormState(features));
    void runPrediction(features);
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void runPrediction(toFeatures(values));
  }

  // Single-prediction verdict honours the simulator's cutoff, not a hardcoded
  // 0.5, so moving the slider reclassifies the scored contributor live.
  const highRisk: boolean = result ? result.probability >= threshold : false;

  return (
    <section className="glass-panel p-6 transition-all focus-within:ring-1 focus-within:ring-cyan-400/40 focus-within:shadow-[0_0_30px_rgba(34,211,238,0.25)]">
      <div className="mb-4 flex items-center gap-2">
        <Gauge className="h-5 w-5 text-cyan-400" />
        <h2 className="text-lg font-semibold text-slate-100">
          Contributor Churn Simulator
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-4 flex flex-wrap gap-2">
            {SCENARIOS.map((scenario) => (
              <button
                key={scenario.name}
                type="button"
                onClick={() => loadScenario(scenario.features)}
                className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 transition-all hover:border-cyan-400/50 hover:text-cyan-300"
              >
                {scenario.name}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {FIELDS.map((field) => (
                <div key={field.key} className="relative">
                  <input
                    id={field.key}
                    type="number"
                    step={field.step}
                    min={field.min || undefined}
                    required
                    placeholder=" "
                    value={values[field.key]}
                    onChange={(event) =>
                      setValues((previous) => ({
                        ...previous,
                        [field.key]: event.target.value,
                      }))
                    }
                    className="peer w-full rounded-xl border border-white/10 bg-slate-900/40 px-3 pb-1.5 pt-5 text-sm text-white opacity-70 outline-none transition-all focus:border-cyan-400/70 focus:opacity-100 focus:ring-2 focus:ring-cyan-400/40"
                  />
                  <label
                    htmlFor={field.key}
                    className="pointer-events-none absolute left-3 top-3.5 text-xs text-slate-500 transition-all peer-focus:top-1 peer-focus:text-[10px] peer-focus:text-cyan-300 peer-[:not(:placeholder-shown)]:top-1 peer-[:not(:placeholder-shown)]:text-[10px] peer-[:not(:placeholder-shown)]:text-slate-400"
                  >
                    {field.label}
                  </label>
                </div>
              ))}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-gradient-to-r from-indigo-500 to-cyan-400 py-3 font-bold text-white shadow-[0_0_20px_rgba(34,211,238,0.4)] transition-all hover:opacity-90 disabled:opacity-50"
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
            <Sigma className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-200">
              Decision Margin
            </h3>
          </div>

          {result ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-cyan-400/20 bg-slate-950/50 p-4">
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">
                    Predicted Log-Odds
                  </p>
                  <p className="mt-1 font-mono text-3xl font-bold text-cyan-300 drop-shadow-[0_0_14px_rgba(34,211,238,0.4)]">
                    {result.log_odds.toFixed(3)}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-700/50 bg-slate-950/50 p-4">
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">
                    Population Baseline
                  </p>
                  <p className="mt-1 font-mono text-3xl font-bold text-slate-300">
                    {result.base_log_odds.toFixed(3)}
                  </p>
                </div>
              </div>

              <div>
                <p className="mb-2 text-[10px] uppercase tracking-widest text-slate-500">
                  Top 3 Deciding Factors
                </p>
                <ul className="space-y-2">
                  {result.top_factors.map((factor) => (
                    <li
                      key={factor.feature}
                      className="flex items-center justify-between rounded-lg border border-white/5 bg-white/5 px-3 py-2 text-xs"
                    >
                      <span className="text-slate-300">{factor.feature}</span>
                      <span
                        className={`font-mono font-semibold ${
                          factor.contribution >= 0
                            ? "text-red-400"
                            : "text-emerald-400"
                        }`}
                      >
                        {factor.contribution >= 0 ? "+" : ""}
                        {factor.contribution.toFixed(3)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <p className="text-[11px] leading-relaxed text-slate-500">
                Log-odds are the raw additive margin XGBoost optimises. The
                baseline is the model&apos;s expected value across the training
                cohort; every SHAP contribution below sums the gap between them.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              Run a prediction to see the model&apos;s decision margin and the
              features that moved it.
            </p>
          )}
        </div>
      </div>

      <div className="mt-6 rounded-xl border border-slate-800/60 bg-slate-950/30 p-5">
        <div className="mb-1 flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-slate-200">
            Decision Threshold Simulator
          </h3>
        </div>
        <p className="mb-4 text-xs text-slate-500">
          {holdout
            ? `Swept live against the ${holdout.n}-contributor temporal holdout (${(holdout.positive_rate * 100).toFixed(1)}% churned). The model never saw these rows.`
            : "Holdout unavailable. Train the model to enable the simulator."}
        </p>

        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="text-slate-400">Classify as churn when P(churn) &ge;</span>
          <span className="font-mono text-lg font-bold text-cyan-300">
            {threshold.toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={threshold}
          disabled={!holdout}
          onChange={(event) => setThreshold(Number(event.target.value))}
          className="w-full accent-cyan-400 disabled:opacity-40"
        />

        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="grid grid-cols-2 gap-2">
            {[
              {
                label: "True Positives",
                sub: "caught before lapsing",
                value: matrix.tp,
                tone: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
              },
              {
                label: "False Positives",
                sub: "wasted outreach",
                value: matrix.fp,
                tone: "border-amber-500/40 bg-amber-500/10 text-amber-300",
              },
              {
                label: "False Negatives",
                sub: "lapsed unnoticed",
                value: matrix.fn,
                tone: "border-red-500/40 bg-red-500/10 text-red-300",
              },
              {
                label: "True Negatives",
                sub: "correctly left alone",
                value: matrix.tn,
                tone: "border-slate-700/60 bg-slate-900/40 text-slate-300",
              },
            ].map((cell) => (
              <div
                key={cell.label}
                className={`rounded-lg border p-3 transition-all ${cell.tone}`}
              >
                <p className="font-mono text-2xl font-bold">{cell.value}</p>
                <p className="mt-0.5 text-[11px] font-semibold">{cell.label}</p>
                <p className="text-[10px] text-slate-500">{cell.sub}</p>
              </div>
            ))}
          </div>

          <div className="space-y-3">
            {[
              { label: "Precision", value: matrix.precision },
              { label: "Recall", value: matrix.recall },
              { label: "F1", value: matrix.f1 },
              { label: "Accuracy", value: matrix.accuracy },
            ].map((metric) => (
              <div key={metric.label}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-slate-400">{metric.label}</span>
                  <span className="font-mono text-cyan-300">
                    {metric.value.toFixed(3)}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all"
                    style={{ width: `${metric.value * 100}%` }}
                  />
                </div>
              </div>
            ))}
            <p className="pt-1 text-[11px] leading-relaxed text-slate-500">
              At this cutoff the model catches{" "}
              <span className="text-cyan-300">
                {(matrix.recall * 100).toFixed(0)}%
              </span>{" "}
              of contributors who actually lapsed, and{" "}
              <span className="text-amber-300">
                {((1 - matrix.precision) * 100).toFixed(0)}%
              </span>{" "}
              of the outreach it triggers is wasted. There is no threshold that
              fixes both.
            </p>
          </div>
        </div>
      </div>

      {result && (
        <div className="mt-6">
          <ShapExplanation data={result.shap_attribution} />
        </div>
      )}
    </section>
  );
}
