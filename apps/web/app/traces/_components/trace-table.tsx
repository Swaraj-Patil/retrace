"use client";

import * as React from "react";
import Link from "next/link";
import { AlertCircle, Inbox, Layers } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { absoluteTime, compactInt, formatMs, relativeTime, shortId } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TraceListItem, TraceListResponse } from "@/lib/types";

const PAGE_SIZE = 50;

interface Props {
  initial: TraceListResponse;
  ragOnly: boolean;
}

export function TraceTable({ initial, ragOnly }: Props) {
  const [items, setItems] = React.useState<TraceListItem[]>(initial.traces);
  const [offset, setOffset] = React.useState<number>(initial.traces.length);
  const total = initial.total;
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // If the filter changes (parent re-renders with a new `initial`), reset.
  React.useEffect(() => {
    setItems(initial.traces);
    setOffset(initial.traces.length);
    setError(null);
  }, [initial]);

  async function loadMore() {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
        ...(ragOnly ? { rag_only: "true" } : {}),
      });
      const res = await fetch(`/api/traces?${qs.toString()}`, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }
      const data = (await res.json()) as TraceListResponse;
      setItems((prev) => [...prev, ...data.traces]);
      setOffset((prev) => prev + data.traces.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load more traces");
    } finally {
      setLoading(false);
    }
  }

  if (items.length === 0) {
    return <EmptyState ragOnly={ragOnly} />;
  }

  const canLoadMore = items.length < total;

  return (
    <TooltipProvider delayDuration={300}>
      <div className="rounded-lg border border-border bg-card/30">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[120px]">Trace</TableHead>
              <TableHead className="w-[140px]">Time</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right w-[90px]">Latency</TableHead>
              <TableHead className="text-right w-[120px]">Tokens (in/out)</TableHead>
              <TableHead className="w-[80px]">RAG</TableHead>
              <TableHead className="text-right w-[80px]">Chunks</TableHead>
              <TableHead className="text-right w-[80px]">Cited</TableHead>
              <TableHead className="w-[90px]">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((t) => (
              <TraceRow key={t.trace_id} trace={t} />
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
        <span className="tabular-nums">
          Showing <span className="font-medium text-foreground">{items.length}</span> of{" "}
          <span className="font-medium text-foreground">{total}</span>
          {ragOnly && (
            <span className="ml-1 text-muted-foreground">
              (filtered to RAG traces)
            </span>
          )}
        </span>

        {canLoadMore && (
          <Button
            variant="outline"
            size="sm"
            onClick={loadMore}
            disabled={loading}
            className="font-medium"
          >
            {loading ? "Loading..." : `Load ${Math.min(PAGE_SIZE, total - items.length)} more`}
          </Button>
        )}
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5" />
          <span>{error}</span>
        </div>
      )}
    </TooltipProvider>
  );
}

function TraceRow({ trace }: { trace: TraceListItem }) {
  const isError = trace.status.toLowerCase() === "error";
  return (
    <TableRow>
      <TableCell className="font-mono text-xs">
        <Link
          href={`/traces/${trace.trace_id}`}
          className="text-foreground hover:text-accent transition-colors"
        >
          {shortId(trace.trace_id)}
        </Link>
      </TableCell>

      <TableCell className="text-muted-foreground">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-default">{relativeTime(trace.start_time)}</span>
          </TooltipTrigger>
          <TooltipContent>
            <span className="font-mono text-[11px]">{absoluteTime(trace.start_time)}</span>
          </TooltipContent>
        </Tooltip>
      </TableCell>

      <TableCell className="font-mono text-xs">{trace.model}</TableCell>

      <TableCell className="text-right tabular-nums">{formatMs(trace.latency_ms)}</TableCell>

      <TableCell className="text-right font-mono text-xs tabular-nums">
        <span className="text-foreground">{compactInt(trace.tokens_in)}</span>
        <span className="px-1 text-muted-foreground/60">/</span>
        <span className="text-muted-foreground">{compactInt(trace.tokens_out)}</span>
      </TableCell>

      <TableCell>
        {trace.has_retrieval ? (
          <Badge variant="rag">
            <Layers className="h-3 w-3" />
            RAG
          </Badge>
        ) : (
          <span className="text-muted-foreground/60">&mdash;</span>
        )}
      </TableCell>

      <TableCell className={cn("text-right tabular-nums", !trace.has_retrieval && "text-muted-foreground/60")}>
        {trace.has_retrieval ? trace.chunk_count : <>&mdash;</>}
      </TableCell>

      <TableCell className={cn("text-right tabular-nums", !trace.has_retrieval && "text-muted-foreground/60")}>
        {trace.has_retrieval ? trace.citation_count : <>&mdash;</>}
      </TableCell>

      <TableCell>
        <Badge variant={isError ? "destructive" : "success"}>{trace.status.toLowerCase()}</Badge>
      </TableCell>
    </TableRow>
  );
}

function EmptyState({ ragOnly }: { ragOnly: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border py-16 text-center">
      <Inbox className="h-8 w-8 text-muted-foreground/60" />
      <div>
        <p className="text-sm font-medium">No traces yet</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {ragOnly
            ? "No RAG traces match the current filter. Try toggling it off."
            : "Send your first trace through the SDK and it will appear here."}
        </p>
      </div>
    </div>
  );
}
