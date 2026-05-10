/**
 * Shell-level wiring for popovers that need a task context.
 *
 * `MorePopover` and `AdvancePopover` accept task data as props so they can
 * be rendered locally next to a task card in tests. At the shell level we
 * resolve the task from `popoverTaskIdAtom` so triggers don't have to pass
 * props through the layout.
 */
import { useAtomValue, useSetAtom } from 'jotai';
import { popoverTaskIdAtom } from '@/lib/atoms/shell';
import { boardDialogAtom, tasksAtom } from '@/lib/atoms/board';
import type { TaskStatus, WireTask } from '@kagan/shared-api-client';
import { MorePopover } from './more-popover';
import { AdvancePopover } from './advance-popover';

function useContextTask(): WireTask | null {
  const id = useAtomValue(popoverTaskIdAtom);
  const tasks = useAtomValue(tasksAtom);
  if (!id) return null;
  return tasks.find((t) => t.id === id) ?? null;
}

export function ConnectedMorePopover() {
  const task = useContextTask();
  const setBoardDialog = useSetAtom(boardDialogAtom);
  return (
    <MorePopover
      task={task}
      onDelete={(taskId) => setBoardDialog({ kind: 'delete', taskId })}
    />
  );
}

export function ConnectedAdvancePopover() {
  const task = useContextTask();
  return (
    <AdvancePopover
      taskId={task?.id ?? null}
      currentStatus={(task?.status as TaskStatus | undefined) ?? null}
    />
  );
}
