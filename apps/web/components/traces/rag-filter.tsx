"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Switch } from "@/components/ui/switch";

export function RagFilter({ value }: { value: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = React.useTransition();

  function toggle(checked: boolean) {
    const params = new URLSearchParams(sp.toString());
    if (checked) params.set("rag_only", "true");
    else params.delete("rag_only");
    const q = params.toString();
    startTransition(() => {
      router.push(q ? `${pathname}?${q}` : pathname);
    });
  }

  return (
    <label
      htmlFor="rag-only"
      className="inline-flex select-none items-center gap-2 text-sm text-muted-foreground"
    >
      <Switch
        id="rag-only"
        checked={value}
        onCheckedChange={toggle}
        disabled={pending}
        aria-label="Toggle RAG-only filter"
      />
      <span>RAG only</span>
    </label>
  );
}
