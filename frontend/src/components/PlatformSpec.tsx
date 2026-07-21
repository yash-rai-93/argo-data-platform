"use client";

import { Boxes, Cpu, Database, GitBranch, Layers, Server } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchModelCard, type ModelCard } from "@/lib/api";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SpecRow {
  label: string;
  value: string;
  mono?: boolean;
}

function bytes(value: number): string {
  return value < 1024 * 1024
    ? `${(value / 1024).toFixed(1)} KB`
    : `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function day(iso: string): string {
  return iso.slice(0, 10);
}

function SpecCard({
  title,
  icon: Icon,
  rows,
}: {
  title: string;
  icon: typeof Cpu;
  rows: SpecRow[];
}) {
  return (
    <div className="rounded-xl border border-red-950/60 bg-black/40 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-red-500" />
        <h3 className="eyebrow">{title}</h3>
      </div>
      <dl className="space-y-2">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-baseline justify-between gap-4 border-b border-white/5 pb-1.5 last:border-0 last:pb-0"
          >
            <dt className="shrink-0 text-[11px] text-slate-500">{row.label}</dt>
            <dd
              className={`text-right text-[11px] ${
                row.mono === false
                  ? "text-slate-300"
                  : "font-mono text-slate-200"
              }`}
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function PlatformSpec() {
  const [card, setCard] = useState<ModelCard | null>(null);
  const [failed, setFailed] = useState<boolean>(false);

  useEffect(() => {
    fetchModelCard()
      .then(setCard)
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <section className="glass-panel p-6">
        <h2 className="text-lg font-semibold">Platform Specification</h2>
        <p className="mt-2 text-sm text-red-300">
          Model card endpoint unreachable. Is the API running?
        </p>
      </section>
    );
  }

  if (!card) return <section className="glass-panel h-96 animate-pulse p-6" />;

  const hyper: string = Object.entries(card.hyperparameters)
    .map(([key, value]) => `${key.replace("xgb__", "")}=${value}`)
    .join("  ");

  return (
    <section className="glass-panel p-6">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-red-500" />
          <h2 className="text-lg font-semibold text-slate-100">
            Platform Specification
          </h2>
        </div>
        <span className="rounded-full border border-red-900/60 bg-red-950/40 px-3 py-1 font-mono text-[10px] text-red-300">
          {card.artifact} &middot; {bytes(card.artifact_bytes)}
        </span>
      </div>
      <p className="mb-5 text-xs text-slate-500">
        Read live from the model artifact and the warehouse. Nothing on this
        page is hardcoded, so it cannot describe a model other than the one
        currently serving predictions.
      </p>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <SpecCard
          title="Model"
          icon={Cpu}
          rows={[
            { label: "Algorithm", value: "XGBClassifier", mono: false },
            { label: "Objective", value: card.objective },
            { label: "Trees", value: card.n_trees.toLocaleString() },
            { label: "Features", value: String(card.n_features) },
            { label: "Target", value: card.target },
            {
              label: "scale_pos_weight",
              value: card.scale_pos_weight?.toFixed(4) ?? "—",
            },
          ]}
        />

        <SpecCard
          title="Training"
          icon={GitBranch}
          rows={[
            { label: "Split", value: "chronological 80/20", mono: false },
            { label: "CV", value: `TimeSeriesSplit(${card.cv_splits ?? "—"})` },
            { label: "CV ROC-AUC", value: card.cv_roc_auc?.toFixed(4) ?? "—" },
            {
              label: "Decision threshold",
              value: card.decision_threshold.toFixed(2),
            },
            {
              label: "Last trained",
              value: card.artifact_modified
                ? day(card.artifact_modified)
                : "—",
            },
            { label: "Explainer", value: "SHAP TreeExplainer", mono: false },
          ]}
        />

        <SpecCard
          title="Data"
          icon={Database}
          rows={[
            { label: "Source", value: "githubarchive.day.*" },
            { label: "Repos", value: String(card.data.repos) },
            {
              label: "Source events",
              value: card.data.source_rows.toLocaleString(),
            },
            {
              label: "Eligible cohort",
              value: card.data.cohort_rows.toLocaleString(),
            },
            {
              label: "Churn rate",
              value: `${(card.data.cohort_churn_rate * 100).toFixed(1)}%`,
            },
            {
              label: "Window",
              value: `${day(card.data.window_start)} → ${day(card.data.window_end)}`,
            },
          ]}
        />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <SpecCard
          title="Leakage Controls"
          icon={Boxes}
          rows={[
            { label: "Observation", value: card.data.observation_window },
            { label: "Target", value: card.data.target_window },
            { label: "Eligibility floor", value: card.data.eligibility },
            {
              label: "Recency anchor",
              value: "observation_end, not max(created_at)",
            },
          ]}
        />

        <SpecCard
          title="Runtime"
          icon={Server}
          rows={[
            { label: "API base", value: `${API_BASE}/api/v1` },
            { label: "Warehouse", value: "DuckDB (columnar, read-only)" },
            { label: "Transform", value: "dbt-core + dbt-duckdb" },
            { label: "Narrative LLM", value: "nvidia/nemotron via OpenRouter" },
          ]}
        />
      </div>

      <div className="mt-3 rounded-xl border border-red-950/60 bg-black/40 p-4">
        <h3 className="eyebrow mb-3">
          Feature Contract &middot; {card.n_features} columns
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {card.features.map((feature, index) => (
            <span
              key={feature.name}
              title={feature.label}
              className="rounded-md border border-red-950/70 bg-red-950/20 px-2 py-1 font-mono text-[10px] text-slate-400"
            >
              <span className="mr-1.5 text-red-600/70">
                {String(index).padStart(2, "0")}
              </span>
              {feature.name}
            </span>
          ))}
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
          Declared once in{" "}
          <span className="font-mono text-slate-400">
            ml/feature_extractor.py
          </span>{" "}
          and asserted at API import time. Order is part of the contract: the
          server refuses to boot if the request schema diverges by name, count,
          or position.
        </p>
      </div>

      <p className="mt-3 font-mono text-[10px] leading-relaxed text-slate-600">
        {hyper}
      </p>
    </section>
  );
}
