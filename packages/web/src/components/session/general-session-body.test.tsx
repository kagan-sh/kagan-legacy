import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { GeneralSessionBody } from '@/components/session/GeneralSessionBody';

vi.mock('@/lib/hooks/use-chat-session', () => ({
  useChatSession: () => ({
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
  }),
}));

describe('GeneralSessionBody', () => {
  it('shows the disclaimer message prominently', () => {
    renderWithProviders(<GeneralSessionBody sessionId="sess-1" />);
    expect(screen.getByText(/general session/i)).toBeInTheDocument();
    expect(screen.getByText(/raw backend streaming/i)).toBeInTheDocument();
  });
});
