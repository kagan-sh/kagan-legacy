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
