/**
 * mention-popover.test.tsx
 *
 * Tests the MentionPopover component:
 * - Does not call search immediately (debounced)
 * - Calls search after debounce with correct args
 * - Renders dual-source rows with source icons
 * - Esc closes the popover
 * - Backspace past `#` closes the popover
 * - Mid-word `#` does not trigger fetch
 *
 * Strategy: real timers + waitFor.
 * Value is set via userEvent.type so jsdom tracks selectionStart correctly.
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

/**
 * Type text into the textarea using userEvent so jsdom properly tracks selectionStart.
 * This is critical — Object.defineProperty bypasses jsdom's selection tracking.
 */
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

    // Type '#foo' with real events — but hold timers so debounce can't fire
    // We use fireEvent here since userEvent.type would hit async complications
    // Instead, manually set value via proper assignment (not Object.defineProperty)
    // so jsdom tracks selectionStart
    el.focus();
    act(() => {
      // Use the native value setter to bypass React's controlled input tracking
      // but still have jsdom set selectionStart properly
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value',
      )?.set;
      nativeSetter?.call(el, '#foo');
      el.setSelectionRange(4, 4);
      fireEvent.input(el);
    });

    // Advance time by less than the debounce
    act(() => { vi.advanceTimersByTime(100); });

    expect(client.searchMentions).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('calls searchMentions with correct args after debounce', async () => {
    const client = await getMockClient();
    const el = buildPopover();

    await typeText(el, '#hello');

    await waitFor(() => {
      expect(client.searchMentions).toHaveBeenCalledWith(
        expect.objectContaining({ projectId: 'proj-1', q: 'hello' }),
      );
    }, { timeout: 1000 });
  });

  it('renders source icons and titles after debounce', async () => {
    const el = buildPopover();
    await typeText(el, '#');

    await waitFor(() => {
      expect(screen.getAllByText('◆').length).toBeGreaterThan(0);
    }, { timeout: 1000 });

    expect(screen.getAllByText('🐙').length).toBeGreaterThan(0);
    expect(screen.getByText('Fix the login bug')).toBeInTheDocument();
    expect(screen.getByText('Improve docs')).toBeInTheDocument();
  });

  it('renders state badge for github mentions', async () => {
    const el = buildPopover();
    await typeText(el, '#');

    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    }, { timeout: 1000 });
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

    // Wait long enough for any debounce to fire
    await new Promise((r) => setTimeout(r, 400));

    expect(client.searchMentions).not.toHaveBeenCalled();
  });
});
