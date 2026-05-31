"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";

import { TIME_RANGES, type TimeRangeValue, DEFAULT_RANGE } from "@/lib/time-range";
import { cn } from "@/lib/utils";

/** Tab-bar style range picker. Active state uses neutral contrast,
 * never amber - amber is reserved for retrieval signals, and a UI
 * affordance for "currently selected" isn't one.
 *
 * The default range is omitted from the URL (clean URL on initial
 * load), other ranges set ?range=...
 */
export function TimeRangeSelect({ active }: { active: TimeRangeValue }) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = React.useTransition();

  function pick(value: TimeRangeValue) {
    const q = value === DEFAULT_RANGE ? "" : `?range=${value}`;
    startTransition(() => {
      router.push(`${pathname}${q}`);
    });
  }

  return (
    <div
      role="tablist"
      aria-label="Time range"
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-card/50 p-0.5",
        pending && "opacity-70",
      )}
    >
      {TIME_RANGES.map((r) => {
        const isActive = active === r.value;
        return (
          <button
            key={r.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => pick(r.value)}
            disabled={pending}
            className={cn(
              "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors",
              isActive
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}
