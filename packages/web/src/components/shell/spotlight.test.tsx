import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { Spotlight } from './spotlight';
import { spotlightOpenAtom } from '@/lib/atoms/shell';
import { tasksAtom } from '@/lib/atoms/board';
import { mockTask } from '@/test/mocks';
import { __resetRegistryForTests, registerCommand } from '@/lib/commands/registry';

vi.mock('@/lib/hooks/use-session-list', () => ({
  useSessionList: () => ({ sessions: [], loading: false, error: null, refresh: vi.fn() }),
}));

beforeEach(() => {
  __resetRegistryForTests();
});

afterEach(() => {
  __resetRegistryForTests();
});

describe('Spotlight', () => {
  it('does not render when closed', () => {
    renderWithProviders(<Spotlight />);
    expect(screen.queryByRole('dialog', { name: /command palette/i })).toBeNull();
  });

  it('renders when spotlightOpenAtom is true', () => {
    const store = createStore();
    store.set(spotlightOpenAtom, true);
    renderWithProviders(<Spotlight />, { store });
    expect(screen.getByRole('dialog', { name: /command palette/i })).toBeInTheDocument();
  });

  it('lists tasks under the Tasks group', async () => {
    const store = createStore();
    store.set(spotlightOpenAtom, true);
    store.set(tasksAtom, [mockTask({ title: 'Wire the daemon' })]);
    renderWithProviders(<Spotlight />, { store });
    await waitFor(() => {
      expect(screen.getByText('Tasks')).toBeInTheDocument();
      expect(screen.getByText('Wire the daemon')).toBeInTheDocument();
    });
  });

  it('runs a command on Enter and closes', async () => {
    const handler = vi.fn();
    registerCommand({
      id: 'open-foo',
      title: 'Open Foo',
      section: 'Navigate',
      handler,
    });
    const store = createStore();
    store.set(spotlightOpenAtom, true);
    renderWithProviders(<Spotlight />, { store });
    const input = screen.getByPlaceholderText(/search tasks/i);
    fireEvent.change(input, { target: { value: 'open-foo' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => {
      expect(handler).toHaveBeenCalled();
      expect(store.get(spotlightOpenAtom)).toBe(false);
    });
  });

  it('closes on Escape', () => {
    const store = createStore();
    store.set(spotlightOpenAtom, true);
    renderWithProviders(<Spotlight />, { store });
    fireEvent.keyDown(screen.getByPlaceholderText(/search tasks/i), { key: 'Escape' });
    expect(store.get(spotlightOpenAtom)).toBe(false);
  });

  it('wraps matching substring in task title with a mark-style element', async () => {
    const store = createStore();
    store.set(spotlightOpenAtom, true);
    store.set(tasksAtom, [mockTask({ title: 'Wire the daemon' })]);
    renderWithProviders(<Spotlight />, { store });

    const input = screen.getByPlaceholderText(/search tasks/i);
    fireEvent.change(input, { target: { value: 'Wire' } });

    await waitFor(() => {
      // The highlighted portion renders inside an <em> element
      const em = document.querySelector('em');
      expect(em).toBeTruthy();
      expect(em?.textContent).toBe('Wire');
    });
  });

  it('renders a status dot for task rows', async () => {
    const store = createStore();
    store.set(spotlightOpenAtom, true);
    store.set(tasksAtom, [mockTask({ title: 'Active task', status: 'IN_PROGRESS' })]);
    renderWithProviders(<Spotlight />, { store });

    await waitFor(() => {
      const dots = screen.getAllByTestId('spotlight-task-dot');
      expect(dots.length).toBeGreaterThan(0);
    });
  });

  it('shows empty state with italic styling when query matches nothing', async () => {
    const store = createStore();
    store.set(spotlightOpenAtom, true);
    store.set(tasksAtom, []);
    renderWithProviders(<Spotlight />, { store });

    const input = screen.getByPlaceholderText(/search tasks/i);
    fireEvent.change(input, { target: { value: 'zzz-no-match-here' } });

    await waitFor(() => {
      const empty = screen.getByTestId('spotlight-empty');
      expect(empty).toBeInTheDocument();
      expect(empty).toHaveTextContent('No results');
    });
  });
});
