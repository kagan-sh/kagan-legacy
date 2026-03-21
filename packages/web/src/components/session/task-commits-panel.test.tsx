import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TaskCommitsPanel } from '@/components/session/task-commits-panel';
import { renderWithProviders } from '@/test/render';

describe('TaskCommitsPanel', () => {
  it('shows a no-workspace state', () => {
    renderWithProviders(
      <TaskCommitsPanel commits={[]} baseBranch="main" hasWorkspace={false} />,
    );

    expect(screen.getByText('No workspace yet')).toBeInTheDocument();
  });

  it('shows an empty branch state when no commits are ahead', () => {
    renderWithProviders(
      <TaskCommitsPanel
        commits={[]}
        branch="kagan/task-1"
        baseBranch="main"
        hasWorkspace
      />,
    );

    expect(screen.getByText('No task-branch commits')).toBeInTheDocument();
    expect(screen.getByText('main')).toBeInTheDocument();
  });

  it('renders up to eight commits and reports overflow', () => {
    const commits = Array.from({ length: 9 }, (_, index) => ({
      short_hash: `hash${index + 1}`,
      message: `Commit message ${index + 1}`,
    }));

    renderWithProviders(
      <TaskCommitsPanel
        commits={commits}
        branch="kagan/task-1"
        baseBranch="main"
        hasWorkspace
      />,
    );

    expect(screen.getByText('Commit message 1')).toBeInTheDocument();
    expect(screen.getByText('Commit message 8')).toBeInTheDocument();
    expect(screen.queryByText('Commit message 9')).not.toBeInTheDocument();
    expect(screen.getByText('+1 more commit')).toBeInTheDocument();
  });
});
