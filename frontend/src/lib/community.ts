/** Metrics for the community report. All calendar boundaries are UTC and half-open. */
export type ActivityEvent = {
    event_id: string;
    created_at: string;
    actor_login: string;
    repo_name: string;
    event_type: string;
    event_category: string;
};
export type Checkpoint = {
    schema_version: number;
    coverage_start: string;
    through_exclusive: string;
    covered_days: string[];
    events: ActivityEvent[];
    repositories?: string[];
};
export type Snapshot = {
    summary_url?: string;
    status: string;
    coverage_start: string;
    through_exclusive: string;
    refreshed_at: string;
    last_event_at: string;
    state_sha256: string;
    event_count: number;
    active_contributors: number;
    pr_issue_events: number;
    daily: { date: string; events: number; contributors: number }[];
    query: {
        kind?: string;
        batches?: number;
        run_id: string;
        bytes_processed: number;
        bytes_billed: number;
        maximum_bytes_billed: number;
        source_commit: string;
    };
    quality: {
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
        } | null;
    };
};
export type Filters = {
    start: string;
    end: string;
    repository: string;
    category: string;
};
export class FilterError extends Error {}
const DAY = 86_400_000;
export function addDays(day: string, offset: number): string {
    return new Date(Date.parse(day + "T00:00:00Z") + offset * DAY)
        .toISOString()
        .slice(0, 10);
}
function validDay(day: string): boolean {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return false;
    const parsed = Date.parse(day + "T00:00:00Z");
    return (
        Number.isFinite(parsed) &&
        new Date(parsed).toISOString().slice(0, 10) === day
    );
}
const users = (events: ActivityEvent[]) =>
    new Set(events.map((e) => e.actor_login));
const prIssue = (e: ActivityEvent) =>
    e.event_category === "pull_request" || e.event_category === "issue";
const inRange = (
    events: ActivityEvent[],
    start: string,
    endExclusive: string,
) =>
    events.filter(
        (e) =>
            e.created_at.slice(0, 10) >= start &&
            e.created_at.slice(0, 10) < endExclusive,
    );
