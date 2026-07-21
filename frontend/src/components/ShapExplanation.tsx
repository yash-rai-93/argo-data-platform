"use client";

import { Info } from "lucide-react";

import type { ShapAttribution } from "@/lib/api";

const TOOLTIP =
  "SHAP values isolate the exact mathematical impact of each customer behavior on the final XGBoost prediction.";

export default function ShapExplanation({
  data,
}: {
  data?: ShapAttribution[];
}) {
  const items: ShapAttribution[] = data ?? [];
  // Scale bar widths relative to the strongest attribution in the payload.
  const max = items.length
    ? Math.max(...items.map((f) => Math.abs(f.contribution)))
    : 1;

  return (
    <section className="glass-panel p-6">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-semibold text-slate-100">
          Model Explainability (SHAP Feature Attribution)
        </h2>
        <span className="group relative">
          <Info className="h-4 w-4 cursor-help text-slate-500" />
          <span className="pointer-events-none absolute left-1/2 top-6 z-50 w-64 -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 p-3 text-xs leading-relaxed text-slate-300 opacity-0 shadow-xl backdrop-blur-xl transition-opacity group-hover:opacity-100">
            {TOOLTIP}
          </span>
        </span>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-slate-500">
          Run a prediction to see how each feature drives the score.
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((f) => {
            const up = f.contribution >= 0;
            const width = `${(Math.abs(f.contribution) / max) * 100}%`;
            return (
              <div key={f.feature} className="flex items-center gap-3">
                <span className="w-44 shrink-0 truncate font-mono text-xs text-slate-400">
                  {f.feature}
                </span>
                <div className="h-6 flex-1 overflow-hidden rounded-md bg-white/5">
                  <div
                    className={`flex h-full items-center rounded-md bg-gradient-to-r ${
                      up
                        ? "from-red-500/20 to-transparent"
                        : "from-emerald-500/20 to-transparent"
                    }`}
                    style={{ width }}
                  >
                    <span
                      className={`pl-2 text-xs font-semibold ${
                        up ? "text-red-300" : "text-emerald-300"
                      }`}
                    >
                      {up ? "+" : "-"}
                      {Math.abs(f.contribution).toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="mt-4 border-t border-white/10 pt-3 text-xs text-slate-500">
        Red bars raise predicted churn risk; green bars lower it, relative to the
        model baseline.
      </p>
    </section>
  );
}
