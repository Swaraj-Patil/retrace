import { cn } from "@/lib/utils";
import type { MetricsOverviewResponse } from "@/lib/types";

interface Props {
  metrics: MetricsOverviewResponse;
}

/** The wedge in macro view.
 *
 * "X% never cited" leads in XL amber; "Y% utilized" complements in muted.
 * A horizontal proportion bar visualizes the split so the ratio is
 * literal, not just a number. The waste framing is the wedge insight no
 * general-purpose observability tool surfaces - this card's job is to
 * make a dev feel it.
 *
 * Total chunk count is derived from score_distribution buckets (the
 * histogram sum is the chunk denominator), so "14 of 20 chunks" is a
 * real number, not an estimate.
 */
export function HeroWasteCard({ metrics }: Props) {
  const totalChunks = metrics.score_distribution.reduce((sum, b) => sum + b.count, 0);
  const neverCitedPct = Math.round(metrics.chunks_never_cited_rate * 100);
  const utilizedPct = 100 - neverCitedPct;
  const neverCitedChunks = Math.round(totalChunks * metrics.chunks_never_cited_rate);

  const hasData = totalChunks > 0;

  return (
    <section
      aria-labelledby="hero-waste-title"
      className="rounded-lg border border-border bg-card/30 p-6"
    >
      <h2
        id="hero-waste-title"
        className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground"
      >
        Retrieval waste
      </h2>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-baseline gap-2 font-mono tabular-nums">
            <span className={cn("text-6xl font-semibold leading-none", hasData ? "text-accent" : "text-muted-foreground")}>
              {hasData ? `${neverCitedPct}%` : "-"}
            </span>
            <span className="text-sm font-medium text-foreground">never cited</span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {hasData
              ? "of retrieved chunks were not used in any citation."
              : "No retrievals captured yet."}
          </p>
        </div>

        <div className="text-right">
          <div className="flex items-baseline gap-2 font-mono tabular-nums text-muted-foreground">
            <span className="text-2xl font-medium">{hasData ? `${utilizedPct}%` : "-"}</span>
            <span className="text-xs">utilized</span>
          </div>
        </div>
      </div>

      {/* Horizontal proportion bar. Amber on the left = waste. Muted on
       * the right = the part that was actually used. */}
      <div
        className="mt-5 flex h-1.5 overflow-hidden rounded-sm bg-muted"
        role="img"
        aria-label={`${neverCitedPct} percent never cited, ${utilizedPct} percent utilized`}
      >
        {hasData && (
          <>
            <div className="bg-accent" style={{ width: `${neverCitedPct}%` }} />
            <div className="bg-muted-foreground/45" style={{ width: `${utilizedPct}%` }} />
          </>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs tabular-nums text-muted-foreground">
        {hasData ? (
          <>
            <span>
              <span className="text-foreground/85">{neverCitedChunks}</span> of{" "}
              <span className="text-foreground/85">{totalChunks}</span> chunks
            </span>
            <Sep />
            <span>
              <span className="text-foreground/85">{metrics.rag_traces}</span> RAG{" "}
              {metrics.rag_traces === 1 ? "trace" : "traces"}
            </span>
          </>
        ) : (
          <span>0 chunks · 0 RAG traces</span>
        )}
      </div>
    </section>
  );
}

function Sep() {
  return <span className="text-muted-foreground/40">·</span>;
}
