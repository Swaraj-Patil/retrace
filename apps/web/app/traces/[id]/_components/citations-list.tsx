import { ArrowRight, Quote } from "lucide-react";

import { shortId } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CitationDetail, RetrievalDetail } from "@/lib/types";

interface Props {
  citations: CitationDetail[];
  retrievals: RetrievalDetail[];
}

/** Citations section.
 *
 * Each citation references a chunk_id; we render its rank when the
 * chunk is also present in this trace's retrievals (the common case),
 * and an "orphan" note when it isn't (e.g., the chunk pre-dated this
 * trace's batch). Clicking a citation jumps to the chunk above via
 * anchor link. The chunk row's :target animation does the highlight.
 */
export function CitationsList({ citations, retrievals }: Props) {
  if (citations.length === 0) return null;

  const chunkRank = new Map<string, number>();
  for (const r of retrievals) {
    for (const c of r.chunks) chunkRank.set(c.chunk_id, c.rank);
  }

  return (
    <section className="mt-10">
      <header className="mb-3 flex items-baseline gap-2">
        <h2 className="text-sm font-semibold tracking-tight">Citations</h2>
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
          ({citations.length})
        </span>
      </header>

      <ol className="overflow-hidden rounded-lg border border-border bg-card/30">
        {citations.map((cit) => {
          const rank = chunkRank.get(cit.chunk_id);
          const isOrphan = rank === undefined;
          return (
            <li
              key={cit.citation_id}
              className="flex items-center gap-3 border-b border-border px-4 py-2.5 text-sm last:border-b-0"
            >
              <Quote className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />

              <a
                href={`#chunk-${cit.chunk_id}`}
                className={cn(
                  "inline-flex items-center gap-2 transition-colors",
                  isOrphan
                    ? "cursor-default text-muted-foreground"
                    : "text-foreground hover:text-accent",
                )}
                aria-disabled={isOrphan}
                onClick={(e) => {
                  if (isOrphan) e.preventDefault();
                }}
              >
                <span className="font-mono text-xs">chunk {shortId(cit.chunk_id)}</span>
                {rank !== undefined && (
                  <span className="font-mono text-[11px] text-muted-foreground">
                    (rank {rank})
                  </span>
                )}
              </a>

              <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground/60" />

              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                chars{" "}
                <span className="text-foreground/85">
                  {cit.response_span_start}&ndash;{cit.response_span_end}
                </span>
              </span>

              {isOrphan && (
                <span className="ml-auto font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  orphan
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
