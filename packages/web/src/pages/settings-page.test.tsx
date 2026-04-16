import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { Component as SettingsPage } from './settings-page';

vi.mock('@/lib/api/client', () => {
  const stored: Record<string, string> = {
    require_review_approval: 'false',
    review_strictness: 'balanced',
    planning_depth: 'always',
    auto_confirm_single_tasks: 'false',
    serialize_merges: 'false',
    worktree_base_ref_strategy: 'local_if_ahead',
    default_agent_backend: 'claude-code',
    use_recommended_backend: 'false',
    additional_instructions: '',
  };
  return {
    __storedSettings: stored,
    apiClient: {
      getBaseUrl: () => 'http://localhost:8765',
      getHealth: vi.fn(async () => ({ status: 'ok', version: '1.0.0' })),
      getSettings: vi.fn(async () => ({ ...stored })),
      setSettings: vi.fn(async (patch: Record<string, string>) => {
        Object.assign(stored, patch);
        return { ...stored };
      }),
      getResolvedSettings: vi.fn(async () => ({
        git_user_name: 'Tester',
        git_user_email: 'tester@example.com',
        dotfile_overrides: {},
        workflow: {},
      })),
      getChatAgents: vi.fn(async () => ({
        backends: [
          { name: 'claude-code', available: true, reference: true },
          { name: 'codex', available: true, reference: true },
        ],
        default: 'claude-code',
      })),
      getPreflight: vi.fn(async () => ({ ok: true, checks: [] })),
      getRecommendedBackend: vi.fn(async () => ({})),
    },
    ApiError: class ApiError extends Error {},
  };
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const apiMock = await import('@/lib/api/client');
const storedSettings = (apiMock as unknown as { __storedSettings: Record<string, string> })
  .__storedSettings;
const setSettingsMock = (apiMock.apiClient as unknown as {
  setSettings: ReturnType<typeof vi.fn>;
}).setSettings;

beforeEach(() => {
  Object.assign(storedSettings, {
    require_review_approval: 'false',
    review_strictness: 'balanced',
    planning_depth: 'always',
    auto_confirm_single_tasks: 'false',
    serialize_merges: 'false',
    worktree_base_ref_strategy: 'local_if_ahead',
    default_agent_backend: 'claude-code',
    use_recommended_backend: 'false',
    additional_instructions: '',
  });
  setSettingsMock.mockClear();
});

describe('SettingsPage progressive disclosure', () => {
  it('renders the three top-level category cards', async () => {
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Workflow/i })).toBeVisible();
    });

    expect(screen.getByRole('button', { name: /Workflow/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.getByRole('button', { name: /Agents/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.getByRole('button', { name: /Advanced/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });

  it('expands Workflow and shows workflow-scoped fields only', async () => {
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Workflow/i })).toBeVisible();
    });

    fireEvent.click(screen.getByRole('button', { name: /Workflow/i }));

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 2, name: /Workflow/i }),
      ).toBeVisible();
    });

    // Workflow-scoped controls present.
    expect(screen.getByLabelText(/Require review approval/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Serialize merges/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Auto-confirm single tasks/i)).toBeInTheDocument();

    // Agents-scoped and Advanced-scoped controls should NOT be rendered.
    expect(screen.queryByText('Default agent backend')).not.toBeInTheDocument();
    expect(screen.queryByText('Git identity mode')).not.toBeInTheDocument();
  });

  it('expands Agents and shows agent-scoped fields only', async () => {
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Agents/i })).toBeVisible();
    });

    fireEvent.click(screen.getByRole('button', { name: /Agents/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Agents/i })).toBeVisible();
    });

    expect(screen.getByText('Default agent backend')).toBeInTheDocument();
    expect(screen.getByLabelText(/Use recommended backend/i)).toBeInTheDocument();

    // Not in Agents.
    expect(screen.queryByLabelText(/Serialize merges/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Git identity mode')).not.toBeInTheDocument();
  });

  it('expands Advanced and shows advanced-scoped fields only', async () => {
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Advanced/i })).toBeVisible();
    });

    fireEvent.click(screen.getByRole('button', { name: /Advanced/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Advanced/i })).toBeVisible();
    });

    expect(screen.getByText('Git identity mode')).toBeInTheDocument();
    expect(screen.getByText('Interactive launcher')).toBeInTheDocument();

    // Not in Advanced.
    expect(screen.queryByLabelText(/Serialize merges/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Default agent backend')).not.toBeInTheDocument();
  });

  it('Back button returns to the category list and restores focus', async () => {
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Workflow/i })).toBeVisible();
    });

    fireEvent.click(screen.getByRole('button', { name: /Workflow/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Workflow/i })).toBeVisible();
    });

    fireEvent.click(screen.getByRole('button', { name: /All settings/i }));

    await waitFor(() => {
      expect(
        screen.queryByRole('heading', { level: 2, name: /Workflow/i }),
      ).not.toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /Workflow/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });

  it('persists a workflow setting via the settings API using the same key', async () => {
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Workflow/i })).toBeVisible();
    });

    fireEvent.click(screen.getByRole('button', { name: /Workflow/i }));

    const toggle = await screen.findByLabelText(/Require review approval/i);
    await act(async () => {
      fireEvent.click(toggle);
    });

    await waitFor(() => {
      expect(setSettingsMock).toHaveBeenCalledWith({ require_review_approval: 'true' });
    });
    expect(storedSettings.require_review_approval).toBe('true');
  });

  it('persists an agents setting via the settings API using the same key', async () => {
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Agents/i })).toBeVisible();
    });

    fireEvent.click(screen.getByRole('button', { name: /Agents/i }));

    const toggle = await screen.findByLabelText(/Use recommended backend/i);
    await act(async () => {
      fireEvent.click(toggle);
    });

    await waitFor(() => {
      expect(setSettingsMock).toHaveBeenCalledWith({ use_recommended_backend: 'true' });
    });
    expect(storedSettings.use_recommended_backend).toBe('true');
  });
});
