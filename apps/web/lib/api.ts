/**
 * Server-only API client for the FastAPI backend.
 *
 * Two auth modes, one module:
 *
 * * **Demo mode** uses the project-scoped ``RETRACE_API_KEY`` env var
 *   and omits ``project_id`` from the query - the API resolves the
 *   project from the key. This is the read path for the public
 *   showcase under ``/demo``.
 * * **User mode** uses the visitor's ``rts_`` session cookie (set
 *   server-side after login/register) and adds ``?project_id=`` for
 *   the active project. This is the read path for the authenticated
 *   app under ``/app`` (wired in Commit 3).
 *
 * The ``server-only`` import below is the load-bearing security
 * boundary. If any client component imports this file the build
 * fails, keeping both the demo key and the session cookie out of the
 * browser bundle. Mutations from the app go through ``/api/app/*``
 * route handlers that wrap these functions server-side; ``SameSite=Lax``
 * on the session cookie covers CSRF at this scale - no token needed.
 */
import "server-only";

import type {
  ListTracesParams,
  MeResponse,
  MetricsOverviewResponse,
  MetricsParams,
  SessionTokenResponse,
  TraceDetailResponse,
  TraceListResponse,
} from "@/lib/types";

const DEFAULT_API_URL = "http://localhost:8000";

/** Context object the read functions consume. Callers construct one
 *  per request via {@link demoContext} (server components on the demo
 *  pages) or via the user-mode helpers wired in Commit 2. */
export type ApiContext =
  | { mode: "demo"; bearer: string }
  | { mode: "user"; bearer: string; projectId: string };

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

/** Read ``RETRACE_API_KEY`` and return a demo context. Throws
 *  {@link ApiConfigError} when the env var is missing so the calling
 *  page can render a configuration-specific error view. */
export function demoContext(): ApiContext {
  const key = process.env.RETRACE_API_KEY;
  if (!key) {
    throw new ApiConfigError(
      "RETRACE_API_KEY is not set. Copy apps/web/.env.example to .env.local and fill it in.",
    );
  }
  return { mode: "demo", bearer: key };
}

function apiBaseUrl(): string {
  return (process.env.RETRACE_API_URL ?? DEFAULT_API_URL).replace(/\/$/, "");
}

interface RequestOptions {
  cache?: RequestCache;
  revalidate?: number;
}

async function request<T>(
  ctx: ApiContext,
  path: string,
  searchParams: Record<string, string | number | boolean | undefined>,
  opts: RequestOptions = {},
): Promise<T> {
  // User mode passes the active project_id through to the API; demo
  // mode never does (the API resolves it from the key). Either way,
  // ``ctx.bearer`` is the only place the credential surfaces - never
  // returned to the caller, never logged.
  const params: Record<string, string | number | boolean | undefined> = { ...searchParams };
  if (ctx.mode === "user") {
    params.project_id = ctx.projectId;
  }
  const qs = buildQueryString(params);
  const fullUrl = `${apiBaseUrl()}${path}${qs ? `?${qs}` : ""}`;

  const res = await fetch(fullUrl, {
    headers: {
      Authorization: `Bearer ${ctx.bearer}`,
      Accept: "application/json",
    },
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

export async function listTraces(
  ctx: ApiContext,
  params: ListTracesParams = {},
): Promise<TraceListResponse> {
  return request<TraceListResponse>(ctx, "/v1/traces", {
    limit: params.limit,
    offset: params.offset,
    rag_only: params.rag_only,
    from: params.from,
    to: params.to,
  });
}

export async function getTrace(ctx: ApiContext, traceId: string): Promise<TraceDetailResponse> {
  return request<TraceDetailResponse>(ctx, `/v1/traces/${encodeURIComponent(traceId)}`, {});
}

export async function getMetrics(
  ctx: ApiContext,
  params: MetricsParams = {},
): Promise<MetricsOverviewResponse> {
  return request<MetricsOverviewResponse>(ctx, "/v1/metrics/overview", {
    from: params.from,
    to: params.to,
  });
}

// ---------------------------------------------------------------------------
// Backend auth helpers
//
// These talk to /v1/auth/{login,register,logout,me} without an
// ``ApiContext`` because they're the ones that *produce* the credential
// (login, register) or operate on it directly (logout, me). They're
// called only from server actions; the response token never crosses
// the server/client boundary except as a ``Set-Cookie`` header.
// ---------------------------------------------------------------------------

async function unauthenticatedPost<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`${apiBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let errorBody: unknown = null;
    try {
      errorBody = await res.json();
    } catch {
      // Non-JSON error body; leave null.
    }
    throw new ApiError(res.status, errorBody);
  }
  return (await res.json()) as T;
}

export async function backendLogin(
  email: string,
  password: string,
): Promise<SessionTokenResponse> {
  return unauthenticatedPost<SessionTokenResponse>("/v1/auth/login", {
    email,
    password,
  });
}

export async function backendRegister(
  email: string,
  password: string,
  name?: string,
): Promise<SessionTokenResponse> {
  return unauthenticatedPost<SessionTokenResponse>("/v1/auth/register", {
    email,
    password,
    ...(name ? { name } : {}),
  });
}

export async function backendLogout(token: string): Promise<void> {
  const res = await fetch(`${apiBaseUrl()}/v1/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  // 204 expected. 401 means the token is already stale (expired/
  // revoked) - the caller is logging out anyway, so swallow it.
  // Anything else is unexpected; surface it.
  if (!res.ok && res.status !== 401) {
    throw new ApiError(res.status, null);
  }
}

export async function backendMe(token: string): Promise<MeResponse> {
  const res = await fetch(`${apiBaseUrl()}/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    let errorBody: unknown = null;
    try {
      errorBody = await res.json();
    } catch {
      // Non-JSON error body; leave null.
    }
    throw new ApiError(res.status, errorBody);
  }
  return (await res.json()) as MeResponse;
}
