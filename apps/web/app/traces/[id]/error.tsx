"use client";

import Link from "next/link";
import { AlertCircle, ArrowLeft, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Segment error boundary. Catches anything that isn't a notFound() -
 * could be an upstream API outage, a malformed payload, an RSC
 * render-time bug, anything thrown inside the page tree. Notably
 * does NOT catch 404s because the page calls notFound() before
 * throwing, which routes to not-found.tsx separately.
 *
 * Copy is intentionally cause-agnostic: the boundary doesn't know
 * whether the failure was network, data, or render. In production
 * Next strips the error to {message, digest} for security so even
 * a runtime check wouldn't reliably tell us. Neutral default is
 * correct - the ref id below is what support actually uses. */
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
          href="/traces"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to traces
        </Link>
      </div>
    </div>
  );
}
