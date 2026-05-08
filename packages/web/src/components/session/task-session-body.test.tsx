import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { TaskSessionBody } from '@/components/session/TaskSessionBody';

vi.mock('@/lib/hooks/use-task-events', () => ({
  useTaskEvents: () => ({
    events: [],
    isRunning: false,
    hasMore: false,
    loadingMore: false,
    loadEarlier: vi.fn(),
  }),
}));

describe('TaskSessionBody', () => {
  it('shows task session replay label', () => {
    renderWithProviders(<TaskSessionBody taskId="task-1" />);
    expect(screen.getByText(/task session replay/i)).toBeInTheDocument();
  });

  it('does not render a chat input', () => {
    renderWithProviders(<TaskSessionBody taskId="task-1" />);
    expect(screen.queryByPlaceholderText(/type a message/i)).not.toBeInTheDocument();
  });
});
