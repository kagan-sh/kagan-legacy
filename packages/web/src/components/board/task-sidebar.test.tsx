import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { TaskSidebar } from '@/components/board/task-sidebar';
import type { WireTask } from '@/lib/api/types';

describe('TaskSidebar', () => {
  it('shows review evidence and merge readiness when review is incomplete', () => {
    const task: WireTask = {
      id: 'task-1',
      title: 'Task',
      status: 'REVIEW',
      priority: 'MEDIUM',
      acceptance_criteria: ['One', 'Two'],
      review_approved: false,
      review_verdicts: [
        { criterion_index: 0, verdict: 'PASS', reason: 'Matches the requested behavior' },
        { criterion_index: 1, verdict: 'FAIL', reason: 'Missing validation' },
      ],
      review_running: false,
    };

    renderWithProviders(<TaskSidebar task={task} />);

    expect(screen.getByText('Pending')).toBeVisible();
    expect(screen.getByText('2/2 reviewed')).toBeVisible();
    expect(screen.getByText('1 pass, 1 fail')).toBeVisible();
    expect(screen.getByText('Resolve failing criteria')).toBeVisible();
  });

  it('shows ready-to-merge state when approved', () => {
    const task: WireTask = {
      id: 'task-2',
      title: 'Approved task',
      status: 'DONE',
      priority: 'HIGH',
      acceptance_criteria: ['Ship it'],
      review_approved: true,
      review_verdicts: [
        { criterion_index: 0, verdict: 'PASS', reason: 'Confirmed in the diff' },
      ],
      review_running: false,
    };

    renderWithProviders(<TaskSidebar task={task} />);

    expect(screen.getByText('Approved')).toBeVisible();
    expect(screen.getByText('1/1 reviewed')).toBeVisible();
    expect(screen.getByText('Ready to merge')).toBeVisible();
  });
});
