import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, act } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { ChatStreamEntries } from '@/components/chat/chat-stream-entries';

afterEach(() => vi.useRealTimers());

describe('StreamThoughtBlock', () => {
  it("renders 'Thinking' label with token count from content length", () => {
    const content = 'a'.repeat(40); // ≈ 10 tokens
    renderWithProviders(
      <ChatStreamEntries
        entries={[{ kind: 'thought', content, startedAt: Date.now() }]}
      />,
    );
    expect(screen.getByText(/thinking…/)).toBeVisible();
    expect(screen.getByText(/10 tok/)).toBeVisible();
  });

  it('elapsed timer increments after 100ms', async () => {
    vi.useFakeTimers();
    const startedAt = Date.now();
    renderWithProviders(
      <ChatStreamEntries
        entries={[{ kind: 'thought', content: 'x', startedAt }]}
      />,
    );
    // At t=0, elapsed = 0s
    expect(screen.getByText(/0s/)).toBeVisible();
    // Advance 500ms — interval fires, elapsed should update
    await act(() => { vi.advanceTimersByTime(500); });
    expect(screen.queryByText(/0\.0s/)).toBeNull();
  });
});
