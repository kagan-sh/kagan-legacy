import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { ConnectionCard } from '@/components/settings/connection-card';
import { sseConnectedAtom } from '@/lib/atoms/connection';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getBaseUrl: () => 'http://localhost:8765',
    getHealth: () => Promise.resolve({ status: 'ok', version: '1.0.0' }),
  },
}));

describe('ConnectionCard', () => {
  it('shows Connected when SSE is connected', () => {
    const store = createStore();
    store.set(sseConnectedAtom, true);
    renderWithProviders(<ConnectionCard />, { store });
    expect(screen.getByText('Connected')).toBeVisible();
  });

  it('shows Reconnecting when SSE is not connected', () => {
    const store = createStore();
    store.set(sseConnectedAtom, false);
    renderWithProviders(<ConnectionCard />, { store });
    expect(screen.getByText('Reconnecting...')).toBeVisible();
  });
});
