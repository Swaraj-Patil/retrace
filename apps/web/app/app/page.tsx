import { redirect } from "next/navigation";

import { ChartCard } from "@/components/dashboard/chart-card";
import { HeroWasteCard } from "@/components/dashboard/hero-waste-card";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { ScoreHistogram } from "@/components/dashboard/score-histogram";
import { TimeRangeSelect } from "@/components/dashboard/time-range-select";
import { TracesOverTimeChart } from "@/components/dashboard/traces-over-time-chart";
import { ApiError, getMetrics, type ApiContext } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";
import { parseTimeRange, timeRangeToFromTo } from "@/lib/time-range";

import { EmptyDashboard } from "./_components/empty-dashboard";

interface PageProps {
  searchParams: { range?: string };
}

export default async function UserDashboardPage({ searchParams }: PageProps) {
  // Layout already validated the session, but a direct route hit (or a
  // race where the cookie disappears between layout and page) needs
  // the same guard. The cached call shares the result with the layout.
  const auth = await getAuthContext();
  if (!auth || !auth.activeProject) {
    redirect("/login");
  }

  const range = parseTimeRange(searchParams.range);
  const { from, to } = timeRangeToFromTo(range);

  const apiCtx: ApiContext = {
    mode: "user",
    bearer: auth.token,
    projectId: auth.activeProject.id,
  };

  let metrics;
  try {
    metrics = await getMetrics(apiCtx, { from, to });
  } catch (err) {
    return <ErrorView error={err} />;
  }

  if (metrics.total_traces === 0) {
    return <EmptyDashboard projectName={auth.activeProject.name} />;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
            {auth.activeProject.name}
          </p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Retrieval quality across your traces. Click any trace to inspect its
            retrieval chain.
          </p>
        </div>
        <TimeRangeSelect active={range} />
      </header>

      <HeroWasteCard metrics={metrics} />

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
              <span className="text-muted-foreground">
                {" "}
                / {metrics.total_traces}
              </span>
            </>
          }
          hint="Traces with at least one retrieval."
        />
      </section>

      <section
        aria-label="Distributions"
        className="mt-8 grid grid-cols-1 gap-3 lg:grid-cols-2"
      >
        <ChartCard
          label="Similarity score distribution"
          hint="Across all retrieved chunks"
        >
          <ScoreHistogram data={metrics.score_distribution} />
        </ChartCard>
        <ChartCard label="Traces over time" hint="Daily counts">
          <TracesOverTimeChart data={metrics.traces_over_time} />
        </ChartCard>
      </section>

      <section
        aria-label="General metrics"
        className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2"
      >
        <KpiCard
          variant="muted"
          label="Avg retrieval latency"
          value={`${metrics.avg_retrieval_latency_ms} ms`}
        />
        <KpiCard variant="muted" label="Total traces" value={metrics.total_traces} />
      </section>
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
          {isApiError ? `Backend error (${(error as ApiError).status})` : "Failed to load dashboard"}
        </h2>
        <p className="mt-2 font-mono text-xs text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}
