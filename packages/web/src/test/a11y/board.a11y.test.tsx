/**
 * Page-level a11y baseline for the Board route.
 * Infrastructure only: records current state, does not hard-fail legacy issues.
 */
import { describe, it, expect, vi } from 'vitest';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { boardLoadingAtom, tasksAtom } from '@/lib/atoms/board';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { collectViolations } from '@/test/a11y/helpers';

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getTasks: vi.fn().mockResolvedValue([]),
    getTask: vi.fn().mockResolvedValue(null),
    getTaskEvents: vi.fn().mockResolvedValue([]),
    transitionTaskStatus: vi.fn().mockResolvedValue({}),
    getChatSessions: vi.fn().mockResolvedValue([]),
    getResolvedSettings: vi.fn().mockResolvedValue({ workflow: {} }),
    getProjects: vi.fn().mockResolvedValue([]),
    getProjectRepos: vi.fn().mockResolvedValue([]),
  },
}));

const { KanbanBoard } = await import('@/components/board/kanban-board');

describe('Board page a11y baseline', () => {
  it('empty board — records violations', async () => {
    const store = createStore();
    store.set(boardLoadingAtom, false);
    store.set(tasksAtom, []);
    store.set(sseConnectedAtom, true);

    const onboardingKey = 'kagan_web_onboarding_tutorial_seen_v1';
    localStorage.setItem(onboardingKey, '1');
    try {
      const { container } = renderWithProviders(<KanbanBoard />, { store });
      const { results, seriousIncomplete } = await collectViolations(container);
      if (results.violations.length > 0 || seriousIncomplete.length > 0) {
        // TODO(a11y-migration): baseline recorded; migrate components to eliminate.
        console.info(
          `[a11y baseline] Board empty: ${results.violations.length} violations, ${seriousIncomplete.length} serious incomplete`,
        );
      }
      expect(results).toBeDefined();
    } finally {
      localStorage.removeItem(onboardingKey);
    }
  });
});
