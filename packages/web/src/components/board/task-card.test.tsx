import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { TaskCard } from '@/components/board/task-card';
import { mockTask } from '@/test/mocks';
import type { WireTask } from '@kagan/shared-api-client';

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

    // aria-label is "Inspect me, Medium priority" — use regex to match title
    await user.click(screen.getByRole('button', { name: /^Inspect me/ }));

    expect(onInspectTask).toHaveBeenCalledWith(task);
  });

  describe('a11y: role and selection', () => {
    it('does not have aria-pressed on the card element', () => {
      renderWithProviders(<TaskCard task={mockTask({ title: 'No pressed' })} />);
      const btn = screen.getByRole('button', { name: /^No pressed/ });
      expect(btn).not.toHaveAttribute('aria-pressed');
    });

    it('has aria-current="true" when isSelected', () => {
      renderWithProviders(
        <TaskCard task={mockTask({ title: 'Selected card' })} isSelected />,
      );
      // aria-label includes priority + "(selected)" suffix
      const btn = screen.getByRole('button', { name: /Selected card.*\(selected\)/i });
      expect(btn).toHaveAttribute('aria-current', 'true');
    });

    it('does not have aria-current when not selected', () => {
      renderWithProviders(
        <TaskCard task={mockTask({ title: 'Unselected card' })} isSelected={false} />,
      );
      const btn = screen.getByRole('button', { name: /^Unselected card/ });
      expect(btn).not.toHaveAttribute('aria-current');
    });

    it('activates on Enter key', async () => {
      const onInspectTask = vi.fn();
      const task = mockTask({ title: 'Key card' });
      renderWithProviders(<TaskCard task={task} onInspectTask={onInspectTask} />);

      const btn = screen.getByRole('button', { name: /^Key card/ });
      btn.focus();
      fireEvent.keyDown(btn, { key: 'Enter' });

      expect(onInspectTask).toHaveBeenCalledWith(task);
    });

    it('does not navigate on j/k/l key presses', () => {
      const onInspectTask = vi.fn();
      const task = mockTask({ title: 'Vim card' });
      renderWithProviders(<TaskCard task={task} onInspectTask={onInspectTask} />);

      const btn = screen.getByRole('button', { name: /^Vim card/ });
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
      // Design uses Unicode minus sign (−) not hyphen-minus (-)
      expect(row).toHaveTextContent('−12');
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

  describe('D6: live-pulse respects prefers-reduced-motion', () => {
    it('omits animate-pulse class on the live dot when reducedMotion=true', () => {
      // Simulate reduced motion via matchMedia mock
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: (query: string) => ({
          matches: query.includes('reduce'),
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }),
      });

      const task: WireTask = mockTask({
        status: 'IN_PROGRESS',
        active_session: {
          id: 's1',
          status: 'running',
          launcher: null,
          agent_backend: 'claude-code',
          started_at: new Date().toISOString(),
        },
      });
      renderWithProviders(<TaskCard task={task} />);

      const liveDot = screen.getByTestId('live-indicator').querySelector('[aria-hidden="true"]');
      expect(liveDot?.className).not.toContain('animate-pulse');
    });
  });

  describe('D10: priority accessibility', () => {
    it('includes priority label in the card aria-label', () => {
      renderWithProviders(<TaskCard task={mockTask({ title: 'Bug fix', priority: 'HIGH' })} />);
      const card = screen.getByRole('button', { name: /Bug fix.*High priority/i });
      expect(card).toBeTruthy();
    });

    it('renders a priority glyph element with aria-hidden', () => {
      renderWithProviders(<TaskCard task={mockTask({ title: 'Glyph test', priority: 'HIGH' })} />);
      const btn = screen.getByRole('button', { name: /Glyph test/i });
      // The glyph is the aria-hidden span with non-empty text.
      // The priority rail stripe also has aria-hidden but contains no text.
      const ariaHiddenEls = Array.from(btn.querySelectorAll('[aria-hidden="true"]'));
      const glyph = ariaHiddenEls.find((el) => (el.textContent ?? '').trim().length > 0);
      expect(glyph).toBeTruthy();
      expect(glyph?.textContent?.trim()).toBe('▲');
    });

    it('LOW priority uses ▼ glyph', () => {
      renderWithProviders(<TaskCard task={mockTask({ title: 'Low task', priority: 'LOW' })} />);
      const btn = screen.getByRole('button', { name: /Low task/i });
      const ariaHiddenEls = Array.from(btn.querySelectorAll('[aria-hidden="true"]'));
      const glyph = ariaHiddenEls.find((el) => (el.textContent ?? '').trim().length > 0);
      expect(glyph?.textContent?.trim()).toBe('▼');
    });
  });

  describe('session progress bar', () => {
    it('renders progress bar when IN_PROGRESS with active_session', () => {
      renderWithProviders(
        <TaskCard
          task={mockTask({
            status: 'IN_PROGRESS',
            active_session: {
              id: 's1',
              status: 'running',
              launcher: null,
              agent_backend: 'claude-code',
              started_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
            },
          })}
        />,
      );
      expect(screen.getByTestId('session-progress-bar')).toBeInTheDocument();
    });

    it('does NOT render progress bar when IN_PROGRESS without active_session', () => {
      renderWithProviders(<TaskCard task={mockTask({ status: 'IN_PROGRESS' })} />);
      expect(screen.queryByTestId('session-progress-bar')).toBeNull();
    });

    it('does NOT render progress bar when BACKLOG', () => {
      renderWithProviders(<TaskCard task={mockTask({ status: 'BACKLOG' })} />);
      expect(screen.queryByTestId('session-progress-bar')).toBeNull();
    });

    it('does NOT render progress bar when REVIEW', () => {
      renderWithProviders(<TaskCard task={mockTask({ status: 'REVIEW' })} />);
      expect(screen.queryByTestId('session-progress-bar')).toBeNull();
    });

    it('does NOT render progress bar when DONE', () => {
      renderWithProviders(<TaskCard task={mockTask({ status: 'DONE' })} />);
      expect(screen.queryByTestId('session-progress-bar')).toBeNull();
    });
  });
});
