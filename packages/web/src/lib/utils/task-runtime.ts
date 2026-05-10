import { EVENT_TYPE } from '@kagan/shared-api-client';
import type { WireEvent } from '@kagan/shared-api-client';

export function deriveTaskRunningSince(events: WireEvent[], currentStatus: string): string | null {
  let runningSince: string | null = null;

  for (const event of events) {
    if (event.type !== EVENT_TYPE.TASK_STATUS_CHANGED || !event.payload) {
      continue;
    }

    // payload.to comes from the wire as unknown — normalise before comparing
    const to = event.payload.to;
    const nextStatus = typeof to === 'string' ? to.toUpperCase() : '';

    if (nextStatus === 'IN_PROGRESS') {
      runningSince = event.created_at;
      continue;
    }

    if (nextStatus === 'BACKLOG' || nextStatus === 'REVIEW' || nextStatus === 'DONE') {
      runningSince = null;
    }
  }

  return currentStatus.toUpperCase() === 'IN_PROGRESS' ? runningSince : null;
}
