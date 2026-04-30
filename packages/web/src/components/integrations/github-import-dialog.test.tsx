/**
 * github-import-dialog.test.tsx
 *
 * Tests the IntegrationImportDialog (already at board/integration-import-dialog.tsx)
 * with preview + sync interaction via mocked apiClient.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { IntegrationImportDialog } from '@/components/board/integration-import-dialog';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    detectIntegrationRepo: vi.fn(),
    getIntegrationPreflight: vi.fn(),
    previewIntegrationIssues: vi.fn(),
    runIntegrationSync: vi.fn(),
  },
}));

const ISSUES = [
  { number: 1, title: 'Fix bug', state: 'open', labels: ['bug'], url: '', already_synced: false },
  { number: 2, title: 'Feature request', state: 'open', labels: [], url: '', already_synced: true },
];

describe('IntegrationImportDialog', () => {
  beforeEach(async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.detectIntegrationRepo).mockResolvedValue({ id: 'github', repo_slug: 'owner/repo' });
    vi.mocked(apiClient.getIntegrationPreflight).mockResolvedValue({ id: 'github', ready: true, checks: [] });
    vi.mocked(apiClient.previewIntegrationIssues).mockResolvedValue({ id: 'github', issues: ISSUES, total: ISSUES.length });
    vi.mocked(apiClient.runIntegrationSync).mockResolvedValue({ id: 'github', created: 1, updated: 0, skipped: 1, errors: [] });
  });

  it('auto-detects repo on open', async () => {
    renderWithProviders(<IntegrationImportDialog open onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('owner/repo')).toBeVisible();
    });
  });

  it('shows preview issues after clicking Preview Issues', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationImportDialog open onOpenChange={vi.fn()} />);

    // Wait for detection
    await waitFor(() => expect(screen.getByDisplayValue('owner/repo')).toBeVisible());

    await user.click(screen.getByRole('button', { name: 'Preview Issues' }));

    await waitFor(() => {
      expect(screen.getByText('Fix bug')).toBeVisible();
      expect(screen.getByText('Feature request')).toBeVisible();
    });
    // Already-synced issue is shown
    expect(screen.getByText('(synced)')).toBeVisible();
  });

  it('calls sync with selected issue numbers', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderWithProviders(<IntegrationImportDialog open onOpenChange={onOpenChange} />);

    await waitFor(() => expect(screen.getByDisplayValue('owner/repo')).toBeVisible());
    await user.click(screen.getByRole('button', { name: 'Preview Issues' }));
    await screen.findByText('Fix bug');

    // Import button label includes selected count
    const importBtn = await screen.findByRole('button', { name: /Import \d+ Selected/ });
    await user.click(importBtn);

    await waitFor(() => {
      expect(apiClient.runIntegrationSync).toHaveBeenCalledWith(
        'github',
        expect.objectContaining({ repo_slug: 'owner/repo' }),
      );
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
