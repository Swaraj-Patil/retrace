import Link from "next/link";
import { ArrowLeft, SearchX } from "lucide-react";

export default function TraceNotFound() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-start gap-4 px-6 py-16">
      <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
        <SearchX className="h-5 w-5 text-muted-foreground" />
      </div>
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Trace not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This trace doesn&rsquo;t exist under this project. It may have been deleted, or the URL
          may be from a different project.
        </p>
      </div>
      <Link
        href="/traces"
        className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to traces
      </Link>
    </div>
  );
}
