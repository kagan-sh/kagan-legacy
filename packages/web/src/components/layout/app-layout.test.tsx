import { describe, expect, it, vi } from 'vitest';
import { createStore } from 'jotai';
import { fireEvent, screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { Component as AppLayout } from '@/components/layout/app-layout';
import {
  rightRailDismissalKey,
  rightRailChatSessionIdAtom,
  rightRailDismissalsAtom,
  rightRailModeAtom,
  rightRailTaskIdAtom,
} from '@/lib/atoms/ui';

vi.mock('@/lib/hooks/use-event-stream', () => ({
  useEventStream: () => undefined,
}));

vi.mock('@/lib/hooks/use-mobile', () => ({
  useIsMobile: () => false,
}));

vi.mock('@/components/session/chat-side-panel', () => ({
  ChatSidePanel: ({
    taskId,
    layout,
    onClose,
  }: {
    taskId: string;
    layout: string;
    onClose: () => void;
  }) => (
    <div data-testid="chat-side-panel" data-layout={layout}>
      <span>{taskId}</span>
      <button type="button" onClick={onClose}>Close chat</button>
    </div>
  ),
}));

vi.mock('@/components/session/orchestrator-chat-panel', () => ({
  OrchestratorChatPanel: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="orchestrator-chat-panel">{sessionId}</div>
  ),
}));

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn().mockResolvedValue([{ id: '1', name: 'Test', active: true }]),
  },
}));

describe('AppLayout', () => {
  it('Space does not cycle chat rail; Escape closes it', async () => {
    const store = createStore();
    store.set(rightRailModeAtom, 'chat-right');
    store.set(rightRailTaskIdAtom, 'task-123');

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/task/task-123'] });

    expect(await screen.findByTestId('chat-side-panel')).toHaveAttribute('data-layout', 'chat-right');

    fireEvent.keyDown(window, { key: ' ' });
    expect(store.get(rightRailModeAtom)).toBe('chat-right');

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(store.get(rightRailModeAtom)).toBe('none');
    expect(store.get(rightRailDismissalsAtom)).toEqual({
      [rightRailDismissalKey({ kind: 'task', id: 'task-123' })]: true,
    });
  });

  it('records task dismissal when the chat panel close button is used', async () => {
    const store = createStore();
    store.set(rightRailModeAtom, 'chat-right');
    store.set(rightRailTaskIdAtom, 'task-456');

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/task/task-456'] });

    fireEvent.click(await screen.findByRole('button', { name: 'Close chat' }));

    expect(store.get(rightRailModeAtom)).toBe('none');
    expect(store.get(rightRailDismissalsAtom)).toEqual({
      [rightRailDismissalKey({ kind: 'task', id: 'task-456' })]: true,
    });
  });

  it('does not mount a duplicate orchestrator rail for the active full chat route', async () => {
    const store = createStore();
    store.set(rightRailModeAtom, 'chat-right');
    store.set(rightRailChatSessionIdAtom, 'chat-123');

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/chat/chat-123'] });

    expect(await screen.findByRole('main')).toBeInTheDocument();
    expect(screen.queryByTestId('orchestrator-chat-panel')).not.toBeInTheDocument();
  });
});
