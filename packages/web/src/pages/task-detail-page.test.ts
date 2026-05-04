import { describe, expect, it } from 'vitest';
import { defaultTabForTask } from '@/pages/task-detail-page';
import type { WireTask } from '@kagan/shared-api-client';

function makeTask(overrides: Partial<WireTask>): WireTask {
  return {
    id: 'task-1',
    title: 'Task',
    description: '',
    status: 'BACKLOG',
    priority: 'MEDIUM',
    acceptance_criteria: [],
    review_approved: false,
    has_workspace: false,
    ...overrides,
  };
}

describe('defaultTabForTask', () => {
  it('opens backlog tasks in overview', () => {
    expect(defaultTabForTask(makeTask({ status: 'BACKLOG', has_workspace: false }))).toBe('overview');
  });

  it('opens changes tab for in-progress tasks with workspace', () => {
    expect(defaultTabForTask(makeTask({ status: 'IN_PROGRESS', has_workspace: true }))).toBe('changes');
  });

  it('opens overview for backlog tasks with an active session', () => {
    expect(
      defaultTabForTask(
        makeTask({
          status: 'BACKLOG',
          active_session: { id: 's1', status: 'RUNNING', launcher: null, agent_backend: 'claude', started_at: '2026-01-01' },
        }),
      ),
    ).toBe('overview');
  });

  it('prefers review tab for review tasks with a workspace', () => {
    expect(defaultTabForTask(makeTask({ status: 'REVIEW', has_workspace: true }))).toBe('review');
  });

  it('prefers changes for done tasks with a workspace', () => {
    expect(defaultTabForTask(makeTask({ status: 'DONE', has_workspace: true }))).toBe('changes');
  });

  it('falls back to overview when no workspace exists', () => {
    expect(defaultTabForTask(makeTask({ status: 'DONE', has_workspace: false }))).toBe('overview');
  });

  it('review without workspace falls back to overview', () => {
    expect(defaultTabForTask(makeTask({ status: 'REVIEW', has_workspace: false }))).toBe('overview');
  });
});
