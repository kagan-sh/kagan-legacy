import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { CreateTaskDialog } from '@/components/board/create-task-dialog';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    createTask: vi.fn().mockResolvedValue({}),
    getTasks: vi.fn().mockResolvedValue([]),
    getChatAgents: vi.fn().mockResolvedValue({ backends: [{ name: 'claude-code', available: true, reference: true }, { name: 'codex', available: true, reference: true }], default: 'claude-code' }),
  },
}));

describe('CreateTaskDialog', () => {
  it('shows validation error when title is empty', async () => {
    const user = userEvent.setup();

    renderWithProviders(<CreateTaskDialog open onOpenChange={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Title is required')).toBeVisible();
  });

  it('submits successfully with a title', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    renderWithProviders(<CreateTaskDialog open onOpenChange={onOpenChange} />);

    await user.type(screen.getByLabelText('Title'), 'Ship polish plan');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(apiClient.createTask).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Ship polish plan' }),
      );
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
