"use client";

import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  TooltipProps,
  XAxis,
  YAxis,
} from "recharts";

import type { ScoreBucket } from "@/lib/types";

import { ChartTooltipBody } from "./chart-tooltip";

/** Canonical bucket order. The API only returns non-empty buckets, so
 * we backfill zeros for missing ones - a histogram with gaps reads as
 * "no data in this range," which is the right semantic, but the bars
 * need to occupy fixed x positions for the shape to be readable. */
const ALL_BUCKETS = [
  "0.0-0.1",
  "0.1-0.2",
  "0.2-0.3",
  "0.3-0.4",
  "0.4-0.5",
  "0.5-0.6",
  "0.6-0.7",
  "0.7-0.8",
  "0.8-0.9",
  "0.9-1.0",
];

function fillBuckets(input: ScoreBucket[]): ScoreBucket[] {
  const byKey = new Map(input.map((b) => [b.bucket, b.count]));
  return ALL_BUCKETS.map((b) => ({ bucket: b, count: byKey.get(b) ?? 0 }));
}

export function ScoreHistogram({ data }: { data: ScoreBucket[] }) {
  const filled = React.useMemo(() => fillBuckets(data), [data]);
  const hasData = filled.some((b) => b.count > 0);

  if (!hasData) return <EmptyChart label="No chunks in range." />;

  return (
    <div className="h-[200px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={filled} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid
            vertical={false}
            stroke="hsl(var(--border))"
            strokeOpacity={0.6}
          />
          <XAxis
            dataKey="bucket"
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={false}
            width={32}
          />
          <Tooltip
            cursor={{ fill: "hsl(var(--muted-foreground))", fillOpacity: 0.08 }}
            content={(props: TooltipProps<number, string>) => {
              const p = props.payload?.[0];
              if (!props.active || !p) return null;
              const count = Number(p.value);
              return (
                <ChartTooltipBody
                  label={`similarity ${props.label}`}
                  value={count}
                  unit={count === 1 ? "chunk" : "chunks"}
                />
              );
            }}
          />
          <Bar dataKey="count" fill="hsl(var(--accent))" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex h-[200px] w-full items-center justify-center text-xs text-muted-foreground">
      {label}
    </div>
  );
}
