import { CreateTaskDialog } from '@/components/board/create-task-dialog';
import { EditTaskDialog } from '@/components/board/edit-task-dialog';
import { TaskDeleteDialog } from '@/components/board/task-delete-dialog';
import { BoardTaskPeekDialog } from '@/components/board/board-task-inspector';
import type { WireTask } from '@/lib/api/types';

interface BoardDialogsProps {
  createOpen: boolean;
  setCreateOpen: (open: boolean) => void;
  editingTask: WireTask | null;
  setEditingTask: (task: WireTask | null) => void;
  deleteTask: WireTask | null;
  setDeleteTask: (task: WireTask | null) => void;
  peekTask: WireTask | null;
  peekOpen: boolean;
  setPeekOpen: (open: boolean) => void;
  selectedTaskId: string | null;
  setSelectedTaskId: (id: string | null) => void;
  onOpenTask: (task: WireTask) => void;
  onOpenStream: () => void;
}

export function BoardDialogs({
  createOpen,
  setCreateOpen,
  editingTask,
  setEditingTask,
  deleteTask,
  setDeleteTask,
  peekTask,
  peekOpen,
  setPeekOpen,
  selectedTaskId,
  setSelectedTaskId,
  onOpenTask,
  onOpenStream,
}: BoardDialogsProps) {
  return (
    <>
      <CreateTaskDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
      <EditTaskDialog
        open={Boolean(editingTask)}
        onOpenChange={(open) => {
          if (!open) setEditingTask(null);
        }}
        task={editingTask}
        onUpdated={(task) => {
          setEditingTask(task);
          setSelectedTaskId(task.id);
        }}
      />
      <BoardTaskPeekDialog
        task={peekTask}
        open={peekOpen}
        onOpenChange={setPeekOpen}
        onOpenTask={() => {
          if (!peekTask) return;
          setPeekOpen(false);
          onOpenTask(peekTask);
        }}
        onOpenStream={() => {
          setPeekOpen(false);
          onOpenStream();
        }}
        onEdit={() => {
          if (!peekTask) return;
          setPeekOpen(false);
          setEditingTask(peekTask);
        }}
        onDelete={() => {
          if (!peekTask) return;
          setPeekOpen(false);
          setDeleteTask(peekTask);
        }}
      />
      <TaskDeleteDialog
        task={deleteTask}
        open={Boolean(deleteTask)}
        onOpenChange={(open) => {
          if (!open) setDeleteTask(null);
        }}
        onDeleted={(task) => {
          if (selectedTaskId === task.id) {
            setSelectedTaskId(null);
          }
          setDeleteTask(null);
        }}
      />
    </>
  );
}
