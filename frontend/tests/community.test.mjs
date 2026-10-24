import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { gunzipSync } from "node:zlib";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import ts from "typescript";

const stateBytes = fs.readFileSync("../data/recent-activity-state.json.gz");
const state = JSON.parse(gunzipSync(stateBytes));
const snapshot = JSON.parse(
    fs.readFileSync("../data/recent-activity.json", "utf8"),
);
function compile(path, context = {}) {
    const testModule = { exports: {} };
    const code = ts.transpileModule(fs.readFileSync(path, "utf8"), {
        compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022,
        },
    }).outputText;
    vm.runInNewContext(code, {
        exports: testModule.exports,
        module: testModule,
        Date,
        URLSearchParams,
        Map,
        Set,
        Error,
        Number,
        ...context,
    });
    return testModule.exports;
}
const metrics = compile("src/lib/community.ts");
const filters = metrics.resolveFilters(new URLSearchParams(), state);
const report = metrics.buildCommunityReport(state, snapshot, filters);
const plain = (value) => JSON.parse(JSON.stringify(value));

test("approved checkpoint reconciles totals, UTC days and weekly changes", () => {
    metrics.validateCheckpoint(state, snapshot);
    assert.deepEqual(plain(report.totals), {
        events: 5657,
        contributors: 1116,
        prIssues: 2174,
    });
    assert.deepEqual(
        plain(
            report.daily.map((d) => ({
                date: d.date,
                events: d.events,
                contributors: d.contributors,
            })),
        ),
        snapshot.daily,
    );
    assert.equal(report.comparison.current.events, 1050);
    assert.equal(report.comparison.previous.events, 1606);
    assert.equal(report.comparison.changes.events.percent, -34.62);
    assert.equal(report.comparison.changes.contributors.percent, -10.65);
    assert.equal(report.comparison.changes.prIssues.percent, 4);
    assert.equal(report.comparison.returning, 106);
    assert.equal(report.comparison.joining, 238);
    assert.equal(report.comparison.absent, 279);
});
test("cohort cells are observed returns, with unavailable future periods blank", () => {
    assert.deepEqual(
        plain(report.cohorts.map((r) => r.cells.map((c) => c?.count ?? null))),
        [
            [385, 148, 115, 113],
            [286, 25, 22, null],
            [245, 9, null, null],
            [200, null, null, null],
        ],
    );
    assert.deepEqual(
        plain(report.weeks.map((w) => w.contributors)),
        [385, 434, 385, 344],
    );
});
test("source concentration and focused UTC-day investigations reconcile", () => {
    assert.equal(report.concentration.accounts[0].name, "bobrenjc93");
    assert.equal(report.concentration.accounts[0].events, 934);
    assert.equal(
        Math.round(report.concentration.topOnePercent * 100) / 100,
        16.51,
    );
    assert.equal(
        Math.round(report.concentration.topFivePercent * 100) / 100,
        32.03,
    );
    assert.deepEqual(
        plain(
            report.spikes.map((s) => [s.events, s.contributors, s.topEvents]),
        ),
        [
            [457, 92, 256],
            [382, 72, 242],
        ],
    );
    assert.equal(
        report.comparison.repositoryDrivers.reduce((n, r) => n + r.delta, 0),
        -556,
    );
    assert.equal(
        report.comparison.categoryDrivers.reduce((n, r) => n + r.delta, 0),
        -556,
    );
});
test("date boundaries are inclusive UTC days and a short selection has no weekly comparison", () => {
    for (const [day, events, contributors] of [
        ["2026-10-14", 457, 92],
        ["2026-10-21", 382, 72],
    ]) {
        const r = metrics.buildCommunityReport(state, snapshot, {
            ...filters,
            start: day,
            end: day,
        });
        assert.equal(r.daily.length, 1);
        assert.equal(r.totals.events, events);
        assert.equal(r.totals.contributors, contributors);
        assert.equal(r.comparison, null);
    }
    const r = metrics.buildCommunityReport(state, snapshot, {
        ...filters,
        start: "2026-10-15",
        end: "2026-10-21",
        repository: "pytorch/pytorch",
    });
    assert.equal(r.totals.events, 545);
    assert.equal(r.repositories.length, 1);
    assert.equal(r.spikes[0].included, false);
    assert.equal(r.source.snapshotEvents, 5657);
});
test("repository and category filters narrow the same event set; empty scopes are honest", () => {
    const r = metrics.buildCommunityReport(state, snapshot, {
        ...filters,
        category: "commit",
    });
    assert.equal(r.totals.events, 2710);
    assert.equal(r.categories.length, 1);
    const none = metrics.buildCommunityReport(state, snapshot, {
        ...filters,
        category: "comment",
        repository: "pypa/pip",
    });
    assert.equal(none.totals.events, 0);
    assert.equal(none.totals.contributors, 0);
    assert.equal(none.daily.length, 28);
    assert(none.daily.every((d) => d.events === 0));
    assert.equal(none.concentration.accounts.length, 0);
});
test("invalid calendar dates, ranges and dimensions are rejected", () => {
    for (const q of [
        "start=2026-02-30",
        "start=2026-09-23",
        "end=2026-10-22",
        "start=2026-10-21&end=2026-10-14",
        "repository=unknown",
        "category=unknown",
    ])
        assert.throws(() =>
            metrics.resolveFilters(new URLSearchParams(q), state),
        );
});
test("duplicate IDs, missing coverage and mismatched summaries fail verification", () => {
    assert.throws(
        () =>
            metrics.validateCheckpoint(
                { ...state, events: [...state.events, state.events[0]] },
                snapshot,
            ),
        /duplicate/,
    );
    assert.throws(
        () =>
            metrics.validateCheckpoint(
                { ...state, covered_days: state.covered_days.slice(1) },
                snapshot,
            ),
        /coverage/,
    );
    assert.throws(
        () =>
            metrics.validateCheckpoint(state, {
                ...snapshot,
                event_count: 5656,
            }),
        /totals/,
    );
});
function routeFixture(corrupt = false, pointer = null) {
    let calls = 0;
    const require = createRequire(import.meta.url);
    const route = compile("src/app/api/community/route.ts", {
        require: (name) =>
            name === "@/lib/community" ? metrics : require(name),
        Buffer,
        AbortSignal,
        Response,
        URL,
        console: { error() {} },
        fetch: async (url) => {
            calls++;
            if (String(url).endsWith("community-source.json"))
                return pointer
                    ? Response.json(pointer)
                    : new Response("", { status: 404 });
            return String(url).endsWith(".gz")
                ? new Response(
                      corrupt
                          ? Buffer.concat([stateBytes, Buffer.from("bad")])
                          : stateBytes,
                  )
                : Response.json(snapshot);
        },
    });
    return { route, calls: () => calls };
}
test("report route caches verified source and rejects invalid filters", async () => {
    const { route, calls } = routeFixture();
    const response = await route.GET(
        new Request("https://argo.test/api/community"),
    );
    assert.equal(response.status, 200);
    assert.equal((await response.json()).totals.events, 5657);
    const invalid = await route.GET(
        new Request("https://argo.test/api/community?repository=unknown"),
    );
    assert.equal(invalid.status, 400);
    assert.equal(calls(), 3);
});
test("report route fails closed when compressed source bytes do not match the summary checksum", async () => {
    const { route } = routeFixture(true);
    const response = await route.GET(
        new Request("https://argo.test/api/community"),
    );
    assert.equal(response.status, 503);
    assert.match((await response.json()).error, /could not be verified/);
});