const counts = (events: ActivityEvent[]) => ({
    events: events.length,
    contributors: users(events).size,
    prIssues: events.filter(prIssue).length,
});
export function validateCheckpoint(
    state: Checkpoint,
    snapshot: Snapshot,
): void {
    if (
        state.schema_version !== 2 ||
        snapshot.status !== "ready" ||
        !snapshot.quality ||
        !validDay(state.coverage_start) ||
        !validDay(state.through_exclusive) ||
        state.coverage_start !== snapshot.coverage_start ||
        state.through_exclusive !== snapshot.through_exclusive ||
        state.coverage_start >= state.through_exclusive
    )
        throw new Error("Unsupported or inconsistent checkpoint.");
    if (
        snapshot.quality.status !== "pass" ||
        snapshot.quality.checks.some(
            (check) => check.status !== "pass" || check.failures !== 0,
        )
    )
        throw new Error("Checkpoint validation did not pass.");
    const ids = new Set<string>();
    for (const e of state.events) {
        if (
            ![
                e.event_id,
                e.actor_login,
                e.repo_name,
                e.event_category,
                e.event_type,
                e.created_at,
            ].every((v) => typeof v === "string" && v.length > 0) ||
            !/Z$|\+00:00$/.test(e.created_at) ||
            !Number.isFinite(Date.parse(e.created_at)) ||
            e.created_at.slice(0, 10) < state.coverage_start ||
            e.created_at.slice(0, 10) >= state.through_exclusive ||
            ids.has(e.event_id)
        )
            throw new Error("Invalid or duplicate source event.");
        ids.add(e.event_id);
    }
    if (
        state.repositories &&
        (new Set(state.repositories).size !== state.repositories.length ||
            state.events.some(
                (e) => !state.repositories!.includes(e.repo_name),
            ))
    )
        throw new Error("Repository registry does not match events.");
    const actual = counts(state.events);
    if (
        actual.events !== snapshot.event_count ||
        actual.contributors !== snapshot.active_contributors ||
        actual.prIssues !== snapshot.pr_issue_events
    )
        throw new Error("Checkpoint totals do not match the approved summary.");
    const expectedDays =
        (Date.parse(state.through_exclusive) -
            Date.parse(state.coverage_start)) /
        DAY;
    const covered = new Set(state.covered_days);
    if (
        covered.size !== expectedDays ||
        snapshot.quality.covered_days !== expectedDays ||
        snapshot.quality.expected_days !== expectedDays
    )
        throw new Error("Checkpoint coverage is incomplete.");
    for (
        let day = state.coverage_start;
        day < state.through_exclusive;
        day = addDays(day, 1)
    ) {
        if (!covered.has(day))
            throw new Error("Source coverage has a missing day.");
        const actualDay = counts(inRange(state.events, day, addDays(day, 1)));
        const expected = snapshot.daily.find((row) => row.date === day);
        if (
            !expected ||
            actualDay.events !== expected.events ||
            actualDay.contributors !== expected.contributors
        )
            throw new Error("Daily totals do not match the approved summary.");
    }
}
export function resolveFilters(
    params: URLSearchParams,
    state: Checkpoint,
): Filters {
    const start = params.get("start") || state.coverage_start;
    const end = params.get("end") || addDays(state.through_exclusive, -1);
    const repository = params.get("repository") || "";
    const category = params.get("category") || "";
    if (
        !validDay(start) ||
        !validDay(end) ||
        start > end ||
        start < state.coverage_start ||
        end >= state.through_exclusive
    )
        throw new FilterError(
            "Choose valid dates within the approved coverage.",
        );
    if (
        repository &&
        !(state.repositories ?? state.events.map((e) => e.repo_name)).includes(
            repository,
        )
    )
        throw new FilterError("Unknown repository.");
    if (category && !state.events.some((e) => e.event_category === category))
        throw new FilterError("Unknown event category.");
    return { start, end, repository, category };
}
function ranking(events: ActivityEvent[], key: (e: ActivityEvent) => string) {
    const groups = new Map<string, ActivityEvent[]>();
    for (const e of events) {
        const name = key(e);
        const bucket = groups.get(name) ?? [];
        bucket.push(e);
        groups.set(name, bucket);
    }
    return [...groups]
        .map(([name, rows]) => ({ name, ...counts(rows) }))
        .sort((a, b) => b.events - a.events || a.name.localeCompare(b.name));
}
function drivers(
    previous: ActivityEvent[],
    current: ActivityEvent[],
    key: (e: ActivityEvent) => string,
) {
    const a = new Map(ranking(previous, key).map((row) => [row.name, row]));
    const b = new Map(ranking(current, key).map((row) => [row.name, row]));
    return [...new Set([...a.keys(), ...b.keys()])]
        .map((name) => ({
            name,
            previous: a.get(name)?.events ?? 0,
            current: b.get(name)?.events ?? 0,
            delta: (b.get(name)?.events ?? 0) - (a.get(name)?.events ?? 0),
            previousContributors: a.get(name)?.contributors ?? 0,
            currentContributors: b.get(name)?.contributors ?? 0,
        }))
        .sort(
            (a, b) =>
                Math.abs(b.delta) - Math.abs(a.delta) ||
                a.name.localeCompare(b.name),
        );
}
function change(current: number, previous: number) {
    return {
        delta: current - previous,
        percent: previous
            ? Math.round((10000 * (current - previous)) / previous) / 100
            : null,
    };
}
export function buildCommunityReport(
    state: Checkpoint,
    snapshot: Snapshot,
    filters: Filters,
) {
    const endExclusive = addDays(filters.end, 1);
    const scope = state.events.filter(
        (e) =>
            (!filters.repository || e.repo_name === filters.repository) &&
            (!filters.category || e.event_category === filters.category),
    );
    const selected = inRange(scope, filters.start, endExclusive);
    const totals = counts(selected);
    const daily = [];
    for (let day = filters.start; day < endExclusive; day = addDays(day, 1))
        daily.push({
            date: day,
            ...counts(inRange(selected, day, addDays(day, 1))),
        });
    const accountRanking = ranking(selected, (e) => e.actor_login).map(
        (row) => ({
            ...row,
            share: totals.events ? (100 * row.events) / totals.events : 0,
        }),
    );
    const concentration = {
        topOnePercent: totals.events
            ? (100 * (accountRanking[0]?.events ?? 0)) / totals.events
            : 0,
        topFivePercent: totals.events
            ? (100 *
                  accountRanking
                      .slice(0, 5)
                      .reduce((sum, row) => sum + row.events, 0)) /
              totals.events
            : 0,
        accounts: accountRanking.slice(0, 10),
    };
    const weekCount = Math.ceil(
        (Date.parse(state.through_exclusive) -
            Date.parse(state.coverage_start)) /
            (7 * DAY),
    );
    const firstWeek = new Map<string, number>();
    for (const e of scope) {
        const w = Math.floor(
            (Date.parse(e.created_at.slice(0, 10)) -
                Date.parse(state.coverage_start)) /
                (7 * DAY),
        );
        firstWeek.set(
            e.actor_login,
            Math.min(firstWeek.get(e.actor_login) ?? w, w),
        );
    }
    const weeks = Array.from({ length: weekCount }, (_, w) => {
        const start = addDays(state.coverage_start, w * 7),
            end = addDays(start, 7);
        const rows = inRange(selected, start, end);
        return {
            start,
            endExclusive: end,
            ...counts(rows),
            complete:
                start >= filters.start &&
                end <= endExclusive &&
                end <= state.through_exclusive,
        };
    });
    const cohorts = weeks
        .map((week, w) => {
            const members = new Set(
                [...firstWeek]
                    .filter(([, first]) => first === w)
                    .map(([actor]) => actor),
            );
            const cells = Array.from({ length: weekCount }, (_, offset) => {
                const target = w + offset;
                if (!weeks[target]?.complete || !week.complete || !members.size)
                    return null;
                const active = new Set(
                    inRange(
                        selected,
                        weeks[target].start,
                        weeks[target].endExclusive,
                    )
                        .filter((e) => members.has(e.actor_login))
                        .map((e) => e.actor_login),
                );
                return {
                    count: active.size,
                    percent: (100 * active.size) / members.size,
                };
            });
            return { start: week.start, size: members.size, cells };
        })
        .filter(
            (row) => row.start >= filters.start && row.start < endExclusive,
        );
    let comparison = null;
    if (Date.parse(endExclusive) - Date.parse(filters.start) >= 14 * DAY) {
        const currentStart = addDays(endExclusive, -7),
            previousStart = addDays(endExclusive, -14);
        const currentRows = inRange(scope, currentStart, endExclusive),
            previousRows = inRange(scope, previousStart, currentStart);
        const current = counts(currentRows),
            previous = counts(previousRows),
            a = users(previousRows),
            b = users(currentRows);
        comparison = {
            current: { start: currentStart, endExclusive, ...current },
            previous: {
                start: previousStart,
                endExclusive: currentStart,
                ...previous,
            },
            changes: {
                events: change(current.events, previous.events),
                contributors: change(
                    current.contributors,
                    previous.contributors,
                ),
                prIssues: change(current.prIssues, previous.prIssues),
            },
            returning: [...b].filter((actor) => a.has(actor)).length,
            joining: [...b].filter((actor) => !a.has(actor)).length,
            absent: [...a].filter((actor) => !b.has(actor)).length,
            repositoryDrivers: drivers(
                previousRows,
                currentRows,
                (e) => e.repo_name,
            ),
            categoryDrivers: drivers(
                previousRows,
                currentRows,
                (e) => e.event_category,
            ),
        };
    }
    const spikes = ["2026-10-14", "2026-10-21"].map((date) => {
        const included = date >= filters.start && date < endExclusive;
        const rows = included ? inRange(selected, date, addDays(date, 1)) : [];
        const top = ranking(rows, (e) => e.actor_login)[0];
        return {
            date,
            included,
            ...counts(rows),
            topAccount: top?.name ?? null,
            topEvents: top?.events ?? 0,
            topShare: rows.length
                ? (100 * (top?.events ?? 0)) / rows.length
                : 0,
        };
    });
    return {
        filters,
        totals,
        daily,
        comparison,
        concentration,
        weeks,
        cohorts,
        spikes,
        repositories: ranking(selected, (e) => e.repo_name),
        categories: ranking(selected, (e) => e.event_category),
        options: {
            repositories: [
                ...new Set(
                    state.repositories ?? state.events.map((e) => e.repo_name),
                ),
            ].sort(),
            categories: [
                ...new Set(state.events.map((e) => e.event_category)),
            ].sort(),
        },
        source: {
            coverageStart: state.coverage_start,
            endExclusive: state.through_exclusive,
            snapshotEvents: snapshot.event_count,
            snapshotContributors: snapshot.active_contributors,
            refreshedAt: snapshot.refreshed_at,
            lastEventAt: snapshot.last_event_at,
            stateSha256: snapshot.state_sha256,
            quality: snapshot.quality,
            query: snapshot.query,
            summaryUrl: snapshot.summary_url,
            coverage: state.covered_days.map((date) => ({
                date,
                events:
                    snapshot.daily.find((row) => row.date === date)?.events ??
                    0,
            })),
        },
    };
}
export type CommunityReport = ReturnType<typeof buildCommunityReport>;
