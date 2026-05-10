/**
 * chat-page.test.tsx
 *
 * Tests:
 *  (a) ws-head renders with a task-bound session
 *  (b) ws-head renders with an orchestrator session (no task)
 *  (c) the page does NOT render any inner sidebar (regression guard)
 */

import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@testing-library/react';
import { createStore } from 'jotai';
import { Provider } from 'jotai';
import { MemoryRouter, Routes, Route } from 'react-router';
import { TooltipProvider } from '@/components/ui/tooltip';
import { tasksAtom } from '@/lib/atoms/board';
import { mockTask } from '@/test/mocks';
import { Component as ChatPage } from './chat-page';
import type { SessionItemResponse } from '@kagan/shared-api-client';

// ── Module mocks ──────────────────────────────────────────────────────────────

// Mutable container — vi.mock factory captures this object reference at
// hoist time; tests mutate `.sessions` per-test.
const sessionListState = {
  sessions: [] as SessionItemResponse[],
};

vi.mock('@/lib/hooks/use-session-list', () => ({
  useSessionList: () => ({
    sessions: sessionListState.sessions,
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

vi.mock('@/components/session/OrchestratorSessionBody', () => ({
  OrchestratorSessionBody: ({ chatSessionId }: { chatSessionId: string }) => (
    <div data-testid="orchestrator-body" data-session-id={chatSessionId} />
  ),
}));

// ── Render helper ─────────────────────────────────────────────────────────────

function renderChatPage(path: string, store = createStore()) {
  return render(
    <Provider store={store}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:id" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </Provider>,
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeOrchestratorSession(): SessionItemResponse {
  return {
    id: 'sess-orch-1',
    chat_session_id: 'chat-orch-1',
    type: 'orchestrator',
    title: 'Orchestrator session',
    task_id: null,
    task_status: null,
    project_id: 'p1',
    updated_at: '2026-05-10T00:00:00Z',
    capabilities: { can_stop: false, can_send: true },
    role: null,
  } as unknown as SessionItemResponse;
}

function makeTaskSession(taskId: string): SessionItemResponse {
  return {
    id: 'sess-task-1',
    chat_session_id: 'chat-task-1',
    type: 'orchestrator',
    title: 'Task session',
    task_id: taskId,
    task_status: 'IN_PROGRESS',
    project_id: 'p1',
    updated_at: '2026-05-10T00:00:00Z',
    capabilities: { can_stop: true, can_send: true },
    role: null,
  } as unknown as SessionItemResponse;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ChatPage — ws-head', () => {
  it('(a) renders ws-head with task-bound session', () => {
    const task = mockTask({ id: 'task-1', title: 'Build the thing', status: 'IN_PROGRESS' });
    const session = makeTaskSession(task.id);
    sessionListState.sessions = [session];

    const store = createStore();
    store.set(tasksAtom, [task]);

    renderChatPage('/chat/sess-task-1', store);

    expect(screen.getByTestId('ws-head')).toBeInTheDocument();
    expect(screen.getByTestId('ws-head-title')).toHaveTextContent('Build the thing');
    // Status pill reflects In Progress
    expect(screen.getByTestId('ws-head-status-pill')).toHaveTextContent('In Progress');
    // Open task link rendered for task-bound sessions
    expect(screen.getByTestId('ws-head-open-task')).toBeInTheDocument();
    // Chat body rendered
    expect(screen.getByTestId('orchestrator-body')).toBeInTheDocument();
  });

  it('(b) renders ws-head with orchestrator session (no task)', () => {
    const session = makeOrchestratorSession();
    sessionListState.sessions = [session];

    const store = createStore();
    store.set(tasksAtom, []);

    renderChatPage('/chat/sess-orch-1', store);

    expect(screen.getByTestId('ws-head')).toBeInTheDocument();
    expect(screen.getByTestId('ws-head-title')).toHaveTextContent('Orchestrator session');
    // No open-task link when no task
    expect(screen.queryByTestId('ws-head-open-task')).not.toBeInTheDocument();
    // Default Backlog when task_status is null
    expect(screen.getByTestId('ws-head-status-pill')).toHaveTextContent('Backlog');
  });

  it('(c) does NOT render any inner sidebar (regression guard)', () => {
    const session = makeOrchestratorSession();
    sessionListState.sessions = [session];

    const store = createStore();
    store.set(tasksAtom, []);

    renderChatPage('/chat/sess-orch-1', store);

    // chat-page must not render its own <aside>. Without ShellLayout, there
    // should be zero elements with role="complementary".
    const asides = screen.queryAllByRole('complementary');
    expect(asides).toHaveLength(0);
  });

  it('shows empty state when no session matches the route id', () => {
    sessionListState.sessions = [];
    renderChatPage('/chat/nonexistent');
    expect(screen.getByTestId('chat-page-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('ws-head')).not.toBeInTheDocument();
  });

  it('shows empty state when route has no id', () => {
    sessionListState.sessions = [];
    renderChatPage('/chat');
    expect(screen.getByTestId('chat-page-empty')).toBeInTheDocument();
  });
});
