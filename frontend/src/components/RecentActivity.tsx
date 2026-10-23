"use client";

import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/api";

interface Snapshot {
  status: "not_initialized" | "ready";
  coverage_start?: string;
  through_exclusive?: string;
  refreshed_at?: string;
  event_count?: number;
  active_contributors?: number;
  pr_issue_events?: number;
  daily?: { date: string; events: number; contributors: number }[];
}

export default function RecentActivity() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/api/v1/activity/recent`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("Recent activity unavailable");
        return response.json() as Promise<Snapshot>;
      })
      .then((data) => {
        setSnapshot(data);
        setStale(Boolean(data.through_exclusive &&
          Date.now() - Date.parse(data.through_exclusive) > 10 * 86400000));
      })
      .catch((error: unknown) => {
        if (!(error instanceof Error && error.name === "AbortError")) {
          setFailed(true);
        }
      });
    return () => controller.abort();
  }, []);

  const ready = snapshot?.status === "ready";
  const bars = snapshot?.daily?.slice(-14) ?? [];
  const peak = Math.max(1, ...bars.map((day) => day.events));

  return (
    <section className="glass-panel p-5" aria-labelledby="recent-activity-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="recent-activity-title" className="text-sm font-semibold text-slate-100">
          Recent GitHub activity
        </h3>
        <span className="text-xs text-slate-400">
          Manual updates{stale ? " · Refresh overdue" : ""}
        </span>
      </div>
      {failed ? (
        <p role="status" className="mt-3 text-sm text-amber-300">
          Recent activity is unavailable. Historical analysis is still shown below.
        </p>
      ) : !snapshot ? (
        <p role="status" className="mt-3 text-sm text-slate-400">
          Loading recent activity…
        </p>
      ) : !ready ? (
        <p className="mt-3 text-sm text-slate-400">
          Awaiting the first manual refresh. No recent activity has been fetched yet.
        </p>
      ) : (
        <>
          <p className="mt-2 text-xs text-slate-400">
            Coverage: {snapshot.coverage_start} to {snapshot.through_exclusive} (end exclusive, UTC).
            Updated {snapshot.refreshed_at ? new Date(snapshot.refreshed_at).toUTCString() : "unknown"}.
          </p>
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              ["Events in coverage", snapshot.event_count],
              ["Contributors in coverage", snapshot.active_contributors],
              ["PR & issue events in coverage", snapshot.pr_issue_events],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dt className="text-xs text-slate-400">{label}</dt>
                <dd className="mt-1 font-mono text-2xl text-slate-100">
                  {typeof value === "number" ? value.toLocaleString() : "—"}
                </dd>
              </div>
            ))}
          </dl>
          <div
            className="mt-4 flex h-16 items-end gap-1"
            role="img"
            aria-label="Daily event counts for the last fourteen covered days; exact counts follow"
          >
            {bars.map((day) => (
              <div
                key={day.date}
                className="min-w-0 flex-1 rounded-t bg-red-500/60"
                style={{ height: `${Math.max(2, day.events / peak * 100)}%` }}
                title={`${day.date}: ${day.events.toLocaleString()} events`}
              />
            ))}
          </div>
          <details className="mt-2 text-xs text-slate-400">
            <summary className="cursor-pointer">Daily counts</summary>
            <ul className="mt-2 space-y-1">
              {bars.map((day) => (
                <li key={day.date}>
                  {day.date}: {day.events.toLocaleString()} events, {day.contributors.toLocaleString()} contributors
                </li>
              ))}
            </ul>
          </details>
          <p className="mt-3 text-xs text-slate-500">
            Public GH Archive events from the scoped Python repositories.
            Publication lag and manual refresh timing apply.
          </p>
        </>
      )}
      <p className="mt-3 border-t border-white/10 pt-3 text-xs text-slate-500">
        The analysis below, model benchmarks, and retention queue use the fixed 2023 study.
      </p>
    </section>
  );
}
