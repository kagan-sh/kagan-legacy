import { useCallback } from 'react';
import { PopoverPanel, PopoverTitle, PopoverItem, useShellPopover } from '../popover';
import { apiClient } from '@/lib/api/client';
import { COLUMN_ORDER, STATUS_LABELS } from '@/lib/utils/constants';
import type { TaskStatus } from '@kagan/shared-api-client';

const STATUS_ICON: Record<TaskStatus, React.ReactNode> = {
  BACKLOG: <span style={{ color: 'var(--muted-foreground)' }}>▸</span>,
  IN_PROGRESS: <span style={{ color: 'var(--kagan-rail-warning)' }}>∿</span>,
  REVIEW: <span style={{ color: 'var(--kagan-rail-review)' }}>R</span>,
  DONE: <span style={{ color: 'var(--kagan-rail-running)' }}>✓</span>,
};

const STATUS_DESC: Record<TaskStatus, string> = {
  BACKLOG: 'Queue task, not yet started',
  IN_PROGRESS: 'Agent running in worktree',
  REVIEW: 'Mark ready for human review',
  DONE: 'Approved and merged to main',
};

interface AdvancePopoverProps {
  taskId: string | null;
  currentStatus: TaskStatus | null;
  onTransitioned?: (taskId: string, status: TaskStatus) => void;
}

export function AdvancePopover({ taskId, currentStatus, onTransitioned }: AdvancePopoverProps) {
  const { close } = useShellPopover('advance', 'right');

  const transition = useCallback(
    async (status: TaskStatus) => {
      if (!taskId) return;
      try {
        await apiClient.transitionStatus(taskId, status);
        onTransitioned?.(taskId, status);
      } catch {
        // silently ignore — the board SSE stream will reconcile
      }
      close();
    },
    [taskId, close, onTransitioned],
  );

  return (
    <PopoverPanel kind="advance">
      <PopoverTitle>Advance status</PopoverTitle>
      {COLUMN_ORDER.map((status) => (
        <PopoverItem
          key={status}
          icon={STATUS_ICON[status]}
          label={STATUS_LABELS[status]}
          desc={STATUS_DESC[status]}
          active={status === currentStatus}
          onClick={() => transition(status)}
        />
      ))}
    </PopoverPanel>
  );
}
