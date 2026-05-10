import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, act } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { AgentsPopover } from './agents-popover';
import { shellPopoverAtom } from '@/lib/atoms/shell';
import { tasksAtom } from '@/lib/atoms/board';
import { apiClient } from '@/lib/api/client';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getChatAgents: vi.fn(),
  },
}));

function openAgents(store: ReturnType<typeof createStore>) {
  act(() => {
    store.set(shellPopoverAtom, { kind: 'agents', anchor: { x: 100, y: 50, align: 'left' } });
  });
}

describe('AgentsPopover', () => {
  beforeEach(() => {
    vi.mocked(apiClient.getChatAgents).mockResolvedValue({
      backends: [
        { name: 'claude-code', available: true },
        { name: 'codex', available: true },
        { name: 'disabled-agent', available: false },
      ],
      default: 'claude-code',
    });
  });

  it('renders nothing when closed', () => {
    const store = createStore();
    renderWithProviders(<AgentsPopover />, { store });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders agent list when opened', async () => {
    const store = createStore();
    renderWithProviders(<AgentsPopover />, { store });
    openAgents(store);
    expect(await screen.findByText('claude-code')).toBeInTheDocument();
    expect(screen.getByText('codex')).toBeInTheDocument();
  });

  it('shows disabled agents in a separate section', async () => {
    const store = createStore();
    renderWithProviders(<AgentsPopover />, { store });
    openAgents(store);
    expect(await screen.findByText('disabled-agent')).toBeInTheDocument();
  });

  it('shows running count for tasks with active sessions', async () => {
    const store = createStore();
    store.set(tasksAtom, [
      {
        id: 't1',
        title: 'Task 1',
        status: 'IN_PROGRESS',
        priority: 'MEDIUM',
        review_running: false,
        active_session: {
          id: 's1',
          status: 'running',
          launcher: null,
          agent_backend: 'claude-code',
          started_at: new Date().toISOString(),
        },
      },
    ] as never);
    renderWithProviders(<AgentsPopover />, { store });
    openAgents(store);
    // The title should mention "1 running"
    expect(await screen.findByText(/1 running/i)).toBeInTheDocument();
  });
});
