import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";

export default function TraceDetailLoading() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <Skeleton className="h-3 w-16" />
      <div className="mt-4 flex items-center gap-3">
        <Skeleton className="h-4 w-72" />
        <Skeleton className="h-5 w-12" />
      </div>
      <div className="mt-6 grid w-full max-w-md grid-cols-[max-content_1fr] gap-x-8 gap-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <React.Fragment key={i}>
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-24" />
          </React.Fragment>
        ))}
      </div>
      <Skeleton className="mt-6 h-4 w-96" />
    </div>
  );
}
