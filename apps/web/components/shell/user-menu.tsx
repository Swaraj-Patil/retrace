"use client";

import { LogOut } from "lucide-react";
import { useFormStatus } from "react-dom";

import { logoutAction } from "@/lib/actions/auth";
import { cn } from "@/lib/utils";

interface Props {
  email: string;
  name: string | null;
}

function LogoutButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      aria-label="Log out"
      title={pending ? "Logging out..." : "Log out"}
      className={cn(
        "rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:opacity-50",
      )}
    >
      <LogOut className="h-3.5 w-3.5" />
    </button>
  );
}

/** Footer row: caller's identity + a logout button bound to the
 *  ``logoutAction`` server action. The form-action pattern means
 *  logout works even with JS disabled (the action handles the
 *  cookie clear + redirect server-side). */
export function UserMenu({ email, name }: Props) {
  return (
    <div className="flex items-center justify-between gap-2 px-2 py-1.5">
      <div className="flex min-w-0 flex-col leading-tight">
        {name && (
          <span className="truncate text-xs font-medium" title={name}>
            {name}
          </span>
        )}
        <span
          className={cn(
            "truncate font-mono text-[10px] text-muted-foreground",
            !name && "text-xs",
          )}
          title={email}
        >
          {email}
        </span>
      </div>
      <form action={logoutAction}>
        <LogoutButton />
      </form>
    </div>
  );
}
