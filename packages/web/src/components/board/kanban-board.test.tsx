import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { KanbanBoard } from '@/components/board/kanban-board';
import { boardLoadingAtom, tasksAtom } from '@/lib/atoms/board';

const navigateMock = vi.fn();

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getTasks: vi.fn().mockResolvedValue([]),
    getTask: vi.fn().mockImplementation(async () => ({
      id: 'task-0',
      title: 'Task',
      description: '',
      status: 'BACKLOG',
      priority: 'MEDIUM',
    })),
    getTaskEvents: vi.fn().mockResolvedValue([]),
    transitionTaskStatus: vi.fn().mockResolvedValue({}),
    getChatSessions: vi.fn().mockResolvedValue([]),
    getChatSession: vi.fn().mockResolvedValue({
      id: 'chat-1',
      label: 'Task chat',
      source: 'web',
      updated_at: '',
      message_count: 1,
      messages: [{ role: 'assistant', content: 'hello' }],
    }),
    createChatSession: vi.fn().mockResolvedValue({ id: 'session-1', label: 'Task session', source: 'web', updated_at: '', message_count: 0, messages: [] }),
    getResolvedSettings: vi.fn().mockResolvedValue({
      workflow: {
        wip_limits: {
          BACKLOG: 0,
          IN_PROGRESS: 4,
          REVIEW: 2,
          DONE: 0,
        },
      },
    }),
  },
}));

describe('KanbanBoard', () => {
  it('shows canonical first-run guidance on an empty board', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.getTasks).mockResolvedValue([]);
    vi.mocked(apiClient.getTaskEvents).mockResolvedValue([]);

    const store = createStore();
    store.set(boardLoadingAtom, false);
    store.set(tasksAtom, []);

    const onboardingKey = 'kagan_web_onboarding_tutorial_seen_v1';
    localStorage.setItem(onboardingKey, '1');
    try {
      renderWithProviders(<KanbanBoard />, { store });

      expect(await screen.findByText('Start your first task')).toBeVisible();
      expect(
        screen.getByText(
          'Create a task, then Start to move it toward review and merge.',
        ),
      ).toBeVisible();
    } finally {
      localStorage.removeItem(onboardingKey);
    }
  });

  it('selects a task on click and opens it on double click', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const task = {
      id: 'task-1',
      title: 'Inspector target',
      description: 'desc',
      status: 'BACKLOG',
      priority: 'MEDIUM',
    };

    vi.mocked(apiClient.getTasks).mockResolvedValue([task]);
    vi.mocked(apiClient.getTask).mockResolvedValue(task);
    vi.mocked(apiClient.getTaskEvents).mockResolvedValue([]);

    const store = createStore();
    store.set(boardLoadingAtom, false);
    store.set(tasksAtom, [task]);

    navigateMock.mockReset();
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithProviders(<KanbanBoard />, { store });

    // The auto-select effect may suffix the label with " (selected)"; use a regex match.
    const card = await screen.findByRole('button', { name: /^Inspector target/ });

    await user.click(card);

    expect(screen.getByText('Task Inspector')).toBeVisible();
    expect(navigateMock).not.toHaveBeenCalled();

    await user.dblClick(card);
    expect(navigateMock).toHaveBeenCalledWith('/task/task-1');
  });

  it('renders 4 column headers', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const tasks = [
      {
        id: 'task-b',
        title: 'Backlog task',
        description: 'desc',
        status: 'BACKLOG',
        priority: 'MEDIUM',
      },
      {
        id: 'task-ip',
        title: 'In progress task',
        description: 'desc',
        status: 'IN_PROGRESS',
        priority: 'MEDIUM',
      },
      {
        id: 'task-r',
        title: 'Review task',
        description: 'desc',
        status: 'REVIEW',
        priority: 'MEDIUM',
      },
      {
        id: 'task-d',
        title: 'Done task',
        description: 'desc',
        status: 'DONE',
        priority: 'MEDIUM',
      },
    ];
    vi.mocked(apiClient.getTasks).mockResolvedValue(tasks);
    vi.mocked(apiClient.getTaskEvents).mockResolvedValue([]);
    vi.mocked(apiClient.getTask).mockImplementation(async (taskId: string) => {
      const match = tasks.find((task) => task.id === taskId);
      return match ?? tasks[0]!;
    });

    const store = createStore();
    store.set(boardLoadingAtom, false);
    store.set(tasksAtom, tasks);

    renderWithProviders(<KanbanBoard />, { store });

    expect(await screen.findByRole('heading', { name: 'Backlog' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'In Progress' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Review' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Done' })).toBeVisible();
  });

  it('keeps lanes visible while loading', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.getTasks).mockImplementation(() => new Promise(() => {}));
    vi.mocked(apiClient.getTaskEvents).mockResolvedValue([]);

    const store = createStore();
    store.set(boardLoadingAtom, true);
    store.set(tasksAtom, []);

    renderWithProviders(<KanbanBoard />, { store });

    expect(await screen.findByRole('heading', { name: 'Backlog' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'In Progress' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Review' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Done' })).toBeVisible();
  });

  it('shows error message', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.getTasks).mockRejectedValue(new Error('Failed to load board'));
    vi.mocked(apiClient.getTaskEvents).mockResolvedValue([]);

    const store = createStore();
    store.set(boardLoadingAtom, false);

    renderWithProviders(<KanbanBoard />, { store });

    expect(await screen.findByText('Failed to load board')).toBeVisible();
  });

  it('selects backlog rows on click and opens them on double click', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const task = {
      id: 'task-2',
      title: 'Chat target',
      description: 'desc',
      status: 'BACKLOG',
      priority: 'MEDIUM',
    };

    vi.mocked(apiClient.getTasks).mockResolvedValue([task]);
    vi.mocked(apiClient.getTask).mockResolvedValue(task);
    vi.mocked(apiClient.getTaskEvents).mockResolvedValue([]);

    const store = createStore();
    store.set(boardLoadingAtom, false);
    store.set(tasksAtom, [task]);

    navigateMock.mockReset();
    const user = userEvent.setup();
    renderWithProviders(<KanbanBoard />, { store });

    await user.click(screen.getByRole('radio', { name: 'Backlog list view' }));
    const rowButton = await screen.findByRole('button', { name: /Chat target/i });
    await user.click(rowButton);

    expect(screen.getByText('Task Inspector')).toBeVisible();
    expect(navigateMock).not.toHaveBeenCalled();

    await user.dblClick(rowButton);
    expect(navigateMock).toHaveBeenCalledWith('/task/task-2');
  });

  it('opens delete confirmation from the card context menu', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const task = {
      id: 'task-3',
      title: 'Delete target',
      description: 'desc',
      status: 'BACKLOG',
      priority: 'MEDIUM',
    };

    vi.mocked(apiClient.getTasks).mockResolvedValue([task]);
    vi.mocked(apiClient.getTask).mockResolvedValue(task);
    vi.mocked(apiClient.getTaskEvents).mockResolvedValue([]);

    const store = createStore();
    store.set(boardLoadingAtom, false);
    store.set(tasksAtom, [task]);

    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWithProviders(<KanbanBoard />, { store });

    // Right-click the card to open the context menu, then select Delete.
    const card = await screen.findByRole('button', { name: /^Delete target/ });
    await user.pointer({ target: card, keys: '[MouseRight]' });

    const deleteItem = await screen.findByRole('menuitem', { name: /Delete/i });
    await user.click(deleteItem);

    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('Delete task?')).toBeVisible();
    expect(within(dialog).getByText('Delete target')).toBeVisible();
  });
});
