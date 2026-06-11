import { notFound, redirect } from "next/navigation";

import { CitationsList } from "@/components/trace-detail/citations-list";
import { RetrievalCard } from "@/components/trace-detail/retrieval-card";
import { TraceHeader } from "@/components/trace-detail/trace-header";
import { ApiError, getTrace, type ApiContext } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";

interface PageProps {
  params: { id: string };
}

export default async function UserTraceDetailPage({ params }: PageProps) {
  const auth = await getAuthContext();
  if (!auth || !auth.activeProject) {
    redirect("/login");
  }

  const apiCtx: ApiContext = {
    mode: "user",
    bearer: auth.token,
    projectId: auth.activeProject.id,
  };

  let detail;
  try {
    detail = await getTrace(apiCtx, params.id);
  } catch (err) {
    // The backend returns 404 ``project_not_found`` for cross-org access
    // (the auth dep's membership check fires before the trace lookup)
    // *and* ``trace_not_found`` for an unknown id in the caller's own
    // project. Both surface as 404 from FastAPI, both render the same
    // not-found.tsx here - the user cannot distinguish either way.
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <TraceHeader detail={detail} backHref="/app/traces" />

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

      <CitationsList citations={detail.citations} retrievals={detail.retrievals} />
    </div>
  );
}