test("failed validation evidence is rejected", () => {
    assert.throws(
        () =>
            metrics.validateCheckpoint(state, {
                ...snapshot,
                quality: { ...snapshot.quality, status: "fail" },
            }),
        /validation/,
    );
});

test("versioned release pointer serves a checksum-verified snapshot", async () => {
    const base =
        "https://github.com/yash-rai-93/argo-data-platform/releases/download/community-data-123-1/";
    const { route } = routeFixture(false, {
        schema_version: 1,
        summary_url: base + "recent-activity.json",
        state_url: base + "recent-activity-state.json.gz",
        summary_sha256: createHash("sha256")
            .update(JSON.stringify(snapshot))
            .digest("hex"),
    });
    const response = await route.GET(
        new Request("https://argo.test/api/community"),
    );
    assert.equal(response.status, 200);
    assert.equal(
        (await response.json()).source.summaryUrl,
        base + "recent-activity.json",
    );
});
test("foreign release URLs and wrong summary hashes fail closed", async () => {
    const base =
        "https://github.com/yash-rai-93/argo-data-platform/releases/download/community-data-123-1/";
    for (const overrides of [
        { summary_url: "https://other.example/recent-activity.json" },
        { summary_sha256: "0".repeat(64) },
        { state_url: base + "../recent-activity-state.json.gz" },
    ]) {
        const { route } = routeFixture(false, {
            schema_version: 1,
            summary_url: base + "recent-activity.json",
            state_url: base + "recent-activity-state.json.gz",
            summary_sha256: createHash("sha256")
                .update(JSON.stringify(snapshot))
                .digest("hex"),
            ...overrides,
        });
        assert.equal(
            (await route.GET(new Request("https://argo.test/api/community")))
                .status,
            503,
        );
    }
});
test("synthetic 90-day scope supports all 500 repositories and blank incomplete cohorts", () => {
    const expanded = {
        ...state,
        coverage_start: "2026-07-24",
        covered_days: Array.from({ length: 90 }, (_, i) =>
            metrics.addDays("2026-07-24", i),
        ),
        repositories: [...new Set(state.events.map((e) => e.repo_name))],
    };
    while (expanded.repositories.length < 500)
        expanded.repositories.push(
            "synthetic/repo-" + expanded.repositories.length,
        );
    const summary = {
        ...snapshot,
        coverage_start: expanded.coverage_start,
        quality: { ...snapshot.quality, expected_days: 90, covered_days: 90 },
        daily: expanded.covered_days.map(
            (date) =>
                snapshot.daily.find((d) => d.date === date) ?? {
                    date,
                    events: 0,
                    contributors: 0,
                },
        ),
    };
    metrics.validateCheckpoint(expanded, summary);
    const output = metrics.buildCommunityReport(
        expanded,
        summary,
        metrics.resolveFilters(new URLSearchParams(), expanded),
    );
    assert.equal(output.weeks.length, 13);
    assert.equal(output.options.repositories.length, 500);
    assert.equal(output.totals.contributors, snapshot.active_contributors);
    const inactive = metrics.buildCommunityReport(
        expanded,
        summary,
        metrics.resolveFilters(
            new URLSearchParams("repository=synthetic/repo-499"),
            expanded,
        ),
    );
    assert.equal(inactive.totals.events, 0);
    assert(output.cohorts.every((row) => row.cells.at(-1) === null));
});
