import Link from "next/link";

import { Brand } from "@/components/shell/brand";
import { Button } from "@/components/ui/button";

/**
 * Landing page. Brief, dev-tool-tone statement of what Retrace is with
 * three paths: view the live demo, sign up, or log in. Matches the
 * existing dense aesthetic (mono labels, restrained colour, no gradient
 * hero); amber stays reserved for retrieval signal elsewhere in the app.
 */
export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-4">
        <Brand />
        <Link
          href="/login"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          Log in
        </Link>
      </header>

      <main className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-2xl py-16">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
            RAG observability · pre-alpha
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
            See every chunk that fed every answer.
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground">
            Most tracing tools log the LLM call well but treat retrieval as a black box.
            Retrace surfaces every retrieved chunk, scores retrieval quality, links citations
            back to source, and flags answers that drift from context.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Button asChild size="lg">
              <Link href="/demo">View live demo</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/register">Sign up free</Link>
            </Button>
          </div>

          {/* A teaser drawn from the seeded demo: dense, monospaced,
           * the kind of line that signals "real numbers, not marketing".
           * Clickable through to the demo. */}
          <Link
            href="/demo"
            className="mt-10 inline-flex items-baseline gap-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground/70 transition-colors hover:text-foreground"
          >
            <span className="text-foreground/80">demo</span>
            <span>·</span>
            <span>75 traces</span>
            <span>·</span>
            <span>70% of retrieved chunks never cited</span>
            <span aria-hidden>→</span>
          </Link>
        </div>
      </main>

      <footer className="border-t border-border/60 px-6 py-4">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60">
          Python SDK · OpenAI &amp; Anthropic auto-instrumentation · Open source
        </p>
      </footer>
    </div>
  );
}
