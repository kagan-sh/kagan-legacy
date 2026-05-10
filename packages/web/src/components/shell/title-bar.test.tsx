import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { TitleBar } from './title-bar';
import { spotlightOpenAtom } from '@/lib/atoms/shell';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { apiClient } from '@/lib/api/client';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getChatAgents: vi.fn(),
  },
}));

vi.mock('@/lib/hooks/use-active-project', () => ({
  useActiveProject: () => ({ id: 'p1', name: 'kagan', active: true }),
}));

beforeEach(() => {
  vi.mocked(apiClient.getChatAgents).mockResolvedValue({
    backends: [
      { name: 'claude-code', available: true },
      { name: 'codex', available: true },
    ],
    default: 'claude-code',
  });
});

describe('TitleBar', () => {
  it('renders both workspace tabs', () => {
    renderWithProviders(<TitleBar />);
    expect(screen.getByRole('link', { name: /workspace/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /kanban/i })).toBeInTheDocument();
  });

  it('opens spotlight when search trigger clicked', () => {
    const store = createStore();
    renderWithProviders(<TitleBar />, { store });
    fireEvent.click(screen.getByRole('button', { name: /search tasks/i }));
    expect(store.get(spotlightOpenAtom)).toBe(true);
  });

  it('shows daemon online state when SSE connected', () => {
    const store = createStore();
    store.set(sseConnectedAtom, true);
    renderWithProviders(<TitleBar />, { store });
    expect(screen.getByTitle(/daemon connected/i)).toBeInTheDocument();
  });

  it('shows daemon offline state when SSE disconnected', () => {
    renderWithProviders(<TitleBar />);
    expect(screen.getByTitle(/daemon offline/i)).toBeInTheDocument();
  });

  it('marks the kanban tab active on /board', () => {
    renderWithProviders(<TitleBar />, { initialEntries: ['/board'] });
    expect(screen.getByRole('link', { name: /kanban/i })).toHaveAttribute('aria-current', 'page');
  });

  it('marks the workspace tab active on /chat', () => {
    renderWithProviders(<TitleBar />, { initialEntries: ['/chat'] });
    expect(screen.getByRole('link', { name: /workspace/i })).toHaveAttribute('aria-current', 'page');
  });
});
