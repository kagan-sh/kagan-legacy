import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { TaskSessionBody } from '@/components/session/TaskSessionBody';

const useTaskEventsMock = vi.hoisted(() =>
  vi.fn(() => ({
    events: [],
    isRunning: false,
    hasMore: false,
    loadingMore: false,
    loadEarlier: vi.fn(),
  })),
);

vi.mock('@/lib/hooks/use-task-events', () => ({
  useTaskEvents: useTaskEventsMock,
}));

describe('TaskSessionBody', () => {
  it('loads task events with raw task and session ids', () => {
    renderWithProviders(<TaskSessionBody taskId="task-1" sessionId="worker-session" />);
    expect(useTaskEventsMock).toHaveBeenCalledWith('task-1', {
      sessionId: 'worker-session',
    });
  });

  it('shows task session replay label', () => {
    renderWithProviders(<TaskSessionBody taskId="task-1" />);
    expect(screen.getByText(/task session replay/i)).toBeInTheDocument();
  });

  it('does not render a chat input', () => {
    renderWithProviders(<TaskSessionBody taskId="task-1" />);
    expect(screen.queryByPlaceholderText(/type a message/i)).not.toBeInTheDocument();
  });
});
