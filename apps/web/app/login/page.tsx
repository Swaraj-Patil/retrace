import Link from "next/link";

import { Brand } from "@/components/shell/brand";

import { LoginForm } from "./_components/login-form";

export const metadata = {
  title: "Log in · Retrace",
};

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-4">
        <Link href="/" aria-label="Retrace home">
          <Brand />
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-sm py-12">
          <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Welcome back.
          </p>

          <div className="mt-8">
            <LoginForm />
          </div>

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
