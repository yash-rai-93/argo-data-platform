"use client";

import type { CommunityReport } from "@/lib/community";
import {
    DataTable,
    DeltaChart,
    Metric,
    Panel,
    Trends,
    VolumeChart,
    number,
    percent,
    signed,
} from "./CommunityCharts";

type Props = { report: CommunityReport; onRepository: (name: string) => void };
function ComparisonNote({ report }: { report: CommunityReport }) {
    const c = report.comparison;
    return (
        <p className="text-xs leading-relaxed text-slate-400">
            {c ? (
                <>
                    Weekly change compares{" "}
                    <strong className="text-slate-200">
                        {c.current.start}–{report.filters.end}
                    </strong>{" "}
                    with {c.previous.start}–
                    {new Date(
                        Date.parse(c.current.start + "T00:00:00Z") - 86400000,
                    )
                        .toISOString()
                        .slice(0, 10)}{" "}
                    UTC. Repository and category filters apply to both weeks.
                </>
            ) : (
                "Select at least 14 days to compare two complete seven-day periods. No weekly change is inferred from a shorter selection."
            )}
        </p>
    );
}
export function CommunityOverview({ report, onRepository }: Props) {
    const c = report.comparison;
    return (
        <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-3">
                <Metric
                    label="GitHub events"
                    value={number(report.totals.events)}
                    detail="Source event occurrences in this selection."
                />
                <Metric
                    label="Distinct accounts"
                    value={number(report.totals.contributors)}
                    detail="Deduplicated across all selected repositories and days."
                />
                <Metric
                    label="PR & issue events"
                    value={number(report.totals.prIssues)}
                    detail="Event categories, not merged-PR or unique-issue counts."
                />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
                <Metric
                    label="Weekly event change"
                    value={c ? percent(c.changes.events.percent) : "—"}
                    detail={
                        c
                            ? signed(c.changes.events.delta) +
                              " events; " +
                              number(c.previous.events) +
                              " → " +
                              number(c.current.events)
                            : "Requires a 14-day selection."
                    }
                />
                <Metric
                    label="Weekly account change"
                    value={c ? percent(c.changes.contributors.percent) : "—"}
                    detail={
                        c
                            ? signed(c.changes.contributors.delta) +
                              " accounts; " +
                              number(c.previous.contributors) +
                              " → " +
                              number(c.current.contributors)
                            : "Requires a 14-day selection."
                    }
                />
                <Metric
                    label="Weekly PR/issue change"
                    value={c ? percent(c.changes.prIssues.percent) : "—"}
                    detail={
                        c
                            ? signed(c.changes.prIssues.delta) +
                              " events; " +
                              number(c.previous.prIssues) +
                              " → " +
                              number(c.current.prIssues)
                            : "Requires a 14-day selection."
                    }
                />
            </div>
            <ComparisonNote report={report} />
            <Trends daily={report.daily} />
            <details className="glass-panel rounded-xl p-4">
                <summary className="cursor-pointer text-sm text-slate-300">
                    Exact daily counts
                </summary>
                <DataTable
                    caption="Daily UTC event and account counts"
                    headers={[
                        "UTC day",
                        "Events",
                        "Distinct accounts",
                        "PR/issue events",
                    ]}
                    rows={report.daily.map((d) => [
                        d.date,
                        number(d.events),
                        number(d.contributors),
                        number(d.prIssues),
                    ])}
                />
            </details>
            <div className="grid gap-5 lg:grid-cols-2">
                <Panel
                    title="Which repositories are active?"
                    note="Top ten by volume; the complete table below includes participation. Select a repository in the table to filter the report."
                >
                    <VolumeChart
                        rows={report.repositories}
                        kind="repositories"
                    />
                </Panel>
                <Panel
                    title="What kind of activity is it?"
                    note="Category counts describe observed actions; they do not prove automation or community health."
                >
                    <VolumeChart rows={report.categories} kind="categories" />
                    <DataTable
                        caption="Event category breadth"
                        headers={["Category", "Events", "Accounts"]}
                        rows={report.categories.map((r) => [
                            r.name,
                            number(r.events),
                            number(r.contributors),
                        ])}
                    />
                </Panel>
            </div>
            <Panel
                title="Repository ranking"
                note="An account active in more than one repository appears in each row. Do not sum repository account counts."
            >
                <DataTable
                    caption="All repositories by event volume"
                    headers={[
                        "Repository",
                        "Events",
                        "Distinct accounts",
                        "PR/issue events",
                    ]}
                    rows={report.repositories.map((r) => [
                        <button
                            key={r.name}
                            type="button"
                            onClick={() => onRepository(r.name)}
                            className="text-left text-red-300 underline decoration-red-400/40 underline-offset-4 hover:text-red-200"
                            aria-label={"Filter repository " + r.name}
                        >
                            {r.name}
                        </button>,
                        number(r.events),
                        number(r.contributors),
                        number(r.prIssues),
                    ])}
                />
            </Panel>
            {c && (
                <div className="grid gap-5 lg:grid-cols-2">
                    <Panel
                        title="Repository drivers of weekly change"
                        note="Current minus preceding complete UTC week. The chart locates change without claiming its cause."
                    >
                        <DeltaChart rows={c.repositoryDrivers} />
                        <details className="mt-3">
                            <summary className="cursor-pointer text-xs text-slate-400">
                                All repository changes
                            </summary>
                            <DataTable
                                caption="Repository weekly changes"
                                headers={[
                                    "Repository",
                                    "Previous",
                                    "Current",
                                    "Delta",
                                ]}
                                rows={c.repositoryDrivers.map((r) => [
                                    r.name,
                                    number(r.previous),
                                    number(r.current),
                                    signed(r.delta),
                                ])}
                            />
                        </details>
                    </Panel>
                    <Panel
                        title="Event-category drivers"
                        note="Positive and negative event changes, under the same filters."
                    >
                        <DeltaChart rows={c.categoryDrivers} />
                        <DataTable
                            caption="Category weekly changes"
                            headers={[
                                "Category",
                                "Previous",
                                "Current",
                                "Delta",
                            ]}
                            rows={c.categoryDrivers.map((r) => [
                                r.name,
                                number(r.previous),
                                number(r.current),
                                signed(r.delta),
                            ])}
                        />
                    </Panel>
                </div>
            )}
        </div>
    );
}
export function CommunityParticipation({ report }: Props) {
    const c = report.comparison;
    return (
        <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-3">
                <Metric
                    label="Returning accounts"
                    value={c ? number(c.returning) : "—"}
                    detail="Observed in both comparison weeks."
                />
                <Metric
                    label="Joining this week"
                    value={c ? number(c.joining) : "—"}
                    detail="In the latest week, absent in the preceding week. Not necessarily new to open source."
                />
                <Metric
                    label="Absent this week"
                    value={c ? number(c.absent) : "—"}
                    detail="In the preceding week, absent in the latest week. This is not a churn label."
                />
            </div>
            <ComparisonNote report={report} />
            <Panel
                title="Does volume reflect broader participation?"
                note="Each metric answers a different question; a highly active account can move event volume without adding new participants."
            >
                <DataTable
                    caption="Weekly activity and participation"
                    headers={[
                        "UTC week starting",
                        "Events",
                        "Distinct accounts",
                        "PR/issue events",
                        "Coverage",
                    ]}
                    rows={report.weeks.map((w) => [
                        w.start,
                        number(w.events),
                        number(w.contributors),
                        number(w.prIssues),
                        w.complete
                            ? "Complete selected week"
                            : "Partial / outside selection",
                    ])}
                />
            </Panel>
            <Panel
                title={report.weeks.length + "-week observed return matrix"}
                note="Cohorts use first appearance within this snapshot, after repository/category filters and before the date filter. Cells show accounts and share of the initial cohort. Partial or unavailable weeks remain blank; joining is not lifetime acquisition."
            >
                <div className="overflow-x-auto">
                    <table
                        className="w-full text-left text-xs"
                        style={{
                            minWidth: Math.max(
                                560,
                                240 + report.weeks.length * 90,
                            ),
                        }}
                    >
                        <caption className="sr-only">
                            Observed weekly cohort returns; unavailable future
                            periods are blank
                        </caption>
                        <thead className="text-slate-400">
                            <tr>
                                <th scope="col" className="p-3">
                                    First observed week
                                </th>
                                <th scope="col" className="p-3">
                                    Initial accounts
                                </th>
                                {Array.from(
                                    { length: report.weeks.length },
                                    (_, i) => (
                                        <th key={i} scope="col" className="p-3">
                                            Week {i}
                                        </th>
                                    ),
                                )}
                            </tr>
                        </thead>
                        <tbody>
                            {report.cohorts.map((row) => (
                                <tr
                                    key={row.start}
                                    className="border-t border-white/10"
                                >
                                    <th scope="row" className="p-3 font-medium">
                                        {row.start}
                                    </th>
                                    <td className="p-3">{number(row.size)}</td>
                                    {row.cells.map((cell, i) => (
                                        <td
                                            key={i}
                                            className="p-3"
                                            data-observed={
                                                cell ? "true" : "false"
                                            }
                                            aria-label={
                                                cell
                                                    ? number(cell.count) +
                                                      " accounts, " +
                                                      percent(cell.percent)
                                                    : "Not observed"
                                            }
                                            style={
                                                cell
                                                    ? {
                                                          backgroundColor:
                                                              "rgba(239,68,68," +
                                                              (0.06 +
                                                                  cell.percent /
                                                                      200) +
                                                              ")",
                                                      }
                                                    : undefined
                                            }
                                        >
                                            {cell && (
                                                <>
                                                    <strong className="font-mono">
                                                        {number(cell.count)}
                                                    </strong>
                                                    <span className="mt-1 block text-slate-300">
                                                        {percent(cell.percent)}
                                                    </span>
                                                </>
                                            )}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <p className="mt-3 text-xs text-slate-500">
                    Week 0 is the initial observed week; later columns are
                    complete seven-day source periods. Blank cells mean
                    unavailable observations, not 0% retention.
                </p>
            </Panel>
            <div className="grid gap-4 sm:grid-cols-2">
                <Metric
                    label="Top account event share"
                    value={
                        report.totals.events
                            ? percent(report.concentration.topOnePercent)
                            : "—"
                    }
                    detail={
                        report.concentration.accounts[0]
                            ? report.concentration.accounts[0].name +
                              " · " +
                              number(report.concentration.accounts[0].events) +
                              " events"
                            : "No activity in the selected scope."
                    }
                />
                <Metric
                    label="Top five event share"
                    value={
                        report.totals.events
                            ? percent(report.concentration.topFivePercent)
                            : "—"
                    }
                    detail="Ranks and shares are recalculated for the current filters."
                />
            </div>
            <Panel
                title="Activity concentration"
                note="Public source accounts ranked within the selected scope. A public handle does not establish a person's identity or whether activity was automated."
            >
                <VolumeChart
                    rows={report.concentration.accounts}
                    kind="accounts"
                />
                <DataTable
                    caption="Top account contribution shares"
                    headers={["Account", "Events", "Share"]}
                    rows={report.concentration.accounts.map((r) => [
                        r.name,
                        number(r.events),
                        percent(r.share),
                    ])}
                />
            </Panel>
            <Panel
                title="Focused investigation: October 14 and October 21"
                note="Exact UTC days under the current repository/category filters. These are observed counts, not proof of automation or poor community health."
            >
                <div className="grid gap-4 sm:grid-cols-2">
                    {report.spikes.map((s) => (
                        <article
                            key={s.date}
                            className="rounded-xl border border-white/10 bg-black/20 p-4"
                        >
                            <h3 className="font-medium">{s.date} UTC</h3>
                            {s.included ? (
                                <>
                                    <p className="mt-3 text-2xl font-mono">
                                        {number(s.events)}{" "}
                                        <span className="text-xs text-slate-400">
                                            events
                                        </span>
                                    </p>
                                    <p className="mt-1 text-sm text-slate-400">
                                        {number(s.contributors)} distinct
                                        accounts
                                    </p>
                                    {s.topAccount ? (
                                        <p className="mt-4 text-sm leading-relaxed">
                                            <strong>{s.topAccount}</strong>{" "}
                                            supplied {number(s.topEvents)}{" "}
                                            events ({percent(s.topShare)}).
                                        </p>
                                    ) : (
                                        <p className="mt-4 text-sm text-slate-400">
                                            No selected activity on this covered
                                            day.
                                        </p>
                                    )}
                                </>
                            ) : (
                                <p className="mt-4 text-sm text-slate-400">
                                    Outside the selected date range.
                                </p>
                            )}
                        </article>
                    ))}
                </div>
                <p className="mt-4 text-sm leading-relaxed text-slate-400">
                    Compare the event counts with the number of participating
                    accounts. Concentration can explain a volume spike without
                    implying broader engagement. Repository and category changes
                    locate the activity; they do not establish a cause.
                </p>
                <a
                    className="mt-3 inline-block text-sm text-red-300 underline"
                    target="_blank"
                    rel="noreferrer"
                    href="https://github.com/yash-rai-93/argo-data-platform/blob/main/docs/investigations/activity-concentration.md"
                >
                    Read the published concentration investigation
                </a>
            </Panel>
        </div>
    );
}
const utc = (value: string) =>
    new Date(value)
        .toISOString()
        .replace("T", " ")
        .replace(/\.\d{3}Z$/, " UTC");
export function CommunityTrust({ report }: Props) {
    const s = report.source,
        q = s.quality,
        bytes = s.query;
    const utilization = bytes.maximum_bytes_billed
        ? (100 * bytes.bytes_billed) / bytes.maximum_bytes_billed
        : null;
    return (
        <div className="space-y-5">
            <p className="rounded-xl border border-sky-400/20 bg-sky-400/5 p-4 text-sm leading-relaxed text-slate-300">
                This page describes the{" "}
                <strong>whole approved checkpoint</strong>. Activity filters do
                not change source coverage or validation evidence. The recorded
                snapshot may combine validated backfill batches; no run-history
                series is inferred.
            </p>
            <div className="grid gap-4 sm:grid-cols-3">
                <Metric
                    label="Daily tables covered"
                    value={q.covered_days + " / " + q.expected_days}
                    detail={
                        q.zero_event_days + " source days recorded zero events."
                    }
                />
                <Metric
                    label="Recorded check failures"
                    value={number(q.checks.reduce((n, c) => n + c.failures, 0))}
                    detail={
                        q.checks.length +
                        " recorded checks; checkpoint status: " +
                        q.status +
                        "."
                    }
                />
                <Metric
                    label="Billing cap used"
                    value={percent(utilization)}
                    detail={
                        bytes.kind === "backfill"
                            ? "Combined billed bytes across " +
                              bytes.batches +
                              " batches against the total backfill budget."
                            : "Billed query bytes divided by the configured cap."
                    }
                />
            </div>
            <Panel
                title="Coverage and freshness"
                note={
                    "Observed window: [" +
                    s.coverageStart +
                    ", " +
                    s.endExclusive +
                    ") UTC. This is a manually refreshed source snapshot."
                }
            >
                <div className="flex flex-wrap gap-2">
                    {s.coverage.map((d) => (
                        <div
                            key={d.date}
                            title={
                                d.date +
                                " UTC · " +
                                number(d.events) +
                                " source events"
                            }
                            className="flex h-14 w-14 flex-col items-center justify-center rounded-lg border border-emerald-400/30 bg-emerald-400/10 text-xs"
                        >
                            <span className="text-emerald-200">
                                {d.date.slice(5)}
                            </span>
                            <span className="mt-1 font-mono text-slate-300">
                                {number(d.events)}
                            </span>
                        </div>
                    ))}
                </div>
                <dl className="mt-6 grid gap-4 text-sm sm:grid-cols-2">
                    <div>
                        <dt className="text-xs text-slate-400">
                            Last recorded refresh
                        </dt>
                        <dd className="mt-1 font-mono text-xs">
                            {utc(s.refreshedAt)}
                        </dd>
                    </div>
                    <div>
                        <dt className="text-xs text-slate-400">
                            Last source event
                        </dt>
                        <dd className="mt-1 font-mono text-xs">
                            {utc(s.lastEventAt)}
                        </dd>
                    </div>
                </dl>
                <p className="mt-4 text-xs leading-relaxed text-slate-400">
                    {q.coverage_note} Publication lag and manual refresh timing
                    apply. Loading this report does not run BigQuery or train a
                    model.
                </p>
            </Panel>
            <Panel
                title="Validation evidence"
                note={
                    "Validated " +
                    utc(q.validated_at) +
                    ". The server also verifies the compressed checkpoint checksum, retained IDs, totals and all daily counts before returning a report."
                }
            >
                <DataTable
                    caption="Recorded checkpoint validation checks"
                    headers={["Check", "Status", "Failures"]}
                    rows={q.checks.map((c) => [
                        c.name,
                        <span
                            key={c.name}
                            className={
                                c.status === "pass"
                                    ? "text-emerald-300"
                                    : "text-amber-300"
                            }
                        >
                            {c.status}
                        </span>,
                        number(c.failures),
                    ])}
                />
            </Panel>
            {q.last_query && (
                <Panel
                    title="Latest refresh: event-ID reconciliation"
                    note="Overlap is expected when the incremental query rereads source days. Retained event IDs are deduplicated."
                >
                    <div className="grid gap-4 sm:grid-cols-3">
                        <Metric
                            label="Incoming rows"
                            value={number(q.last_query.incoming_rows)}
                        />
                        <Metric
                            label="New event IDs"
                            value={number(q.last_query.new_ids)}
                        />
                        <Metric
                            label="Overlapping IDs"
                            value={number(q.last_query.overlap_ids)}
                        />
                    </div>
                    <p className="mt-3 text-xs text-slate-400">
                        Repeated incoming IDs:{" "}
                        {number(q.last_query.duplicate_incoming_ids)}. This
                        describes one recorded refresh, not a pipeline
                        success-rate history.
                    </p>
                </Panel>
            )}
            <Panel
                title="Query bytes versus billing cap"
                note="Exact source values are shown below. GB uses 1,000,000,000 bytes."
            >
                <div className="mb-5">
                    <meter
                        className="h-6 w-full"
                        min={0}
                        max={bytes.maximum_bytes_billed}
                        value={bytes.bytes_billed}
                        aria-label="Billed query bytes relative to cap"
                    />
                    <p className="mt-1 text-right text-xs text-slate-400">
                        {percent(utilization)} of cap used
                    </p>
                </div>
                <DataTable
                    caption="Source query resource usage"
                    headers={["Measure", "Exact bytes", "Decimal GB"]}
                    rows={[
                        [
                            "Processed",
                            number(bytes.bytes_processed),
                            (bytes.bytes_processed / 1e9).toFixed(6),
                        ],
                        [
                            "Billed",
                            number(bytes.bytes_billed),
                            (bytes.bytes_billed / 1e9).toFixed(6),
                        ],
                        [
                            "Billing cap",
                            number(bytes.maximum_bytes_billed),
                            (bytes.maximum_bytes_billed / 1e9).toFixed(6),
                        ],
                    ]}
                />
            </Panel>
            <Panel title="Source and audit trail">
                <div className="flex flex-wrap gap-4 text-sm text-red-300">
                    {/^[0-9]+$/.test(bytes.run_id) && (
                        <a
                            href={
                                "https://github.com/yash-rai-93/argo-data-platform/actions/runs/" +
                                bytes.run_id
                            }
                            target="_blank"
                            rel="noreferrer"
                            className="underline"
                        >
                            Source refresh run
                        </a>
                    )}
                    <a
                        href={
                            s.summaryUrl ??
                            "https://github.com/yash-rai-93/argo-data-platform/blob/main/data/recent-activity.json"
                        }
                        target="_blank"
                        rel="noreferrer"
                        className="underline"
                    >
                        Approved summary and checks
                    </a>
                    <a
                        href="https://github.com/yash-rai-93/argo-data-platform/blob/main/docs/investigations/activity-concentration.md"
                        target="_blank"
                        rel="noreferrer"
                        className="underline"
                    >
                        Published investigation
                    </a>
                </div>
                <p className="mt-5 text-xs text-slate-400">
                    Checkpoint SHA-256
                </p>
                <p className="mt-1 break-all font-mono text-xs text-slate-300">
                    {s.stateSha256}
                </p>
                <p className="mt-4 text-xs leading-relaxed text-slate-400">
                    The 2023 historical training study and its model results
                    remain separate. This report describes recent repository
                    participation, not ARGO website visitors.
                </p>
            </Panel>
        </div>
    );
}
