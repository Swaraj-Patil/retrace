"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";

/** Two-step revoke: the first click arms an inline confirm so a stray
 *  click can't kill a live key. On confirm it DELETEs through the route
 *  handler and refreshes; the server re-render drops this control (the
 *  row is now revoked), so we leave ``pending`` set through the
 *  transition rather than resetting it. */
export function RevokeKeyButton({ projectId, keyId }: { projectId: string; keyId: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const [failed, setFailed] = React.useState(false);

  async function revoke() {
    setPending(true);
    setFailed(false);
    try {
      const res = await fetch(`/api/app/projects/${projectId}/keys/${keyId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        setFailed(true);
        setPending(false);
        setConfirming(false);
        return;
      }
      router.refresh();
    } catch {
      setFailed(true);
      setPending(false);
      setConfirming(false);
    }
  }

  if (!confirming) {
    return (
      <div className="flex items-center justify-end gap-2">
        {failed && <span className="text-xs text-destructive">Try again</span>}
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => setConfirming(true)}
        >
          Revoke
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-end gap-1.5">
      <span className="text-xs text-muted-foreground">Revoke?</span>
      <Button variant="destructive" size="sm" disabled={pending} onClick={revoke}>
        {pending ? "Revoking…" : "Confirm"}
      </Button>
      <Button variant="ghost" size="sm" disabled={pending} onClick={() => setConfirming(false)}>
        Cancel
      </Button>
    </div>
  );
}
