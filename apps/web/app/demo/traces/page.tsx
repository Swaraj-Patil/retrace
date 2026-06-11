import { ApiConfigError, demoContext, listTraces } from "@/lib/api";

import { RagFilter } from "@/components/traces/rag-filter";
import { TraceTable } from "@/components/traces/trace-table";

const PAGE_SIZE = 50;

interface PageProps {
  searchParams: { rag_only?: string };
}

export default async function TracesPage({ searchParams }: PageProps) {
  const ragOnly = searchParams.rag_only === "true";

  let initial;
  try {
    initial = await listTraces(demoContext(), {
      limit: PAGE_SIZE,
      offset: 0,
      rag_only: ragOnly,
    });
  } catch (err) {
    return <ErrorView error={err} />;
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Traces</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every LLM call captured by the SDK, newest first.
          </p>
        </div>
        <RagFilter value={ragOnly} />
      </header>

      <TraceTable
        initial={initial}
        ragOnly={ragOnly}
        apiPath="/api/demo/traces"
        basePath="/demo/traces"
      />
    </div>
  );
}

function ErrorView({ error }: { error: unknown }) {
  const isConfig = error instanceof ApiConfigError;
  const message = error instanceof Error ? error.message : "Unknown error";
  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6">
        <h2 className="text-base font-semibold text-destructive">
          {isConfig ? "API not configured" : "Failed to load traces"}
        </h2>
        <p className="mt-2 font-mono text-xs text-muted-foreground">{message}</p>
        {isConfig && (
          <p className="mt-4 text-sm text-muted-foreground">
            Set <code className="rounded bg-muted px-1.5 py-0.5 font-mono">RETRACE_API_KEY</code>{" "}
            in <code className="rounded bg-muted px-1.5 py-0.5 font-mono">apps/web/.env.local</code>.
            Run <code className="rounded bg-muted px-1.5 py-0.5 font-mono">make seed</code> for a
            fresh demo key.
          </p>
        )}
      </div>
    </div>
  );
}
