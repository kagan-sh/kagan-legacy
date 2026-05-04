import { atom } from 'jotai';
import type { ClientPresence } from '@kagan/shared-api-client';

/** Active client presence records. */
export const presenceAtom = atom<ClientPresence[]>([]);

/** Watchers grouped by task ID. */
export const taskWatchersAtom = atom((get) => {
  const presence = get(presenceAtom);
  const byTask = new Map<string, ClientPresence[]>();
  for (const p of presence) {
    if (p.active_task_id) {
      const existing = byTask.get(p.active_task_id) ?? [];
      existing.push(p);
      byTask.set(p.active_task_id, existing);
    }
  }
  return byTask;
});
