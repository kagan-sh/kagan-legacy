import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { PermissionDialog } from '@/components/PermissionDialog';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    resolvePermission: vi.fn().mockResolvedValue(undefined),
  },
}));

const { apiClient } = await import('@/lib/api/client');

describe('PermissionDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('only offers permission outcomes supported by the chat permission API', () => {
    renderWithProviders(
      <PermissionDialog
        request={{ sessionId: 'session-1', futureId: 'future-1', toolName: 'bash' }}
        onResolved={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Allow once' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Allow tool for session' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Allow all for session' })).not.toBeInTheDocument();
  });

  it('resolves a session tool grant as allow_always', async () => {
    const user = userEvent.setup();
    const onResolved = vi.fn();
    renderWithProviders(
      <PermissionDialog
        request={{ sessionId: 'session-1', futureId: 'future-1', toolName: 'bash' }}
        onResolved={onResolved}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Allow tool for session' }));

    expect(apiClient.resolvePermission).toHaveBeenCalledWith(
      'session-1',
      'future-1',
      'allow_always',
    );
    expect(onResolved).toHaveBeenCalledOnce();
  });
});
