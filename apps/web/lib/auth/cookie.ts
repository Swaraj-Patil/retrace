/**
 * Shared auth primitives that aren't themselves server actions.
 *
 * Next 14 restricts ``"use server"`` files to async-function exports
 * only, so the cookie name and form-state type live here instead of
 * alongside the actions. Imported by both ``lib/actions/auth.ts`` and
 * the consumers that need to read the cookie (the ``/app`` layout in
 * Commit 3 and the client form components).
 */

export const SESSION_COOKIE = "retrace_session";

/** Active-project preference. NOT a credential - just a pointer to
 *  which of the caller's projects the /app pages should scope to.
 *  The server validates membership before serving any data, so
 *  cookie tampering yields a 404 via the membership check, never
 *  cross-org leakage. Non-httpOnly so the client switcher can
 *  read/clear it if needed (though all writes go through the
 *  /api/app/active-project handler, which validates membership). */
export const ACTIVE_PROJECT_COOKIE = "retrace_active_project";

export interface AuthFormState {
  formError?: string;
  fieldErrors?: { email?: string; password?: string; name?: string };
  /** Submitted values to repopulate after a failed submit. Never password. */
  values?: { email?: string; name?: string };
}
