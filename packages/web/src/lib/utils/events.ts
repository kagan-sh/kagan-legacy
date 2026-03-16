import type { WireEvent } from '@/lib/api/types';

/** Merge and deduplicate wire events by ID, sorted chronologically. */
export function mergeWireEvents(current: WireEvent[], incoming: WireEvent[]): WireEvent[] {
  const byId = new Map<string, WireEvent>();
  for (const event of current) byId.set(event.id, event);
  for (const event of incoming) byId.set(event.id, event);
  return [...byId.values()].sort(
    (left, right) => Date.parse(left.created_at) - Date.parse(right.created_at),
  );
}

/**
 * Return up to `limit` unique session IDs from `events`, ordered by first
 * appearance (earliest timestamp first).  Position 0 = worker, 1 = reviewer.
 */
export function buildSessionOrder(events: WireEvent[], limit = 2): string[] {
  const firstSeen = new Map<string, number>();
  for (const event of events) {
    const sessionId = event.session_id;
    if (!sessionId) continue;
    if (firstSeen.has(sessionId)) continue;
    const parsed = Date.parse(event.created_at);
    const timestamp = Number.isFinite(parsed) ? parsed : 0;
    firstSeen.set(sessionId, timestamp);
  }

  return [...firstSeen.entries()]
    .sort((a, b) => a[1] - b[1])
    .slice(0, limit)
    .map(([sessionId]) => sessionId);
}

/**
 * Filter events for a given lane (worker / reviewer) using session ordering.
 * Returns an empty array when the lane has no matching session — never falls
 * back to showing the other lane's events.
 */
export function filterEventsForLane(
  events: WireEvent[],
  sessionOrder: string[],
  lane: 'worker' | 'reviewer',
): WireEvent[] {
  const laneSessionId = lane === 'reviewer' ? sessionOrder[1] : sessionOrder[0];

  // No sessions discovered at all — show everything (initial load / empty state)
  if (sessionOrder.length === 0) return events;

  // Lane has no session yet (e.g. reviewer not started) — empty
  if (!laneSessionId) return [];

  return events.filter((event) => event.session_id === laneSessionId);
}
