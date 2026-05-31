import { notFound } from "next/navigation";

import { ApiError, getTrace } from "@/lib/api";

import { RetrievalCard } from "./_components/retrieval-card";
import { TraceHeader } from "./_components/trace-header";

interface PageProps {
  params: { id: string };
}

export default async function TraceDetailPage({ params }: PageProps) {
  let detail;
  try {
    detail = await getTrace(params.id);
  } catch (err) {
    // Both unknown-trace and cross-project access surface as 404 from the
    // API. notFound() renders the segment's not-found.tsx; anything else
    // propagates to error.tsx (or the global error boundary).
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <TraceHeader detail={detail} />

      {detail.retrievals.length > 0 && (
        <div className="mt-10 space-y-6">
          {detail.retrievals.map((r, i) => (
            <RetrievalCard
              key={r.retrieval_id}
              retrieval={r}
              index={i}
              total={detail.retrievals.length}
            />
          ))}
        </div>
      )}

      {/* Citations section lands in the next commit. */}
    </div>
  );
}
