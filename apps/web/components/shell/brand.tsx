import { cn } from "@/lib/utils";

/** The wordmark. The amber dot is the only chrome that ever uses the accent
 * outside of "this trace is RAG" - keeps the meaning of the accent tight. */
export function Brand({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className="relative flex h-6 w-6 items-center justify-center">
        <div className="absolute inset-0 rounded-md bg-accent/15" aria-hidden />
        <div className="relative h-2 w-2 rounded-full bg-accent" aria-hidden />
      </div>
      <span className="text-sm font-semibold tracking-tight">Retrace</span>
    </div>
  );
}
