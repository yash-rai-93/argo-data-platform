"use client";

import type { ReactNode } from "react";
import {
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import type { CommunityReport } from "@/lib/community";

export const number = (value: number) => value.toLocaleString("en-US");
export const percent = (value: number | null) =>
    value === null ? "—" : value.toFixed(2) + "%";
export const signed = (value: number) => (value > 0 ? "+" : "") + number(value);
const colors = [
    "#f87171",
    "#38bdf8",
    "#a78bfa",
    "#34d399",
    "#fbbf24",
    "#fb923c",
];
const tooltipStyle = {
    background: "#111827",
    border: "1px solid #475569",
    borderRadius: 8,
    color: "#e2e8f0",
};
export function Panel({
    title,
    note,
    children,
}: {
    title: string;
    note?: string;
    children: ReactNode;
}) {
    return (
        <section className="glass-panel min-w-0 rounded-2xl p-4 sm:p-6">
            <h2 className="text-base font-semibold text-slate-100">{title}</h2>
            {note && (
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                    {note}
                </p>
            )}
            <div className="mt-4">{children}</div>
        </section>
    );
}
export function Metric({
    label,
    value,
    detail,
}: {
    label: string;
    value: string;
    detail?: string;
}) {
    return (
        <div className="glass-panel rounded-2xl border-t-2 border-t-red-500/60 p-5">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
                {label}
            </p>
            <p className="mt-3 font-mono text-3xl font-semibold tabular-nums text-slate-50">
                {value}
            </p>
            {detail && (
                <p className="mt-2 text-xs leading-relaxed text-slate-400">
                    {detail}
                </p>
            )}
        </div>
    );
}
export function Trends({ daily }: { daily: CommunityReport["daily"] }) {
    return (
        <div className="grid gap-4 lg:grid-cols-2">
            {(["events", "contributors"] as const).map((metric, i) => (
                <Panel
                    key={metric}
                    title={
                        i ? "Daily contributor breadth" : "Daily event activity"
                    }
                    note={
                        i
                            ? "Distinct accounts per UTC day. Do not sum daily unique counts."
                            : "Event occurrences per UTC day, including covered days with zero selected events."
                    }
                >
                    <div
                        className="h-56"
                        role="img"
                        aria-label={"UTC daily " + metric + " trend"}
                    >
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart
                                data={daily}
                                margin={{
                                    left: 0,
                                    right: 12,
                                    top: 12,
                                    bottom: 0,
                                }}
                            >
                                <CartesianGrid
                                    stroke="#334155"
                                    strokeDasharray="3 3"
                                    vertical={false}
                                />
                                <XAxis
                                    dataKey="date"
                                    stroke="#94a3b8"
                                    tick={{ fontSize: 10 }}
                                    tickFormatter={(date: string) =>
                                        date.slice(5)
                                    }
                                />
                                <YAxis
                                    stroke="#94a3b8"
                                    tick={{ fontSize: 10 }}
                                    width={42}
                                    allowDecimals={false}
                                />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Line
                                    name={i ? "Contributors" : "Events"}
                                    type="monotone"
                                    dataKey={metric}
                                    stroke={colors[i]}
                                    strokeWidth={2.5}
                                    dot={false}
                                    isAnimationActive={false}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </Panel>
            ))}
        </div>
    );
}
export function VolumeChart({
    rows,
    kind,
}: {
    rows: { name: string; events: number }[];
    kind: "repositories" | "categories" | "accounts";
}) {
    const shown = rows.slice(0, kind === "categories" ? 8 : 10);
    return shown.length ? (
        <div
            style={{ height: Math.max(170, shown.length * 32) }}
            role="img"
            aria-label={kind + " ranked by events"}
        >
            <ResponsiveContainer width="100%" height="100%">
                <BarChart
                    data={shown}
                    layout="vertical"
                    margin={{ left: 0, right: 24, top: 0, bottom: 0 }}
                >
                    <CartesianGrid
                        stroke="#334155"
                        strokeDasharray="3 3"
                        horizontal={false}
                    />
                    <XAxis
                        type="number"
                        stroke="#94a3b8"
                        tick={{ fontSize: 10 }}
                        allowDecimals={false}
                    />
                    <YAxis
                        type="category"
                        dataKey="name"
                        width={kind === "repositories" ? 145 : 120}
                        stroke="#cbd5e1"
                        tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                        contentStyle={tooltipStyle}
                        cursor={{ fill: "#ffffff08" }}
                    />
                    <Bar
                        dataKey="events"
                        name="Events"
                        radius={[0, 4, 4, 0]}
                        isAnimationActive={false}
                    >
                        {shown.map((row, i) => (
                            <Cell
                                key={row.name}
                                fill={colors[i % colors.length]}
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    ) : (
        <p className="text-sm text-slate-400">
            No events match the current filters.
        </p>
    );
}
export function DeltaChart({
    rows,
}: {
    rows: { name: string; delta: number }[];
}) {
    const shown = rows.slice(0, 10);
    return shown.length ? (
        <div
            style={{ height: Math.max(180, shown.length * 30) }}
            role="img"
            aria-label="Event change by scope"
        >
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shown} layout="vertical" margin={{ right: 20 }}>
                    <CartesianGrid
                        stroke="#334155"
                        strokeDasharray="3 3"
                        horizontal={false}
                    />
                    <XAxis
                        type="number"
                        stroke="#94a3b8"
                        tick={{ fontSize: 10 }}
                        allowDecimals={false}
                    />
                    <YAxis
                        type="category"
                        dataKey="name"
                        width={145}
                        stroke="#cbd5e1"
                        tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                        contentStyle={tooltipStyle}
                        cursor={{ fill: "#ffffff08" }}
                    />
                    <Bar
                        dataKey="delta"
                        name="Current minus previous"
                        isAnimationActive={false}
                    >
                        {shown.map((row) => (
                            <Cell
                                key={row.name}
                                fill={row.delta < 0 ? "#f87171" : "#34d399"}
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    ) : (
        <p className="text-sm text-slate-400">
            No activity in either comparison period.
        </p>
    );
}
export function DataTable({
    caption,
    headers,
    rows,
}: {
    caption: string;
    headers: string[];
    rows: ReactNode[][];
}) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
                <caption className="sr-only">{caption}</caption>
                <thead className="text-slate-400">
                    <tr>
                        {headers.map((h) => (
                            <th
                                key={h}
                                scope="col"
                                className="whitespace-nowrap px-2 py-3 font-medium"
                            >
                                {h}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="text-slate-200">
                    {rows.map((row, i) => (
                        <tr key={i} className="border-t border-white/10">
                            {row.map((value, j) => (
                                <td
                                    key={j}
                                    className="px-2 py-2.5 tabular-nums"
                                >
                                    {value}
                                </td>
                            ))}
                        </tr>
                    ))}
                    {!rows.length && (
                        <tr>
                            <td
                                colSpan={headers.length}
                                className="p-4 text-slate-400"
                            >
                                No events match the current filters.
                            </td>
                        </tr>
                    )}
                </tbody>
            </table>
        </div>
    );
}
