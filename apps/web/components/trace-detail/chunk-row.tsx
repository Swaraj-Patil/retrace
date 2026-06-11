"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { shortId } from "@/lib/format";
import type { ChunkDetail } from "@/lib/types";

import { ScoreBar } from "./score-bar";

/** The wedge moment.
 *
 * Cited chunks: 2px amber left stripe, faint amber-tinted background,
 * "Cited" badge in amber, full opacity. Uncited: neutral border,
 * "not cited" tag in muted, 65% opacity. Rank order preserved across
 * both states so the visual signal is the amber stripes against the
 * muted rows, not a re-ordering.
 *
 * Anchor id="chunk-{chunk_id}" lets the citations list scroll to a
 * specific chunk; the parent applies a brief amber ring on landed
 * chunks (see _components/citation-anchor.tsx).
 */
export function ChunkRow({ chunk }: { chunk: ChunkDetail }) {
  const [expanded, setExpanded] = React.useState(false);
  const cited = chunk.was_cited;
  const metaTags = describeMetadata(chunk.doc_metadata);

  return (
    <li
      id={`chunk-${chunk.chunk_id}`}
      className={cn(
        "relative scroll-mt-24 border-l-2 border-l-transparent transition-colors",
        cited
          ? "border-l-accent bg-accent/[0.03]"
          : "border-l-border opacity-65 hover:opacity-100",
      )}
    >
      <div className="flex items-start gap-4 px-3 py-2.5">
        {/* Rank + score column */}
        <div className="flex shrink-0 flex-col gap-1.5 pt-0.5">
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            rank {chunk.rank}
          </span>
          <ScoreBar score={chunk.similarity_score} />
        </div>

        {/* Content + metadata column */}
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="group block w-full text-left"
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse chunk content" : "Expand chunk content"}
          >
            <p
              className={cn(
                "whitespace-pre-wrap text-sm leading-relaxed text-foreground",
                !expanded && "line-clamp-3",
              )}
            >
              {chunk.content}
            </p>
            {chunk.content.length > 200 && (
              <span className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground group-hover:text-foreground">
                <ChevronDown
                  className={cn("h-3 w-3 transition-transform", expanded && "rotate-180")}
                />
                {expanded ? "Collapse" : "Expand"}
              </span>
            )}
          </button>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
            <span className="text-foreground/80">{chunk.source_doc_id || "—"}</span>
            {metaTags.length > 0 && <Sep />}
            {metaTags.map((m, i) => (
              <React.Fragment key={i}>
                {i > 0 && <Sep />}
                <span>{m}</span>
              </React.Fragment>
            ))}
            <Sep />
            <span className="text-muted-foreground/70">chunk {shortId(chunk.chunk_id)}</span>
          </div>
        </div>

        {/* Cited / not-cited indicator */}
        <div className="shrink-0 self-start pt-0.5">
          {cited ? (
            <Badge variant="rag">Cited</Badge>
          ) : (
            <span className="font-mono text-[11px] text-muted-foreground/70">not cited</span>
          )}
        </div>
      </div>
    </li>
  );
}

function Sep() {
  return <span className="text-muted-foreground/40">·</span>;
}

/** Render doc_metadata as a list of "key=value" tags. Skip noisy/huge
 * values; this is for at-a-glance context, not a JSON viewer. */
function describeMetadata(meta: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(meta ?? {})) {
    if (v == null) continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      out.push(`${k}=${String(v)}`);
    }
    // dicts/arrays intentionally elided
  }
  return out;
}
