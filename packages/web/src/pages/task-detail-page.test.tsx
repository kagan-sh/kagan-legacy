import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { Routes, Route } from 'react-router';
import { renderWithProviders } from '@/test/render';
import { Component as TaskDetailPage } from '@/pages/task-detail-page';

const openMock = vi.fn();

vi.mock('@/lib/hooks/use-session-overlay', () => ({
  useSessionOverlay: () => ({
    open: openMock,
    close: vi.fn(),
    toggle: vi.fn(),
    isOpen: false,
    layout: 'docked',
    selectedSession: null,
    setLayout: vi.fn(),
    selectSession: vi.fn(),
  }),
}));

vi.mock('@/lib/hooks/use-task-events', () => ({
  useTaskEvents: () => ({
    task: {
      id: 'task-1',
      title: 'Test Task',
      description: 'Desc',
      status: 'IN_PROGRESS',
      priority: 'MEDIUM',
      active_session: null,
      has_workspace: false,
      review_approved: false,
      acceptance_criteria: [],
    },
    loading: false,
    runningSince: null,
    events: [],
    isRunning: false,
    sessions: [],
    sentFollowUps: [],
    queue: [],
    sendingFollowUp: false,
    queuePrompt: vi.fn(),
    removePrompt: vi.fn(),
    editPrompt: vi.fn(),
    interruptAndSend: vi.fn(),
    hasMore: false,
    loadingMore: false,
    loadEarlier: vi.fn(),
  }),
}));

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getSessions: vi.fn().mockResolvedValue({
      sessions: [
        {
          id: 'sess-task-1',
          type: 'task',
          title: 'Task Session',
          task_id: 'task-1',
          role: null,
          status: 'active',
          backend: null,
          project_id: null,
          session_id: null,
          chat_session_id: null,
          updated_at: '2026-05-08T12:00:00Z',
          capabilities: {
            can_chat: false,
            can_stream: false,
            can_replay: true,
            can_stop: false,
            can_close: true,
            has_kagan_tools: false,
          },
        },
      ],
    }),
    getTaskWorktree: vi.fn().mockResolvedValue({ worktree: null }),
    getSettings: vi.fn().mockResolvedValue({}),
  },
}));

describe('TaskDetailPage', () => {
  beforeEach(() => {
    openMock.mockClear();
  });

  it('opens the global overlay when Open session is clicked', async () => {
    renderWithProviders(
      <Routes>
        <Route path="/task/:id" element={<TaskDetailPage />} />
      </Routes>,
      { initialEntries: ['/task/task-1'] },
    );

    const btn = await screen.findByRole('button', { name: /open session/i });
    fireEvent.click(btn);

    await vi.waitFor(() => {
      expect(openMock).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'sess-task-1', task_id: 'task-1' }),
      );
    });
  });
});
