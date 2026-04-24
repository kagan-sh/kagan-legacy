import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { TaskSidebar } from '@/components/board/task-sidebar';
import { mockCriterion } from '@/test/mocks';
import type { WireTask } from '@/lib/api/types';

describe('TaskSidebar', () => {
  it('shows review evidence and merge readiness when review is incomplete', () => {
    const crit1 = mockCriterion({ id: 'crit-1', task_id: 'task-1', ordinal: 0, text: 'One' });
    const crit2 = mockCriterion({ id: 'crit-2', task_id: 'task-1', ordinal: 1, text: 'Two' });

    const task: WireTask = {
      id: 'task-1',
      title: 'Task',
      status: 'REVIEW',
      priority: 'MEDIUM',
      acceptance_criteria: [crit1, crit2],
      review_approved: false,
      review_verdicts: [
        { id: 'v1', criterion_id: 'crit-1', verdict: 'PASS', reason: 'Matches the requested behavior' },
        { id: 'v2', criterion_id: 'crit-2', verdict: 'FAIL', reason: 'Missing validation' },
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
    const crit1 = mockCriterion({ id: 'crit-3', task_id: 'task-2', ordinal: 0, text: 'Ship it' });

    const task: WireTask = {
      id: 'task-2',
      title: 'Approved task',
      status: 'DONE',
      priority: 'HIGH',
      acceptance_criteria: [crit1],
      review_approved: true,
      review_verdicts: [
        { id: 'v3', criterion_id: 'crit-3', verdict: 'PASS', reason: 'Confirmed in the diff' },
      ],
      review_running: false,
    };

    renderWithProviders(<TaskSidebar task={task} />);

    expect(screen.getByText('Approved')).toBeVisible();
    expect(screen.getByText('1/1 reviewed')).toBeVisible();
    expect(screen.getByText('Ready to merge')).toBeVisible();
  });
});
