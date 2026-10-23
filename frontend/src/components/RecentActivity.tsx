"use client";

import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/api";

type Driver = { name: string; previous: number; current: number; delta: number };
type Counts = {
  start: string;
  end_exclusive: string;
  events: number;
  active_contributors: number;
  pr_issue_events: number;
};
type Metric = "events" | "active_contributors" | "pr_issue_events";

interface Snapshot {
  status: "not_initialized" | "ready";
  coverage_start?: string;
  through_exclusive?: string;
  refreshed_at?: string;
  event_count?: number;
  active_contributors?: number;
  pr_issue_events?: number;
  daily?: { date: string; events: number; contributors: number }[];
  query?: { run_id?: string };
  weekly?: {
    status: "ready" | "insufficient_coverage";
    days_needed?: number;
    previous?: Counts;
    current?: Counts;
    changes?: Record<Metric, { delta: number; percent: number | null }>;
    returning_contributors?: number;
    joining_this_period?: number;
    absent_this_period?: number;
    repository_drivers?: Driver[];
    category_drivers?: Driver[];
    summary?: string;
  };
  quality?: {
    status: string;
    validated_at: string;
    expected_days: number;
    covered_days: number;
    zero_event_days: number;
    coverage_note: string;
    checks: { name: string; status: string; failures: number }[];
    last_query: {
      incoming_rows: number;
      duplicate_incoming_ids: number;
      overlap_ids: number;
      new_ids: number;
      legacy_coverage_inherited: boolean;
    } | null;
  };
}

const metrics: [Metric, string][] = [
  ["events", "Events"],
  ["active_contributors", "Active contributors"],
  ["pr_issue_events", "PR & issue events"],
];
const number = (value?: number) => typeof value === "number" ? value.toLocaleString() : "—";
const signed = (value: number) => (value > 0 ? "+" : "") + value.toLocaleString();

