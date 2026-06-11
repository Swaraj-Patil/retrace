/**
 * POST /api/app/active-project { project_id }
 *
 * Sets the ``retrace_active_project`` cookie so subsequent /app pages
 * scope to the chosen project. The pointer is non-credential, but the
 * handler still validates that ``project_id`` is one of the caller's
 * memberships - tampering yields a 404, never cross-org leakage.
 *
 * Called from the client ``ProjectSwitcher``; on success the switcher
 * triggers ``router.refresh()`` to re-render the tree against the new
 * scope.
 */
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { ApiError, backendListProjects } from "@/lib/api";
import { ACTIVE_PROJECT_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookie";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  let body: { project_id?: unknown };
  try {
    body = (await req.json()) as { project_id?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_body" }, { status: 400 });
  }
  const projectId = typeof body.project_id === "string" ? body.project_id : null;
  if (!projectId) {
    return NextResponse.json({ error: "missing_project_id" }, { status: 400 });
  }

  // Validate against the caller's actual memberships - membership is
  // the only thing that prevents cookie tampering from being a
  // navigation footgun later.
  let projects;
  try {
    projects = (await backendListProjects(token)).projects;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
    }
    return NextResponse.json({ error: "internal_error" }, { status: 500 });
  }
  if (!projects.some((p) => p.id === projectId)) {
    return NextResponse.json({ error: "project_not_found" }, { status: 404 });
  }

  cookieStore.set(ACTIVE_PROJECT_COOKIE, projectId, {
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    // 1y - not a credential; the value gets re-validated against
    // membership on every read anyway.
    maxAge: 60 * 60 * 24 * 365,
  });
  return NextResponse.json({ ok: true });
}
