import Link from "next/link";

import { Brand } from "@/components/shell/brand";

/**
 * Stub login page. Real form arrives in Commit 2 (session plumbing).
 * Kept as a routable placeholder so the landing-page CTA resolves to a
 * real page during the Commit 1 smoke pass.
 */
export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-4">
        <Link href="/" aria-label="Retrace home">
          <Brand />
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-sm py-16">
          <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign-in form lands in the next commit.
          </p>
          <p className="mt-6 text-sm text-muted-foreground">
            Need an account?{" "}
            <Link href="/register" className="text-foreground hover:underline">
              Sign up free
            </Link>
            .
          </p>
        </div>
      </main>
    </div>
  );
}
