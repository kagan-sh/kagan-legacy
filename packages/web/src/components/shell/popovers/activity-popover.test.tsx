import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, act } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { ActivityPopover } from './activity-popover';
import { shellPopoverAtom } from '@/lib/atoms/shell';
import { tasksAtom } from '@/lib/atoms/board';
import { apiClient } from '@/lib/api/client';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getSessions: vi.fn(),
    getTaskCommits: vi.fn(),
  },
}));

// Default: no sessions (overridden in individual tests if needed)
let mockSessions: Array<{ id: string; type: string; title: string; updated_at: string }> = [];

vi.mock('@/lib/hooks/use-session-list', () => ({
  useSessionList: () => ({
    sessions: mockSessions,
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

function openActivity(store: ReturnType<typeof createStore>) {
  act(() => {
    store.set(shellPopoverAtom, { kind: 'activity', anchor: { x: 100, y: 50, align: 'right' } });
  });
}

describe('ActivityPopover', () => {
  beforeEach(() => {
    mockSessions = [];
    vi.mocked(apiClient.getTaskCommits).mockResolvedValue({
      task_id: 't1',
      branch: 'feat/test',
      base_branch: 'main',
      commits: [],
    });
  });

  it('renders nothing when closed', () => {
    const store = createStore();
    renderWithProviders(<ActivityPopover />, { store });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('shows empty state with no tasks and no sessions', async () => {
    // mockSessions is [] from beforeEach, tasksAtom is empty by default
    const store = createStore();
    renderWithProviders(<ActivityPopover />, { store });
    openActivity(store);
    expect(await screen.findByText(/no recent activity/i)).toBeInTheDocument();
  });

  it('shows task status transitions when tasks exist', async () => {
    const store = createStore();
    store.set(tasksAtom, [
      {
        id: 'task-id-1234',
        title: 'Build thing',
        status: 'IN_PROGRESS',
        priority: 'MEDIUM',
        review_running: false,
        updated_at: new Date().toISOString(),
      },
    ] as never);
    renderWithProviders(<ActivityPopover />, { store });
    openActivity(store);
    // Should show "In Progress" label (from STATUS_LABELS)
    expect(await screen.findByText(/→ In Progress/)).toBeInTheDocument();
  });

  it('shows session events when sessions exist', async () => {
    mockSessions = [
      { id: 's1', type: 'orchestrator', title: 'Orch', updated_at: new Date().toISOString() },
    ];
    const store = createStore();
    renderWithProviders(<ActivityPopover />, { store });
    openActivity(store);
    expect(await screen.findByText('Session started')).toBeInTheDocument();
  });
});
