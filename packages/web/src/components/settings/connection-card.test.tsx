import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { ConnectionCard } from '@/components/settings/connection-card';
import { wsConnectedAtom } from '@/lib/atoms/connection';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getBaseUrl: () => 'http://localhost:8765',
    getHealth: () => Promise.resolve({ status: 'ok', version: '1.0.0' }),
  },
}));

vi.mock('@/lib/api/websocket', () => ({
  kaganWs: { disconnect: vi.fn(), connect: vi.fn() },
}));

describe('ConnectionCard', () => {
  it('shows Connected when ws is connected', () => {
    const store = createStore();
    store.set(wsConnectedAtom, true);
    renderWithProviders(<ConnectionCard />, { store });
    expect(screen.getByText('Connected')).toBeVisible();
  });

  it('shows Disconnected when ws is not connected', () => {
    const store = createStore();
    store.set(wsConnectedAtom, false);
    renderWithProviders(<ConnectionCard />, { store });
    expect(screen.getByText('Disconnected')).toBeVisible();
  });
});
