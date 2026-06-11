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

export interface AuthFormState {
  formError?: string;
  fieldErrors?: { email?: string; password?: string; name?: string };
  /** Submitted values to repopulate after a failed submit. Never password. */
  values?: { email?: string; name?: string };
}
