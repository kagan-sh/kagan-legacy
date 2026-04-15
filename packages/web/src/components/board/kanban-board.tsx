import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import {
  Plus,
  Search,
} from 'lucide-react';
import {
  DndContext,
  DragOverlay,
} from '@dnd-kit/core';
import {
  boardErrorAtom,
  boardLoadingAtom,
  boardSortAtom,
  boardStatusFilterAtom,
  boardDialogAtom,
  fetchTasksAtom,
  filteredGroupedTasksAtom,
  projectSwitchVersionAtom,
  searchQueryAtom,
  tasksAtom,
} from '@/lib/atoms/board';
import { COLUMN_ORDER, STATUS_LABELS, isAllowedTaskTransition } from '@/lib/utils/constants';
import { KanbanColumn } from '@/components/board/kanban-column';
import { TaskCardOverlayPreview } from '@/components/board/task-card';
import { BoardDialogs } from '@/components/board/board-dialogs';
import { BoardTaskInspector } from '@/components/board/board-task-inspector';
import { BoardToolbar } from '@/components/board/board-toolbar';
import { BacklogListView } from '@/components/board/backlog-list-view';
import { FirstBootTutorialDialog } from '@/components/board/first-boot-tutorial-dialog';
import { apiClient } from '@/lib/api/client';
import type { TaskStatus, WireTask } from '@/lib/api/types';
import { helpOverlayOpenAtom } from '@/lib/atoms/ui';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { toast } from 'sonner';
import { useIsMobile } from '@/lib/hooks/use-mobile';
import { useBoardDnd } from '@/lib/hooks/use-board-dnd';
import { useBoardKeyboard } from '@/lib/hooks/use-board-keyboard';
import { Button } from '@/components/ui/button';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import {
  loadWebOnboardingTutorialSeen,
  saveWebOnboardingTutorialSeen,
} from '@/lib/utils/storage';

const DEFAULT_WIP_LIMITS: Record<TaskStatus, number> = {
  BACKLOG: 0,
  IN_PROGRESS: 4,
  REVIEW: 2,
  DONE: 0,
};