function DriverTable({ rows, label }: { rows: Driver[]; label: string }) {
  return (
    <details className="mt-3 rounded-lg border border-white/10 p-3">
      <summary className="cursor-pointer text-sm text-slate-200">{label}</summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <caption className="sr-only">{label}: exhaustive event-count changes</caption>
          <thead className="text-slate-400">
            <tr><th scope="col" className="py-2">Scope</th><th scope="col">Previous</th><th scope="col">Latest</th><th scope="col">Change</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name} className="border-t border-white/5 text-slate-300">
                <th scope="row" className="py-2 pr-3 font-normal">{row.name}</th>
                <td>{number(row.previous)}</td><td>{number(row.current)}</td>
                <td className="font-mono">{signed(row.delta)}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={4} className="py-2">No events in either period.</td></tr>}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default function RecentActivity() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [ageDays, setAgeDays] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(API_BASE_URL + "/api/v1/activity/recent", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Recent activity unavailable");
        return response.json() as Promise<Snapshot>;
      })
      .then((data) => {
        setSnapshot(data);
        const end = data.through_exclusive && Date.parse(data.through_exclusive);
        setAgeDays(typeof end === "number" && Number.isFinite(end)
          ? Math.max(0, Math.floor((Date.now() - end) / 86400000)) : null);
      })
      .catch((error: unknown) => {
        if (!(error instanceof Error && error.name === "AbortError")) setFailed(true);
      });
    return () => controller.abort();
  }, []);

  const ready = snapshot?.status === "ready";
  const bars = snapshot?.daily?.slice(-28) ?? [];
  const peak = Math.max(1, ...bars.map((day) => day.events));
  const weekly = snapshot?.weekly;
  const quality = snapshot?.quality;

  return (
    <section className="glass-panel p-5" aria-labelledby="recent-activity-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="recent-activity-title" className="text-sm font-semibold text-slate-100">
          Recent GitHub activity
        </h3>
        <span className="text-xs text-slate-400">
          Manual updates{ageDays !== null && ageDays > 10 ? " · Refresh overdue" : ""}
        </span>
      </div>
      {failed ? (
        <p role="status" className="mt-3 text-sm text-amber-300">
          Recent activity is unavailable. Historical analysis is still shown below.
        </p>
      ) : !snapshot ? (
        <p role="status" className="mt-3 text-sm text-slate-400">Loading recent activity…</p>
      ) : !ready ? (
        <p className="mt-3 text-sm text-slate-400">Awaiting the first manual refresh.</p>
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
                  {typeof value === "number" ? number(value) : "—"}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-6 flex h-20 items-end gap-1" role="img"
            aria-label="Daily event counts for up to 28 covered days; exact values follow">
            {bars.map((day, index) => (
              <div key={day.date}
                className={"min-w-0 flex-1 rounded-t " + (index >= bars.length - 7 ? "bg-red-400/80" : "bg-slate-500/60")}
                style={{ height: (day.events ? Math.max(2, day.events / peak * 100) : 0) + "%" }}
                title={day.date + ": " + number(day.events) + " events"} />
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {bars[0]?.date} — {bars.at(-1)?.date} · Red: latest seven covered days.
          </p>
          <details className="mt-2 text-xs text-slate-400">
            <summary className="cursor-pointer">Exact daily counts</summary>
            <ul className="mt-2 space-y-1">
              {bars.map((day) => (
                <li key={day.date}>{day.date}: {number(day.events)} events, {number(day.contributors)} contributors</li>
              ))}
            </ul>
          </details>

          <div className="mt-6 border-t border-white/10 pt-4">
            <h4 className="text-sm font-semibold text-slate-100">What changed this week?</h4>
            {weekly?.status === "ready" && weekly.current && weekly.previous && weekly.changes ? (
              <>
                <p className="mt-2 text-xs text-slate-400">
                  Latest: [{weekly.current.start}, {weekly.current.end_exclusive}).
                  Previous: [{weekly.previous.start}, {weekly.previous.end_exclusive}). UTC.
                </p>
                <dl className="mt-4 grid gap-4 sm:grid-cols-3">
                  {metrics.map(([key, label]) => {
                    const change = weekly.changes![key];
                    return (
                      <div key={key}>
                        <dt className="text-xs text-slate-400">{label}</dt>
                        <dd className="mt-1 font-mono text-xl text-slate-100">{number(weekly.current![key])}</dd>
                        <dd className="mt-1 text-xs text-slate-400">
                          {signed(change.delta)} · {change.percent === null ? "Percentage unavailable (previous = 0)" : signed(change.percent) + "%"}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
                <p className="mt-3 text-sm text-slate-300">{weekly.summary}</p>
                <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-3">
                  <div><dt className="text-slate-400">Returning in both periods</dt><dd className="mt-1 text-slate-200">{number(weekly.returning_contributors)}</dd></div>
                  <div><dt className="text-slate-400">Joining this period</dt><dd className="mt-1 text-slate-200">{number(weekly.joining_this_period)}</dd></div>
                  <div><dt className="text-slate-400">Absent this period</dt><dd className="mt-1 text-slate-200">{number(weekly.absent_this_period)}</dd></div>
                </dl>
                <p className="mt-2 text-xs text-slate-500">
                  Joining means absent in the preceding period; absent does not establish churn.
                  PR/issue counts are events, not unique items.
                </p>
                <DriverTable rows={weekly.repository_drivers ?? []} label="Repository drivers" />
                <DriverTable rows={weekly.category_drivers ?? []} label="Event-category drivers" />
                <p className="mt-2 text-xs text-slate-500">
                  Each table reconciles to the total event change. FastAPI aliases are combined.
                </p>
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                {weekly?.days_needed
                  ? number(weekly.days_needed) + " more covered days needed for a two-week comparison."
                  : "Comparison not recorded in this snapshot. A validated refresh or backfill will generate it."}
              </p>
            )}
          </div>

          <div className="mt-6 border-t border-white/10 pt-4">
            <h4 className="text-sm font-semibold text-slate-100">Data quality & freshness</h4>
            <p className="mt-2 text-xs text-slate-400">
              Data age: {ageDays === null ? "unknown" : number(ageDays) + " days since coverage end"}.
              Manual updates have no automatic refresh schedule.
            </p>
            {quality ? (
              <>
                <p className="mt-2 text-sm text-slate-200">
                  Validation: {quality.status} · {quality.covered_days}/{quality.expected_days} covered days
                  · {quality.zero_event_days} valid zero-event days.
                </p>
                <p className="mt-1 text-xs text-slate-500">Validated {new Date(quality.validated_at).toUTCString()}.</p>
                <ul className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                  {quality.checks.map((check) => (
                    <li key={check.name} className={check.status === "pass" ? "text-slate-300" : "text-amber-300"}>
                      {check.status === "pass" ? "✓" : "!"} {check.name}: {check.status} ({check.failures} failures)
                    </li>
                  ))}
                </ul>
                {quality.last_query && (
                  <p className="mt-3 text-xs text-slate-400">
                    Last query: {number(quality.last_query.incoming_rows)} rows,
                    {" "}{number(quality.last_query.duplicate_incoming_ids)} repeated incoming IDs,
                    {" "}{number(quality.last_query.overlap_ids)} IDs already in the checkpoint,
                    {" "}{number(quality.last_query.new_ids)} new IDs.
                    {quality.last_query.legacy_coverage_inherited ? " Earlier coverage inherited from the validated legacy checkpoint." : ""}
                  </p>
                )}
                <p className="mt-2 text-xs text-slate-500">{quality.coverage_note}</p>
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-400">
                Detailed quality checks were not recorded in this older snapshot. No pass rate is inferred.
              </p>
            )}
            {snapshot.query?.run_id && /^\d+$/.test(snapshot.query.run_id) && (
              <a className="mt-3 inline-block text-xs text-red-300 underline"
                href={"https://github.com/yash-rai-93/argo-data-platform/actions/runs/" + snapshot.query.run_id}
                target="_blank" rel="noreferrer">View source refresh run</a>
            )}
          </div>
          <a className="mt-4 inline-block text-xs text-red-300 underline"
            href="https://github.com/yash-rai-93/argo-data-platform/blob/main/docs/investigations/activity-concentration.md"
            target="_blank" rel="noreferrer">Read the activity concentration investigation</a>
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
