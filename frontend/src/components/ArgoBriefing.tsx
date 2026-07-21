"use client";

import { GitFork, Rocket } from "lucide-react";

function Accent({ children }: { children: string }) {
  return (
    <span className="font-semibold text-red-400 drop-shadow-[0_0_8px_rgba(220,38,38,0.7)]">
      {children}
    </span>
  );
}

const PIPELINE: { step: string; detail: string }[] = [
  {
    step: "Extract",
    detail:
      "Partition-pruned BigQuery scan over githubarchive.day.2023*. The payload column is never read; bots are filtered at source.",
  },
  {
    step: "Land",
    detail:
      "Zero-copy Arrow handoff into DuckDB. No CSV round-trip, no dtype coercion, no intermediate serialisation.",
  },
  {
    step: "Transform",
    detail:
      "dbt marts with half-open observation and target windows, recency anchored to the window edge, seven schema tests gating the build.",
  },
  {
    step: "Model",
    detail:
      "XGBoost fitted on the chronologically earlier cohort, tuned with forward-chaining CV, explained per prediction with SHAP.",
  },
];

export default function ArgoBriefing() {
  return (
    <section className="glass-panel p-6">
      <div className="mb-4 flex items-center gap-2">
        <Rocket className="h-5 w-5 text-red-500 drop-shadow-[0_0_8px_rgba(220,38,38,0.8)]" />
        <h2 className="text-lg font-semibold text-slate-100">What is ARGO?</h2>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <p className="leading-relaxed text-slate-300">
            ARGO predicts <Accent>open-source contributor churn</Accent>. It also predicts SaaS churn from
            547,434 real GitHub Archive events across 24 production Python
            repositories. It answers one falsifiable question: given a
            contributor&apos;s behaviour across a four-month observation window,
            will they go completely inactive over the following two months?
          </p>

          <div className="mt-4 border-l-2 border-red-600/50 pl-4">
            <div className="mb-1.5 flex items-center gap-2">
              <GitFork className="h-4 w-4 text-red-400" />
              <h3 className="text-sm font-semibold text-red-400">
                Why Maintainer Attrition Matters
              </h3>
            </div>
            <p className="text-sm leading-relaxed text-slate-400">
              A project does not die when its issue count spikes. It dies when
              the three people who understand the build system quietly stop
              showing up. That signal sits in public event streams nobody
              aggregates, and by the time a maintainer announces they are
              stepping back the knowledge has already left.
            </p>
          </div>
        </div>

        <div>
          <h3 className="eyebrow mb-2">Pipeline</h3>
          <div className="space-y-2">
            {PIPELINE.map((item, index) => (
              <div
                key={item.step}
                className="rounded-lg border border-red-950/60 bg-black/30 p-3"
              >
                <div className="mb-0.5 flex items-baseline gap-2">
                  <span className="font-mono text-[10px] text-red-600/80">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="text-xs font-semibold text-slate-200">
                    {item.step}
                  </span>
                </div>
                <p className="text-[11px] leading-relaxed text-slate-500">
                  {item.detail}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <p className="mt-5 border-t border-red-950/60 pt-3 text-[11px] leading-relaxed text-slate-500">
        No synthetic data. A model trained on generated events can only
        rediscover the rules its author wrote &mdash; the earlier synthetic
        build scored 0.97 ROC-AUC and meant nothing. On real events the honest
        number is <Accent>0.7553</Accent>, measured on a temporal holdout the
        model never saw.
      </p>
    </section>
  );
}
