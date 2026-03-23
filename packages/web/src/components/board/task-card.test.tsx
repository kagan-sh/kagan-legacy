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

  it('shows a live indicator when a managed run is active', () => {
    renderWithProviders(
      <TaskCard
        task={mockTask({
          status: 'IN_PROGRESS',
          active_session: {
            id: 's1',
            status: 'running',
            launcher: null,
            agent_backend: 'claude-code',
            started_at: new Date().toISOString(),
          },
        })}
      />,
    );
    expect(screen.getByTestId('live-indicator')).toBeVisible();
  });

  it('shows a live indicator when an interactive run is active', () => {
    renderWithProviders(
      <TaskCard
        task={mockTask({
          status: 'IN_PROGRESS',
          active_session: {
            id: 's1',
            status: 'running',
            launcher: 'tmux',
            agent_backend: 'claude-code',
            started_at: new Date().toISOString(),
          },
        })}
      />,
    );
    expect(screen.getByTestId('live-indicator')).toBeVisible();
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
