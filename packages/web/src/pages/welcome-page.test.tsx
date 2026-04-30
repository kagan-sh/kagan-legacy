import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { mockProject, mockRepository } from '@/test/mocks';
import { isAuthenticatedAtom } from '@/lib/atoms/auth';

const navigateMock = vi.fn();

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('@/components/welcome/preflight-gate', () => ({
  PreflightGate: () => null,
}));

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn(),
    getProjectRepos: vi.fn(),
    activateProject: vi.fn(),
    selectProjectRepo: vi.fn(),
    createProject: vi.fn(),
    addProjectRepo: vi.fn(),
    deleteProject: vi.fn(),
    resolveProjectFolder: vi.fn(),
  },
}));

const { apiClient } = await import('@/lib/api/client');
const { Component: WelcomePage } = await import('./welcome-page');

const api = apiClient as unknown as {
  getProjects: ReturnType<typeof vi.fn>;
  getProjectRepos: ReturnType<typeof vi.fn>;
  activateProject: ReturnType<typeof vi.fn>;
  selectProjectRepo: ReturnType<typeof vi.fn>;
  createProject: ReturnType<typeof vi.fn>;
  addProjectRepo: ReturnType<typeof vi.fn>;
  resolveProjectFolder: ReturnType<typeof vi.fn>;
};

function renderWelcome() {
  const store = createStore();
  store.set(isAuthenticatedAtom, true);
  return renderWithProviders(<WelcomePage />, { store, initialEntries: ['/welcome'] });
}

beforeEach(() => {
  navigateMock.mockClear();
  api.getProjects.mockReset();
  api.getProjectRepos.mockReset();
  api.activateProject.mockReset();
  api.selectProjectRepo.mockReset();
  api.createProject.mockReset();
  api.addProjectRepo.mockReset();
  api.resolveProjectFolder.mockReset();
  api.resolveProjectFolder.mockResolvedValue(null);
});

describe('WelcomePage', () => {
  it('shows selected repository details for recent projects', async () => {
    const project = mockProject({ id: 'project-1', name: 'Kagan', active: true });
    const repo = mockRepository({
      id: 'repo-1',
      project_id: project.id,
      name: 'kagan',
      path: '/Users/test/kagan',
      default_branch: 'main',
      selected: true,
    });
    api.getProjects.mockResolvedValue([project]);
    api.getProjectRepos.mockResolvedValue([repo]);

    renderWelcome();

    expect(await screen.findByText('/Users/test/kagan')).toBeVisible();
    expect(screen.getByText(/kagan \(selected\).*main/)).toBeVisible();
  });

  it('renders an explicit no-repository state for projects without repos', async () => {
    api.getProjects.mockResolvedValue([mockProject({ name: 'Empty project' })]);
    api.getProjectRepos.mockResolvedValue([]);

    renderWelcome();

    expect(await screen.findByText('Empty project')).toBeVisible();
    expect(screen.getByText('No repository attached')).toBeVisible();
  });

  it('opens the server current folder when the optional endpoint is available', async () => {
    api.resolveProjectFolder.mockResolvedValue({
      path: '/Users/test/current-repo',
      repo_path: '/Users/test/current-repo',
      suggested_project_name: 'current-repo',
      is_git_repo: true,
    });
    api.getProjects.mockResolvedValue([]);
    api.createProject.mockResolvedValue(mockProject({ id: 'created', name: 'current-repo' }));
    api.addProjectRepo.mockResolvedValue(
      mockRepository({
        id: 'repo-created',
        project_id: 'created',
        path: '/Users/test/current-repo',
      }),
    );

    renderWelcome();

    expect(await screen.findByText('No projects yet')).toBeVisible();
    expect(screen.getByText('/Users/test/current-repo')).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: 'Open Current Folder' }));

    await waitFor(() => {
      expect(api.createProject).toHaveBeenCalledWith('current-repo');
    });
    expect(api.addProjectRepo).toHaveBeenCalledWith('created', '/Users/test/current-repo');
    expect(api.activateProject).toHaveBeenCalledWith('created');
    expect(navigateMock).toHaveBeenCalledWith('/board');
  });

  it('hides the current-folder affordance when the optional endpoint is unavailable', async () => {
    api.getProjects.mockResolvedValue([]);
    api.resolveProjectFolder.mockResolvedValue(null);

    renderWelcome();

    expect(await screen.findByText('No projects yet')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Open Current Folder' })).not.toBeInTheDocument();
  });
});
