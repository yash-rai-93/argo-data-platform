"use client";

import { Crosshair } from "lucide-react";

const QUADRANTS = [
  {
    title: "Monitor",
    sub: "Low Risk, High Value",
    glow: "bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.12),transparent_70%)]",
    ring: "border-amber-400/50",
    avatar: "N",
    pulse: "",
  },
  {
    title: "Critical Save",
    sub: "High Risk, High Value",
    glow: "bg-[radial-gradient(circle_at_top_right,rgba(239,68,68,0.16),transparent_70%)]",
    ring: "border-red-400/70 shadow-[0_0_14px_rgba(239,68,68,0.5)]",
    avatar: "E",
    pulse: "animate-pulse",
  },
  {
    title: "Safe",
    sub: "Low Risk, Low Value",
    glow: "bg-[radial-gradient(circle_at_bottom_left,rgba(16,185,129,0.15),transparent_70%)]",
    ring: "border-emerald-400/50",
    avatar: "S",
    pulse: "",
  },
  {
    title: "Let Go",
    sub: "High Risk, Low Value",
    glow: "bg-[radial-gradient(circle_at_bottom_right,rgba(100,116,139,0.14),transparent_70%)]",
    ring: "border-slate-500/50",
    avatar: "T",
    pulse: "",
  },
];

export default function StrategyMatrix() {
  return (
    <section className="glass-panel p-6">
      <div className="mb-1 flex items-center gap-2">
        <Crosshair className="h-5 w-5 text-cyan-400" />
        <h2 className="text-lg font-semibold text-slate-100">
          Layman Action Matrix: Where to Focus
        </h2>
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Each dot is an account. The top-right needs a retention offer now.
      </p>

      <div className="grid grid-cols-2 grid-rows-2 gap-3">
        {QUADRANTS.map((q) => (
          <div
            key={q.title}
            className={`relative flex min-h-[130px] flex-col justify-between rounded-xl border border-white/5 p-4 ${q.glow}`}
          >
            <div>
              <p className="text-sm font-semibold text-slate-100">{q.title}</p>
              <p className="text-[11px] text-slate-400">{q.sub}</p>
            </div>
            <div className="flex justify-end">
              <div
                className={`flex h-9 w-9 items-center justify-center rounded-full border-2 bg-slate-950/70 text-xs font-bold text-white ${q.ring} ${q.pulse}`}
              >
                {q.avatar}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex justify-between text-[10px] uppercase tracking-widest text-slate-600">
        <span>Low Churn Risk</span>
        <span>High Churn Risk</span>
      </div>
    </section>
  );
}
