import { redirect } from "next/navigation";

import { RagFilter } from "@/components/traces/rag-filter";
import { TraceTable } from "@/components/traces/trace-table";
import { ApiError, listTraces, type ApiContext } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";

import { EmptyTraces } from "./_components/empty-traces";

const PAGE_SIZE = 50;

interface PageProps {
  searchParams: { rag_only?: string };
}

export default async function UserTracesPage({ searchParams }: PageProps) {
  const auth = await getAuthContext();
  if (!auth || !auth.activeProject) {
    redirect("/login");
  }

  const ragOnly = searchParams.rag_only === "true";

  const apiCtx: ApiContext = {
    mode: "user",
    bearer: auth.token,
    projectId: auth.activeProject.id,
  };

  let initial;
  try {
    initial = await listTraces(apiCtx, {
      limit: PAGE_SIZE,
      offset: 0,
      rag_only: ragOnly,
    });
  } catch (err) {
    return <ErrorView error={err} />;
  }

  // The "no traces at all" empty-state only fires when the filter is
  // off too - otherwise we want the in-table empty state that explains
  // the filter is hiding rows.
  if (initial.total === 0 && !ragOnly) {
    return <EmptyTraces />;
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
            {auth.activeProject.name}
          </p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">Traces</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every LLM call captured by the SDK, newest first.
          </p>
        </div>
        <RagFilter value={ragOnly} />
      </header>

      <TraceTable
        initial={initial}
        ragOnly={ragOnly}
        apiPath="/api/app/traces"
        basePath="/app/traces"
      />
    </div>
  );
}

function ErrorView({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Unknown error";
  const isApiError = error instanceof ApiError;
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6">
        <h2 className="text-base font-semibold text-destructive">
          {isApiError ? `Backend error (${(error as ApiError).status})` : "Failed to load traces"}
        </h2>
        <p className="mt-2 font-mono text-xs text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}
