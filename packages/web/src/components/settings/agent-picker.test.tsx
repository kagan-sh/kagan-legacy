import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { AgentPicker } from '@/components/settings/agent-picker';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getSettings: vi.fn().mockResolvedValue({
      use_recommended_backend: 'false',
    }),
    getChatAgents: vi.fn().mockResolvedValue({
      backends: [
        { name: 'cursor', available: false },
        { name: 'codex', available: true, reference: true },
        { name: 'claude-code', available: true, reference: true },
      ],
      default: 'cursor',
    }),
    getRecommendedBackend: vi.fn().mockResolvedValue({}),
    setSettings: vi.fn().mockResolvedValue({}),
  },
}));

describe('AgentPicker', () => {
  it('shows only available backends and surfaces reference ones first', async () => {
    renderWithProviders(<AgentPicker />);

    await waitFor(() => {
      expect(screen.getAllByText('Reference').length).toBeGreaterThan(0);
    });

    const claudeButton = screen.getByRole('button', { name: /claude-code/i });
    expect(claudeButton).toHaveTextContent('Reference');

    // Unavailable backends should not be shown in the selection buttons
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument();
  });
});
