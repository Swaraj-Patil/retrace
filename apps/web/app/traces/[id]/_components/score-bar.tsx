import { cn } from "@/lib/utils";

/** Similarity score: mono number + thin magnitude bar.
 * Bar fill is neutral on purpose - coloring by quality would
 * fight the amber-means-retrieval discipline. */
export function ScoreBar({ score, className }: { score: number; className?: string }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  return (
    <div className={cn("inline-flex items-center gap-2 font-mono text-xs tabular-nums", className)}>
      <span className="w-10 text-right text-foreground">{score.toFixed(2)}</span>
      <div
        className="h-1.5 w-16 overflow-hidden rounded-sm bg-muted"
        role="img"
        aria-label={`similarity ${score.toFixed(2)}`}
      >
        <div
          className="h-full bg-muted-foreground/55"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
