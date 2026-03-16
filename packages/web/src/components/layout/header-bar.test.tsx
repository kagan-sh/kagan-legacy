import { describe, expect, it, vi } from 'vitest';
import { createStore } from 'jotai';
import { screen } from '@testing-library/react';
import { HeaderBar } from '@/components/layout/header-bar';
import { wsConnectedAtom } from '@/lib/atoms/connection';
import { renderWithProviders } from '@/test/render';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn().mockResolvedValue([]),
    getProjectRepos: vi.fn().mockResolvedValue([]),
  },
}));

describe('HeaderBar', () => {
  it('shows disconnected status when websocket is offline', () => {
    const store = createStore();
    store.set(wsConnectedAtom, false);

    renderWithProviders(<HeaderBar />, { store });

    expect(screen.getByText('Offline')).toBeVisible();
  });

  it('calls callback when Quick Actions trigger is clicked', async () => {
    const onOpenCommandPalette = vi.fn();

    renderWithProviders(<HeaderBar onOpenCommandPalette={onOpenCommandPalette} />);

    screen.getByRole('button', { name: /Search or jump/ }).click();

    expect(onOpenCommandPalette).toHaveBeenCalledTimes(1);
  });
});
