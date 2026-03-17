import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { ChatSidePanel } from '@/components/session/chat-side-panel';
import { mockEvent, mockTask } from '@/test/mocks';
import { useTaskEvents } from '@/lib/hooks/use-task-events';
import { apiClient } from '@/lib/api/client';

const eventStreamRender = vi.fn();
const chatInputBarRender = vi.fn();

vi.mock('@/components/session/event-stream', () => ({
  EventStream: (props: Record<string, unknown>) => {
    eventStreamRender(props);
    return <div data-testid="mock-event-stream" />;
  },
}));

vi.mock('@/components/session/follow-up-queue', () => ({
  FollowUpQueue: () => <div data-testid="mock-follow-up-queue" />,
}));

vi.mock('@/components/chat/chat-input-bar', () => ({
  ChatInputBar: (props: Record<string, unknown>) => {
    chatInputBarRender(props);
    return <div data-testid="mock-chat-input" data-disable-send={props.disableSend ? 'true' : 'false'} />;
  },
}));

vi.mock('@/lib/hooks/use-task-events', () => ({
  useTaskEvents: vi.fn(),
}));

vi.mock('@/lib/hooks/use-mobile', () => ({
  useIsMobile: () => false,
}));

describe('ChatSidePanel', () => {
  const useTaskEventsMock = vi.mocked(useTaskEvents);

  beforeEach(() => {
    eventStreamRender.mockReset();
    chatInputBarRender.mockReset();
    useTaskEventsMock.mockReset();
    vi.spyOn(apiClient, 'getTaskSessions').mockResolvedValue([
      { id: 'worker-session', mode: 'AUTO', status: 'COMPLETED', agent_backend: 'test', started_at: '2026-01-01T00:00:00Z' },
      { id: 'reviewer-session', mode: 'AUTO', status: 'COMPLETED', agent_backend: 'test', started_at: '2026-01-01T01:00:00Z' },
    ]);
  });

  const workerEvents = [
    mockEvent({ session_id: 'worker-session', created_at: '2026-01-01T00:00:00Z' }),
  ];

  const reviewerEvents = [
    mockEvent({ session_id: 'reviewer-session', created_at: '2026-01-01T01:00:00Z' }),
  ];

  const defaultHookReturn = {
    task: mockTask(),
    events: workerEvents,
    loading: false,
    runningSince: null,
    isRunning: false,
    sessions: [
      { id: 'worker-session', mode: 'AUTO', status: 'COMPLETED', agent_backend: 'test', started_at: '2026-01-01T00:00:00Z' },
      { id: 'reviewer-session', mode: 'AUTO', status: 'COMPLETED', agent_backend: 'test', started_at: '2026-01-01T01:00:00Z' },
    ],
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
  };

  it('passes sessionId to useTaskEvents based on active lane', async () => {
    useTaskEventsMock.mockReturnValue(defaultHookReturn);

    renderWithProviders(
      <ChatSidePanel taskId="task-1" layout="chat-right" onSetLayout={vi.fn()} onClose={vi.fn()} />,
      { initialEntries: ['/?lane=worker'] },
    );

    // Wait for sessions preload to resolve
    await vi.waitFor(() => {
      const calls = useTaskEventsMock.mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.[1]?.sessionId).toBe('worker-session');
    });

    useTaskEventsMock.mockReturnValue({ ...defaultHookReturn, events: reviewerEvents });
    const reviewerTab = screen.getByRole('tab', { name: 'Reviewer' });
    const user = userEvent.setup();
    await user.click(reviewerTab);

    await vi.waitFor(() => {
      const calls = useTaskEventsMock.mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.[1]?.sessionId).toBe('reviewer-session');
    });
  });

  it('passes isRunning to the chat input disable flag', () => {
    useTaskEventsMock.mockReturnValue({ ...defaultHookReturn, isRunning: true });

    renderWithProviders(
      <ChatSidePanel taskId="task-1" layout="chat-right" onSetLayout={vi.fn()} onClose={vi.fn()} />,
      { initialEntries: ['/?lane=worker'] },
    );

    expect(chatInputBarRender).toHaveBeenCalled();
    const { disableSend } = chatInputBarRender.mock.calls[0]![0];
    expect(disableSend).toBe(true);
  });
});
