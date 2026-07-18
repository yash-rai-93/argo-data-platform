"use client";

import { TrendingUp } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  type TooltipProps,
  XAxis,
  YAxis,
} from "recharts";

const DATA = [
  { month: "Feb", mrr: 420 },
  { month: "Mar", mrr: 520 },
  { month: "Apr", mrr: 610 },
  { month: "May", mrr: 680 },
  { month: "Jun", mrr: 740 },
  { month: "Jul", mrr: 880 },
];

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/90 px-3 py-2 text-sm shadow-xl backdrop-blur">
      <p className="text-slate-400">{label}</p>
      <p className="font-semibold text-cyan-300">
        ${Number(payload[0].value).toLocaleString()}
      </p>
    </div>
  );
}

export default function RevenueChart() {
  return (
    <section className="glass-panel p-6">
      <div className="mb-4 flex items-center gap-2">
        <TrendingUp className="h-5 w-5 text-cyan-400" />
        <h2 className="text-lg font-semibold text-slate-100">MRR Trend</h2>
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={DATA}
            accessibilityLayer={false}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="mrrFill" x1="0" y1="0" x2="0" y2="1">
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
              dataKey="month"
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
              dataKey="mrr"
              stroke="#06b6d4"
              strokeWidth={6}
              strokeOpacity={0.2}
              fill="none"
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="mrr"
              stroke="#06b6d4"
              strokeWidth={2.5}
              fill="url(#mrrFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
