"use client";

import Link from "next/link";
import { AlertCircle, ArrowLeft, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function TraceDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-start gap-4 px-6 py-16">
      <div className="flex h-10 w-10 items-center justify-center rounded-md bg-destructive/15">
        <AlertCircle className="h-5 w-5 text-destructive" />
      </div>
      <div>
        <h1 className="text-xl font-semibold tracking-tight">
          Something went wrong loading this trace
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          We couldn&rsquo;t show this trace. Try again, or head back to the list.
        </p>
        {error.digest && (
          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
            ref: <span className="text-foreground/85">{error.digest}</span>
          </p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={reset}>
          <RotateCw className="h-3.5 w-3.5" />
          Try again
        </Button>
        <Link
          href="/app/traces"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to traces
        </Link>
      </div>
    </div>
  );
}
