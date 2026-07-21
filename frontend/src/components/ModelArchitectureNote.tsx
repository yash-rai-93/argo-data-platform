"use client";

import { ChevronDown, Layers } from "lucide-react";
import { useState } from "react";

interface ModelSpec {
  surface: string;
  question: string;
  algorithm: string;
  output: string;
  metric: string;
  score: string;
  accent: string;
  border: string;
}

// Two models, two questions. Naming the metric next to the model it grades is
// the point of this panel: a reader who sees 0.7553 on one tab and 0.7005 on
// another will otherwise assume the second is a regression.
const MODELS: readonly ModelSpec[] = [
  {
    surface: "Priority Triage Queue",
    question: "When will they lapse?",
    algorithm: "Cox proportional hazards (survival:cox)",
    output: "Hazard ratio + median survival days",
    metric: "Concordance index",
    score: "0.7005",
    accent: "text-red-400",
    border: "border-red-500/30",
  },
  {
    surface: "Decision Threshold Simulator",
    question: "Will they lapse at all?",
    algorithm: "Gradient-boosted classifier (binary:logistic)",
    output: "Probability, swept against a cutoff",
    metric: "ROC-AUC",
    score: "0.7553",
    accent: "text-sky-400",
    border: "border-sky-400/30",
  },
];

/**
 * Collapsible explanation of why two models serve one workspace.
 *
 * Collapsed by default: it is context for a first-time reader, not something
 * an operator needs on every visit. Purely presentational -- it reads no
 * state and triggers no fetch.
 */
export default function ModelArchitectureNote() {
  const [open, setOpen] = useState<boolean>(false);

  return (
    <section className="glass-panel overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((previous) => !previous)}
        aria-expanded={open}
        aria-controls="architecture-note-body"
        className="flex w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-white/5"
      >
        <Layers className="h-4 w-4 shrink-0 text-red-500" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-slate-100">
            Architecture note: this page runs two models
          </span>
          <span className="block text-[11px] text-slate-500">
            One ranks <em>when</em> a contributor lapses, the other decides{" "}
            <em>if</em>. Their scores are not comparable.
          </span>
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-300 ${
            open ? "rotate-180" : ""
          }`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          id="architecture-note-body"
          className="border-t border-white/10 px-5 py-4"
        >
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {MODELS.map((model) => (
              <div
                key={model.surface}
                className={`rounded-xl border bg-slate-950/40 p-4 ${model.border}`}
              >
                <p className="eyebrow">{model.surface}</p>
                <p className={`mt-1 text-sm font-semibold ${model.accent}`}>
                  {model.question}
                </p>

                <dl className="mt-3 space-y-1.5 text-[11px]">
                  {[
                    ["Model", model.algorithm],
                    ["Returns", model.output],
                    ["Graded by", `${model.metric} — ${model.score}`],
                  ].map(([label, value]) => (
                    <div key={label} className="flex gap-2">
                      <dt className="w-20 shrink-0 text-slate-500">{label}</dt>
                      <dd className="min-w-0 flex-1 text-slate-300">{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>

          <p className="mt-4 border-t border-white/10 pt-3 text-[11px] leading-relaxed text-slate-500">
            <span className="font-semibold text-slate-400">
              Why 0.7005 is not worse than 0.7553.
            </span>{" "}
            A concordance index and an ROC-AUC measure different things on
            different populations. ROC-AUC needs a hard label at a fixed
            horizon, which forces every contributor still active at the study
            cutoff to be labelled &ldquo;retained&rdquo; — 1,186 of 2,426
            training rows whose outcome was never observed. The survival model
            keeps them in the risk set instead, and the C-index scores ranking
            quality over the pairs where an ordering is actually known. Plotting
            the two on one axis would be a category error, which is why the
            model registry flags them as not comparable.
          </p>
        </div>
      )}
    </section>
  );
}
