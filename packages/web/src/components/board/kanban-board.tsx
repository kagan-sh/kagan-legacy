import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import {
  Bot,
  LayoutGrid,
  ListTodo,
  Plus,
  Radar,
  Search,
  Users,
} from 'lucide-react';
import {
  DndContext,
  DragOverlay,
} from '@dnd-kit/core';
import {
  boardErrorAtom,
  boardLoadingAtom,
  boardModeFilterAtom,
  boardSortAtom,
  boardStatusFilterAtom,
  fetchTasksAtom,
  filteredGroupedTasksAtom,
  projectSwitchVersionAtom,
  searchQueryAtom,
  tasksAtom,
} from '@/lib/atoms/board';
import { COLUMN_ORDER, STATUS_LABELS, SORT_LABELS, isAllowedTaskTransition, type SortOption } from '@/lib/utils/constants';
import { KanbanColumn } from '@/components/board/kanban-column';
import { TaskCardOverlayPreview } from '@/components/board/task-card';
import { BoardDialogs } from '@/components/board/board-dialogs';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { BoardTaskInspector } from '@/components/board/board-task-inspector';
import { BacklogListView } from '@/components/board/backlog-list-view';
import { FirstBootTutorialDialog } from '@/components/board/first-boot-tutorial-dialog';
import { apiClient } from '@/lib/api/client';
import type { TaskStatus, WorkMode, WireTask } from '@/lib/api/types';
import { helpOverlayOpenAtom } from '@/lib/atoms/ui';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { toast } from 'sonner';
import { useIsMobile } from '@/lib/hooks/use-mobile';
import { useBoardDnd } from '@/lib/hooks/use-board-dnd';
import { useBoardKeyboard } from '@/lib/hooks/use-board-keyboard';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { ActionEmptyState } from '@/components/shared/workspace';
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
  const [modeFilter, setModeFilter] = useAtom(boardModeFilterAtom);
  const [sort, setSort] = useAtom(boardSortAtom);
  const [createOpen, setCreateOpen] = useState(false);
  const [createExecutionMode, setCreateExecutionMode] = useState<WorkMode>('AUTO');
  const [view, setView] = useState<'kanban' | 'backlog'>('kanban');
  const [wipLimits, setWipLimits] = useState<Record<TaskStatus, number>>(DEFAULT_WIP_LIMITS);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [inspectorClosed, setInspectorClosed] = useState(false);
  const [peekOpen, setPeekOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<WireTask | null>(null);
  const [deleteTask, setDeleteTask] = useState<WireTask | null>(null);
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

  const { activeTask, liveTasksByStatus, sensors, collisionDetection, handleDragStart, handleDragOver, handleDragEnd } =
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

  const openCreateDialog = useCallback((mode: WorkMode = 'AUTO') => {
    setCreateExecutionMode(mode);
    setCreateOpen(true);
  }, []);

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

  const startPairFlowFromTutorial = useCallback(() => {
    saveWebOnboardingTutorialSeen(true);
    setTutorialOpen(false);
    openCreateDialog('PAIR');
  }, [openCreateDialog]);

  const startAutoFlowFromTutorial = useCallback(() => {
    saveWebOnboardingTutorialSeen(true);
    setTutorialOpen(false);
    openCreateDialog('AUTO');
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

  const isAnyDialogOpen = createOpen || peekOpen || Boolean(editingTask) || Boolean(deleteTask);

  useBoardKeyboard({
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
      <div className="flex flex-wrap items-center gap-2 border-b border-[color:var(--border-subtle)] pb-3">
        <ToggleGroup
          type="single"
          value={view}
          onValueChange={(value) => {
            if (value === 'kanban' || value === 'backlog') {
              setView(value);
            }
          }}
          variant="outline"
          size="sm"
          aria-label="Board view"
        >
          <ToggleGroupItem value="kanban" aria-label="Kanban view" className="data-[state=on]:bg-[color:var(--foreground)] data-[state=on]:text-[color:var(--background)]">
            <LayoutGrid className="size-3.5" />
            Board
          </ToggleGroupItem>
          <ToggleGroupItem value="backlog" aria-label="Backlog list view" className="data-[state=on]:bg-[color:var(--foreground)] data-[state=on]:text-[color:var(--background)]">
            <ListTodo className="size-3.5" />
            List
          </ToggleGroupItem>
        </ToggleGroup>

        <span className="h-4 w-px bg-[color:var(--border-subtle)]" />

        {view === 'backlog' ? (
          <>
            {(['ALL', ...COLUMN_ORDER] as const).map((value) => (
              <Button
                key={value}
                type="button"
                variant="ghost"
                size="xs"
                className={statusFilter === value ? 'bg-[color:var(--foreground)] text-[color:var(--background)] hover:bg-[color:var(--foreground)]/90 hover:text-[color:var(--background)]' : 'text-[var(--muted-foreground)]'}
                onClick={() => setStatusFilter(value)}
              >
                {value === 'ALL' ? 'All' : STATUS_LABELS[value as TaskStatus]}
              </Button>
            ))}
            <span className="h-4 w-px bg-[color:var(--border-subtle)]" />
          </>
        ) : null}

        {(['ALL', 'AUTO', 'PAIR'] as const).map((value) => (
          <Button
            key={value}
            type="button"
            variant="ghost"
            size="xs"
            className={modeFilter === value ? 'bg-[color:var(--foreground)] text-[color:var(--background)] hover:bg-[color:var(--foreground)]/90 hover:text-[color:var(--background)]' : 'text-[var(--muted-foreground)]'}
            onClick={() => setModeFilter(value as WorkMode | 'ALL')}
          >
            {value === 'PAIR' ? <Users className="size-3" /> : null}
            {value === 'AUTO' ? <Bot className="size-3" /> : null}
            {value === 'ALL' ? 'All modes' : value === 'AUTO' ? 'Auto' : 'Pair'}
          </Button>
        ))}

        <span className="h-4 w-px bg-[color:var(--border-subtle)]" />

        <NativeSelect
          value={sort}
          onChange={(e) => setSort(e.target.value as SortOption)}
          className="h-7 min-w-[7rem] border-none bg-transparent px-2 text-xs text-[var(--muted-foreground)] shadow-none"
          aria-label="Sort tasks"
        >
          {(Object.entries(SORT_LABELS) as [SortOption, string][]).map(([value, label]) => (
            <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>
          ))}
        </NativeSelect>

        <div className="ml-auto flex items-center gap-2">
          <span className="font-code text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
            <Radar className="mr-1 inline size-3" />
            {boardMetrics.running} live
          </span>
          <span className="font-code text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
            {boardMetrics.readyForReview} review
          </span>

          <div className="relative min-w-[7rem]">
            <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <Input
              ref={searchInputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="/"
              className="h-7 w-28 border-[color:var(--border-subtle)] bg-transparent pl-7 pr-2 text-xs"
              aria-label="Search tasks"
            />
          </div>

          <Button size="sm" onClick={() => openCreateDialog('AUTO')}>
            <Plus className="size-3.5" />
            New
          </Button>
        </div>
      </div>

      {error ? (
        <div className=" border border-[var(--destructive)]/25 bg-[var(--destructive)]/10 px-4 py-3 text-sm text-[var(--destructive)]">
          {error}
        </div>
      ) : null}


      <div className="flex min-h-0 flex-1 gap-px overflow-hidden pt-3">
        <div className="min-w-0 flex-1">
          {showBoardEmpty ? (
            <ActionEmptyState
              title="Start the first autonomous task"
              description="Create an initial task and Kagan will begin filling this workspace with execution telemetry, review state, and session history."
              icon={<Plus className="size-6" />}
              action={(
                <Button onClick={() => openCreateDialog('AUTO')} className="cta-glow">
                  <Plus className="size-4" />
                  Create first task
                </Button>
              )}
            />
          ) : showFilteredEmpty ? (
            <ActionEmptyState
              title="No tasks match the active filters"
              description="Broaden your mode/status filters to bring more of the workspace back into view."
              icon={<Search className="size-6" />}
              action={(
                <Button
                  variant="outline"
                  className=""
                  onClick={() => {
                    setStatusFilter('ALL');
                    setModeFilter('ALL');
                  }}
                >
                  Reset filters
                </Button>
              )}
            />
          ) : view === 'kanban' ? (
            <DndContext
              sensors={sensors}
              collisionDetection={collisionDetection}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
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
                    onEditTask={setEditingTask}
                    onDeleteTask={setDeleteTask}
                    selectedTaskId={selectedTaskId}
                    wipLimit={wipLimits[status] ?? 0}
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
              onPeek={() => setPeekOpen(true)}
              onEdit={() => setEditingTask(selectedTask)}
              onDelete={() => setDeleteTask(selectedTask)}
              onClose={() => {
                setInspectorClosed(true);
                setSelectedTaskId(null);
              }}
            />
          </aside>
        ) : null}
      </div>

      <BoardDialogs
        createOpen={createOpen}
        createExecutionMode={createExecutionMode}
        setCreateOpen={setCreateOpen}
        editingTask={editingTask}
        setEditingTask={setEditingTask}
        deleteTask={deleteTask}
        setDeleteTask={setDeleteTask}
        peekTask={selectedTask}
        peekOpen={peekOpen}
        setPeekOpen={setPeekOpen}
        selectedTaskId={selectedTaskId}
        setSelectedTaskId={setSelectedTaskId}
        onOpenTask={openTask}
        onOpenStream={openSelectedStream}
      />
      <FirstBootTutorialDialog
        open={tutorialOpen}
        onOpenChange={handleTutorialOpenChange}
        onStartPairFlow={startPairFlowFromTutorial}
        onStartAutoFlow={startAutoFlowFromTutorial}
        onOpenHelp={openHelpFromTutorial}
      />
    </div>
  );
}
