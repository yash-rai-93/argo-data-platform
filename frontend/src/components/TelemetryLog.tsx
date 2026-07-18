"use client";

import { Terminal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const HEX = "0123456789abcdef";

function shortId() {
  let s = "";
  for (let i = 0; i < 8; i++) s += HEX[Math.floor(Math.random() * 16)];
  return s;
}

function buildLine() {
  const time = new Date().toLocaleTimeString("en-GB");
  const events = [
    () => "duckdb: materialized view fact_sessions updated",
    () => `duckdb: staged ${200 + Math.floor(Math.random() * 800)} raw events`,
    () => `xgboost: computed churn risk for user_id ${shortId()}`,
    () =>
      `xgboost: inference batch complete in ${(Math.random() * 40 + 5).toFixed(1)}ms`,
    () => "nemotron: executive brief generated successfully",
    () => "dbt: model metric_mrr build passed",
    () => "api: 200 GET /api/v1/customers/risk",
    () => `pipeline: ingested ${1300 + Math.floor(Math.random() * 200)} events/sec`,
  ];
  return `[${time}] ${events[Math.floor(Math.random() * events.length)]()}`;
}

const MAX_LINES = 10;

export default function TelemetryLog() {
  const [lines, setLines] = useState<{ id: number; text: string }[]>([]);
  const idRef = useRef(0);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let mounted = true;
    const tick = () => {
      setLines((prev) =>
        [...prev, { id: idRef.current++, text: buildLine() }].slice(-MAX_LINES),
      );
      if (mounted) timer = setTimeout(tick, 400 + Math.random() * 900);
    };
    tick();
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, []);

  return (
    <section className="glass-panel p-6">
      <div className="mb-3 flex items-center gap-2">
        <Terminal className="h-4 w-4 text-emerald-400" />
        <h2 className="text-sm font-semibold text-slate-200">System Telemetry</h2>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          live
        </span>
      </div>
      <div className="h-48 overflow-hidden rounded-lg border border-white/5 bg-black/40 p-3 font-mono text-xs leading-relaxed">
        {lines.map((l, i) => (
          <div
            key={l.id}
            className="whitespace-pre-wrap text-emerald-300"
            style={{ opacity: 0.3 + (i / MAX_LINES) * 0.6 }}
          >
            <span className="text-slate-600">&gt;</span> {l.text}
          </div>
        ))}
      </div>
    </section>
  );
}
