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
