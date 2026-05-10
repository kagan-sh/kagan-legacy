import { useState } from 'react';
import { useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { fetchTasksAtom } from '@/lib/atoms/board';
import type { WireTask } from '@kagan/shared-api-client';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';

interface TaskDeleteDialogProps {
  task: WireTask | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: (task: WireTask) => void;
}

export function TaskDeleteDialog({
  task,
  open,
  onOpenChange,
  onDeleted,
}: TaskDeleteDialogProps) {
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!task || deleting) return;
    const target = task;

    setDeleting(true);
    try {
      await apiClient.deleteTask(target.id);
      // Close the dialog before triggering the board re-fetch so the UI
      // doesn't appear frozen while tasks are reloading.
      setDeleting(false);
      onOpenChange(false);
      onDeleted?.(target);
      fetchTasks();
      toast.success('Task deleted');
    } catch (error) {
      setDeleting(false);
      toast.error(error instanceof Error ? error.message : 'Failed to delete task');
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogTitle>Delete task?</AlertDialogTitle>
          <AlertDialogDescription>
            <span className="font-medium text-[var(--foreground)]">{task?.title ?? 'This task'}</span>
            {' '}
            will be removed from the board, task workspace, and session flows.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleting || !task}
          >
            {deleting ? 'Deleting...' : 'Delete task'}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
