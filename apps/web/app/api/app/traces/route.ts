/**
 * Load-more proxy for the per-user trace list.
 *
 * Same shape as ``/api/demo/traces``, but the credential is the user
 * session cookie (forwarded as the bearer to FastAPI) and the active
 * project resolves through ``getAuthContext`` - cookie value if set,
 * else the user's first project, mirroring the layout's behaviour so
 * a load-more click can never miss the active project a fresh user
 * never explicitly picked.
 */
import { NextRequest, NextResponse } from "next/server";

import { ApiError, listTraces, type ApiContext } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";

export const runtime = "nodejs";

function parseIntParam(value: string | null, fallback: number): number {
  if (value === null) return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export async function GET(req: NextRequest) {
  const auth = await getAuthContext();
  if (!auth || !auth.activeProject) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  const ctx: ApiContext = {
    mode: "user",
    bearer: auth.token,
    projectId: auth.activeProject.id,
  };
  const sp = req.nextUrl.searchParams;

  try {
    const data = await listTraces(ctx, {
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
