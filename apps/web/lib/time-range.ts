/** Shared time-range constants and helpers. Lives in lib/ (not under a
 * "use client" component) so the server-side page.tsx can call into
 * it without tripping Next 14's client/server boundary check.
 *
 * Default is "7d" - matches what a production dashboard would lead
 * with. "all" omits the from/to params so the API sees no time
 * filter at all.
 */

export const TIME_RANGES = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "all", label: "All" },
] as const;

export type TimeRangeValue = (typeof TIME_RANGES)[number]["value"];

export const DEFAULT_RANGE: TimeRangeValue = "7d";

export function parseTimeRange(input: string | undefined): TimeRangeValue {
  if (!input) return DEFAULT_RANGE;
  const allowed: readonly string[] = TIME_RANGES.map((r) => r.value);
  return allowed.includes(input) ? (input as TimeRangeValue) : DEFAULT_RANGE;
}

export function timeRangeToFromTo(range: TimeRangeValue): { from?: string; to?: string } {
  if (range === "all") return {};
  const now = new Date();
  const offsets: Record<Exclude<TimeRangeValue, "all">, number> = {
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
  };
  const from = new Date(now.getTime() - offsets[range]);
  return { from: from.toISOString(), to: now.toISOString() };
}
