"use client";

import { KeyRound, X } from "lucide-react";

import { CopyButton } from "@/components/console/copy-button";

/** Show-once reveal for a freshly minted API key. The backend returns
 *  the raw secret exactly once at creation; this is the only place it
 *  ever reaches the browser. Kept in component state only - never
 *  persisted, never re-fetched. Neutral chrome (no amber - that accent
 *  is reserved for retrieval signal). ``onDismiss``, when given, renders
 *  a corner close button so the caller can clear the reveal. */
export function ApiKeyReveal({ rawKey, onDismiss }: { rawKey: string; onDismiss?: () => void }) {
  return (
    <div className="relative rounded-lg border border-border bg-secondary/30 p-4">
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="absolute right-2 top-2 rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      <div className="flex items-center gap-2 text-xs font-medium">
        <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
        New API key
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        Copy it now. This is the only time the full key is shown. If you lose
        it, revoke the key and create another.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-background px-3 py-2 font-mono text-xs">
          {rawKey}
        </code>
        <CopyButton value={rawKey} />
      </div>
    </div>
  );
}
