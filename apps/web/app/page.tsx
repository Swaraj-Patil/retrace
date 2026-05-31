import { ApiConfigError, getMetrics } from "@/lib/api";

import { HeroWasteCard } from "./_components/hero-waste-card";
import { KpiCard } from "./_components/kpi-card";

export default async function DashboardPage() {
  let metrics;
  try {
    metrics = await getMetrics();
  } catch (err) {
    return <ErrorView error={err} />;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Retrieval quality across all traces.
        </p>
      </header>

      <HeroWasteCard metrics={metrics} />

      {/* Supporting RAG metrics. None of these carry the accent - amber
       * stays reserved for the wedge insight in the hero card. */}
      <section
        aria-label="Retrieval quality metrics"
        className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3"
      >
        <KpiCard
          label="Avg top similarity"
          value={metrics.avg_top_similarity.toFixed(2)}
          hint="Rank-0 chunk score, averaged across retrievals."
        />
        <KpiCard
          label="Citation coverage"
          value={`${Math.round(metrics.citation_coverage * 100)}%`}
          hint="RAG traces that produced at least one citation."
        />
        <KpiCard
          label="RAG traces"
          value={
            <>
              {metrics.rag_traces}
              <span className="text-muted-foreground"> / {metrics.total_traces}</span>
            </>
          }
          hint="Traces with at least one retrieval."
        />
      </section>

      {/* Charts row lands in the next commit. */}

      {/* Generic supporting metrics - muted variant so they recede. */}
      <section
        aria-label="General metrics"
        className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2"
      >
        <KpiCard
          variant="muted"
          label="Avg retrieval latency"
          value={`${metrics.avg_retrieval_latency_ms} ms`}
        />
        <KpiCard
          variant="muted"
          label="Total traces"
          value={metrics.total_traces}
        />
      </section>
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
          {isConfig ? "API not configured" : "Failed to load dashboard"}
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
