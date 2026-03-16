import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { ChatSidePanel } from '@/components/session/chat-side-panel';
import { mockEvent, mockTask } from '@/test/mocks';
import { useTaskEvents } from '@/lib/hooks/use-task-events';

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
  });

  const defaultEvents = [
    mockEvent({ session_id: 'worker-session', created_at: '2026-01-01T00:00:00Z' }),
    mockEvent({ session_id: 'reviewer-session', created_at: '2026-01-01T01:00:00Z' }),
  ];

  const defaultHookReturn = {
    task: mockTask(),
    events: defaultEvents,
    loading: false,
    runningSince: null,
    isRunning: false,
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

  it('filters the event stream by lane session when the user switches tabs', async () => {
    useTaskEventsMock.mockReturnValue(defaultHookReturn);

    renderWithProviders(
      <ChatSidePanel taskId="task-1" layout="chat-right" onSetLayout={vi.fn()} onClose={vi.fn()} />,
      { initialEntries: ['/?lane=worker'] },
    );

    expect(eventStreamRender).toHaveBeenCalled();
    const workerEvents = eventStreamRender.mock.calls.at(-1)![0].events;
    expect(workerEvents.filter((event: typeof defaultEvents[number]) => event.session_id !== 'worker-session')).toHaveLength(0);

    eventStreamRender.mockClear();
    const reviewerTab = screen.getByRole('tab', { name: 'Reviewer' });
    const user = userEvent.setup();
    await user.click(reviewerTab);

    const reviewerEvents = eventStreamRender.mock.calls.at(-1)![0].events;
    expect(reviewerEvents.filter((event: typeof defaultEvents[number]) => event.session_id !== 'reviewer-session')).toHaveLength(0);
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
