import { notFound } from "next/navigation";

import { ApiError, getTrace } from "@/lib/api";

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
      {/* Retrieval cards land in the next commit. */}
    </div>
  );
}
