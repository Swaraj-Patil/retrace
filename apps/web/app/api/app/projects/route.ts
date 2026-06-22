/**
 * POST /api/app/projects { name, slug? }
 *
 * Creates a project (and its owning org membership) for the caller and
 * returns the new project. The session token comes from the httpOnly
 * cookie via ``getAuthContext`` - never from the request body - so the
 * browser never handles the credential. Backend validation errors are
 * forwarded with their status so the client form can show inline
 * messages: 409 (slug already taken), 422 (name has no slug-able
 * characters and no explicit slug given).
 *
 * Called from the client ``CreateProjectForm``; on success the form
 * navigates to the new project's key page.
 */
import { NextRequest, NextResponse } from "next/server";

import { ApiError, createProject } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const auth = await getAuthContext();
  if (!auth) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  let body: { name?: unknown; slug?: unknown };
  try {
    body = (await req.json()) as { name?: unknown; slug?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_body" }, { status: 400 });
  }
  const name = typeof body.name === "string" ? body.name.trim() : "";
  const slug = typeof body.slug === "string" && body.slug.trim() ? body.slug.trim() : undefined;
  if (!name) {
    return NextResponse.json({ error: "missing_name" }, { status: 400 });
  }

  try {
    const project = await createProject(auth.token, name, slug);
    return NextResponse.json(project, { status: 201 });
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
