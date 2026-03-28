/**
 * Parse a backend timestamp as UTC.
 *
 * The Kagan backend stores timestamps in SQLite as naive UTC strings
 * (e.g. "2026-03-16T12:04:42.430663") without a trailing "Z".
 * JavaScript's Date constructor treats such strings as local time,
 * which shifts them by the user's timezone offset.
 *
 * This helper appends "Z" when missing so the timestamp is correctly
 * interpreted as UTC and then displayed in the user's local timezone.
 */
export function parseUtc(value: string): Date {
  return new Date(value.endsWith('Z') ? value : `${value}Z`);
}

/** Like Date.parse but treats naive timestamps as UTC. */
export function parseUtcMs(value: string): number {
  return parseUtc(value).getTime();
}

/** Human-friendly relative timestamp: "just now", "5m", "3h", "2d". */
export function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - parseUtc(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}
