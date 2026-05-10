/**
 * mention-popover.test.tsx
 *
 * Contract tests for MentionPopover debounce + keyboard behavior.
 * Product-critical fetch/ render journeys belong in Playwright.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MentionPopover } from '@/components/mentions/mention-popover';
import { MemoryRouter } from 'react-router';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    searchMentions: vi.fn(),
  },
}));

const MENTIONS = [
  { source: 'kagan' as const, id: 'kagan#abc12345', title: 'Fix the login bug', state: null },
  { source: 'github' as const, id: '#42', title: 'Improve docs', state: 'open' },
];

async function getMockClient() {
  const { apiClient } = await import('@/lib/api/client');
  return apiClient;
}

function buildPopover() {
  const { container } = render(
    <MemoryRouter>
      <MentionPopover projectId="proj-1">
        <textarea />
      </MentionPopover>
    </MemoryRouter>,
  );
  return container.querySelector('textarea')!;
}

async function typeText(el: HTMLTextAreaElement, text: string) {
  const user = userEvent.setup();
  el.focus();
  await user.type(el, text);
}

describe('MentionPopover', () => {
  beforeEach(async () => {
    const client = await getMockClient();
    vi.mocked(client.searchMentions).mockResolvedValue(MENTIONS);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('does not call search before debounce fires', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    const client = await getMockClient();

    const el = buildPopover();

    el.focus();
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value',
      )?.set;
      nativeSetter?.call(el, '#foo');
      el.setSelectionRange(4, 4);
      fireEvent.input(el);
    });

    act(() => { vi.advanceTimersByTime(100); });

    expect(client.searchMentions).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('closes the popover on Escape', async () => {
    const el = buildPopover();
    await typeText(el, '#hi');

    await waitFor(() => {
      expect(screen.getByText('Fix the login bug')).toBeInTheDocument();
    }, { timeout: 1000 });

    act(() => {
      fireEvent.keyDown(el, { key: 'Escape' });
    });

    expect(screen.queryByText('Fix the login bug')).toBeNull();
  });

  it('closes when cursor goes before #', async () => {
    const el = buildPopover();
    await typeText(el, '#t');

    await waitFor(() => {
      expect(screen.getByText('Fix the login bug')).toBeInTheDocument();
    }, { timeout: 1000 });

    act(() => {
      el.setSelectionRange(0, 0);
      fireEvent.keyDown(el, { key: 'Backspace' });
    });

    expect(screen.queryByText('Fix the login bug')).toBeNull();
  });

  it('does not call search when # is mid-word', async () => {
    const client = await getMockClient();
    vi.mocked(client.searchMentions).mockResolvedValue([]);

    const el = buildPopover();
    await typeText(el, 'foo#bar');

    await new Promise((r) => setTimeout(r, 400));

    expect(client.searchMentions).not.toHaveBeenCalled();
  });
});
