"use client";

/** Shared Recharts tooltip body. Matches the popover style used by the
 * shadcn Tooltip primitive so chart hovers feel consistent with the
 * rest of the app. */
export function ChartTooltipBody({
  label,
  value,
  unit,
}: {
  label: string;
  value: string | number;
  unit?: string;
}) {
  return (
    <div className="rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-md">
      <div className="font-mono text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-mono tabular-nums font-medium text-foreground">
        {value}
        {unit && <span className="ml-1 font-normal text-muted-foreground">{unit}</span>}
      </div>
    </div>
  );
}
