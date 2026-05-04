import { CreateTaskDialog } from '@/components/board/create-task-dialog';
import { EditTaskDialog } from '@/components/board/edit-task-dialog';
import { TaskDeleteDialog } from '@/components/board/task-delete-dialog';
import type { WireTask } from '@kagan/shared-api-client';
import type { BoardDialog } from '@/lib/atoms/board';

interface BoardDialogsProps {
  boardDialog: BoardDialog;
  closeDialog: () => void;
  editingTask: WireTask | null;
  deleteTask: WireTask | null;
  selectedTaskId: string | null;
  setSelectedTaskId: (id: string | null) => void;
}

export function BoardDialogs({
  boardDialog,
  closeDialog,
  editingTask,
  deleteTask,
  selectedTaskId,
  setSelectedTaskId,
}: BoardDialogsProps) {
  return (
    <>
      <CreateTaskDialog
        open={boardDialog.kind === 'create'}
        onOpenChange={(open) => { if (!open) closeDialog(); }}
      />
      <EditTaskDialog
        open={boardDialog.kind === 'edit'}
        onOpenChange={(open) => { if (!open) closeDialog(); }}
        task={editingTask}
        onUpdated={(task) => {
          setSelectedTaskId(task.id);
        }}
      />
      <TaskDeleteDialog
        task={deleteTask}
        open={boardDialog.kind === 'delete'}
        onOpenChange={(open) => { if (!open) closeDialog(); }}
        onDeleted={(task) => {
          if (selectedTaskId === task.id) {
            setSelectedTaskId(null);
          }
          closeDialog();
        }}
      />
    </>
  );
}
