"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Inline create-project form. POSTs the name to the route handler
 *  (slug is derived server-side), then navigates straight to the new
 *  project's key page - the next thing a user wants is a key. The
 *  backend surfaces two expected failures: a derived-slug collision
 *  (409) and a name with no slug-able characters (422). */
export function CreateProjectForm() {
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || pending) return;
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/app/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!res.ok) {
        setError(messageForStatus(res.status));
        setPending(false);
        return;
      }
      const project = (await res.json()) as { id: string };
      router.push(`/app/console/${project.id}/keys`);
      router.refresh();
    } catch {
      setError("Something went wrong. Try again.");
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <div className="flex-1">
        <Input
          name="name"
          placeholder="New project name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={pending}
          aria-label="New project name"
          maxLength={255}
        />
        {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
      </div>
      <Button type="submit" disabled={pending || !name.trim()}>
        <Plus className="h-4 w-4" />
        {pending ? "Creating…" : "Create project"}
      </Button>
    </form>
  );
}

function messageForStatus(status: number): string {
  if (status === 409) return "A project with that name already exists. Try another.";
  if (status === 422) return "Use a name with at least one letter or number.";
  if (status === 401) return "Your session expired. Refresh and sign in again.";
  return "Couldn't create the project. Try again.";
}
