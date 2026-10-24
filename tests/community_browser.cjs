const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const base = process.env.COMMUNITY_URL || "http://127.0.0.1:3000";
const output = process.env.COMMUNITY_OUTPUT || "community-browser-output";
fs.mkdirSync(output, { recursive: true });
async function main() {
    const browser = await chromium.launch({
        headless: true,
        ...(process.env.TEST_BROWSER_PATH
            ? { executablePath: process.env.TEST_BROWSER_PATH }
            : {}),
    });
    const context = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
        reducedMotion: "reduce",
        locale: "en-US",
    });
    const page = await context.newPage();
    page.setDefaultTimeout(45000);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const responsePromise = page.waitForResponse(
        (r) => r.url().includes("/api/community") && r.status() === 200,
    );
    await page.goto(base + "/community", { waitUntil: "domcontentloaded" });
    const baseline = await (await responsePromise).json();
    await page
        .getByText(baseline.totals.events.toLocaleString("en-US"), {
            exact: true,
        })
        .first()
        .waitFor();
    await page
        .getByRole("button", { name: "Apply filters", exact: true })
        .waitFor();
    const call = async (action) => {
        const [response] = await Promise.all([
            page.waitForResponse(
                (r) => r.url().includes("/api/community") && r.status() === 200,
            ),
            action(),
        ]);
        const result = await response.json();
        await page
            .getByRole("button", { name: "Apply filters", exact: true })
            .isEnabled()
            .then(async (enabled) => {
                if (!enabled)
                    await page
                        .getByRole("status")
                        .filter({ hasText: "Loading and verifying" })
                        .waitFor({ state: "hidden" });
            });
        return result;
    };
    await page.screenshot({
        path: path.join(output, "01-community-overview.png"),
    });
    await page.getByText("Exact daily counts", { exact: true }).click();
    const daily = page.getByRole("table", {
        name: "Daily UTC event and account counts",
    });
    assert.equal(
        await daily.locator("tbody tr").count(),
        baseline.daily.length,
    );
    await page.getByText("Exact daily counts", { exact: true }).click();

    await page
        .getByLabel("Repository", { exact: true })
        .selectOption("pytorch/pytorch");
    const scoped = await call(() =>
        page
            .getByRole("button", { name: "Apply filters", exact: true })
            .click(),
    );
    assert.equal(scoped.filters.repository, "pytorch/pytorch");
    assert(
        scoped.repositories.length === 1 &&
            scoped.repositories[0].name === "pytorch/pytorch",
    );
    await call(() =>
        page
            .getByRole("button", { name: "Reset filters", exact: true })
            .click(),
    );
    const clicked = await call(() =>
        page
            .getByRole("button", {
                name: "Filter repository pandas-dev/pandas",
                exact: true,
            })
            .click(),
    );
    assert.equal(clicked.filters.repository, "pandas-dev/pandas");
    assert.equal(
        await page.getByLabel("Repository", { exact: true }).inputValue(),
        "pandas-dev/pandas",
    );

    await page
        .getByLabel("Repository", { exact: true })
        .selectOption("pypa/pip");
    await page
        .getByLabel("Event category", { exact: true })
        .selectOption("comment");
    const empty = await call(() =>
        page
            .getByRole("button", { name: "Apply filters", exact: true })
            .click(),
    );
    assert.equal(empty.totals.events, 0);
    await page.getByText(/No events match this selection/).waitFor();
    await call(() =>
        page
            .getByRole("button", { name: "Reset filters", exact: true })
            .click(),
    );

    await page
        .getByRole("button", { name: /Participation & Concentration/ })
        .click();
    const cohort = page.getByRole("table", {
        name: /Observed weekly cohort returns/,
    });
    await cohort.waitFor();
    const nullCells = baseline.cohorts.reduce(
        (n, row) => n + row.cells.filter((cell) => cell === null).length,
        0,
    );
    assert.equal(
        await cohort.locator('td[data-observed="false"]').count(),
        nullCells,
    );
    for (const cell of await cohort.locator('td[data-observed="false"]').all())
        assert.equal(await cell.innerText(), "");
    await cohort.scrollIntoViewIfNeeded();
    await page.screenshot({
        path: path.join(output, "02-participation-cohorts.png"),
    });

    await page
        .getByRole("button", { name: /Data Trust & Pipeline Health/ })
        .click();
    const checks = page.getByRole("table", {
        name: "Recorded checkpoint validation checks",
    });
    await checks.waitFor();
    assert.equal(
        await checks.locator("tbody tr").count(),
        baseline.source.quality.checks.length,
    );
    assert.equal(
        await page.locator('[title$="source events"]').count(),
        baseline.source.coverage.length,
    );
    await checks.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, "03-data-trust.png") });
    const invalid = await context.request.get(
        base + "/api/community?start=2026-02-30",
    );
    assert.equal(invalid.status(), 400);

    const mobile = await context.newPage();
    await mobile.setViewportSize({ width: 390, height: 844 });
    await mobile.goto(base + "/community", { waitUntil: "domcontentloaded" });
    await mobile
        .getByText(baseline.totals.events.toLocaleString("en-US"), {
            exact: true,
        })
        .first()
        .waitFor();
    const widths = await mobile.evaluate(() => ({
        viewport: innerWidth,
        document: document.documentElement.scrollWidth,
    }));
    assert(widths.document <= widths.viewport + 2, JSON.stringify(widths));
    await mobile
        .getByRole("button", { name: /Participation & Concentration/ })
        .click();
    await mobile
        .getByRole("table", { name: /Observed weekly cohort returns/ })
        .waitFor();
    await mobile.screenshot({
        path: path.join(output, "04-mobile-report.png"),
    });

    // Synthetic layout fixture only: real 90-day metric semantics are unit-tested.
    const synthetic = structuredClone(baseline);
    synthetic.filters.start = "2026-07-24";
    synthetic.source.coverageStart = "2026-07-24";
    synthetic.source.coverage = Array.from({length:90},(_,i)=>({
        date:new Date(Date.UTC(2026,6,24+i)).toISOString().slice(0,10),events:0
    }));
    synthetic.weeks = Array.from({length:13},(_,i)=>({
        ...baseline.weeks[0], start:synthetic.source.coverage[i*7].date,complete:i<12
    }));
    synthetic.cohorts = synthetic.weeks.map((w,i)=>({
        start:w.start,size:1,cells:Array.from({length:13},(_,j)=>
            i+j<12?{count:1,percent:100}:null)
    }));
    while(synthetic.options.repositories.length<500)
        synthetic.options.repositories.push("synthetic/repo-"+synthetic.options.repositories.length);
    const expanded = await context.newPage();
    expanded.on("pageerror",error=>errors.push(error.message));
    await expanded.route("**/api/community*",route=>route.fulfill({json:synthetic}));
    await expanded.goto(base+"/community");
    await expanded.getByText(baseline.totals.events.toLocaleString("en-US"),{exact:true}).first().waitFor();
    await expanded.getByRole("button",{name:/Participation & Concentration/}).click();
    const wide=expanded.getByRole("table",{name:/Observed weekly cohort returns/});
    await wide.waitFor();
    assert.equal(await wide.locator("thead th").count(),15);
    await wide.scrollIntoViewIfNeeded();
    assert(await expanded.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
    await expanded.screenshot({path:path.join(output,"05-synthetic-90-day-cohorts.png")});
    await expanded.setViewportSize({width:390,height:844});
    assert(await expanded.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
    await expanded.screenshot({path:path.join(output,"06-synthetic-90-day-mobile.png")});

    assert.deepEqual(errors, []);
    await browser.close();
    const report = {
        status: "passed",
        checks: [
            "source API and overview totals",
            "all daily rows",
            "repository dropdown",
            "repository row click",
            "empty intersection",
            "reset",
            "cohort unavailable cells blank",
            "recorded quality checks",
            "coverage days",
            "invalid UTC date",
            "mobile navigation and overflow",
            "no page exceptions",
            "synthetic 13-week cohort layout",
            "synthetic 90-day mobile overflow",
        ],
        sourceEvents: baseline.source.snapshotEvents,
    };
    fs.writeFileSync(
        path.join(output, "report.json"),
        JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify(report));
}
main().catch((error) => {
    console.error(error);
    process.exit(1);
});
