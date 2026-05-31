import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardLoading() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <Skeleton className="h-6 w-32" />
      <Skeleton className="mt-2 h-4 w-64" />

      {/* Hero waste card skeleton */}
      <div className="mt-6 rounded-lg border border-border bg-card/30 p-6">
        <Skeleton className="h-3 w-24" />
        <div className="mt-4 flex items-end justify-between gap-4">
          <Skeleton className="h-14 w-44" />
          <Skeleton className="h-8 w-24" />
        </div>
        <Skeleton className="mt-5 h-1.5 w-full rounded-sm" />
        <Skeleton className="mt-3 h-3 w-72" />
      </div>

      {/* 3 supporting cards */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-border bg-card/30 p-4">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-3 h-7 w-16" />
            <Skeleton className="mt-2 h-3 w-32" />
          </div>
        ))}
      </div>
    </div>
  );
}
