import { format, formatDistanceToNowStrict, parseISO } from "date-fns";

export function relativeTime(iso: string): string {
  return formatDistanceToNowStrict(parseISO(iso), { addSuffix: true });
}

export function absoluteTime(iso: string): string {
  // Locked to UTC so server and client agree on the display until we
  // adopt a user-timezone story. Fine for the demo.
  return format(parseISO(iso), "yyyy-MM-dd HH:mm:ss 'UTC'");
}

/** Date only, e.g. ``Jun 21, 2026``. Used for created/revoked stamps
 *  in the console where time-of-day is noise. */
export function dateOnly(iso: string): string {
  return format(parseISO(iso), "MMM d, yyyy");
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/** Compact integer (1.2k, 12.3k). Falls back to the raw number under 1000. */
export function compactInt(n: number): string {
  if (n < 1000) return n.toString();
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

/** Truncate a UUID for display: first 8 chars. */
export function shortId(id: string): string {
  return id.slice(0, 8);
}
