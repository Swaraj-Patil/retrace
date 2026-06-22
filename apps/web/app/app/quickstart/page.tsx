import { redirect } from "next/navigation";

import { listApiKeys } from "@/lib/api";
import { getAuthContext } from "@/lib/auth/server";

import { Quickstart } from "./_components/quickstart";

export default async function QuickstartPage() {
  const auth = await getAuthContext();
  if (!auth || !auth.activeProject) {
    redirect("/login");
  }
  const project = auth.activeProject;

  // Whether the project already has a live key changes the framing of
  // the key step (offer to reuse vs. create a first one). Best-effort:
  // if the list call fails we just fall back to "no keys yet".
  let hasActiveKey = false;
  try {
    const { keys } = await listApiKeys(auth.token, project.id);
    hasActiveKey = keys.some((k) => k.revoked_at === null);
  } catch {
    hasActiveKey = false;
  }

  // The base URL the SDK posts to, baked at render time. Same backend
  // the web app reads from; set via RETRACE_API_URL in prod. Not a
  // secret - safe to ship into the client snippet.
  const apiUrl = (process.env.RETRACE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <header className="mb-8">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
          {project.name}
        </p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">Connect your app</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Four steps to your first trace. The SDK wraps your OpenAI and
          Anthropic calls and ships generation + retrieval telemetry to this
          project, with no code changes beyond the init call.
        </p>
      </header>

      <Quickstart projectId={project.id} apiUrl={apiUrl} hasActiveKey={hasActiveKey} />
    </div>
  );
}
