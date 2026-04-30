/**
 * task-form.test.tsx
 *
 * Tests the GitHub issue selector field: three states (none/link/new),
 * correct github_issue serialization, and hidden state when no GitHub link.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { CreateTaskDialog } from '@/components/board/create-task-dialog';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    createTask: vi.fn().mockResolvedValue({}),
    getTasks: vi.fn().mockResolvedValue([]),
    getChatAgents: vi.fn().mockResolvedValue({
      backends: [],
      default: 'claude-code',
    }),
    detectIntegrationRepo: vi.fn(),
  },
}));

describe('TaskForm — GitHub issue selector', () => {
  beforeEach(async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.createTask).mockClear();
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: null });
  });

  it('hides GitHub issue field when no GitHub link', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: null });
    renderWithProviders(<CreateTaskDialog open onOpenChange={vi.fn()} />);

    // Wait for repo detection to complete
    await waitFor(() => {
      expect(apiClient.detectIntegrationRepo).toHaveBeenCalled();
    });

    expect(screen.queryByLabelText('GitHub issue link')).toBeNull();
    expect(screen.queryByText('GitHub Issue')).toBeNull();
  });

  it('shows GitHub issue field when a GitHub repo is linked', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: 'owner/repo' });
    renderWithProviders(<CreateTaskDialog open onOpenChange={vi.fn()} />);

    expect(await screen.findByText('GitHub Issue')).toBeVisible();
    expect(screen.getByLabelText('GitHub issue link')).toBeVisible();
  });

  it('submits with github_issue undefined when mode is none', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: 'owner/repo' });
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    renderWithProviders(<CreateTaskDialog open onOpenChange={onOpenChange} />);

    await screen.findByText('GitHub Issue');
    await user.type(screen.getByLabelText('Title'), 'My task');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(apiClient.createTask).toHaveBeenCalledWith(
        expect.objectContaining({ github_issue: undefined }),
      );
    });
  });

  it('submits with github_issue "new" when mode is create new', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: 'owner/repo' });
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    renderWithProviders(<CreateTaskDialog open onOpenChange={onOpenChange} />);

    await screen.findByText('GitHub Issue');
    await user.type(screen.getByLabelText('Title'), 'My task');

    // Select "Create new issue from task"
    await user.selectOptions(screen.getByLabelText('GitHub issue link'), 'new');

    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(apiClient.createTask).toHaveBeenCalledWith(
        expect.objectContaining({ github_issue: 'new' }),
      );
    });
  });

  it('shows number input when mode is link', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: 'owner/repo' });
    const user = userEvent.setup();

    renderWithProviders(<CreateTaskDialog open onOpenChange={vi.fn()} />);

    await screen.findByText('GitHub Issue');
    await user.selectOptions(screen.getByLabelText('GitHub issue link'), 'link');

    expect(screen.getByPlaceholderText('Issue number, e.g. 42')).toBeVisible();
  });

  it('submits with issue number when mode is link and number is valid', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: 'owner/repo' });
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    renderWithProviders(<CreateTaskDialog open onOpenChange={onOpenChange} />);

    await screen.findByText('GitHub Issue');
    await user.type(screen.getByLabelText('Title'), 'My task');
    await user.selectOptions(screen.getByLabelText('GitHub issue link'), 'link');
    await user.type(screen.getByPlaceholderText('Issue number, e.g. 42'), '42');

    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(apiClient.createTask).toHaveBeenCalledWith(
        expect.objectContaining({ github_issue: '42' }),
      );
    });
  });
});
