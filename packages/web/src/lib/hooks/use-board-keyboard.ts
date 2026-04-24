import { useEffect } from 'react';
import type { TaskStatus, WireTask } from '@/lib/api/types';
import { COLUMN_ORDER } from '@/lib/utils/constants';
import { hasOpenOverlay, isEditableTarget } from '@/lib/utils/dom';

interface UseBoardKeyboardOptions {
  selectedTask: WireTask | null;
  selectedTaskPosition: { status: TaskStatus; index: number } | null;
  grouped: Record<TaskStatus, WireTask[]>;
  allFilteredTasks: WireTask[];
  view: 'kanban' | 'backlog';
  query: string;
  setSelectedTaskId: (id: string | null) => void;
  setEditingTask: (task: WireTask | null) => void;
  setQuery: (query: string) => void;
  openTask: (task: WireTask) => void;
  moveSelectedTaskToAdjacentLane: (direction: -1 | 1) => Promise<void>;
  searchInputRef: React.RefObject<HTMLInputElement | null>;
  isAnyDialogOpen: boolean;
}

/**
 * Board keyboard bindings.
 *
 * Kept bindings:
 *   - Arrow keys — navigate tasks within/across columns
 *   - Shift+Arrow Left/Right — move task to adjacent lane
 *   - Enter — open selected task
 *   - Escape — clear search query (when search is focused)
 *   - e — edit selected task
 *
 * Removed bindings (conflicted with AT virtual cursors or were TUI-ism):
 *   - j/k/h/l — vim navigation (use Arrow keys instead)
 *   - s/S — start/stop (use visible buttons)
 *   - n — new task (use toolbar button or Cmd+K palette)
 *   - x — delete (use context menu)
 *   - p — peek (use click or Enter)
 *   - / — search focus (AT intercepts; use click)
 */
export function useBoardKeyboard({
  selectedTask,
  selectedTaskPosition,
  grouped,
  allFilteredTasks,
  view,
  query,
  setSelectedTaskId,
  setEditingTask,
  setQuery,
  openTask,
  moveSelectedTaskToAdjacentLane,
  searchInputRef,
  isAnyDialogOpen,
}: UseBoardKeyboardOptions): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isAnyDialogOpen) return;
      if (hasOpenOverlay()) return;

      const isEditable = isEditableTarget(event.target);

      if (!isEditable && selectedTask) {
        if (event.key === 'Enter') {
          event.preventDefault();
          openTask(selectedTask);
          return;
        }
        if (!event.metaKey && !event.ctrlKey && !event.altKey && event.key.toLowerCase() === 'e') {
          event.preventDefault();
          setEditingTask(selectedTask);
          return;
        }

        if (view === 'backlog') {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            const currentIndex = allFilteredTasks.findIndex((task) => task.id === selectedTask.id);
            const nextTask = allFilteredTasks[currentIndex + 1];
            if (nextTask) setSelectedTaskId(nextTask.id);
            return;
          }
          if (event.key === 'ArrowUp') {
            event.preventDefault();
            const currentIndex = allFilteredTasks.findIndex((task) => task.id === selectedTask.id);
            const previousTask = allFilteredTasks[currentIndex - 1];
            if (previousTask) setSelectedTaskId(previousTask.id);
            return;
          }
        } else if (selectedTaskPosition) {
          if (event.shiftKey && event.key === 'ArrowLeft') {
            event.preventDefault();
            void moveSelectedTaskToAdjacentLane(-1);
            return;
          }
          if (event.shiftKey && event.key === 'ArrowRight') {
            event.preventDefault();
            void moveSelectedTaskToAdjacentLane(1);
            return;
          }

          const columnTasks = grouped[selectedTaskPosition.status];

          if (event.key === 'ArrowDown') {
            event.preventDefault();
            const nextTask = columnTasks[selectedTaskPosition.index + 1];
            if (nextTask) setSelectedTaskId(nextTask.id);
            return;
          }
          if (event.key === 'ArrowUp') {
            event.preventDefault();
            const previousTask = columnTasks[selectedTaskPosition.index - 1];
            if (previousTask) setSelectedTaskId(previousTask.id);
            return;
          }
          if (!event.shiftKey && event.key === 'ArrowLeft') {
            event.preventDefault();
            const currentColumnIndex = COLUMN_ORDER.indexOf(selectedTaskPosition.status);
            for (
              let nextColumnIndex = currentColumnIndex - 1;
              nextColumnIndex >= 0;
              nextColumnIndex--
            ) {
              const nextStatus = COLUMN_ORDER[nextColumnIndex]!;
              const nextColumn = grouped[nextStatus];
              if (nextColumn.length === 0) continue;
              const nextTask = nextColumn[Math.min(selectedTaskPosition.index, nextColumn.length - 1)];
              if (nextTask) {
                setSelectedTaskId(nextTask.id);
                return;
              }
            }
            return;
          }
          if (!event.shiftKey && event.key === 'ArrowRight') {
            event.preventDefault();
            const currentColumnIndex = COLUMN_ORDER.indexOf(selectedTaskPosition.status);
            for (
              let nextColumnIndex = currentColumnIndex + 1;
              nextColumnIndex < COLUMN_ORDER.length;
              nextColumnIndex++
            ) {
              const nextStatus = COLUMN_ORDER[nextColumnIndex]!;
              const nextColumn = grouped[nextStatus];
              if (nextColumn.length === 0) continue;
              const nextTask = nextColumn[Math.min(selectedTaskPosition.index, nextColumn.length - 1)];
              if (nextTask) {
                setSelectedTaskId(nextTask.id);
                return;
              }
            }
            return;
          }
        }
      }

      if (document.activeElement === searchInputRef.current && event.key === 'Escape' && query) {
        event.preventDefault();
        setQuery('');
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [
    allFilteredTasks,
    grouped,
    isAnyDialogOpen,
    moveSelectedTaskToAdjacentLane,
    openTask,
    query,
    searchInputRef,
    selectedTask,
    selectedTaskPosition,
    setEditingTask,
    setQuery,
    setSelectedTaskId,
    view,
  ]);
}
