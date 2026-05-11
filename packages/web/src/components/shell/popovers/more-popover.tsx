import { useNavigate } from 'react-router';
import { useAtom } from 'jotai';
import { shellPopoverAtom } from '@/lib/atoms/shell';
import { PopoverPanel, PopoverTitle, PopoverItem, PopoverSeparator, useShellPopover } from '../popover';
import type { WireTask } from '@kagan/shared-api-client';

interface MorePopoverProps {
  task: WireTask | null;
  onDelete?: (taskId: string) => void;
}

/**
 * Task actions popover ("more" button on workspace head or task card).
 * Anchors next to the "more" trigger button.
 */
export function MorePopover({ task, onDelete }: MorePopoverProps) {
  const { close } = useShellPopover('more', 'right');
  const navigate = useNavigate();
  const [popover, setPopover] = useAtom(shellPopoverAtom);

  const copyId = () => {
    if (task) {
      navigator.clipboard.writeText(task.id).catch(() => {});
    }
    close();
  };

  const openBoard = () => {
    if (task) navigate(`/task/${task.id}`);
    close();
  };

  const advanceStatus = () => {
    if (!popover.anchor) return;
    // Re-use the same anchor but switch to advance popover
    setPopover({ kind: 'advance', anchor: popover.anchor });
  };

  const deleteTask = () => {
    if (task && onDelete) onDelete(task.id);
    close();
  };

  return (
    <PopoverPanel kind="more">
      <PopoverTitle>Task actions</PopoverTitle>
      <PopoverItem
        icon={<span>⎘</span>}
        label="Copy task ID"
        desc="Copy to clipboard"
        onClick={copyId}
      />
      <PopoverItem
        icon={<span style={{ color: 'var(--primary)' }}>⊞</span>}
        label="Open in board"
        desc="Open in board"
        onClick={openBoard}
      />
      <PopoverItem
        icon={<span style={{ color: 'var(--kagan-rail-warning)' }}>›</span>}
        label="Advance status"
        desc="Move to next stage"
        onClick={advanceStatus}
      />
      <PopoverSeparator />
      <PopoverItem
        icon={<span style={{ color: '#e85535' }}>✕</span>}
        label="Delete task"
        desc="Remove from board"
        danger
        onClick={deleteTask}
      />
    </PopoverPanel>
  );
}
