import { ApiConfigError, demoContext, getMetrics } from "@/lib/api";
import { parseTimeRange, timeRangeToFromTo } from "@/lib/time-range";

import { ChartCard } from "@/components/dashboard/chart-card";
import { HeroWasteCard } from "@/components/dashboard/hero-waste-card";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { ScoreHistogram } from "@/components/dashboard/score-histogram";
import { TimeRangeSelect } from "@/components/dashboard/time-range-select";
import { TracesOverTimeChart } from "@/components/dashboard/traces-over-time-chart";

interface PageProps {
  searchParams: { range?: string };
}

export default async function DashboardPage({ searchParams }: PageProps) {
  const range = parseTimeRange(searchParams.range);
  const { from, to } = timeRangeToFromTo(range);

  let metrics;
  try {
    metrics = await getMetrics(demoContext(), { from, to });
  } catch (err) {
    return <ErrorView error={err} />;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
            Demo · sample data
          </p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Retrieval quality across all traces. Click any trace to inspect its retrieval chain.
          </p>
        </div>
        <TimeRangeSelect active={range} />
      </header>

      {/* Cold-visitor framing. Static text; not amber - the wedge is the
       * hero card below, not this prose. Bold first sentence acts as a
       * soft label for what Retrace is. */}
      <section aria-label="About Retrace" className="mb-6 max-w-3xl">
        <p className="text-sm leading-relaxed text-foreground/85">
          <span className="font-medium">RAG-native observability for LLM applications.</span>{" "}
          The headline below is the share of retrieved chunks the model didn&rsquo;t cite &mdash;
          retrieval waste, made visible.
        </p>
      </section>

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
        <KpiCard variant="muted" label="Total traces" value={metrics.total_traces} />
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
