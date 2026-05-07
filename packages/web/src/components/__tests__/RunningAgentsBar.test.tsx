/**
 * RunningAgentsBar component tests.
 *
 * Tests: empty state, 2 rows render, click fires attach, reactive to atom updates.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, fireEvent, act } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { RunningAgentsBar } from '@/components/session/running-agents-bar';
import {
  setRunningAgentsAtom,
} from '@/lib/atoms/running-agents';
import {
  chatAttachAtom,
} from '@/lib/atoms/chat-attach';
import type { ActiveAgentRowResponse } from '@kagan/shared-api-client';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getRunningAgents: vi.fn().mockResolvedValue({ agents: [] }),
  },
}));

function makeAgent(overrides: Partial<ActiveAgentRowResponse> = {}): ActiveAgentRowResponse {
  return {
    task_id: 'task-1',
    task_title: 'Fix auth bug',
    task_status: 'IN_PROGRESS',
    session_id: 'sess-1',
    agent_role: 'worker',
    agent_backend: 'claude-code',
    session_status: 'running',
    started_at: new Date(Date.now() - 23_000).toISOString(),
    last_event_at: null,
    input_tokens: 12_000,
    output_tokens: 3_000,
    ...overrides,
  };
}

describe('RunningAgentsBar', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  it('renders empty state when no agents are running', () => {
    renderWithProviders(<RunningAgentsBar />, { store });
    expect(screen.getByLabelText('No agents running')).toBeInTheDocument();
    expect(screen.getByText('no agents running')).toBeInTheDocument();
  });

  it('renders a row for each running agent', () => {
    const agents = [
      makeAgent({ session_id: 'sess-1', task_title: 'Fix auth bug', agent_role: 'worker' }),
      makeAgent({ session_id: 'sess-2', task_title: 'Review PR', agent_role: 'reviewer' }),
    ];
    act(() => { store.set(setRunningAgentsAtom, agents); });

    renderWithProviders(<RunningAgentsBar />, { store });

    expect(screen.getByLabelText('Attach to worker agent: Fix auth bug')).toBeInTheDocument();
    expect(screen.getByLabelText('Attach to reviewer agent: Review PR')).toBeInTheDocument();
  });

  it('shows role glyphs', () => {
    const agents = [
      makeAgent({ session_id: 'sess-1', agent_role: 'worker' }),
      makeAgent({ session_id: 'sess-2', agent_role: 'reviewer' }),
    ];
    act(() => { store.set(setRunningAgentsAtom, agents); });

    renderWithProviders(<RunningAgentsBar />, { store });
    const glyphs = screen.getAllByText(/^[WR]$/);
    expect(glyphs).toHaveLength(2);
  });

  it('clicking a row attaches to that agent session', () => {
    const agent = makeAgent({ session_id: 'sess-abc', task_title: 'Build feature', agent_role: 'worker' });
    act(() => { store.set(setRunningAgentsAtom, [agent]); });

    renderWithProviders(<RunningAgentsBar />, { store });

    fireEvent.click(screen.getByLabelText('Attach to worker agent: Build feature'));

    const attach = store.get(chatAttachAtom);
    expect(attach).not.toBeNull();
    expect(attach?.attachedSessionId).toBe('sess-abc');
    expect(attach?.taskTitle).toBe('Build feature');
    expect(attach?.role).toBe('worker');
  });

  it('reviewer agent attach sets role correctly', () => {
    const agent = makeAgent({ session_id: 'sess-rev', task_title: 'Review', agent_role: 'reviewer' });
    act(() => { store.set(setRunningAgentsAtom, [agent]); });

    renderWithProviders(<RunningAgentsBar />, { store });
    fireEvent.click(screen.getByLabelText('Attach to reviewer agent: Review'));

    expect(store.get(chatAttachAtom)?.role).toBe('reviewer');
  });

  it('updates rendered list when atom changes', () => {
    renderWithProviders(<RunningAgentsBar />, { store });
    expect(screen.getByText('no agents running')).toBeInTheDocument();

    act(() => {
      store.set(setRunningAgentsAtom, [makeAgent({ session_id: 'sess-new', task_title: 'New task' })]);
    });

    expect(screen.getByLabelText('Attach to worker agent: New task')).toBeInTheDocument();
  });

  it('truncates long task titles', () => {
    const longTitle = 'A'.repeat(50);
    act(() => { store.set(setRunningAgentsAtom, [makeAgent({ task_title: longTitle })]); });

    renderWithProviders(<RunningAgentsBar />, { store });
    // title truncated to 28 chars + …
    expect(screen.getByText(/A{25}…/)).toBeInTheDocument();
  });
});
