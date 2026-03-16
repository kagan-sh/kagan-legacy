import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { TaskCard } from '@/components/board/task-card';
import { mockTask } from '@/test/mocks';

describe('TaskCard', () => {
  it('renders task title', () => {
    renderWithProviders(<TaskCard task={mockTask({ title: 'Fix login bug' })} />);
    expect(screen.getByText('Fix login bug')).toBeVisible();
  });

  it('shows Auto mode for AUTO execution_mode', () => {
    renderWithProviders(<TaskCard task={mockTask({ execution_mode: 'AUTO' })} />);
    expect(screen.getByText('Auto')).toBeVisible();
  });

  it('shows Pair mode for PAIR execution_mode', () => {
    renderWithProviders(<TaskCard task={mockTask({ execution_mode: 'PAIR' })} />);
    expect(screen.getByText('Pair')).toBeVisible();
  });

  it('calls inspector callback when provided', async () => {
    const onInspectTask = vi.fn();
    const task = mockTask({ title: 'Inspect me' });
    const user = userEvent.setup();

    renderWithProviders(<TaskCard task={task} onInspectTask={onInspectTask} />);

    await user.click(screen.getByRole('button', { name: 'Inspect me' }));

    expect(onInspectTask).toHaveBeenCalledWith(task);
  });
});
