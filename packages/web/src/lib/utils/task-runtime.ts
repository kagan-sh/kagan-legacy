import type { TaskStatus, WireEvent } from '@kagan/shared-api-client';

const TASK_STATUS_CHANGED = 'TASK_STATUS_CHANGED';

export function deriveTaskRunningSince(events: WireEvent[], currentStatus: string): string | null {
  let runningSince: string | null = null;

  for (const event of events) {
    if (event.type !== TASK_STATUS_CHANGED || !event.payload) {
      continue;
    }

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

  const normalizedCurrentStatus = currentStatus.toUpperCase() as TaskStatus;
  return normalizedCurrentStatus === 'IN_PROGRESS' ? runningSince : null;
}
