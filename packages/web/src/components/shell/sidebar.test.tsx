import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { Sidebar } from './sidebar';
import { boardDialogAtom, tasksAtom } from '@/lib/atoms/board';
import { newSessionModalOpenAtom, sidebarCollapsedAtom } from '@/lib/atoms/shell';
import { apiClient } from '@/lib/api/client';
import { mockTask } from '@/test/mocks';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn(),
    getHealth: vi.fn(),
  },
}));

vi.mock('@/lib/hooks/use-active-project', () => ({
  useActiveProject: () => ({ id: 'p1', name: 'kagan', active: true }),
}));

vi.mock('@/lib/hooks/use-session-list', () => ({
  useSessionList: () => ({
    sessions: [
      { id: 's1', type: 'orchestrator', title: 'Orchestrator', updated_at: '2026-05-10' },
    ],
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

beforeEach(() => {
  vi.mocked(apiClient.getProjects).mockResolvedValue([
    { id: 'p1', name: 'kagan', active: true },
  ]);
  vi.mocked(apiClient.getHealth).mockResolvedValue({ status: 'ok', version: '0.14.4' });
});

describe('Sidebar', () => {
  it('renders primary actions', () => {
    renderWithProviders(<Sidebar />);
    expect(screen.getByRole('button', { name: /new task/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^new session$/i })).toBeInTheDocument();
  });

  it('opens the create-task dialog when New task is clicked', () => {
    const store = createStore();
    renderWithProviders(<Sidebar />, { store });
    fireEvent.click(screen.getByRole('button', { name: /new task/i }));
    expect(store.get(boardDialogAtom)).toEqual({ kind: 'create' });
  });

  it('opens the new session modal when New session is clicked', () => {
    const store = createStore();
    renderWithProviders(<Sidebar />, { store });
    fireEvent.click(screen.getByRole('button', { name: /^new session$/i }));
    expect(store.get(newSessionModalOpenAtom)).toBe(true);
  });

  it('collapses to width 0 when sidebarCollapsedAtom flipped on', () => {
    const store = createStore();
    store.set(sidebarCollapsedAtom, true);
    const { container } = renderWithProviders(<Sidebar />, { store });
    const aside = container.querySelector('aside');
    expect(aside).toHaveAttribute('data-collapsed', 'true');
  });

  it('renders the orchestrator session badge', async () => {
    renderWithProviders(<Sidebar />);
    const badges = await screen.findAllByText('ORCH');
    expect(badges.length).toBeGreaterThan(0);
  });

  it('renders project tasks under the active project', async () => {
    const store = createStore();
    store.set(tasksAtom, [mockTask({ title: 'Build the thing' })]);
    renderWithProviders(<Sidebar />, { store });
    expect(await screen.findByRole('button', { name: /build the thing/i })).toBeInTheDocument();
  });
});
