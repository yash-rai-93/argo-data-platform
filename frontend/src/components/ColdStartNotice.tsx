"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

// The API runs on a scale-to-zero container, so the first request after an idle
// period pays for booting the image, loading two XGBoost boosters, and
// computing the Breslow baseline over the training split before anything is
// served. A warm request returns in milliseconds.
//
// Below this threshold the wait is indistinguishable from normal latency and
// explaining it would be noise. Above it, silence reads as a broken page.
const EXPLAIN_AFTER_SECONDS = 3;

const COLD_START_HEADING = "Waking up the analytics engine";

// Measured, not estimated: a real cold start on the Render free tier was timed
// at 1 minute 47 seconds from first byte requested to first byte served. Quoting
// the observed figure beats a rounded guess -- a user told "40 seconds" who
// waits 107 concludes the app is broken.
const COLD_START_BODY =
  "This runs on a free scale-to-zero tier, so the first request after an idle " +
  "period takes ~1 minute and 47 seconds while the container boots and the " +
  "survival model loads. Everything after it is instant. Thanks for your " +
  "patience.";

/**
 * Progressive loading state for the API cold start.
 *
 * Mount this only while a request is outstanding -- it owns no `active` prop,
 * so unmounting is what resets it. That is deliberate: resetting internal state
 * from inside an effect means calling setState synchronously in the effect
 * body, which triggers a cascading render and is what the React Compiler lint
 * rule exists to prevent.
 *
 * For the first EXPLAIN_AFTER_SECONDS the copy stays generic, so a warm load
 * never flashes an explanation the user did not need.
 */
export default function ColdStartNotice() {
  const [elapsed, setElapsed] = useState<number>(0);

  useEffect(() => {
    // setInterval rather than a rAF loop: this ticks once a second and must
    // keep running while the tab is backgrounded, which rAF does not. One
    // timer on a 1s cadence never contends for the main thread.
    const tick = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(tick);
  }, []);

  const explain: boolean = elapsed >= EXPLAIN_AFTER_SECONDS;

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-start gap-3 rounded-xl border p-4 transition-colors duration-500 ${
        explain
          ? "border-amber-500/30 bg-amber-500/5"
          : "border-white/10 bg-white/5"
      }`}
    >
      <Loader2
        className={`mt-0.5 h-4 w-4 shrink-0 animate-spin ${
          explain ? "text-amber-400" : "text-red-500"
        }`}
        aria-hidden="true"
      />

      <div className="min-w-0 flex-1">
        {explain ? (
          <>
            <p className="text-sm font-semibold text-amber-300">
              {COLD_START_HEADING}
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-slate-400">
              {COLD_START_BODY}
            </p>
          </>
        ) : (
          <p className="text-sm text-slate-400">Loading cohort metrics…</p>
        )}
      </div>

      <span className="shrink-0 font-mono text-[11px] tabular-nums text-slate-500">
        {elapsed}s
      </span>
    </div>
  );
}