export function KanbanBoard() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const grouped = useAtomValue(filteredGroupedTasksAtom);
  const tasks = useAtomValue(tasksAtom);
  const loading = useAtomValue(boardLoadingAtom);
  const error = useAtomValue(boardErrorAtom);
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);
  const projectVersion = useAtomValue(projectSwitchVersionAtom);
  const sseConnected = useAtomValue(sseConnectedAtom);
  const [query, setQuery] = useAtom(searchQueryAtom);
  const [statusFilter, setStatusFilter] = useAtom(boardStatusFilterAtom);
  const [sort, setSort] = useAtom(boardSortAtom);
  const [boardDialog, setBoardDialog] = useAtom(boardDialogAtom);
  const [view, setView] = useState<'kanban' | 'backlog'>('kanban');
  const [wipLimits, setWipLimits] = useState<Record<TaskStatus, number>>(DEFAULT_WIP_LIMITS);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [inspectorClosed, setInspectorClosed] = useState(false);
  const [tutorialOpen, setTutorialOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const allFilteredTasks = useMemo(
    () => COLUMN_ORDER.flatMap((status) => grouped[status]),
    [grouped],
  );

  const selectedTask = useMemo(
    () => allFilteredTasks.find((task) => task.id === selectedTaskId) ?? null,
    [allFilteredTasks, selectedTaskId],
  );

  const selectedTaskPosition = useMemo(() => {
    if (!selectedTaskId) return null;
    for (const status of COLUMN_ORDER) {
      const index = grouped[status].findIndex((task) => task.id === selectedTaskId);
      if (index >= 0) {
        return { status, index };
      }
    }
    return null;
  }, [grouped, selectedTaskId]);

  const { activeTask, liveTasksByStatus, sensors, collisionDetection, handleDragStart, handleDragOver, handleDragEnd, handleDragCancel, validDropTargets, isDragActive } =
    useBoardDnd({ tasks, grouped, fetchTasks });

  // Re-fetch tasks on mount and when the active project changes
  useEffect(() => {
    fetchTasks();
  }, [fetchTasks, projectVersion]);

  useEffect(() => {
    apiClient
      .getResolvedSettings()
      .then((resolved) => {
        setWipLimits(resolved.workflow.wip_limits);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (allFilteredTasks.length === 0) {
      setSelectedTaskId(null);
      return;
    }

    // Skip auto-select if user explicitly closed the inspector
    if (inspectorClosed) {
      return;
    }

    if (!selectedTaskId || !allFilteredTasks.some((task) => task.id === selectedTaskId)) {
      setSelectedTaskId(allFilteredTasks[0]!.id);
    }
  }, [allFilteredTasks, selectedTaskId, inspectorClosed]);

  useEffect(() => {
    if (!selectedTaskId) return;
    const element = document.querySelector<HTMLElement>(`[data-task-id="${selectedTaskId}"]`);
    element?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [selectedTaskId, view]);

  useEffect(() => {
    if (view === 'kanban') {
      setStatusFilter('ALL');
    }
  }, [setStatusFilter, view]);

  const selectTask = useCallback((task: WireTask) => {
    setInspectorClosed(false);
    setSelectedTaskId(task.id);
  }, []);

  const openTask = useCallback(
    (task: WireTask) => {
      navigate(`/task/${task.id}`);
    },
    [navigate],
  );

  const attachTask = useCallback(
    (task: WireTask) => {
      navigate(`/task/${task.id}`);
    },
    [navigate],
  );

  const openSelectedStream = useCallback(() => {
    if (!selectedTask) return;
    navigate(`/task/${selectedTask.id}?lane=worker`);
  }, [navigate, selectedTask]);

  const startSelectedTask = useCallback(() => {
    if (!selectedTask) return;
    if (!sseConnected) {
      toast.error('Not connected to server');
      return;
    }
    if (selectedTask.status === 'DONE') {
      toast.error('Done tasks cannot be started again');
      return;
    }
    apiClient.runTask(selectedTask.id).catch((err) =>
      toast.error(err instanceof Error ? err.message : 'Failed to start task'),
    );
    toast.success(`Starting ${selectedTask.title}`);
  }, [selectedTask, sseConnected]);

  const stopSelectedTask = useCallback(() => {
    if (!selectedTask) return;
    if (!sseConnected) {
      toast.error('Not connected to server');
      return;
    }
    apiClient.cancelTask(selectedTask.id).catch((err) =>
      toast.error(err instanceof Error ? err.message : 'Failed to stop task'),
    );
    toast.success(`Stopping ${selectedTask.title}`);
  }, [selectedTask, sseConnected]);

  const startAgent = useCallback((task: WireTask) => {
    if (!sseConnected) {
      toast.error('Not connected to server');
      return;
    }
    if (task.status === 'DONE') {
      toast.error('Done tasks cannot be started again');
      return;
    }
    apiClient.runTask(task.id).catch((err) =>
      toast.error(err instanceof Error ? err.message : 'Failed to start task'),
    );
    toast.success(`Starting ${task.title}`);
  }, [sseConnected]);

  const stopAgent = useCallback((task: WireTask) => {
    if (!sseConnected) {
      toast.error('Not connected to server');
      return;
    }
    apiClient.cancelTask(task.id).catch((err) =>
      toast.error(err instanceof Error ? err.message : 'Failed to stop task'),
    );
    toast.success(`Stopping ${task.title}`);
  }, [sseConnected]);

  const openCreateDialog = useCallback(() => {
    setBoardDialog({ kind: 'create' });
  }, [setBoardDialog]);

  const editingTask = useMemo(
    () => (boardDialog.kind === 'edit' ? tasks.find((t) => t.id === boardDialog.taskId) ?? null : null),
    [boardDialog, tasks],
  );

  const deleteTask = useMemo(
    () => (boardDialog.kind === 'delete' ? tasks.find((t) => t.id === boardDialog.taskId) ?? null : null),
    [boardDialog, tasks],
  );

  const peekTask = useMemo(
    () => (boardDialog.kind === 'peek' ? tasks.find((t) => t.id === boardDialog.taskId) ?? null : null),
    [boardDialog, tasks],
  );

  useEffect(() => {
    if (loading) return;
    if (tasks.length > 0) return;
    if (loadWebOnboardingTutorialSeen()) return;
    setTutorialOpen(true);
  }, [loading, tasks.length]);

  const handleTutorialOpenChange = useCallback((open: boolean) => {
    setTutorialOpen(open);
    if (!open) {
      saveWebOnboardingTutorialSeen(true);
    }
  }, []);

  const startAttachedFlowFromTutorial = useCallback(() => {
    saveWebOnboardingTutorialSeen(true);
    setTutorialOpen(false);
    openCreateDialog();
  }, [openCreateDialog]);

  const startDetachedFlowFromTutorial = useCallback(() => {
    saveWebOnboardingTutorialSeen(true);
    setTutorialOpen(false);
    openCreateDialog();
  }, [openCreateDialog]);

  const openHelpFromTutorial = useCallback(() => {
    saveWebOnboardingTutorialSeen(true);
    setTutorialOpen(false);
    setHelpOverlayOpen(true);
  }, [setHelpOverlayOpen]);

  const moveSelectedTaskToAdjacentLane = useCallback(
    async (direction: -1 | 1) => {
      if (!selectedTaskPosition || !selectedTask) return;

      const currentIndex = COLUMN_ORDER.indexOf(selectedTaskPosition.status);
      const nextStatus = COLUMN_ORDER[currentIndex + direction];
      if (!nextStatus) {
        toast.error('No adjacent lane in that direction');
        return;
      }
      if (!isAllowedTaskTransition(selectedTask.status as TaskStatus, nextStatus)) {
        toast.error(`Cannot move ${STATUS_LABELS[selectedTask.status as TaskStatus]} directly to ${STATUS_LABELS[nextStatus]}`);
        return;
      }

      try {
        await apiClient.transitionTaskStatus(selectedTask.id, nextStatus);
        fetchTasks();
        toast.success(`Moved to ${STATUS_LABELS[nextStatus]}`);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to move task');
      }
    },
    [fetchTasks, selectedTask, selectedTaskPosition],
  );

  const isAnyDialogOpen = boardDialog.kind !== 'none';

  const openPeekDialog = useCallback((task: WireTask) => {
    setBoardDialog({ kind: 'peek', taskId: task.id });
  }, [setBoardDialog]);

  const openEditDialog = useCallback((task: WireTask) => {
    setBoardDialog({ kind: 'edit', taskId: task.id });
  }, [setBoardDialog]);

  const openDeleteDialog = useCallback((task: WireTask) => {
    setBoardDialog({ kind: 'delete', taskId: task.id });
  }, [setBoardDialog]);

  const closeDialog = useCallback(() => {
    setBoardDialog({ kind: 'none' });
  }, [setBoardDialog]);

  useBoardKeyboard({
    selectedTask,
    selectedTaskPosition,
    grouped,
    allFilteredTasks,
    view,
    query,
    setSelectedTaskId,
    openCreateDialog,
    setPeekOpen: (open: boolean) => { if (open && selectedTask) setBoardDialog({ kind: 'peek', taskId: selectedTask.id }); else setBoardDialog({ kind: 'none' }); },
    setEditingTask: (task: WireTask | null) => { if (task) setBoardDialog({ kind: 'edit', taskId: task.id }); else setBoardDialog({ kind: 'none' }); },
    setDeleteTask: (task: WireTask | null) => { if (task) setBoardDialog({ kind: 'delete', taskId: task.id }); else setBoardDialog({ kind: 'none' }); },
    setQuery,
    openTask,
    startSelectedTask,
    stopSelectedTask,
    moveSelectedTaskToAdjacentLane,
    searchInputRef,
    isAnyDialogOpen,
  });

  const boardMetrics = useMemo(() => {
    const running = tasks.filter((task) => Boolean(task.active_session)).length;
    const readyForReview = tasks.filter((task) => task.status === 'REVIEW').length;
    const approved = tasks.filter((task) => task.review_approved).length;
    return { running, readyForReview, approved };
  }, [tasks]);

  const showBoardEmpty = !loading && tasks.length === 0;
  const showFilteredEmpty = !loading && tasks.length > 0 && allFilteredTasks.length === 0;

  return (
    <div className="mx-auto flex h-full w-full max-w-[1800px] flex-col px-4 py-3 sm:px-6">
      <BoardToolbar
        query={query}
        setQuery={setQuery}
        statusFilter={statusFilter}
        setStatusFilter={setStatusFilter}
        sort={sort}
        setSort={setSort}
        view={view}
        setView={setView}
        boardMetrics={boardMetrics}
        onCreateTask={openCreateDialog}
        searchInputRef={searchInputRef}
      />

      {error ? (
        <div className=" border border-[var(--destructive)]/25 bg-[var(--destructive)]/10 px-4 py-3 text-sm text-[var(--destructive)]">
          {error}
        </div>
      ) : null}


      <div className="flex min-h-0 flex-1 gap-px overflow-hidden pt-3">
        <div className="min-w-0 flex-1">
          {showBoardEmpty ? (
            <Empty className="border-0">
              <EmptyHeader>
                <EmptyMedia variant="icon"><Plus className="size-6" /></EmptyMedia>
                <EmptyTitle>Start your first task</EmptyTitle>
                <EmptyDescription>Create a task, then Start to move it toward review and merge. Attach stays available from the task view if you need an interactive session.</EmptyDescription>
              </EmptyHeader>
              <Button onClick={openCreateDialog} className="cta-glow">
                <Plus className="size-4" />
                Create first task
              </Button>
            </Empty>
          ) : showFilteredEmpty ? (
            <Empty className="border-0">
              <EmptyHeader>
                <EmptyMedia variant="icon"><Search className="size-6" /></EmptyMedia>
                <EmptyTitle>No tasks match the active filters</EmptyTitle>
                <EmptyDescription>Broaden your filters to bring more of the workspace back into view.</EmptyDescription>
              </EmptyHeader>
              <Button
                variant="outline"
                onClick={() => {
                  setStatusFilter('ALL');
                  setQuery('');
                  setSort('default');
                }}
              >
                Reset filters
              </Button>
            </Empty>
          ) : view === 'kanban' ? (
            <DndContext
              sensors={sensors}
              collisionDetection={collisionDetection}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
              onDragCancel={handleDragCancel}
            >
              <div className="flex h-full min-h-0 min-w-0 gap-px overflow-x-auto snap-x snap-mandatory xl:grid xl:grid-cols-4 xl:overflow-x-visible xl:snap-none">
                {COLUMN_ORDER.map((status) => (
                  <KanbanColumn
                    key={status}
                    status={status as TaskStatus}
                    tasks={liveTasksByStatus[status]}
                    onInspectTask={isMobile ? openTask : undefined}
                    onSelectTask={isMobile ? undefined : selectTask}
                    onOpenTask={isMobile ? undefined : openTask}
                    onEditTask={openEditDialog}
                    onDeleteTask={openDeleteDialog}
                    onStartAgent={startAgent}
                    onStopAgent={stopAgent}
                    onAttachTask={attachTask}
                    selectedTaskId={selectedTaskId}
                    wipLimit={wipLimits[status] ?? 0}
                    isDragActive={isDragActive}
                    isValidDropTarget={validDropTargets.has(status as TaskStatus)}
                    className="w-[80vw] shrink-0 snap-start sm:w-[44vw] xl:w-auto xl:shrink xl:snap-align-none"
                  />
                ))}
              </div>
              <DragOverlay>
                {activeTask ? (
                  <TaskCardOverlayPreview task={activeTask} className="w-[18rem] max-w-[18rem] shadow-xl" />
                ) : null}
              </DragOverlay>
            </DndContext>
          ) : (
            <BacklogListView
              tasks={allFilteredTasks}
              grouped={grouped}
              onInspectTask={openTask}
              onSelectTask={isMobile ? undefined : selectTask}
              selectedTaskId={selectedTaskId}
            />
          )}
        </div>

        {!isMobile && selectedTask ? (
          <aside className="hidden w-[24rem] shrink-0 overflow-y-auto xl:block">
            <BoardTaskInspector
              task={selectedTask}
              className="h-full min-h-0 overflow-hidden"
              onOpenTask={() => openTask(selectedTask)}
              onOpenStream={openSelectedStream}
              onPeek={() => openPeekDialog(selectedTask)}
              onEdit={() => openEditDialog(selectedTask)}
              onDelete={() => openDeleteDialog(selectedTask)}
              onClose={() => {
                setInspectorClosed(true);
                setSelectedTaskId(null);
              }}
            />
          </aside>
        ) : null}
      </div>

      <BoardDialogs
        boardDialog={boardDialog}
        closeDialog={closeDialog}
        editingTask={editingTask}
        deleteTask={deleteTask}
        peekTask={peekTask}
        selectedTaskId={selectedTaskId}
        setSelectedTaskId={setSelectedTaskId}
        onOpenTask={openTask}
        onOpenStream={openSelectedStream}
        onEditTask={openEditDialog}
        onDeleteTask={openDeleteDialog}
      />
      <FirstBootTutorialDialog
        open={tutorialOpen}
        onOpenChange={handleTutorialOpenChange}
        onStartAttachedFlow={startAttachedFlowFromTutorial}
        onStartDetachedFlow={startDetachedFlowFromTutorial}
        onOpenHelp={openHelpFromTutorial}
      />
    </div>
  );
}
