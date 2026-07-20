"use client";

import { TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from "recharts";

import { fetchContributorTrend, type TrendMetric } from "@/lib/api";

// recharts v3 omits payload/label from TooltipProps and moves them onto
// TooltipContentProps, which is what a custom content component receives.
// Partial, because <CustomTooltip /> is mounted without props and recharts
// injects them at render time.
type MrrTooltipProps = Partial<TooltipContentProps<number, string>>;

function CustomTooltip({ active, payload, label }: MrrTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const value = payload[0]?.value;
  if (typeof value !== "number") return null;
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/90 px-3 py-2 text-sm shadow-xl backdrop-blur">
      <p className="text-slate-400">{label}</p>
      <p className="font-semibold text-cyan-300">
        {value.toLocaleString()} contributors
      </p>
    </div>
  );
}

export default function RevenueChart() {
  const [data, setData] = useState<TrendMetric[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    fetchContributorTrend()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <section className="glass-panel flex h-80 items-center justify-center p-6">
        <div className="flex items-center gap-3">
          <span className="h-2.5 w-2.5 animate-ping rounded-full bg-cyan-400" />
          <span className="animate-pulse font-mono text-sm text-cyan-300 drop-shadow-[0_0_12px_rgba(34,211,238,0.6)]">
            Streaming warehouse telemetry...
          </span>
        </div>
      </section>
    );
  }

  return (
    <section className="glass-panel p-6">
      <div className="mb-4 flex items-center gap-2">
        <TrendingUp className="h-5 w-5 text-cyan-400" />
        <h2 className="text-lg font-semibold text-slate-100">Monthly Active Contributors</h2>
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            accessibilityLayer={false}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.22} />
                <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.03)"
              vertical={false}
            />
            <XAxis
              dataKey="name"
              stroke="#64748b"
              tickLine={false}
              axisLine={false}
            />
            <YAxis stroke="#64748b" tickLine={false} axisLine={false} width={40} />
            <Tooltip
              content={<CustomTooltip />}
              wrapperStyle={{ outline: "none", border: "none" }}
              contentStyle={{ border: "none", background: "transparent" }}
              cursor={{ stroke: "rgba(34,211,238,0.2)", strokeWidth: 2 }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#06b6d4"
              strokeWidth={6}
              strokeOpacity={0.2}
              fill="none"
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#06b6d4"
              strokeWidth={2.5}
              fill="url(#trendFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
