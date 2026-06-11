"use client";

import { useFormState, useFormStatus } from "react-dom";
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { loginAction } from "@/lib/actions/auth";
import type { AuthFormState } from "@/lib/auth/cookie";

/** Submit button reads pending state from the parent form via
 *  ``useFormStatus`` (which only works inside a ``<form>``), so the
 *  button can disable itself during the action's argon2 verify
 *  without the parent having to track ``isPending`` separately. */
function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending} className="w-full">
      {pending ? "Logging in..." : "Log in"}
    </Button>
  );
}

const INITIAL_STATE: AuthFormState = {};

export function LoginForm() {
  const [state, formAction] = useFormState(loginAction, INITIAL_STATE);

  return (
    <form action={formAction} className="grid gap-4" noValidate>
      {state.formError && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{state.formError}</span>
        </div>
      )}

      <div className="grid gap-1.5">
        <label htmlFor="email" className="text-xs font-medium">
          Email
        </label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          defaultValue={state.values?.email ?? ""}
          aria-invalid={state.fieldErrors?.email ? "true" : undefined}
        />
        {state.fieldErrors?.email && (
          <p className="text-xs text-destructive">{state.fieldErrors.email}</p>
        )}
      </div>

      <div className="grid gap-1.5">
        <label htmlFor="password" className="text-xs font-medium">
          Password
        </label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          aria-invalid={state.fieldErrors?.password ? "true" : undefined}
        />
        {state.fieldErrors?.password && (
          <p className="text-xs text-destructive">{state.fieldErrors.password}</p>
        )}
      </div>

      <SubmitButton />
    </form>
  );
}
