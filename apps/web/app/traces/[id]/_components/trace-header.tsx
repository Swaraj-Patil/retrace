import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { absoluteTime, compactInt, formatMs, relativeTime } from "@/lib/format";
import type { TraceDetailResponse } from "@/lib/types";

import { CopyIdButton } from "./copy-id-button";

interface Props {
  detail: TraceDetailResponse;
}

export function TraceHeader({ detail }: Props) {
  const { trace, retrievals, citations } = detail;
  const summary = computeRetrievalSummary(detail);
  const isError = trace.status.toLowerCase() === "error";

  return (
    <header>
      <Link
        href="/traces"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Traces
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-xs uppercase tracking-wider text-muted-foreground">Trace</span>
        <code className="font-mono text-sm text-foreground">{trace.trace_id}</code>
        <CopyIdButton value={trace.trace_id} />
        <Badge variant={isError ? "destructive" : "success"}>{trace.status.toLowerCase()}</Badge>
      </div>

      <dl className="mt-6 grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:max-w-md sm:grid-cols-[max-content_1fr]">
        <Row label="Model">
          <span className="font-mono">{trace.model}</span>
        </Row>
        <Row label="Latency">
          <span className="tabular-nums">{formatMs(trace.latency_ms)}</span>
        </Row>
        <Row label="Tokens">
          <span className="font-mono tabular-nums">
            {compactInt(trace.tokens_in)}
            <span className="px-1 text-muted-foreground/60">/</span>
            <span className="text-muted-foreground">{compactInt(trace.tokens_out)}</span>
          </span>
        </Row>
        <Row label="Started">
          <TooltipProvider delayDuration={300}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="cursor-default tabular-nums">{relativeTime(trace.start_time)}</span>
              </TooltipTrigger>
              <TooltipContent>
                <span className="font-mono text-[11px]">{absoluteTime(trace.start_time)}</span>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </Row>
      </dl>

      {retrievals.length > 0 && (
        <p className="mt-6 font-mono text-sm tabular-nums">
          <span className="text-muted-foreground">
            {summary.totalChunks} {summary.totalChunks === 1 ? "chunk" : "chunks"} retrieved
          </span>
          <Sep />
          <span className="font-medium text-foreground">
            {summary.citedChunks} cited
          </span>
          <Sep />
          <span className="text-muted-foreground">
            {summary.uncitedPct}% uncited
          </span>
          {citations.length > 0 && retrievals.length > 1 && (
            <>
              <Sep />
              <span className="text-muted-foreground">
                {retrievals.length} retrievals
              </span>
            </>
          )}
        </p>
      )}
    </header>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-xs uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function Sep() {
  return <span className="mx-2 text-muted-foreground/40">·</span>;
}

/** Total chunks retrieved across all retrievals, distinct chunks that were
 * cited (intersection of citations' chunk_ids with retrieved chunk_ids),
 * and the uncited percentage. */
function computeRetrievalSummary(detail: TraceDetailResponse) {
  const allChunkIds = new Set<string>();
  for (const r of detail.retrievals) for (const c of r.chunks) allChunkIds.add(c.chunk_id);
  const totalChunks = allChunkIds.size;

  const citedIds = new Set<string>();
  for (const cit of detail.citations) {
    if (allChunkIds.has(cit.chunk_id)) citedIds.add(cit.chunk_id);
  }
  const citedChunks = citedIds.size;

  const uncitedPct = totalChunks === 0 ? 0 : Math.round(((totalChunks - citedChunks) / totalChunks) * 100);

  return { totalChunks, citedChunks, uncitedPct };
}
