import Link from "next/link";
import { Zap } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  projectName: string;
}

/** Dashboard empty-state for a brand-new user with zero traces.
 *  The bridge to /app/quickstart is the load-bearing CTA - the
 *  whole register-to-first-trace flow lives in that one click. */
export function EmptyDashboard({ projectName }: Props) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
        {projectName} · no traces yet
      </p>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight">
        Connect your app to get started.
      </h1>
      <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">
        Send a trace through the SDK and this dashboard fills in with retrieval
        quality, citation coverage, and per-trace inspection. The quickstart
        walks you through it in under a minute.
      </p>
      <div className="mt-7">
        <Button asChild>
          <Link href="/app/quickstart">
            <Zap className="h-4 w-4" />
            Open quickstart
          </Link>
        </Button>
      </div>
    </div>
  );
}
