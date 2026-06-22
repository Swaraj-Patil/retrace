/**
 * DELETE /api/app/projects/[pid]/keys/[kid]
 *
 * Revokes (soft-deletes) an API key. Idempotent on the backend: an
 * unknown or already-revoked key in the caller's own project still
 * returns 204; a key under a project the caller can't see returns 404,
 * indistinguishable from "doesn't exist".
 *
 * Called from the client ``RevokeKeyButton``; on success the client
 * calls ``router.refresh()`` to re-render the key list with the row
 * now showing as revoked.
 */
import { NextResponse } from "next/server";

import { ApiError, revokeApiKey } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";

export const runtime = "nodejs";

export async function DELETE(
  _req: Request,
  { params }: { params: { pid: string; kid: string } },
) {
  const auth = await getAuthContext();
  if (!auth) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  try {
    await revokeApiKey(auth.token, params.pid, params.kid);
    return new NextResponse(null, { status: 204 });
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
