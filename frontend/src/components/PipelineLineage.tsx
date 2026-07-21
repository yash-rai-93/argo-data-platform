"use client";

import { ArrowRight, Cpu, Database, FileJson, Sparkles } from "lucide-react";
import { Fragment } from "react";

const STAGES = [
  {
    title: "1. Extraction",
    subtitle: "BigQuery → Arrow",
    stat: "547,434 events",
    icon: FileJson,
    tip: "A partition-pruned scan of githubarchive.day.2023* pulls six columns across 184 daily tables. The nested payload blob, which dominates dataset size, is never referenced.",
  },
  {
    title: "2. Warehouse",
    subtitle: "DuckDB + dbt",
    stat: "7/7 tests passing",
    icon: Database,
    tip: "Events are deduplicated on event_id, bucketed into behavioural categories, and aggregated into a leakage-free training mart with half-open observation and target windows.",
  },
  {
    title: "3. Inference",
    subtitle: "XGBoost + SHAP",
    stat: "16 features · 400 trees",
    icon: Cpu,
    tip: "Each contributor is scored for the probability of going inactive, and every prediction is decomposed into per-feature log-odds contributions by a SHAP TreeExplainer.",
  },
  {
    title: "4. Synthesis",
    subtitle: "NVIDIA Nemotron",
    stat: "narrative layer",
    icon: Sparkles,
    tip: "An LLM turns the cohort metrics and risk scores into a plain-English executive brief. This is the only stage that requires an external API key.",
  },
];

export default function PipelineLineage() {
  return (
    <section className="glass-panel p-6">
      <h2 className="text-lg font-semibold text-slate-100">
        Data Lineage Pipeline
      </h2>
      <p className="mb-6 text-xs text-slate-500">
        Hover any stage for what it actually does.
      </p>
      <div className="flex flex-col items-stretch gap-4 md:flex-row md:items-center">
        {STAGES.map((s, i) => {
          const Icon = s.icon;
          return (
            <Fragment key={s.title}>
              <div className="group/node relative flex flex-1 flex-col items-center text-center">
                <span className="relative flex h-14 w-14 items-center justify-center">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500/25" />
                  <span className="relative flex h-14 w-14 items-center justify-center rounded-full border border-red-500/40 bg-slate-950/60 text-red-400 shadow-[0_0_18px_rgba(239,68,68,0.35)]">
                    <Icon className="h-6 w-6" />
                  </span>
                </span>
                <p className="mt-3 text-sm font-semibold text-slate-100">
                  {s.title}
                </p>
                <p className="text-xs text-slate-500">{s.subtitle}</p>
                <p className="mt-1 font-mono text-[10px] text-red-500/80">
                  {s.stat}
                </p>
                <div className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-3 w-56 -translate-x-1/2 rounded-xl border border-white/10 bg-slate-900/95 p-3 text-xs leading-relaxed text-slate-300 opacity-0 shadow-xl backdrop-blur transition-opacity duration-200 group-hover/node:opacity-100">
                  {s.tip}
                </div>
              </div>
              {i < STAGES.length - 1 && (
                <ArrowRight className="mx-auto h-5 w-5 shrink-0 rotate-90 text-slate-600 md:rotate-0" />
              )}
            </Fragment>
          );
        })}
      </div>
    </section>
  );
}
