import { CreateTaskDialog } from '@/components/board/create-task-dialog';
import { EditTaskDialog } from '@/components/board/edit-task-dialog';
import { TaskDeleteDialog } from '@/components/board/task-delete-dialog';
import { BoardTaskPeekDialog } from '@/components/board/board-task-inspector';
import type { WireTask } from '@/lib/api/types';
import type { BoardDialog } from '@/lib/atoms/board';

interface BoardDialogsProps {
  boardDialog: BoardDialog;
  closeDialog: () => void;
  editingTask: WireTask | null;
  deleteTask: WireTask | null;
  peekTask: WireTask | null;
  selectedTaskId: string | null;
  setSelectedTaskId: (id: string | null) => void;
  onOpenTask: (task: WireTask) => void;
  onOpenStream: () => void;
  onEditTask: (task: WireTask) => void;
  onDeleteTask: (task: WireTask) => void;
}

export function BoardDialogs({
  boardDialog,
  closeDialog,
  editingTask,
  deleteTask,
  peekTask,
  selectedTaskId,
  setSelectedTaskId,
  onOpenTask,
  onOpenStream,
  onEditTask,
  onDeleteTask,
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
      <BoardTaskPeekDialog
        task={peekTask}
        open={boardDialog.kind === 'peek'}
        onOpenChange={(open) => { if (!open) closeDialog(); }}
        onOpenTask={() => {
          if (!peekTask) return;
          closeDialog();
          onOpenTask(peekTask);
        }}
        onOpenStream={() => {
          closeDialog();
          onOpenStream();
        }}
        onEdit={() => {
          if (!peekTask) return;
          onEditTask(peekTask);
        }}
        onDelete={() => {
          if (!peekTask) return;
          onDeleteTask(peekTask);
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
