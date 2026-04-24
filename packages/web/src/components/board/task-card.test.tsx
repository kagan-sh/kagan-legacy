import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
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

  describe('diff summary', () => {
    it('renders inline diff row when task has diff_summary with changes', () => {
      renderWithProviders(
        <TaskCard
          task={mockTask({
            status: 'REVIEW',
            diff_summary: { files_changed: 3, additions: 47, deletions: 12 },
          })}
        />,
      );

      const row = screen.getByTestId('diff-summary');
      expect(row).toBeVisible();
      expect(row).toHaveTextContent('+47');
      expect(row).toHaveTextContent('-12');
      expect(row).toHaveTextContent('3 files');
    });

    it('does not render diff row when diff_summary is null', () => {
      renderWithProviders(
        <TaskCard
          task={mockTask({ status: 'REVIEW', diff_summary: null })}
        />,
      );

      expect(screen.queryByTestId('diff-summary')).toBeNull();
    });

    it('does not render diff row when diff_summary is absent', () => {
      renderWithProviders(
        <TaskCard task={mockTask({ status: 'BACKLOG' })} />,
      );

      expect(screen.queryByTestId('diff-summary')).toBeNull();
    });

    it('does not render diff row when all counts are zero', () => {
      renderWithProviders(
        <TaskCard
          task={mockTask({
            status: 'REVIEW',
            diff_summary: { files_changed: 0, additions: 0, deletions: 0 },
          })}
        />,
      );

      expect(screen.queryByTestId('diff-summary')).toBeNull();
    });

    it('clicking diff row stops propagation and does not trigger card open', () => {
      const onInspectTask = vi.fn();

      renderWithProviders(
        <TaskCard
          task={mockTask({
            status: 'REVIEW',
            diff_summary: { files_changed: 2, additions: 10, deletions: 5 },
          })}
          onInspectTask={onInspectTask}
        />,
      );

      fireEvent.click(screen.getByTestId('diff-summary'));

      expect(onInspectTask).not.toHaveBeenCalled();
    });
  });
});
