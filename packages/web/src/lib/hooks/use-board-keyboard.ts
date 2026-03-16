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
  openCreateDialog: (mode: 'AUTO' | 'PAIR') => void;
  setPeekOpen: (open: boolean) => void;
  setEditingTask: (task: WireTask | null) => void;
  setDeleteTask: (task: WireTask | null) => void;
  setQuery: (query: string) => void;
  openTask: (task: WireTask) => void;
  startSelectedTask: () => void;
  stopSelectedTask: () => void;
  moveSelectedTaskToAdjacentLane: (direction: -1 | 1) => Promise<void>;
  searchInputRef: React.RefObject<HTMLInputElement | null>;
  isAnyDialogOpen: boolean;
}

export function useBoardKeyboard({
  selectedTask,
  selectedTaskPosition,
  grouped,
  allFilteredTasks,
  view,
  query,
  setSelectedTaskId,
  openCreateDialog,
  setPeekOpen,
  setEditingTask,
  setDeleteTask,
  setQuery,
  openTask,
  startSelectedTask,
  stopSelectedTask,
  moveSelectedTaskToAdjacentLane,
  searchInputRef,
  isAnyDialogOpen,
}: UseBoardKeyboardOptions): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isAnyDialogOpen) return;
      if (hasOpenOverlay()) return;

      const isEditable = isEditableTarget(event.target);

      if (!isEditable && event.key === '/') {
        event.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
        return;
      }

      if (!isEditable && !event.metaKey && !event.ctrlKey && !event.altKey && event.key.toLowerCase() === 'n') {
        event.preventDefault();
        openCreateDialog(event.shiftKey ? 'AUTO' : 'PAIR');
        return;
      }

      if (!isEditable && selectedTask) {
        const lowerKey = event.key.toLowerCase();

        if (lowerKey === 's' && event.shiftKey) {
          event.preventDefault();
          stopSelectedTask();
          return;
        }
        if (lowerKey === 's') {
          event.preventDefault();
          startSelectedTask();
          return;
        }
        if (event.key === 'Enter') {
          event.preventDefault();
          openTask(selectedTask);
          return;
        }
        if (lowerKey === 'p') {
          event.preventDefault();
          setPeekOpen(true);
          return;
        }
        if (lowerKey === 'e') {
          event.preventDefault();
          setEditingTask(selectedTask);
          return;
        }
        if (lowerKey === 'x') {
          event.preventDefault();
          setDeleteTask(selectedTask);
          return;
        }

        if (view === 'backlog') {
          if (event.key === 'ArrowDown' || lowerKey === 'j') {
            event.preventDefault();
            const currentIndex = allFilteredTasks.findIndex((task) => task.id === selectedTask.id);
            const nextTask = allFilteredTasks[currentIndex + 1];
            if (nextTask) setSelectedTaskId(nextTask.id);
            return;
          }
          if (event.key === 'ArrowUp' || lowerKey === 'k') {
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

          if (event.key === 'ArrowDown' || lowerKey === 'j') {
            event.preventDefault();
            const nextTask = columnTasks[selectedTaskPosition.index + 1];
            if (nextTask) setSelectedTaskId(nextTask.id);
            return;
          }
          if (event.key === 'ArrowUp' || lowerKey === 'k') {
            event.preventDefault();
            const previousTask = columnTasks[selectedTaskPosition.index - 1];
            if (previousTask) setSelectedTaskId(previousTask.id);
            return;
          }
          if (event.key === 'ArrowLeft' || lowerKey === 'h') {
            event.preventDefault();
            // select neighbor in adjacent left column
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
          if (event.key === 'ArrowRight' || lowerKey === 'l') {
            event.preventDefault();
            // select neighbor in adjacent right column
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
    openCreateDialog,
    setDeleteTask,
    setEditingTask,
    setPeekOpen,
    setQuery,
    setSelectedTaskId,
    startSelectedTask,
    stopSelectedTask,
    view,
  ]);
}
