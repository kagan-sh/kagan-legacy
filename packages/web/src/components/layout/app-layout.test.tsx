import { describe, expect, it, vi } from 'vitest';
import { createStore } from 'jotai';
import { fireEvent, screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { Component as AppLayout } from '@/components/layout/app-layout';
import {
  sessionOverlayOpenAtom,
} from '@/lib/atoms/ui';

vi.mock('@/lib/hooks/use-event-stream', () => ({
  useEventStream: () => undefined,
}));

vi.mock('@/lib/hooks/use-mobile', () => ({
  useIsMobile: () => false,
}));

vi.mock('@/components/session/SessionOverlay', () => ({
  SessionOverlay: () => <div data-testid="session-overlay" />,
}));

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn().mockResolvedValue([{ id: '1', name: 'Test', active: true }]),
  },
}));

describe('AppLayout', () => {
  it('renders a single session overlay shell', async () => {
    const store = createStore();
    renderWithProviders(<AppLayout />, { store, initialEntries: ['/board'] });
    expect(await screen.findByTestId('session-overlay')).toBeInTheDocument();
  });

  it('Space does not toggle overlay', async () => {
    const store = createStore();
    store.set(sessionOverlayOpenAtom, true);

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/board'] });

    fireEvent.keyDown(window, { key: ' ' });
    expect(store.get(sessionOverlayOpenAtom)).toBe(true);
  });

  it('does not mount a duplicate overlay for the active full chat route', async () => {
    const store = createStore();
    store.set(sessionOverlayOpenAtom, true);

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/chat/chat-123'] });

    expect(await screen.findByRole('main')).toBeInTheDocument();
    const overlays = screen.queryAllByTestId('session-overlay');
    expect(overlays).toHaveLength(1);
  });
});
