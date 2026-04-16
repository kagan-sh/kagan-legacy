import { describe, expect, it, vi } from 'vitest';
import { createStore } from 'jotai';
import { screen } from '@testing-library/react';
import { HeaderBar } from '@/components/layout/header-bar';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { renderWithProviders } from '@/test/render';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn().mockResolvedValue([]),
    getProjectRepos: vi.fn().mockResolvedValue([]),
  },
}));

describe('HeaderBar', () => {
  it('shows disconnected status when SSE is offline', () => {
    const store = createStore();
    store.set(sseConnectedAtom, false);

    renderWithProviders(<HeaderBar />, { store });

    expect(screen.getByText('Offline')).toBeVisible();
  });

  it('calls callback when search button is clicked', async () => {
    const onOpenCommandPalette = vi.fn();

    renderWithProviders(<HeaderBar onOpenCommandPalette={onOpenCommandPalette} />);

    // The search button contains a Search icon and ⌘K shortcut hint
    const searchButton = screen.getAllByRole('button')[0]!;
    searchButton.click();

    expect(onOpenCommandPalette).toHaveBeenCalledTimes(1);
  });
});
