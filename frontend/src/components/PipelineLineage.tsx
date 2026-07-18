"use client";

import { ArrowRight, Cpu, Database, FileJson, Sparkles } from "lucide-react";
import { Fragment } from "react";

const STAGES = [
  {
    title: "1. Raw Ingestion",
    subtitle: "JSONL Stream",
    icon: FileJson,
    tip: "Every product click, login, and payment lands here as a raw event stream, the unprocessed record of what customers actually do.",
  },
  {
    title: "2. Analytics Warehouse",
    subtitle: "DuckDB + dbt",
    icon: Database,
    tip: "Raw events are cleaned, joined, and organized into governed tables and metrics, turning noise into trustworthy numbers like revenue and active users.",
  },
  {
    title: "3. Risk Inference",
    subtitle: "XGBoost Engine",
    icon: Cpu,
    tip: "A machine learning model scores each account, predicting how likely it is to cancel based on recent behavior and how long they have been a customer.",
  },
  {
    title: "4. Strategic Synthesis",
    subtitle: "NVIDIA Nemotron",
    icon: Sparkles,
    tip: "An AI turns the numbers and risk scores into plain-English strategy, recommending exactly which accounts to save and how.",
  },
];

export default function PipelineLineage() {
  return (
    <section className="glass-panel p-6">
      <h2 className="mb-6 text-lg font-semibold text-slate-100">
        Data Lineage Pipeline
      </h2>
      <div className="flex flex-col items-stretch gap-4 md:flex-row md:items-center">
        {STAGES.map((s, i) => {
          const Icon = s.icon;
          return (
            <Fragment key={s.title}>
              <div className="group/node relative flex flex-1 flex-col items-center text-center">
                <span className="relative flex h-14 w-14 items-center justify-center">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400/25" />
                  <span className="relative flex h-14 w-14 items-center justify-center rounded-full border border-cyan-400/40 bg-slate-950/60 text-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.35)]">
                    <Icon className="h-6 w-6" />
                  </span>
                </span>
                <p className="mt-3 text-sm font-semibold text-slate-100">
                  {s.title}
                </p>
                <p className="text-xs text-slate-500">{s.subtitle}</p>
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
