import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act } from '@testing-library/react';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { CardPulse } from '@/components/board/card-pulse';
import type { WireEvent } from '@kagan/shared-api-client';

function dispatchSessionEvent(event: WireEvent) {
  window.dispatchEvent(
    new CustomEvent('kagan:session-event', {
      detail: { task_id: 't-1', event },
    }),
  );
}

function mockEvent(overrides: Partial<WireEvent> = {}): WireEvent {
  return {
    id: 'evt-1',
    session_id: 's-1',
    type: 'OUTPUT_CHUNK',
    payload: { text: 'building' },
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('CardPulse', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns null for completed/done tasks', () => {
    const { container } = renderWithProviders(
      <CardPulse sessionId={null} status="DONE" />,
    );
    expect(container.querySelector('[data-testid="card-pulse-running"]')).toBeNull();
    expect(container.querySelector('[data-testid="card-pulse-queued"]')).toBeNull();
  });

  it('shows a queued pill for BACKLOG tasks', () => {
    renderWithProviders(<CardPulse sessionId={null} status="BACKLOG" />);
    expect(screen.getByTestId('card-pulse-queued')).toBeVisible();
    expect(screen.getByText(/Queued/)).toBeVisible();
    expect(screen.getByRole('status', { name: 'Queued' })).toBeVisible();
  });

  it('renders running dot + elapsed time when active', () => {
    const startedAt = new Date(Date.now() - 74_000).toISOString();
    renderWithProviders(
      <CardPulse sessionId="s-1" status="IN_PROGRESS" startedAt={startedAt} />,
    );
    expect(screen.getByTestId('card-pulse-running')).toBeVisible();
    expect(screen.getByRole('status', { name: 'Running' })).toBeVisible();
    expect(screen.getByText('1m 14s')).toBeVisible();
  });

  it('shows the latest SSE log line after a 1 Hz coalesced tick', () => {
    const startedAt = new Date().toISOString();
    renderWithProviders(
      <CardPulse sessionId="s-1" status="IN_PROGRESS" startedAt={startedAt} />,
    );

    act(() => {
      dispatchSessionEvent(mockEvent({ payload: { text: 'compiling sources' } }));
      vi.advanceTimersByTime(1000);
    });

    expect(screen.getByText('compiling sources')).toBeVisible();
  });

  it('disables the dot pulse animation when prefers-reduced-motion is on', () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = (query: string) =>
      ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList;

    try {
      const startedAt = new Date().toISOString();
      renderWithProviders(
        <CardPulse sessionId="s-1" status="IN_PROGRESS" startedAt={startedAt} />,
      );
      const dot = screen.getByRole('status', { name: 'Running' });
      expect(dot.className).not.toMatch(/animate-pulse/);
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });

  it('renders nothing when IN_PROGRESS without an active session', () => {
    const { container } = renderWithProviders(
      <CardPulse sessionId={null} status="IN_PROGRESS" />,
    );
    expect(container.querySelector('[data-testid="card-pulse-running"]')).toBeNull();
    expect(container.querySelector('[data-testid="card-pulse-queued"]')).toBeNull();
  });
});
