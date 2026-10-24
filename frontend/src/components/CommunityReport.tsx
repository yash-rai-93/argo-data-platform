"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, RefreshCw } from "lucide-react";
import Link from "next/link";
import type { CommunityReport, Filters } from "@/lib/community";
import {
    CommunityOverview,
    CommunityParticipation,
    CommunityTrust,
} from "./CommunityViews";
import { number } from "./CommunityCharts";

const pages = [
    {
        id: "overview",
        label: "Community Overview",
        question:
            "Is activity changing, and which repositories and actions explain it?",
    },
    {
        id: "participation",
        label: "Participation & Concentration",
        question:
            "Does more activity mean broader participation, and which accounts return?",
    },
    {
        id: "trust",
        label: "Data Trust & Pipeline Health",
        question: "How current is the snapshot, and what evidence supports it?",
    },
] as const;
type PageId = (typeof pages)[number]["id"];
const empty: Filters = { start: "", end: "", repository: "", category: "" };
const inputClass =
    "mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-400";
function queryFor(filters: Filters) {
    const p = new URLSearchParams();
    for (const [key, value] of Object.entries(filters))
        if (value) p.set(key, value);
    return p.toString();
}
export default function CommunityReportApp() {
    const [page, setPage] = useState<PageId>("overview");
    const [report, setReport] = useState<CommunityReport | null>(null);
    const [draft, setDraft] = useState<Filters>(empty);
    const [query, setQuery] = useState("");
    const [reload, setReload] = useState(0);
    const [busy, setBusy] = useState(true);
    const [error, setError] = useState("");
    useEffect(() => {
        const controller = new AbortController();
        fetch("/api/community" + (query ? "?" + query : ""), {
            signal: controller.signal,
        })
            .then(async (response) => {
                const data = await response.json();
                if (!response.ok)
                    throw new Error(
                        data.error ||
                            "The community report could not be loaded.",
                    );
                return data as CommunityReport;
            })
            .then((data) => {
                setReport(data);
                setDraft(data.filters);
            })
            .catch((error) => {
                if (!controller.signal.aborted)
                    setError(
                        error instanceof Error
                            ? error.message
                            : "Report unavailable.",
                    );
            })
            .finally(() => {
                if (!controller.signal.aborted) setBusy(false);
            });
        return () => controller.abort();
    }, [query, reload]);
    function beginQuery(next: string) {
        if (next !== query) {
            setBusy(true);
            setError("");
            setQuery(next);
        }
    }
    function reloadReport() {
        setBusy(true);
        setError("");
        setReload((n) => n + 1);
    }
    function apply(event: FormEvent) {
        event.preventDefault();
        beginQuery(queryFor(draft));
    }
    function chooseRepository(name: string) {
        const next = { ...draft, repository: name };
        setDraft(next);
        beginQuery(queryFor(next));
    }
    function reset() {
        const next = report
            ? {
                  ...report.filters,
                  start: report.source.coverageStart,
                  end: new Date(
                      Date.parse(report.source.endExclusive + "T00:00:00Z") -
                          86400000,
                  )
                      .toISOString()
                      .slice(0, 10),
                  repository: "",
                  category: "",
              }
            : empty;
        setDraft(next);
        beginQuery("");
    }
    const current = pages.find((p) => p.id === page)!;
    const min = report?.source.coverageStart;
    const max = report
        ? new Date(
              Date.parse(report.source.endExclusive + "T00:00:00Z") - 86400000,
          )
              .toISOString()
              .slice(0, 10)
        : undefined;
    return (
        <main className="min-h-screen px-3 py-6 text-slate-100 sm:px-6 lg:px-10">
            <div className="mx-auto max-w-7xl">
                <header className="mb-6">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                        <Link
                            href="/"
                            className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-red-300"
                        >
                            <ArrowLeft size={15} /> ARGO command suite
                        </Link>
                        <span className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300">
                            GH Archive · recent participation
                        </span>
                    </div>
                    <p className="mt-7 text-xs font-semibold uppercase tracking-[.25em] text-red-400">
                        Community intelligence
                    </p>
                    <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
                        GitHub Contributor Analysis
                    </h1>
                    <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-400">
                        Activity, participation and trust across the scoped
                        Python repositories. Every metric is derived from the
                        approved event-level checkpoint. Website visitor
                        analytics and the 2023 model study are separate.
                    </p>
                    {report && (
                        <p className="mt-3 text-xs text-slate-400">
                            Source coverage:{" "}
                            <strong className="text-slate-200">
                                {report.source.coverageStart} through {max} UTC
                            </strong>{" "}
                            · {number(report.source.snapshotEvents)} source
                            events · {report.options.repositories.length}{" "}
                            repositories · manual refresh
                        </p>
                    )}
                </header>

                <nav
                    aria-label="Report pages"
                    className="mb-5 grid gap-2 md:grid-cols-3"
                >
                    {pages.map((p, i) => (
                        <button
                            key={p.id}
                            type="button"
                            aria-pressed={page === p.id}
                            onClick={() => setPage(p.id)}
                            className={
                                "rounded-xl border px-4 py-3 text-left text-sm font-medium transition-colors " +
                                (page === p.id
                                    ? "border-red-400/60 bg-red-500/15 text-red-200"
                                    : "border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-600 hover:text-slate-200")
                            }
                        >
                            <span className="mr-2 font-mono text-xs opacity-60">
                                0{i + 1}
                            </span>
                            {p.label}
                        </button>
                    ))}
                </nav>

                <form
                    onSubmit={apply}
                    aria-label="Community report filters"
                    className="glass-panel mb-5 rounded-2xl p-4 sm:p-5"
                >
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <label className="text-xs text-slate-400">
                            Start date · UTC
                            <input
                                aria-label="Start date UTC"
                                className={inputClass}
                                type="date"
                                min={min}
                                max={draft.end || max}
                                value={draft.start}
                                onChange={(e) =>
                                    setDraft({
                                        ...draft,
                                        start: e.target.value,
                                    })
                                }
                            />
                        </label>
                        <label className="text-xs text-slate-400">
                            End date · UTC, inclusive
                            <input
                                aria-label="End date UTC"
                                className={inputClass}
                                type="date"
                                min={draft.start || min}
                                max={max}
                                value={draft.end}
                                onChange={(e) =>
                                    setDraft({ ...draft, end: e.target.value })
                                }
                            />
                        </label>
                        <label className="text-xs text-slate-400">
                            Repository
                            <select
                                aria-label="Repository"
                                className={inputClass}
                                value={draft.repository}
                                onChange={(e) =>
                                    setDraft({
                                        ...draft,
                                        repository: e.target.value,
                                    })
                                }
                            >
                                <option value="">All repositories</option>
                                {report?.options.repositories.map((repo) => (
                                    <option key={repo} value={repo}>
                                        {repo}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="text-xs text-slate-400">
                            Event category
                            <select
                                aria-label="Event category"
                                className={inputClass}
                                value={draft.category}
                                onChange={(e) =>
                                    setDraft({
                                        ...draft,
                                        category: e.target.value,
                                    })
                                }
                            >
                                <option value="">All categories</option>
                                {report?.options.categories.map((category) => (
                                    <option key={category} value={category}>
                                        {category}
                                    </option>
                                ))}
                            </select>
                        </label>
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                        <button
                            type="submit"
                            disabled={busy}
                            className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                        >
                            Apply filters
                            <ArrowRight size={14} />
                        </button>
                        <button
                            type="button"
                            onClick={reset}
                            disabled={busy}
                            className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 disabled:opacity-50"
                        >
                            Reset filters
                        </button>
                        <button
                            type="button"
                            onClick={reloadReport}
                            disabled={busy}
                            className="ml-auto inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-50"
                        >
                            <RefreshCw
                                size={13}
                                className={busy ? "animate-spin" : ""}
                            />
                            Reload approved checkpoint
                        </button>
                    </div>
                </form>

                <div aria-live="polite">
                    {busy && (
                        <p
                            role="status"
                            className="mb-5 rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400"
                        >
                            Loading and verifying the approved checkpoint…
                        </p>
                    )}
                    {error && (
                        <div
                            role="alert"
                            className="mb-5 rounded-xl border border-amber-400/40 bg-amber-400/10 p-4 text-sm text-amber-100"
                        >
                            <p>{error}</p>
                            <button
                                className="mt-3 underline"
                                type="button"
                                onClick={reloadReport}
                            >
                                Retry report
                            </button>
                        </div>
                    )}
                </div>
                {report && !error && (
                    <div
                        aria-busy={busy}
                        className={busy ? "pointer-events-none opacity-50" : ""}
                    >
                        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
                            <div>
                                <h2 className="text-xl font-semibold">
                                    {current.label}
                                </h2>
                                <p className="mt-1 text-sm text-slate-400">
                                    {current.question}
                                </p>
                            </div>
                            <p className="text-xs text-slate-400">
                                {report.filters.start}–{report.filters.end} UTC
                                · {report.filters.repository || "all repos"} ·{" "}
                                {report.filters.category || "all categories"}
                            </p>
                        </div>
                        {!report.totals.events && page !== "trust" && (
                            <p
                                role="status"
                                className="mb-5 rounded-xl border border-slate-700 bg-slate-900/50 p-4 text-sm text-slate-300"
                            >
                                No events match this selection. Covered
                                zero-activity days remain visible. Try another
                                repository, category or date range.
                            </p>
                        )}
                        {page === "overview" && (
                            <CommunityOverview
                                report={report}
                                onRepository={chooseRepository}
                            />
                        )}
                        {page === "participation" && (
                            <CommunityParticipation
                                report={report}
                                onRepository={chooseRepository}
                            />
                        )}
                        {page === "trust" && (
                            <CommunityTrust
                                report={report}
                                onRepository={chooseRepository}
                            />
                        )}
                    </div>
                )}
                <footer className="mt-8 border-t border-white/10 py-5 text-xs leading-relaxed text-slate-500">
                    ARGO · Public GH Archive data · UTC calendar boundaries ·
                    Snapshot evidence is bounded by its observation window.
                </footer>
            </div>
        </main>
    );
}
