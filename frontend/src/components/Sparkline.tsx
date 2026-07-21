"use client";

import { Area, AreaChart, ResponsiveContainer } from "recharts";

type SparklineProps = {
  data: number[];
  color?: string;
};

export default function Sparkline({ data, color = "#22d3ee" }: SparklineProps) {
  const points = data.map((value, index) => ({ index, value }));
  const gradientId = `spark-${color.replace("#", "")}`;
  return (
    <div className="h-10 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.4} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
