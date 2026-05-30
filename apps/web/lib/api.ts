/**
 * Server-only API client for the FastAPI read endpoints.
 *
 * The "server-only" import is the load-bearing security boundary: if
 * anyone imports this module into a client component, the build fails.
 * That keeps RETRACE_API_KEY out of the browser bundle. Route handlers
 * and server components are the only call sites.
 */
import "server-only";

import type {
  ListTracesParams,
  MetricsOverviewResponse,
  MetricsParams,
  TraceDetailResponse,
  TraceListResponse,
} from "@/lib/types";

const DEFAULT_API_URL = "http://localhost:8000";

function getConfig(): { url: string; key: string } {
  const url = process.env.RETRACE_API_URL ?? DEFAULT_API_URL;
  const key = process.env.RETRACE_API_KEY;
  if (!key) {
    throw new ApiConfigError(
      "RETRACE_API_KEY is not set. Copy apps/web/.env.example to .env.local and fill it in.",
    );
  }
  return { url: url.replace(/\/$/, ""), key };
}

export class ApiConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigError";
  }
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `Retrace API error: ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions {
  /** Force a fresh fetch (default: revalidate every 5s for dashboards). */
  cache?: RequestCache;
  /** Override Next 14's revalidate window. */
  revalidate?: number;
}

async function request<T>(
  path: string,
  searchParams: Record<string, string | number | boolean | undefined>,
  opts: RequestOptions = {},
): Promise<T> {
  const { url, key } = getConfig();
  const qs = buildQueryString(searchParams);
  const fullUrl = `${url}${path}${qs ? `?${qs}` : ""}`;

  const res = await fetch(fullUrl, {
    headers: {
      Authorization: `Bearer ${key}`,
      Accept: "application/json",
    },
    // Next.js fetch caching: short revalidation by default. Dashboards are
    // not real-time but should reflect new traces within a few seconds.
    next: opts.revalidate !== undefined ? { revalidate: opts.revalidate } : { revalidate: 5 },
    cache: opts.cache,
  });

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // Non-JSON error body; leave null.
    }
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

function buildQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    sp.set(k, String(v));
  }
  return sp.toString();
}

export async function listTraces(params: ListTracesParams = {}): Promise<TraceListResponse> {
  return request<TraceListResponse>("/v1/traces", {
    limit: params.limit,
    offset: params.offset,
    rag_only: params.rag_only,
    from: params.from,
    to: params.to,
  });
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return request<TraceDetailResponse>(`/v1/traces/${encodeURIComponent(traceId)}`, {});
}

export async function getMetrics(params: MetricsParams = {}): Promise<MetricsOverviewResponse> {
  return request<MetricsOverviewResponse>("/v1/metrics/overview", {
    from: params.from,
    to: params.to,
  });
}
