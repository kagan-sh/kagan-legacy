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

  describe('a11y: role and selection', () => {
    it('does not have aria-pressed on the card element', () => {
      renderWithProviders(<TaskCard task={mockTask({ title: 'No pressed' })} />);
      const btn = screen.getByRole('button', { name: 'No pressed' });
      expect(btn).not.toHaveAttribute('aria-pressed');
    });

    it('has aria-current="true" when isSelected', () => {
      renderWithProviders(
        <TaskCard task={mockTask({ title: 'Selected card' })} isSelected />,
      );
      // aria-label includes "(selected)" suffix
      const btn = screen.getByRole('button', { name: 'Selected card (selected)' });
      expect(btn).toHaveAttribute('aria-current', 'true');
    });

    it('does not have aria-current when not selected', () => {
      renderWithProviders(
        <TaskCard task={mockTask({ title: 'Unselected card' })} isSelected={false} />,
      );
      const btn = screen.getByRole('button', { name: 'Unselected card' });
      expect(btn).not.toHaveAttribute('aria-current');
    });

    it('activates on Enter key', async () => {
      const onInspectTask = vi.fn();
      const task = mockTask({ title: 'Key card' });
      renderWithProviders(<TaskCard task={task} onInspectTask={onInspectTask} />);

      const btn = screen.getByRole('button', { name: 'Key card' });
      btn.focus();
      fireEvent.keyDown(btn, { key: 'Enter' });

      expect(onInspectTask).toHaveBeenCalledWith(task);
    });

    it('does not navigate on j/k/l key presses', () => {
      const onInspectTask = vi.fn();
      const task = mockTask({ title: 'Vim card' });
      renderWithProviders(<TaskCard task={task} onInspectTask={onInspectTask} />);

      const btn = screen.getByRole('button', { name: 'Vim card' });
      btn.focus();
      fireEvent.keyDown(btn, { key: 'j' });
      fireEvent.keyDown(btn, { key: 'k' });
      fireEvent.keyDown(btn, { key: 'l' });

      expect(onInspectTask).not.toHaveBeenCalled();
    });
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
