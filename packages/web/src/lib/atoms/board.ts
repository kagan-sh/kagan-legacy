import { atom } from 'jotai';
import type { TaskStatus, WireTask } from '@/lib/api/types';
import { apiClient } from '@/lib/api/client';
import { COLUMN_ORDER, type SortOption } from '@/lib/utils/constants';

/** Discriminated union for all board-level dialog states. */
export type BoardDialog =
  | { kind: 'none' }
  | { kind: 'create' }
  | { kind: 'edit'; taskId: string }
  | { kind: 'delete'; taskId: string };

export const boardDialogAtom = atom<BoardDialog>({ kind: 'none' });

type TaskGroups = Record<TaskStatus, WireTask[]>;
type TaskCounts = Record<TaskStatus, number>;

export interface BoardFilters {
  query: string;
  status: TaskStatus | 'ALL';
  sort: SortOption;
  repoId: string | null;
}

function createEmptyGroups(): TaskGroups {
  return { BACKLOG: [], IN_PROGRESS: [], REVIEW: [], DONE: [] };
}

function createEmptyCounts(): TaskCounts {
  return { BACKLOG: 0, IN_PROGRESS: 0, REVIEW: 0, DONE: 0 };
}

export const tasksAtom = atom<WireTask[]>([]);
export const boardLoadingAtom = atom(false);
export const boardErrorAtom = atom<string | null>(null);
export const boardFiltersAtom = atom<BoardFilters>({
  query: '',
  status: 'ALL',
  sort: 'default',
  repoId: null,
});
export const searchQueryAtom = atom(
  (get) => get(boardFiltersAtom).query,
  (_get, set, value: string) => set(boardFiltersAtom, (prev) => ({ ...prev, query: value })),
);
export const boardStatusFilterAtom = atom(
  (get) => get(boardFiltersAtom).status,
  (_get, set, value: TaskStatus | 'ALL') => set(boardFiltersAtom, (prev) => ({ ...prev, status: value })),
);
export const boardSortAtom = atom(
  (get) => get(boardFiltersAtom).sort,
  (_get, set, value: SortOption) => set(boardFiltersAtom, (prev) => ({ ...prev, sort: value })),
);
export const boardRepoFilterAtom = atom(
  (get) => get(boardFiltersAtom).repoId,
  (_get, set, value: string | null) => set(boardFiltersAtom, (prev) => ({ ...prev, repoId: value })),
);
export const resetBoardFiltersAtom = atom(null, (_get, set) => {
  set(boardFiltersAtom, {
    query: '',
    status: 'ALL',
    sort: 'default',
    repoId: null,
  });
});

/**
 * Incremented when the active project changes.
 * Board and WebSocket sync depend on this to re-fetch / re-subscribe.
 */
export const projectSwitchVersionAtom = atom(0);

export const groupedTasksAtom = atom((get) => {
  const tasks = get(tasksAtom);
  const groups = createEmptyGroups();
  for (const task of tasks) {
    if (COLUMN_ORDER.includes(task.status as TaskStatus)) {
      groups[task.status as TaskStatus].push(task);
    }
  }
  return groups;
});

export const taskCountsAtom = atom((get) => {
  const grouped = get(groupedTasksAtom);
  const counts = createEmptyCounts();
  for (const status of COLUMN_ORDER) {
    counts[status] = grouped[status].length;
  }
  return counts;
});

const PRIORITY_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function sortTasks(tasks: WireTask[], sort: SortOption): WireTask[] {
  if (sort === 'default') return tasks;
  return [...tasks].sort((a, b) => {
    if (sort === 'priority') {
      return (PRIORITY_RANK[a.priority] ?? 4) - (PRIORITY_RANK[b.priority] ?? 4);
    }
    if (sort === 'recent') {
      const bTime = b.last_event_at || b.updated_at || '';
      const aTime = a.last_event_at || a.updated_at || '';
      return bTime.localeCompare(aTime);
    }
    // 'created' — older first (by updated_at as proxy)
    const aTime = a.updated_at || '';
    const bTime = b.updated_at || '';
    return aTime.localeCompare(bTime);
  });
}

export const filteredGroupedTasksAtom = atom((get) => {
  const grouped = get(groupedTasksAtom);
  const { query, status: statusFilter, sort, repoId } = get(boardFiltersAtom);
  const normalizedQuery = query.toLowerCase().trim();

  const result = createEmptyGroups();
  for (const status of COLUMN_ORDER) {
    if (statusFilter !== 'ALL' && status !== statusFilter) {
      result[status] = [];
      continue;
    }
    const filtered = grouped[status].filter(
      (task) =>
        (!normalizedQuery ||
          task.title.toLowerCase().includes(normalizedQuery) ||
          task.description?.toLowerCase().includes(normalizedQuery)) &&
        (!repoId || task.repo_id === repoId),
    );
    result[status] = sortTasks(filtered, sort);
  }
  return result;
});

export const fetchTasksAtom = atom(null, async (get, set) => {
  set(boardLoadingAtom, true);
  set(boardErrorAtom, null);
  try {
    const { repoId } = get(boardFiltersAtom);
    const tasks = await apiClient.getTasks(undefined, repoId ?? undefined);
    set(tasksAtom, tasks);
  } catch (error) {
    set(boardErrorAtom, error instanceof Error ? error.message : 'Failed to load board');
  } finally {
    set(boardLoadingAtom, false);
  }
});
