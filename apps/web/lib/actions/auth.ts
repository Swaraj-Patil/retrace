"use server";

/**
 * Server actions for login, register, and logout.
 *
 * Each action runs entirely on the Next server: it talks to FastAPI
 * via ``lib/api.ts``, sets or clears the ``retrace_session`` httpOnly
 * cookie via ``next/headers``, and either redirects the navigation
 * (success) or returns an ``AuthFormState`` for inline display
 * (validation / auth failures). ``redirect()`` is called outside the
 * try/catch because it works by throwing a special error that Next
 * handles; a catch would swallow it.
 *
 * CSRF posture: the session cookie is ``SameSite=Lax`` + ``httpOnly``,
 * so cross-site form posts cannot replay it - Next-Action POSTs from
 * a third-party origin are blocked at the browser layer. No CSRF token
 * is added here; the same posture covers the ``/api/app/*`` mutation
 * route handlers in Commit 4.
 *
 * The form state echoes back the submitted ``email`` (and ``name`` on
 * register) so the user does not have to retype them after an error.
 * Passwords are never echoed.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  ApiError,
  backendLogin,
  backendLogout,
  backendRegister,
} from "@/lib/api";
import { SESSION_COOKIE, type AuthFormState } from "@/lib/auth/cookie";

function setSessionCookie(token: string, expiresAtIso: string): void {
  cookies().set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    // Only mark Secure in production - the dev server is http://localhost.
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires: new Date(expiresAtIso),
  });
}

function mapValidationError(body: unknown, submitted: { email?: string; name?: string }): AuthFormState {
  // FastAPI 422 shape: ``{ detail: [{ type, loc, msg, ctx, input }, ...] }``.
  // ``loc`` is typically ``["body", "<field>"]`` for field-level errors and
  // ``["body"]`` for a model-level (model_validator) error. We map known
  // field names; anything else falls back to a form-level error.
  const fieldErrors: NonNullable<AuthFormState["fieldErrors"]> = {};
  let formError: string | undefined;
  const detail = (body as { detail?: unknown[] } | null | undefined)?.detail;
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const it = item as { loc?: unknown[]; msg?: string } | null;
      const loc = it?.loc;
      const msg = humanize(it?.msg ?? "Invalid value.");
      const field = Array.isArray(loc) && loc[1] ? String(loc[1]) : undefined;
      if (field === "email") fieldErrors.email = msg;
      else if (field === "password") fieldErrors.password = msg;
      else if (field === "name") fieldErrors.name = msg;
      else if (!formError) formError = msg;
    }
  }
  if (!formError && Object.keys(fieldErrors).length === 0) {
    formError = "Please check the form and try again.";
  }
  return { formError, fieldErrors, values: submitted };
}

function humanize(msg: string): string {
  // Pydantic prepends ``"Value error, "`` on field/model validators.
  return msg.replace(/^Value error,\s*/, "");
}

export async function loginAction(
  _prevState: AuthFormState | null,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const submitted = { email };

  if (!email) {
    return { fieldErrors: { email: "Enter your email." }, values: submitted };
  }
  if (!password) {
    return { fieldErrors: { password: "Enter your password." }, values: submitted };
  }

  try {
    const { token, expires_at } = await backendLogin(email, password);
    setSessionCookie(token, expires_at);
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 401) {
        return { formError: "Invalid email or password.", values: submitted };
      }
      if (err.status === 429) {
        return {
          formError: "Too many attempts. Wait a minute and try again.",
          values: submitted,
        };
      }
      if (err.status === 422) {
        return mapValidationError(err.body, submitted);
      }
    }
    return {
      formError: "Something went wrong. Please try again.",
      values: submitted,
    };
  }
  redirect("/app");
}

export async function registerAction(
  _prevState: AuthFormState | null,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const nameRaw = String(formData.get("name") ?? "").trim();
  const name = nameRaw || undefined;
  const submitted = { email, name };

  if (!email) {
    return { fieldErrors: { email: "Enter your email." }, values: submitted };
  }
  if (!password) {
    return { fieldErrors: { password: "Choose a password." }, values: submitted };
  }
  if (password.length < 8) {
    return {
      fieldErrors: { password: "Password must be at least 8 characters." },
      values: submitted,
    };
  }

  try {
    const { token, expires_at } = await backendRegister(email, password, name);
    setSessionCookie(token, expires_at);
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 409) {
        return {
          fieldErrors: { email: "An account with this email already exists." },
          values: submitted,
        };
      }
      if (err.status === 422) {
        return mapValidationError(err.body, submitted);
      }
    }
    return {
      formError: "Something went wrong. Please try again.",
      values: submitted,
    };
  }
  redirect("/app");
}

export async function logoutAction(): Promise<void> {
  const token = cookies().get(SESSION_COOKIE)?.value;
  if (token) {
    try {
      await backendLogout(token);
    } catch {
      // Backend revocation failed (network, 5xx, etc.). The cookie
      // is still cleared below so the local session ends either way;
      // the backend row will hit ``expires_at`` on its own.
    }
  }
  cookies().delete(SESSION_COOKIE);
  redirect("/");
}
