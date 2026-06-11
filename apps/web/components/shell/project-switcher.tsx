"use client";

import { useRouter } from "next/navigation";
import { useTransition, type ChangeEvent } from "react";

import { cn } from "@/lib/utils";
import type { ProjectListItem } from "@/lib/types";

interface Props {
  projects: ProjectListItem[];
  activeProjectId: string;
}

/**
 * Project switcher rendered in the user sidebar.
 *
 * With a single project the user gets a static label - no dropdown
 * chrome until it earns its keep. With multiple projects a native
 * ``<select>`` POSTs the new id to ``/api/app/active-project`` and
 * triggers ``router.refresh()`` so the dashboard, traces, and
 * trace-detail pages re-fetch under the new scope.
 *
 * Going native here (instead of a custom dropdown menu) keeps the
 * client bundle small; a custom switcher can ship if the multi-
 * project flow becomes prominent.
 */
export function ProjectSwitcher({ projects, activeProjectId }: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  if (projects.length === 0) {
    return null;
  }

  if (projects.length === 1) {
    const p = projects[0];
    return (
      <div className="px-2 py-1.5">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
          Project
        </p>
        <p className="mt-0.5 truncate text-xs font-medium" title={p.name}>
          {p.name}
        </p>
      </div>
    );
  }

  function onChange(e: ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value;
    if (next === activeProjectId) return;
    startTransition(async () => {
      await fetch("/api/app/active-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: next }),
      });
      router.refresh();
    });
  }

  return (
    <div className="px-2 py-1.5">
      <label
        htmlFor="project-switcher"
        className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80"
      >
        Project
      </label>
      <select
        id="project-switcher"
        value={activeProjectId}
        onChange={onChange}
        disabled={pending}
        className={cn(
          "mt-0.5 w-full bg-transparent text-xs font-medium",
          "border-0 px-0 py-0 focus:outline-none focus:ring-0",
          pending && "opacity-60",
        )}
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  );
}
