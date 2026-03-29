import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { PreflightChecks } from '@/components/settings/preflight-checks';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getPreflight: vi.fn().mockResolvedValue({
      ok: false,
      checks: [
        {
          name: 'agent backend',
          status: 'warn',
          message: 'Default backend is not reachable',
          fix_hint: 'Install the backend or switch defaults',
          is_blocking: false,
        },
      ],
    }),
    getChatAgents: vi.fn().mockResolvedValue({
      backends: [
        { name: 'claude-code', available: true, reference: true },
        { name: 'codex', available: false, reference: true },
        { name: 'cursor', available: true },
      ],
      default: 'claude-code',
    }),
  },
}));

describe('PreflightChecks', () => {
  it('surfaces reference backend guidance next to backend-related warnings', async () => {
    renderWithProviders(<PreflightChecks />);

    await waitFor(() => {
      expect(screen.getByText('Reference backends')).toBeVisible();
    });

    expect(screen.getByText('claude-code')).toBeVisible();
    expect(screen.getByText('codex')).toBeVisible();
    expect(screen.getByText('Try a reference backend first if this check is warning or failing.')).toBeVisible();
  });
});
