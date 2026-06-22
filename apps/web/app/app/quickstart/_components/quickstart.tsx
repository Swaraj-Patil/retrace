"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { BarChart3, ListTree, Plus } from "lucide-react";

import { ApiKeyReveal } from "@/components/console/api-key-reveal";
import { CopyButton } from "@/components/console/copy-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { CreateApiKeyResponse } from "@/lib/types";

const PLACEHOLDER_KEY = "rt_your_api_key";

interface Props {
  projectId: string;
  apiUrl: string;
  hasActiveKey: boolean;
}

/** Interactive connect-your-LLM flow. The key the user mints here is
 *  the only time the raw secret exists in the browser, so we hold it in
 *  state and splice it straight into the init snippet below - copy the
 *  snippet and the key goes with it. Before a key is created the snippet
 *  shows a placeholder. ``apiUrl`` is baked server-side from
 *  RETRACE_API_URL; it's not a secret. */
export function Quickstart({ projectId, apiUrl, hasActiveKey }: Props) {
  const router = useRouter();
  const [keyName, setKeyName] = React.useState("quickstart");
  const [created, setCreated] = React.useState<CreateApiKeyResponse | null>(null);
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const apiKeyForSnippet = created?.raw_key ?? PLACEHOLDER_KEY;
  const installCmd = `pip install "retrace-sdk[openai]"`;
  const initSnippet = `import retrace
from openai import OpenAI

retrace.init(
    api_key="${apiKeyForSnippet}",
    endpoint="${apiUrl}",
)

# Your existing OpenAI calls are now traced automatically.
client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello, Retrace!"}],
)
print(resp.choices[0].message.content)`;

  async function createKey() {
    const name = keyName.trim() || "quickstart";
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const res = await fetch(`/api/app/projects/${projectId}/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        setError(messageForStatus(res.status));
        setPending(false);
        return;
      }
      const key = (await res.json()) as CreateApiKeyResponse;
      setCreated(key);
      setPending(false);
      router.refresh();
    } catch {
      setError("Something went wrong. Try again.");
      setPending(false);
    }
  }

  return (
    <div className="space-y-8">
      <Step n={1} title="Install the SDK">
        <p className="mb-3 text-sm text-muted-foreground">
          Python 3.12+. The <code className="font-mono text-xs">[openai]</code> extra pulls in the
          OpenAI client; swap it for <code className="font-mono text-xs">[anthropic]</code> if that
          is your provider.
        </p>
        <CodeBlock code={installCmd} />
      </Step>

      <Step n={2} title="Create an API key">
        {created ? (
          <>
            <p className="text-sm text-muted-foreground">
              Done. This key is already filled into the snippet below. Copy it
              somewhere safe now; it won&apos;t be shown again.
            </p>
            <div className="mt-3">
              <ApiKeyReveal rawKey={created.raw_key} />
            </div>
          </>
        ) : (
          <>
            {hasActiveKey && (
              <p className="text-sm text-muted-foreground">
                This project already has an active key. Paste the one you saved
                into the snippet below, or mint a fresh one here.
              </p>
            )}
            <div
              className={cn(
                "flex flex-col gap-2 sm:flex-row sm:items-start",
                hasActiveKey && "mt-3",
              )}
            >
              <div className="flex-1">
                <Input
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="Key name"
                  aria-label="API key name"
                  disabled={pending}
                  maxLength={255}
                />
                {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
              </div>
              <Button onClick={createKey} disabled={pending}>
                <Plus className="h-4 w-4" />
                {pending ? "Creating…" : "Create key"}
              </Button>
            </div>
          </>
        )}
      </Step>

      <Step n={3} title="Initialize and trace">
        <p className="mb-3 text-sm text-muted-foreground">
          Call <code className="font-mono text-xs">retrace.init()</code> once at startup. From then
          on your LLM calls are captured automatically. To attach retrieval
          context, wrap a call with{" "}
          <code className="font-mono text-xs">retrace.trace_retrieval(...)</code> and log chunks via{" "}
          <code className="font-mono text-xs">retrace.log_chunks(...)</code>.
        </p>
        <CodeBlock code={initSnippet} />
      </Step>

      <Step n={4} title="Watch traces land">
        <p className="mb-3 text-sm text-muted-foreground">
          Run your app, then come back. Traces show up within seconds, newest
          first.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/app">
              <BarChart3 className="h-3.5 w-3.5" />
              Dashboard
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/app/traces">
              <ListTree className="h-3.5 w-3.5" />
              Traces
            </Link>
          </Button>
        </div>
      </Step>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-2.5">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium tabular-nums">
          {n}
        </span>
        <h2 className="text-sm font-semibold">{title}</h2>
      </div>
      <div className="mt-3 sm:pl-[2.1rem]">{children}</div>
    </section>
  );
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-lg border border-border bg-muted/40 p-4 text-xs leading-relaxed">
        <code className="font-mono">{code}</code>
      </pre>
      <div className="absolute right-2 top-2">
        <CopyButton value={code} />
      </div>
    </div>
  );
}

function messageForStatus(status: number): string {
  if (status === 404) return "This project is no longer available.";
  if (status === 422) return "Enter a name for the key.";
  if (status === 401) return "Your session expired. Refresh and sign in again.";
  return "Couldn't create the key. Try again.";
}
