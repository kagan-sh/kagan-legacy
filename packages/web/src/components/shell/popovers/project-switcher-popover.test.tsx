import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, act, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { ProjectSwitcherPopover } from './project-switcher-popover';
import {
  shellPopoverAtom,
  createProjectDialogOpenAtom,
  addRepoDialogOpenAtom,
} from '@/lib/atoms/shell';
import { projectSwitchVersionAtom } from '@/lib/atoms/board';
import { apiClient } from '@/lib/api/client';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn(),
    activateProject: vi.fn(),
    getProjectRepos: vi.fn(),
  },
}));

vi.mock('@/lib/hooks/use-active-project', () => ({
  useActiveProject: () => ({ id: 'p1', name: 'kagan', active: true }),
}));

function openPopover(store: ReturnType<typeof createStore>) {
  act(() => {
    store.set(shellPopoverAtom, {
      kind: 'project-switcher',
      anchor: { x: 100, y: 50, align: 'left' },
    });
  });
}

describe('ProjectSwitcherPopover', () => {
  beforeEach(() => {
    vi.mocked(apiClient.getProjects).mockResolvedValue([
      { id: 'p1', name: 'kagan', active: true },
      { id: 'p2', name: 'other-project', active: false },
    ]);
    vi.mocked(apiClient.activateProject).mockResolvedValue({ project_id: 'p2', active: true });
    vi.mocked(apiClient.getProjectRepos).mockResolvedValue([
      { id: 'r1', project_id: 'p1', name: 'repo', path: '/repo', default_branch: 'main', selected: true },
    ]);
  });

  it('renders nothing when closed', () => {
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders project list when opened', async () => {
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    expect(await screen.findByText('kagan')).toBeInTheDocument();
    expect(screen.getByText('other-project')).toBeInTheDocument();
  });

  it('marks the active project with a checkmark', async () => {
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    await screen.findByText('kagan');
    // The active PopoverItem renders a ✓ check
    const check = screen.getByText('✓');
    expect(check).toBeInTheDocument();
  });

  it('calls activateProject and bumps version on project click', async () => {
    const store = createStore();
    const initialVersion = store.get(projectSwitchVersionAtom);
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    await screen.findByText('other-project');
    fireEvent.click(screen.getByRole('menuitem', { name: /other-project/i }));
    await waitFor(() => {
      expect(vi.mocked(apiClient.activateProject)).toHaveBeenCalledWith('p2');
    });
    await waitFor(() => {
      expect(store.get(projectSwitchVersionAtom)).toBe(initialVersion + 1);
    });
  });

  it('closes the popover after project selection', async () => {
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    await screen.findByText('other-project');
    fireEvent.click(screen.getByRole('menuitem', { name: /other-project/i }));
    await waitFor(() => {
      expect(store.get(shellPopoverAtom).kind).toBeNull();
    });
  });

  it('opens CreateProjectDialog when "New project" is clicked', async () => {
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    await screen.findByText('New project');
    fireEvent.click(screen.getByRole('menuitem', { name: /new project/i }));
    expect(store.get(createProjectDialogOpenAtom)).toBe(true);
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });

  it('shows "Add repository" when active project has no repos', async () => {
    vi.mocked(apiClient.getProjectRepos).mockResolvedValue([]);
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    expect(await screen.findByRole('menuitem', { name: /add repository/i })).toBeInTheDocument();
  });

  it('does not show "Add repository" when active project already has repos', async () => {
    // Default mock already returns a repo — so it should be absent
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    await screen.findByText('kagan');
    await waitFor(() => {
      expect(screen.queryByRole('menuitem', { name: /add repository/i })).toBeNull();
    });
  });

  it('opens AddRepoDialog when "Add repository" is clicked', async () => {
    vi.mocked(apiClient.getProjectRepos).mockResolvedValue([]);
    const store = createStore();
    renderWithProviders(<ProjectSwitcherPopover />, { store });
    openPopover(store);
    const addBtn = await screen.findByRole('menuitem', { name: /add repository/i });
    fireEvent.click(addBtn);
    expect(store.get(addRepoDialogOpenAtom)).toBe(true);
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });
});
