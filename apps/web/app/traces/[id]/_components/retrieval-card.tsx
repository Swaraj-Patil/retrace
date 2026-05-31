import { Search } from "lucide-react";

import { formatMs } from "@/lib/format";
import type { RetrievalDetail } from "@/lib/types";

import { ChunkRow } from "./chunk-row";

interface Props {
  retrieval: RetrievalDetail;
  index: number;
  total: number;
}

export function RetrievalCard({ retrieval, index, total }: Props) {
  const cited = retrieval.chunks.filter((c) => c.was_cited).length;

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card/30">
      <header className="border-b border-border bg-muted/20 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            {total > 1 ? `Retrieval ${index + 1} of ${total}` : "Retrieval"}
          </span>
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
            {retrieval.chunks.length} chunk{retrieval.chunks.length === 1 ? "" : "s"} ·{" "}
            <span className="text-foreground/85">{cited} cited</span>
          </span>
        </div>

        <div className="mt-2.5 flex items-start gap-2">
          <Search className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <p className="text-[15px] font-medium leading-snug text-foreground">
            {retrieval.query}
          </p>
        </div>

        <dl className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <Pair label="embedding">{retrieval.embedding_model}</Pair>
          <Pair label="top_k">
            <span className="tabular-nums">{retrieval.top_k}</span>
          </Pair>
          <Pair label="latency">
            <span className="tabular-nums">{formatMs(retrieval.latency_ms)}</span>
          </Pair>
        </dl>
      </header>

      {retrieval.chunks.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm text-muted-foreground">
          No chunks returned for this retrieval.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {retrieval.chunks.map((c) => (
            <ChunkRow key={c.chunk_id} chunk={c} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Pair({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="uppercase tracking-wider text-muted-foreground/80">{label}</span>
      <span className="text-foreground/85">{children}</span>
    </span>
  );
}
