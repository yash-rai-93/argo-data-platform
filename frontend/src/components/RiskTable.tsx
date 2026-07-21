"use client";

import { AlertTriangle, MousePointerClick, Send, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

import {
  fetchRiskList,
  type CustomerRisk,
  type SurvivalPoint,
} from "@/lib/api";

// Longest survival time the study can observe, and the cohort's own median.
// The bullet graph's comparator tick is the second of these: a bar without a
// reference point says nothing about whether 90 days is good or bad.
const HORIZON_DAYS = 180;
const COHORT_MEDIAN_DAYS = 95;

interface UrgencyBand {
  label: string;
  copy: string;
  text: string;
  border: string;
  background: string;
  bar: string;
  // Literal hex, because recharts writes stroke into an SVG attribute and
  // cannot resolve a Tailwind class name.
  stroke: string;
}

// Banded on median_survival_days, not hazard_ratio. A hazard ratio is relative
// to the cohort baseline and means nothing to a non-technical reader; days are
// the only unit that survives translation. Copy is deliberately approximate --
// the model's holdout C-index is 0.70, which supports ranking, not calibration.
function urgency(days: number | null): UrgencyBand {
  if (days === null) {
    return {
      label: "Stable",
      copy: "No lapse projected",
      text: "text-emerald-400",
      border: "border-emerald-500/40",
      background: "bg-emerald-500/10",
      bar: "bg-emerald-400",
      stroke: "#34d399",
    };
  }
  if (days <= 30) {
    return {
      label: "Critical",
      copy: "Lapses in ~3 weeks",
      text: "text-red-500",
      border: "border-red-500/50",
      background: "bg-red-500/10",
      bar: "bg-red-500",
      stroke: "#ef4444",
    };
  }
  if (days <= 90) {
    return {
      label: "Elevated",
      copy: "~2 months left",
      text: "text-amber-400",
      border: "border-amber-400/40",
      background: "bg-amber-400/10",
      bar: "bg-amber-400",
      stroke: "#fbbf24",
    };
  }
  return {
    label: "Watch",
    copy: "Slow decline",
    text: "text-sky-400",
    border: "border-sky-400/40",
    background: "bg-sky-400/10",
    bar: "bg-sky-400",
    stroke: "#38bdf8",
  };
}

// Ascending by projected lifespan, nulls last. Sorting by hazard_ratio would
// order the queue by a column the table no longer renders.
function byUrgency(a: CustomerRisk, b: CustomerRisk): number {
  if (a.median_survival_days === null && b.median_survival_days === null) {
    return b.hazard_ratio - a.hazard_ratio;
  }
  if (a.median_survival_days === null) return 1;
  if (b.median_survival_days === null) return -1;
  return a.median_survival_days - b.median_survival_days;
}

// Templated locally from the row's own scored features. No LLM call, no
// network request, nothing sent -- the draft is composed client-side so the
// demo cannot fail on a missing API key.
function generateDraft(c: CustomerRisk): string {
  const window: string =
    c.median_survival_days === null
      ? "You are not currently projected to lapse"
      : `Our retention model projects roughly ${c.median_survival_days} days before you go quiet`;

  return `Subject: Checking in on ${c.primary_repo}

Hi ${c.contributor},

I noticed you haven't been active in ${c.primary_repo} for the last ${c.days_since_last_event} days. Given your impact (${c.total_events.toLocaleString()} lifetime events over ${c.tenure_days} days), I wanted to reach out and see if you need any support or triage help.

${window}.

Best,
ARGO System`;
}

// Tufte-style inline Kaplan-Meier. Every axis, grid, tooltip, and legend is
// stripped: at 96x28 the only readable channel is the shape of the decline.
//
// Subsampled to every third point (37 -> 13). Twenty rows of 37-point SVG paths
// is ~740 nodes recomputed on each re-render, which is what makes a table of
// charts feel sluggish.
//
// The hidden YAxis is not decoration. Without a fixed [0, 1] domain recharts
// auto-scales each row independently, so a contributor decaying from 1.00 to
// 0.98 draws exactly the same cliff as one collapsing to 0.20. That would make
// the column actively misleading.
function SurvivalSparkline({
  row,
  stroke,
}: {
  row: CustomerRisk;
  stroke: string;
}) {
  const points: SurvivalPoint[] = row.survival_curve.filter(
    (_, index) => index % 3 === 0,
  );
  if (points.length === 0) return null;

  return (
    <div className="h-7 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={points}
          margin={{ top: 2, right: 2, bottom: 2, left: 2 }}
        >
          <YAxis hide domain={[0, 1]} />
          <Line
            type="stepAfter"
            dataKey="survival"
            stroke={stroke}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// 180-day track with the contributor's projected lifespan filled and the cohort
// median marked. Pure CSS grid -- no chart library for a 4px bar.
function BulletGraph({ row }: { row: CustomerRisk }) {
  const band: UrgencyBand = urgency(row.median_survival_days);
  const filled: number = row.median_survival_days ?? HORIZON_DAYS;
  const width: number = Math.min(100, (filled / HORIZON_DAYS) * 100);
  const tick: number = (COHORT_MEDIAN_DAYS / HORIZON_DAYS) * 100;

  return (
    <div className="w-32">
      <div className="relative h-1.5 w-full rounded-full bg-slate-800">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${band.bar}`}
          style={{ width: `${width}%` }}
        />
        <div
          className="absolute -top-1 h-3.5 w-px bg-slate-500"
          style={{ left: `${tick}%` }}
          title={`Cohort median: ${COHORT_MEDIAN_DAYS}d`}
        />
      </div>
      <p className="mt-1 font-mono text-[10px] text-slate-500">
        {row.median_survival_days === null
          ? "180d+"
          : `${row.median_survival_days}d`}
      </p>
    </div>
  );
}

// Placeholder for the persistent profile column. The panel is a fixed-width
// structural block now, so with nothing selected it would otherwise sit as a
// dead rectangle. The shimmer runs over skeleton blocks that mirror the real
// layout -- header, stat row, body -- so the space reads as "waiting for input"
// rather than "still loading". Nothing here is fetched.
function IdleProfile() {
  return (
    <div aria-hidden="true" className="flex flex-col">
      <div className="flex items-center gap-2 border-b border-white/10 pb-4">
        <MousePointerClick className="h-4 w-4 text-slate-600" />
        <p className="eyebrow">Contributor Profile</p>
      </div>

      <div className="space-y-4 py-6">
        <div className="relative h-6 w-2/3 overflow-hidden rounded-md bg-slate-800/60 before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_2s_infinite] before:bg-gradient-to-r before:from-transparent before:via-white/10 before:to-transparent" />
        <div className="relative h-3 w-1/3 overflow-hidden rounded-md bg-slate-800/40 before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_2s_infinite] before:bg-gradient-to-r before:from-transparent before:via-white/10 before:to-transparent" />

        <div className="grid grid-cols-3 gap-2 pt-2">
          {[0, 1, 2].map((slot) => (
            <div
              key={slot}
              className="relative h-14 overflow-hidden rounded-lg border border-white/5 bg-slate-800/40 before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_2s_infinite] before:bg-gradient-to-r before:from-transparent before:via-white/10 before:to-transparent"
            />
          ))}
        </div>

        <div className="relative h-32 overflow-hidden rounded-xl border border-white/5 bg-slate-800/30 before:absolute before:inset-0 before:-translate-x-full before:animate-[shimmer_2s_infinite] before:bg-gradient-to-r before:from-transparent before:via-white/10 before:to-transparent" />
      </div>

      <p className="border-t border-white/10 pt-4 text-center text-xs text-slate-500">
        Select a contributor to view triage profile
      </p>
    </div>
  );
}

export default function RiskTable() {
  const [rows, setRows] = useState<CustomerRisk[]>([]);
  const [error, setError] = useState<string>("");
  const [selected, setSelected] = useState<CustomerRisk | null>(null);

  useEffect(() => {
    fetchRiskList()
      .then(setRows)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load risk data"),
      );
  }, []);

  // Escape closes the panel. A slide-over that can only be dismissed by
  // hitting a small target is a keyboard trap.
  useEffect(() => {
    if (!selected) return;
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") setSelected(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  const sorted: CustomerRisk[] = useMemo(
    () => [...rows].sort(byUrgency),
    [rows],
  );

  const draft: string = selected ? generateDraft(selected) : "";
  const band: UrgencyBand | null = selected
    ? urgency(selected.median_survival_days)
    : null;

  return (
    <section className="glass-panel p-6">
      <div className="mb-4 flex items-center gap-2">
        <AlertTriangle className="h-5 w-5 text-red-400" />
        <h2 className="text-lg font-semibold text-slate-100">
          Priority Triage Queue
        </h2>
      </div>
      <p className="-mt-2 mb-4 text-xs text-slate-500">
        Top contributors by event volume, ranked by projected time-to-lapse from
        the Cox survival model. Select a row for the full profile.
      </p>

      <div className="flex flex-col items-start gap-6 lg:flex-row">
        <div className="w-full flex-1 overflow-hidden">
          {error ? (
            <p className="text-sm text-red-300">{error}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-400">
                  <tr className="border-b border-white/10">
                    <th className="py-2 pr-4 font-medium">Contributor</th>
                    <th className="py-2 pr-4 font-medium">Events</th>
                    <th className="py-2 pr-4 font-medium">Last Seen</th>
                    <th className="py-2 pr-4 font-medium">Urgency</th>
                    <th className="py-2 font-medium">Projected Lifespan</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((r) => {
                    const cell: UrgencyBand = urgency(r.median_survival_days);
                    return (
                      <tr
                        key={r.contributor}
                        role="button"
                        tabIndex={0}
                        aria-label={`Open profile for ${r.contributor}`}
                        onClick={() => setSelected(r)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelected(r);
                          }
                        }}
                        className={`group h-14 cursor-pointer border-b border-slate-800/50 outline-none transition-colors hover:bg-slate-800/30 focus-visible:bg-slate-800/40 ${
                          selected?.contributor === r.contributor
                            ? "bg-slate-800/40"
                            : ""
                        }`}
                      >
                        <td className="pr-4 align-middle">
                          <span className="flex items-center gap-2">
                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-red-500 opacity-0 shadow-[0_0_8px_rgba(239,68,68,0.9)] transition-opacity group-hover:opacity-100" />
                            <span className="min-w-0">
                              <span className="block truncate font-mono text-xs text-slate-300">
                                {r.contributor}
                              </span>
                              <span className="block truncate font-mono text-[10px] text-slate-500">
                                {r.primary_repo}
                              </span>
                            </span>
                          </span>
                        </td>
                        <td className="pr-4 align-middle font-mono text-xs text-slate-300">
                          {r.total_events.toLocaleString()}
                        </td>
                        <td className="pr-4 align-middle font-mono text-xs text-slate-400">
                          {r.days_since_last_event}d ago
                        </td>
                        <td className="pr-4 align-middle">
                          <div className="flex items-center gap-3">
                            <div>
                              <span
                                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${cell.border} ${cell.background} ${cell.text}`}
                              >
                                {cell.label}
                              </span>
                              <span className="mt-1 block font-mono text-[10px] text-slate-500">
                                {cell.copy} &middot; {r.hazard_ratio.toFixed(2)}
                                &times;
                              </span>
                            </div>
                            <SurvivalSparkline row={r} stroke={cell.stroke} />
                          </div>
                        </td>
                        <td className="align-middle">
                          <BulletGraph row={r} />
                        </td>
                      </tr>
                    );
                  })}
                  {sorted.length === 0 && !error && (
                    <tr>
                      <td
                        colSpan={5}
                        className="py-6 text-center text-slate-500"
                      >
                        No contributors scored. Build the warehouse and train
                        the model first.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Persistent structural column, not an overlay. It never unmounts, so
            the table's width is stable whether or not a row is selected --
            a slide-over that reflowed the grid on every click was the reason
            this became a fixed column. */}
        <aside className="w-full shrink-0 rounded-xl border border-slate-800 bg-slate-900/50 p-6 transition-all duration-300 lg:w-[440px]">
          {selected && band ? (
            <div className="flex flex-col">
              <header className="flex items-start justify-between border-b border-white/10 pb-4">
                <div className="min-w-0">
                  <p className="eyebrow">Contributor Profile</p>
                  <h3 className="mt-1 truncate font-mono text-lg font-bold text-slate-100">
                    {selected.contributor}
                  </h3>
                  <p className="truncate font-mono text-xs text-slate-500">
                    {selected.primary_repo}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  aria-label="Clear selection"
                  className="shrink-0 rounded-lg border border-white/10 p-1.5 text-slate-400 transition-colors hover:border-red-500/50 hover:text-red-400"
                >
                  <X className="h-4 w-4" />
                </button>
              </header>

              <div className="space-y-5 py-5">
                <div
                  className={`rounded-xl border p-4 ${band.border} ${band.background}`}
                >
                  <p className={`text-sm font-bold ${band.text}`}>
                    {band.label}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">{band.copy}</p>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  {[
                    {
                      label: "Hazard Ratio",
                      value: `${selected.hazard_ratio.toFixed(2)}×`,
                    },
                    {
                      label: "Median",
                      value:
                        selected.median_survival_days === null
                          ? "180d+"
                          : `${selected.median_survival_days}d`,
                    },
                    {
                      label: "Last Seen",
                      value: `${selected.days_since_last_event}d`,
                    },
                  ].map((stat) => (
                    <div
                      key={stat.label}
                      className="rounded-lg border border-white/5 bg-white/5 px-2 py-2 text-center"
                    >
                      <p className="text-[9px] uppercase tracking-wider text-slate-500">
                        {stat.label}
                      </p>
                      <p className="mt-0.5 font-mono text-sm font-semibold text-slate-200">
                        {stat.value}
                      </p>
                    </div>
                  ))}
                </div>

                <p className="text-[11px] leading-relaxed text-slate-500">
                  A hazard ratio of 1.0 is the cohort baseline; above it this
                  contributor is decaying faster than average. Median is the
                  first day their survival curve falls below 50%.
                </p>

                <div>
                  <p className="eyebrow mb-2">Outreach Draft</p>
                  <pre className="whitespace-pre-wrap rounded-xl border border-white/10 bg-slate-950/60 p-3 font-mono text-[11px] leading-relaxed text-slate-300">
                    {draft}
                  </pre>
                </div>
              </div>

              <footer className="border-t border-white/10 pt-4">
                <button
                  type="button"
                  onClick={() => void navigator.clipboard.writeText(draft)}
                  className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-red-500/30 bg-white/5 px-3 py-2 text-xs font-medium text-red-400 transition-colors hover:border-red-500/70 hover:bg-red-500/10"
                >
                  <Send className="h-3.5 w-3.5" />
                  Copy Draft
                </button>
                <p className="mt-2 text-center text-[10px] uppercase tracking-wider text-slate-500">
                  Templated client-side &middot; nothing sent
                </p>
              </footer>
            </div>
          ) : (
            <IdleProfile />
          )}
        </aside>
      </div>
    </section>
  );
}
