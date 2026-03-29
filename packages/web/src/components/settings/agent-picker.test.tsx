import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { AgentPicker } from '@/components/settings/agent-picker';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getChatAgents: vi.fn().mockResolvedValue({
      backends: [
        { name: 'cursor', available: false },
        { name: 'codex', available: true, reference: true },
        { name: 'claude-code', available: true, reference: true },
      ],
      default: 'cursor',
    }),
    setSettings: vi.fn().mockResolvedValue({}),
  },
}));

describe('AgentPicker', () => {
  it('surfaces reference backends first and marks unavailable entries', async () => {
    renderWithProviders(<AgentPicker />);

    await waitFor(() => {
      expect(screen.getAllByText('Reference').length).toBeGreaterThan(0);
    });

    const buttons = screen.getAllByRole('button');
    expect(buttons[0]).toHaveTextContent('claude-code');
    expect(buttons[0]).toHaveTextContent('Reference');
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
  });
});
