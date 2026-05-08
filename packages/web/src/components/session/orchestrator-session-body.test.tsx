import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';
import { OrchestratorSessionBody } from '@/components/session/OrchestratorSessionBody';

const useChatSessionMock = vi.hoisted(() =>
  vi.fn(() => ({
    loading: false,
    messages: [],
    streamEntries: [],
    isStreaming: false,
    projectId: null,
    onSend: vi.fn(),
    onInterrupt: vi.fn(),
    onSlashCommand: vi.fn(),
    scrollRef: { current: null },
    onPrefillConsumed: vi.fn(),
  })),
);

vi.mock('@/lib/hooks/use-chat-session', () => ({
  useChatSession: useChatSessionMock,
}));

describe('OrchestratorSessionBody', () => {
  it('loads the legacy chat hook with the raw chat session id', () => {
    renderWithProviders(<OrchestratorSessionBody chatSessionId="chat-raw" />);
    expect(useChatSessionMock).toHaveBeenCalledWith('chat-raw');
  });
});
