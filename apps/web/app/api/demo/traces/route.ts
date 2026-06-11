/**
 * Read-side proxy used by the client TraceTable's "Load more" button.
 *
 * The initial page render hits lib/api.ts directly inside the RSC.
 * Subsequent paginated fetches come through here so the bearer token
 * stays server-side. The route handler does no work beyond forwarding;
 * lib/api.ts is the source of truth for headers, caching, and error
 * shape.
 */
import { NextRequest, NextResponse } from "next/server";

import { ApiError, demoContext, listTraces } from "@/lib/api";

export const runtime = "nodejs";

function parseIntParam(value: string | null, fallback: number): number {
  if (value === null) return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  try {
    const data = await listTraces(demoContext(), {
      limit: parseIntParam(sp.get("limit"), 50),
      offset: parseIntParam(sp.get("offset"), 0),
      rag_only: sp.get("rag_only") === "true",
      from: sp.get("from") ?? undefined,
      to: sp.get("to") ?? undefined,
    });
    return NextResponse.json(data);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: "upstream_error", upstream_status: err.status },
        { status: err.status },
      );
    }
    return NextResponse.json({ error: "internal_error" }, { status: 500 });
  }
}
