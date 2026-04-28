import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { ReviewPanel } from '@/components/board/review-panel';
import { mockCriterion } from '@/test/mocks';
import type { WireTask } from '@/lib/api/types';

vi.mock('@/lib/api/client', () => ({
  apiClient: { reviewDecide: vi.fn().mockResolvedValue({}), runTask: vi.fn().mockResolvedValue({}), getTasks: vi.fn().mockResolvedValue([]) },
}));

describe('ReviewPanel', () => {
  const crit1 = mockCriterion({ id: 'crit-1', task_id: 't1', ordinal: 0, text: 'One' });

  const reviewTask: WireTask = {
    id: 't1',
    title: 'Task',
    status: 'REVIEW',
    priority: 'MEDIUM',
    acceptance_criteria: [crit1],
    review_running: false,
  };

  const crit2a = mockCriterion({ id: 'crit-2a', task_id: 't2', ordinal: 0, text: 'First' });
  const crit2b = mockCriterion({ id: 'crit-2b', task_id: 't2', ordinal: 1, text: 'Second' });

  const reviewEvidenceTask: WireTask = {
    id: 't2',
    title: 'Evidence task',
    status: 'REVIEW',
    priority: 'HIGH',
    acceptance_criteria: [crit2a, crit2b],
    review_approved: false,
    review_verdicts: [
      { id: 'v1', criterion_id: 'crit-2a', verdict: 'PASS', reason: 'Covers the acceptance criteria' },
      { id: 'v2', criterion_id: 'crit-2b', verdict: 'FAIL', reason: 'Missing regression coverage' },
    ],
    review_running: false,
  };

  it('renders review actions', () => {
    renderWithProviders(<ReviewPanel taskId="t1" task={reviewTask} />);
    expect(screen.getByText('Review snapshot')).toBeVisible();
    expect(screen.getByText('Run AI Review')).toBeVisible();
    expect(screen.getByText('Approve')).toBeVisible();
    expect(screen.getByText('Reject')).toBeVisible();
    expect(screen.getByText('Merge')).toBeVisible();
    expect(screen.getByText('Rebase')).toBeVisible();
  });

  it('summarizes evidence and merge state', () => {
    renderWithProviders(<ReviewPanel taskId="t2" task={reviewEvidenceTask} />);

    expect(screen.getByText('2/2 criteria reviewed')).toBeVisible();
    expect(screen.getByText('1 pass, 1 fail')).toBeVisible();
    expect(screen.getAllByText('Fix failing criteria')).toHaveLength(2);
    expect(screen.getByText('Evidence log')).toBeVisible();
    expect(screen.getByText('1/2 passed')).toBeVisible();
  });

  it('calls API on approve', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const user = userEvent.setup();
    renderWithProviders(<ReviewPanel taskId="t1" task={reviewTask} />);
    await user.click(screen.getByText('Approve'));
    expect(apiClient.reviewDecide).toHaveBeenCalledWith('t1', { action: 'approve', feedback: undefined });
  });

  it('starts AI review explicitly', async () => {
    const { apiClient } = await import('@/lib/api/client');
    const user = userEvent.setup();
    renderWithProviders(<ReviewPanel taskId="t1" task={reviewTask} />);
    await user.click(screen.getByText('Run AI Review'));
    expect(apiClient.runTask).toHaveBeenCalledWith('t1');
  });

  it('supports review hotkeys', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.reviewDecide).mockClear();

    const user = userEvent.setup();
    renderWithProviders(<ReviewPanel taskId="t1" task={reviewTask} enableHotkeys />);

    await user.keyboard('b');
    expect(apiClient.reviewDecide).toHaveBeenCalledWith('t1', { action: 'rebase', feedback: undefined });
  });
});
