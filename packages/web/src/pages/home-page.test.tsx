import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { mockTask } from '@/test/mocks';

const navigateMock = vi.fn();

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getTasks: vi.fn().mockResolvedValue([]),
    createTask: vi.fn(),
  },
}));

// Import after mocks so the page picks up the mocked modules.
const { HomePage } = await import('@/pages/home-page');
const { apiClient } = await import('@/lib/api/client');

function renderHome() {
  return renderWithProviders(<HomePage />);
}

beforeEach(() => {
  vi.clearAllMocks();
  (apiClient.getTasks as ReturnType<typeof vi.fn>).mockResolvedValue([]);
});

describe('HomePage', () => {
  it('renders the greeting and hero input', async () => {
    renderHome();

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      /good (morning|afternoon|evening)|still up/i,
    );
    expect(screen.getByLabelText('Describe what you want to do')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('autofocuses the hero input on mount', () => {
    renderHome();
    expect(document.activeElement).toBe(screen.getByLabelText('Describe what you want to do'));
  });

  it('shows an intent preview once the user types enough characters', async () => {
    const user = userEvent.setup();
    renderHome();

    const input = screen.getByLabelText('Describe what you want to do');
    await user.type(input, 'add dark mode');

    expect(await screen.findByText(/create task:/i)).toBeVisible();
  });

  it('creates a task on submit for imperative input', async () => {
    (apiClient.createTask as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockTask({ id: 'new-task', title: 'Add dark mode toggle' }),
    );
    const user = userEvent.setup();
    renderHome();

    const input = screen.getByLabelText('Describe what you want to do');
    await user.type(input, 'add dark mode toggle');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => {
      expect(apiClient.createTask).toHaveBeenCalledWith({ title: 'Add dark mode toggle' });
    });
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/task/new-task');
    });
  });

  it('routes to the workspace for questions', async () => {
    const user = userEvent.setup();
    renderHome();

    const input = screen.getByLabelText('Describe what you want to do');
    await user.type(input, 'how do I cancel a running task?');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/workspace');
    });
    expect(apiClient.createTask).not.toHaveBeenCalled();
  });

  it('routes to the board search for find-style queries', async () => {
    const user = userEvent.setup();
    renderHome();

    const input = screen.getByLabelText('Describe what you want to do');
    await user.type(input, 'find OAuth tasks');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith(`/board?q=${encodeURIComponent('find OAuth tasks')}`);
    });
  });

  it('renders recents when tasks exist', async () => {
    (apiClient.getTasks as ReturnType<typeof vi.fn>).mockResolvedValue([
      mockTask({ title: 'First recent task' }),
      mockTask({ title: 'Second recent task' }),
    ]);
    renderHome();

    expect(await screen.findByText('First recent task')).toBeVisible();
    expect(screen.getByText('Second recent task')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Recent tasks' })).toBeInTheDocument();
  });

  it('hides recents entirely when the list is empty', async () => {
    renderHome();

    // Wait until loading state finishes.
    await waitFor(() => {
      expect(apiClient.getTasks).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: 'Recent tasks' })).not.toBeInTheDocument();
    });
  });

  it('does not submit when the input is empty', async () => {
    const user = userEvent.setup();
    renderHome();

    const input = screen.getByLabelText('Describe what you want to do');
    await user.click(input);
    await user.keyboard('{Enter}');

    expect(navigateMock).not.toHaveBeenCalled();
    expect(apiClient.createTask).not.toHaveBeenCalled();
  });
});
