"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { Plus } from "lucide-react";

import { ApiKeyReveal } from "@/components/console/api-key-reveal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CreateApiKeyResponse } from "@/lib/types";

/** Create-key form + show-once reveal. On success the raw key lives in
 *  component state (the reveal) while ``router.refresh()`` re-fetches
 *  the list below - which only carries the safe prefix. The reveal
 *  survives the refresh (client state is preserved) so the user keeps
 *  their one chance to copy until they dismiss it. */
export function CreateKeyForm({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<CreateApiKeyResponse | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || pending) return;
    setPending(true);
    setError(null);
    try {
      const res = await fetch(`/api/app/projects/${projectId}/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!res.ok) {
        setError(messageForStatus(res.status));
        setPending(false);
        return;
      }
      const key = (await res.json()) as CreateApiKeyResponse;
      setCreated(key);
      setName("");
      setPending(false);
      router.refresh();
    } catch {
      setError("Something went wrong. Try again.");
      setPending(false);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex-1">
          <Input
            name="name"
            placeholder="Key name (e.g. production, local-dev)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={pending}
            aria-label="New API key name"
            maxLength={255}
          />
          {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
        </div>
        <Button type="submit" disabled={pending || !name.trim()}>
          <Plus className="h-4 w-4" />
          {pending ? "Creating…" : "Create key"}
        </Button>
      </form>
      {created && <ApiKeyReveal rawKey={created.raw_key} onDismiss={() => setCreated(null)} />}
    </div>
  );
}

function messageForStatus(status: number): string {
  if (status === 404) return "This project is no longer available.";
  if (status === 422) return "Enter a name for the key.";
  if (status === 401) return "Your session expired. Refresh and sign in again.";
  return "Couldn't create the key. Try again.";
}
