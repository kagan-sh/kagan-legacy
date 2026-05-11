import { describe, it, expect, beforeEach } from 'vitest';
import { createStore } from 'jotai';
import {
  tasksAtom,
  groupedTasksAtom,
  filteredGroupedTasksAtom,
  boardFiltersAtom,
  searchQueryAtom,
  boardStatusFilterAtom,
  boardSortAtom,
} from '@/lib/atoms/board';
import { mockTask } from '@/test/mocks';

describe('board atoms', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  it('groups tasks by status', () => {
    const tasks = [
      mockTask({ status: 'BACKLOG' }),
      mockTask({ status: 'IN_PROGRESS' }),
      mockTask({ status: 'BACKLOG' }),
    ];
    store.set(tasksAtom, tasks);

    const grouped = store.get(groupedTasksAtom);
    expect(grouped.BACKLOG).toHaveLength(2);
    expect(grouped.IN_PROGRESS).toHaveLength(1);
    expect(grouped.REVIEW).toHaveLength(0);
    expect(grouped.DONE).toHaveLength(0);
  });

  it('counts tasks per column', () => {
    const tasks = [
      mockTask({ status: 'BACKLOG' }),
      mockTask({ status: 'DONE' }),
      mockTask({ status: 'DONE' }),
    ];
    store.set(tasksAtom, tasks);

    const grouped = store.get(groupedTasksAtom);
    expect(grouped.BACKLOG).toHaveLength(1);
    expect(grouped.DONE).toHaveLength(2);
    expect(grouped.IN_PROGRESS).toHaveLength(0);
  });

  it('filters tasks by search query', () => {
    const tasks = [
      mockTask({ title: 'Fix login bug', status: 'BACKLOG' }),
      mockTask({ title: 'Add feature', status: 'BACKLOG' }),
    ];
    store.set(tasksAtom, tasks);
    store.set(searchQueryAtom, 'login');

    const filtered = store.get(filteredGroupedTasksAtom);
    expect(filtered.BACKLOG).toHaveLength(1);
    expect(filtered.BACKLOG[0]!.title).toBe('Fix login bug');
  });

  it('updates consolidated filters through legacy derived atoms', () => {
    store.set(searchQueryAtom, 'query');
    store.set(boardStatusFilterAtom, 'DONE');
    store.set(boardSortAtom, 'recent');

    expect(store.get(boardFiltersAtom)).toEqual({
      query: 'query',
      status: 'DONE',
      sort: 'recent',
      repoId: null,
      agent: null,
    });
  });
});
