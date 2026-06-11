import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  /** Reduces visual weight so generic-context KPIs recede behind the
   * RAG metrics. The amber-discipline is enforced here: KPI cards
   * never carry the accent on their own; only the hero waste card
   * does, because only that card represents the wedge insight. */
  variant?: "default" | "muted";
}

export function KpiCard({ label, value, hint, variant = "default" }: KpiCardProps) {
  const muted = variant === "muted";
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card/30 p-4",
        muted && "bg-transparent",
      )}
    >
      <div
        className={cn(
          "text-[11px] font-medium uppercase tracking-wider",
          muted ? "text-muted-foreground/70" : "text-muted-foreground",
        )}
      >
        {label}
      </div>
      <div
        className={cn(
          "mt-2 font-mono tabular-nums",
          muted ? "text-lg text-muted-foreground" : "text-2xl text-foreground",
        )}
      >
        {value}
      </div>
      {hint && (
        <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
      )}
    </div>
  );
}
