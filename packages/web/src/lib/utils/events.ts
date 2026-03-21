import type { WireEvent } from '@/lib/api/types';

/** Merge and deduplicate wire events by ID, sorted chronologically. */
export function mergeWireEvents(current: WireEvent[], incoming: WireEvent[]): WireEvent[] {
  if (current.length === 0) return incoming;
  if (incoming.length === 0) return current;

  const existingIds = new Set(current.map((event) => event.id));
  const newEvents: WireEvent[] = [];
  for (const event of incoming) {
    if (existingIds.has(event.id)) continue;
    existingIds.add(event.id);
    newEvents.push(event);
  }

  if (newEvents.length === 0) return current;

  const lastCurrent = current[current.length - 1];
  const firstNew = newEvents[0];
  if (!lastCurrent || !firstNew) return current;

  const lastCurrentTs = Date.parse(lastCurrent.created_at);
  const firstNewTs = Date.parse(firstNew.created_at);

  if (firstNewTs >= lastCurrentTs) {
    return [...current, ...newEvents];
  }

  const merged = [...current, ...newEvents];
  merged.sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at));
  return merged;
}
