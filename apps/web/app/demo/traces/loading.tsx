import { Skeleton } from "@/components/ui/skeleton";

export default function TracesLoading() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <Skeleton className="h-6 w-24" />
          <Skeleton className="mt-2 h-4 w-72" />
        </div>
        <Skeleton className="h-5 w-24" />
      </header>

      <div className="rounded-lg border border-border bg-card/30">
        <div className="h-9 border-b border-border bg-muted/30" />
        <div className="divide-y divide-border">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex h-11 items-center gap-4 px-3">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-28" />
              <div className="ml-auto flex items-center gap-4">
                <Skeleton className="h-3 w-12" />
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-5 w-12" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
