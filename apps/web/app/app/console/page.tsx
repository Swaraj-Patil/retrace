import Link from "next/link";
import { redirect } from "next/navigation";
import { ChevronRight, KeyRound } from "lucide-react";

import { getAuthContext } from "@/lib/auth/server";
import { dateOnly } from "@/lib/format";

import { CreateProjectForm } from "./_components/create-project-form";

export default async function ConsolePage() {
  const auth = await getAuthContext();
  if (!auth) {
    redirect("/login");
  }
  const { projects } = auth;

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Console</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your projects and the API keys that authorize the SDK to send telemetry.
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-medium">Projects</h2>
        <CreateProjectForm />

        <ul className="mt-4 divide-y divide-border overflow-hidden rounded-lg border border-border">
          {projects.map((p) => (
            <li key={p.id}>
              <Link
                href={`/app/console/${p.id}/keys`}
                className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-secondary/40"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{p.name}</p>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">
                    {p.slug} · {p.org_name} · {p.role}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                  <span className="hidden sm:inline">created {dateOnly(p.created_at)}</span>
                  <KeyRound className="h-4 w-4" />
                  <ChevronRight className="h-4 w-4" />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
