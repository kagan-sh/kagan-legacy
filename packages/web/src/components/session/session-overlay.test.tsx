import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { SessionOverlay } from '@/components/session/SessionOverlay';
import {
  selectedSessionAtom,
  sessionOverlayOpenAtom,
  sessionOverlayLayoutAtom,
} from '@/lib/atoms/ui';
import type { SessionItemResponse } from '@kagan/shared-api-client';

const actionMocks = vi.hoisted(() => ({
  stop: vi.fn(),
  close: vi.fn(),
}));

function makeSession(overrides: Partial<SessionItemResponse> = {}): SessionItemResponse {
  return {
    id: 'sess-1',
    type: 'orchestrator',
    role: null,
    status: 'active',
    title: 'Test Session',
    backend: 'claude',
    project_id: null,
    task_id: null,
    session_id: null,
    chat_session_id: null,
    updated_at: '2026-05-08T12:00:00Z',
    capabilities: {
      can_chat: true,
      can_stream: true,
      can_replay: true,
      can_stop: true,
      can_close: true,
      has_kagan_tools: true,
    },
    ...overrides,
  };
}

vi.mock('@/lib/hooks/use-session-list', () => ({
  useSessionList: () => ({
    sessions: [
      makeSession({ id: 'sess-1', type: 'orchestrator', title: 'Orchestrator' }),
      makeSession({ id: 'sess-2', type: 'task', title: 'Task', task_id: 'task-1' }),
      makeSession({ id: 'sess-3', type: 'general', title: 'General' }),
    ],
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

vi.mock('@/lib/hooks/use-session-actions', () => ({
  useSessionActions: () => ({
    canStop: (session: SessionItemResponse) => session.capabilities.can_stop,
    canClose: (session: SessionItemResponse) => session.capabilities.can_close,
    stop: actionMocks.stop,
    close: actionMocks.close,
  }),
}));

vi.mock('@/components/session/OrchestratorSessionBody', () => ({
  OrchestratorSessionBody: ({ chatSessionId }: { chatSessionId: string }) => (
    <div data-testid="orchestrator-body">{chatSessionId}</div>
  ),
}));

vi.mock('@/components/session/TaskSessionBody', () => ({
  TaskSessionBody: ({ taskId, sessionId }: { taskId: string; sessionId?: string }) => (
    <div data-testid="task-body">{`${taskId}:${sessionId ?? ''}`}</div>
  ),
}));

vi.mock('@/components/session/GeneralSessionBody', () => ({
  GeneralSessionBody: ({ chatSessionId }: { chatSessionId: string }) => (
    <div data-testid="general-body">{chatSessionId}</div>
  ),
}));

describe('SessionOverlay', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
    actionMocks.stop.mockClear();
    actionMocks.close.mockClear();
  });

  it('renders orchestrator session body', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(selectedSessionAtom, makeSession({ type: 'orchestrator' }));

    renderWithProviders(<SessionOverlay />, { store });
    expect(screen.getByTestId('orchestrator-body')).toBeInTheDocument();
  });

  it('passes raw chat_session_id to orchestrator body', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(
      selectedSessionAtom,
      makeSession({
        id: 'orch:chat-raw',
        type: 'orchestrator',
        chat_session_id: 'chat-raw',
      }),
    );

    renderWithProviders(<SessionOverlay />, { store });
    expect(screen.getByTestId('orchestrator-body')).toHaveTextContent('chat-raw');
  });

  it('renders task session body', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(selectedSessionAtom, makeSession({ type: 'task', task_id: 'task-1' }));

    renderWithProviders(<SessionOverlay />, { store });
    expect(screen.getByTestId('task-body')).toBeInTheDocument();
  });

  it('passes task_id and raw session_id to task body', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(
      selectedSessionAtom,
      makeSession({
        id: 'task:worker-session',
        type: 'task',
        task_id: 'task-1',
        session_id: 'worker-session',
      }),
    );

    renderWithProviders(<SessionOverlay />, { store });
    expect(screen.getByTestId('task-body')).toHaveTextContent('task-1:worker-session');
  });

  it('renders general session body', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(selectedSessionAtom, makeSession({ type: 'general' }));

    renderWithProviders(<SessionOverlay />, { store });
    expect(screen.getByTestId('general-body')).toBeInTheDocument();
  });

  it('passes raw chat_session_id to general body', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(
      selectedSessionAtom,
      makeSession({
        id: 'gen:chat-raw',
        type: 'general',
        chat_session_id: 'chat-raw',
      }),
    );

    renderWithProviders(<SessionOverlay />, { store });
    expect(screen.getByTestId('general-body')).toHaveTextContent('chat-raw');
  });

  it('keeps unified session id for stop and close actions', () => {
    const session = makeSession({
      id: 'orch:chat-raw',
      type: 'orchestrator',
      chat_session_id: 'chat-raw',
    });
    store.set(sessionOverlayOpenAtom, true);
    store.set(selectedSessionAtom, session);

    renderWithProviders(<SessionOverlay />, { store });
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(actionMocks.stop).toHaveBeenCalledWith(expect.objectContaining({ id: 'orch:chat-raw' }));
    expect(actionMocks.close).toHaveBeenCalledWith(expect.objectContaining({ id: 'orch:chat-raw' }));
  });

  it('closes on Escape key', () => {
    store.set(sessionOverlayOpenAtom, true);
    renderWithProviders(<SessionOverlay />, { store });

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(store.get(sessionOverlayOpenAtom)).toBe(false);
  });

  it('toggles layout between docked and fullscreen', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(selectedSessionAtom, makeSession());
    store.set(sessionOverlayLayoutAtom, 'docked');

    renderWithProviders(<SessionOverlay />, { store });
    const fullscreenBtn = screen.getByLabelText('Fullscreen');
    fireEvent.click(fullscreenBtn);

    expect(store.get(sessionOverlayLayoutAtom)).toBe('fullscreen');
  });
});
