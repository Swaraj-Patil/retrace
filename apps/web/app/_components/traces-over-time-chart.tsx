"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  TooltipProps,
  XAxis,
  YAxis,
} from "recharts";

import type { TracesOverTimePoint } from "@/lib/types";

import { ChartTooltipBody } from "./chart-tooltip";

/** Traces-over-time area. Generic context, not retrieval-specific, so
 * intentionally muted - amber stays bound to the wedge metrics. */
export function TracesOverTimeChart({ data }: { data: TracesOverTimePoint[] }) {
  if (data.length === 0) {
    return (
      <div className="flex h-[200px] w-full items-center justify-center text-xs text-muted-foreground">
        No traces in range.
      </div>
    );
  }

  return (
    <div className="h-[200px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="traces-over-time-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--muted-foreground))" stopOpacity={0.25} />
              <stop offset="100%" stopColor="hsl(var(--muted-foreground))" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            vertical={false}
            stroke="hsl(var(--border))"
            strokeOpacity={0.6}
          />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickFormatter={(d: string) => d.slice(5)}
            minTickGap={32}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={false}
            width={32}
          />
          <Tooltip
            cursor={{ stroke: "hsl(var(--border))", strokeWidth: 1 }}
            content={(props: TooltipProps<number, string>) => {
              const p = props.payload?.[0];
              if (!props.active || !p) return null;
              const count = Number(p.value);
              return (
                <ChartTooltipBody
                  label={String(props.label)}
                  value={count}
                  unit={count === 1 ? "trace" : "traces"}
                />
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="count"
            stroke="hsl(var(--muted-foreground))"
            strokeWidth={1.5}
            fill="url(#traces-over-time-fill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
