/**
 * POST /api/app/projects/[pid]/keys { name }
 *
 * Mints a new API key for the project and returns it - including the
 * one-time ``raw_key``, which the backend never exposes again. The
 * client surfaces ``raw_key`` exactly once (show-once reveal) and then
 * relies on the key list, which only ever carries the safe prefix.
 *
 * ``pid`` is scoped by membership on the backend: a project the caller
 * can't see returns 404, indistinguishable from "doesn't exist", so
 * the key surface can't be used to enumerate other orgs' projects.
 */
import { NextRequest, NextResponse } from "next/server";

import { ApiError, createApiKey } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest, { params }: { params: { pid: string } }) {
  const auth = await getAuthContext();
  if (!auth) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  let body: { name?: unknown };
  try {
    body = (await req.json()) as { name?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_body" }, { status: 400 });
  }
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!name) {
    return NextResponse.json({ error: "missing_name" }, { status: 400 });
  }

  try {
    const key = await createApiKey(auth.token, params.pid, name);
    return NextResponse.json(key, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: "upstream_error", upstream_status: err.status, detail: err.body },
        { status: err.status },
      );
    }
    return NextResponse.json({ error: "internal_error" }, { status: 500 });
  }
}
