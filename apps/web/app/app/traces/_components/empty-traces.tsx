import Link from "next/link";
import { Inbox, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Traces-list empty-state. Same load-bearing bridge to the
 *  quickstart as the dashboard's, kept visually consistent with the
 *  ``EmptyState`` rendered inside the trace table - same dashed
 *  border, same restraint on amber. */
export function EmptyTraces() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <div className="flex flex-col items-start gap-4 rounded-lg border border-dashed border-border p-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
          <Inbox className="h-5 w-5 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-base font-semibold tracking-tight">No traces yet</h2>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            Send your first trace through the SDK and it shows up here, newest
            first. The quickstart has the exact snippet for your project.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/app/quickstart">
            <Zap className="h-3.5 w-3.5" />
            Open quickstart
          </Link>
        </Button>
      </div>
    </div>
  );
}
