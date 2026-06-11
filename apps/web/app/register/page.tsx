import Link from "next/link";

import { Brand } from "@/components/shell/brand";

import { RegisterForm } from "./_components/register-form";

export const metadata = {
  title: "Sign up · Retrace",
};

export default function RegisterPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-4">
        <Link href="/" aria-label="Retrace home">
          <Brand />
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-sm py-12">
          <h1 className="text-2xl font-semibold tracking-tight">Sign up</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Free. No card required.
          </p>

          <div className="mt-8">
            <RegisterForm />
          </div>

          <p className="mt-6 text-sm text-muted-foreground">
            Have an account?{" "}
            <Link href="/login" className="text-foreground hover:underline">
              Log in
            </Link>
            .
          </p>
        </div>
      </main>
    </div>
  );
}
