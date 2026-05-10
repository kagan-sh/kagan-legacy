import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { Sidebar } from './sidebar';
import { boardDialogAtom, tasksAtom } from '@/lib/atoms/board';
import { newSessionModalOpenAtom, sidebarCollapsedAtom, shellPopoverAtom } from '@/lib/atoms/shell';
import { sessionPickerOpenAtom } from '@/lib/atoms/ui';
import { apiClient } from '@/lib/api/client';
import { useSessionList } from '@/lib/hooks/use-session-list';
import type { SessionItemResponse } from '@kagan/shared-api-client';
import { mockTask } from '@/test/mocks';

// All mock factories are self-contained (no outer-scope references) per vitest hoisting rules.
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getHealth: vi.fn(),
    closeSession: vi.fn(),
  },
}));

vi.mock('@/lib/hooks/use-active-project', () => ({
  useActiveProject: () => ({ id: 'p1', name: 'kagan', active: true }),
}));

// Mocked as vi.fn() so tests can call .mockReturnValue() on it.
vi.mock('@/lib/hooks/use-session-list', () => ({
  useSessionList: vi.fn(),
}));

const mockRefresh = vi.fn();

function makeSession(overrides: Partial<SessionItemResponse> = {}): SessionItemResponse {
  return {
    id: 's1',
    type: 'orchestrator',
    role: null,
    status: 'active',
    title: 'Orchestrator',
    backend: null,
    project_id: null,
    task_id: null,
    task_status: null,
    session_id: null,
    chat_session_id: null,
    updated_at: '2026-05-10',
    capabilities: { can_chat: true, can_stream: true, can_replay: false, can_stop: false, can_close: true, has_kagan_tools: false },
    ...overrides,
  };
}

function makeSessions(count: number): SessionItemResponse[] {
  return Array.from({ length: count }, (_, i) =>
    makeSession({
      id: `s${i + 1}`,
      type: i === 0 ? 'orchestrator' : 'general',
      title: `Session ${i + 1}`,
    }),
  );
}

function setSessionListMock(sessions: SessionItemResponse[]) {
  vi.mocked(useSessionList).mockReturnValue({
    sessions,
    loading: false,
    error: null,
    refresh: mockRefresh,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiClient.getHealth).mockResolvedValue({ status: 'ok', version: '0.14.4' });
  vi.mocked(apiClient.closeSession).mockResolvedValue(undefined);
  mockRefresh.mockResolvedValue(undefined);
  // Default: 1 session (≤ 8, no search field)
  setSessionListMock([makeSession()]);
});

describe('Sidebar', () => {
  it('renders primary actions', () => {
    renderWithProviders(<Sidebar />);
    expect(screen.getByRole('button', { name: /new task/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^new session$/i })).toBeInTheDocument();
  });

  it('opens the create-task dialog when New task is clicked', () => {
    const store = createStore();
    renderWithProviders(<Sidebar />, { store });
    fireEvent.click(screen.getByRole('button', { name: /new task/i }));
    expect(store.get(boardDialogAtom)).toEqual({ kind: 'create' });
  });

  it('opens the new session modal when New session is clicked', () => {
    const store = createStore();
    renderWithProviders(<Sidebar />, { store });
    fireEvent.click(screen.getByRole('button', { name: /^new session$/i }));
    expect(store.get(newSessionModalOpenAtom)).toBe(true);
  });

  it('collapses to width 0 when sidebarCollapsedAtom flipped on', () => {
    const store = createStore();
    store.set(sidebarCollapsedAtom, true);
    const { container } = renderWithProviders(<Sidebar />, { store });
    const aside = container.querySelector('aside');
    expect(aside).toHaveAttribute('data-collapsed', 'true');
  });

  it('renders the orchestrator session badge', async () => {
    renderWithProviders(<Sidebar />);
    const badges = await screen.findAllByText('ORCH');
    expect(badges.length).toBeGreaterThan(0);
  });

  it('renders tasks in the Tasks section', async () => {
    const store = createStore();
    store.set(tasksAtom, [mockTask({ title: 'Build the thing' })]);
    renderWithProviders(<Sidebar />, { store });
    expect(await screen.findByRole('button', { name: /build the thing/i })).toBeInTheDocument();
  });

  it('does NOT render an Activity nav link (replaced by title-bar button)', () => {
    renderWithProviders(<Sidebar />);
    expect(screen.queryByRole('link', { name: /^activity$/i })).toBeNull();
  });

  it('renders Agents as a button (not a link) that opens the agents popover', () => {
    const store = createStore();
    renderWithProviders(<Sidebar />, { store });
    const agentsBtn = screen.getByRole('button', { name: /agents/i });
    expect(agentsBtn).toBeInTheDocument();
    fireEvent.click(agentsBtn);
    expect(store.get(shellPopoverAtom).kind).toBe('agents');
  });

  it('renders a Tasks section header', async () => {
    renderWithProviders(<Sidebar />);
    expect(await screen.findByText(/^tasks$/i)).toBeInTheDocument();
  });

  it('groups tasks under per-status subheaders', async () => {
    const store = createStore();
    store.set(tasksAtom, [
      mockTask({ title: 'Backlog task', status: 'BACKLOG' }),
      mockTask({ title: 'Running task', status: 'IN_PROGRESS' }),
    ]);
    renderWithProviders(<Sidebar />, { store });
    expect(await screen.findByText('Backlog task')).toBeInTheDocument();
    expect(screen.getByText('Running task')).toBeInTheDocument();
  });
});

describe('SessionsSection — search field', () => {
  it('does NOT render the search field when sessions.length <= 8', () => {
    setSessionListMock(makeSessions(8));
    renderWithProviders(<Sidebar />);
    expect(screen.queryByRole('searchbox', { name: /search sessions/i })).toBeNull();
  });

  it('renders the search field when sessions.length > 8', () => {
    setSessionListMock(makeSessions(9));
    renderWithProviders(<Sidebar />);
    expect(screen.getByRole('searchbox', { name: /search sessions/i })).toBeInTheDocument();
  });

  it('filters visible session rows by typed query', async () => {
    setSessionListMock([
      makeSession({ id: 's1', type: 'orchestrator', title: 'Alpha chat' }),
      makeSession({ id: 's2', type: 'general', title: 'Beta chat' }),
      makeSession({ id: 's3', type: 'general', title: 'Gamma chat' }),
      makeSession({ id: 's4', type: 'general', title: 'Delta chat' }),
      makeSession({ id: 's5', type: 'general', title: 'Epsilon chat' }),
      makeSession({ id: 's6', type: 'general', title: 'Zeta chat' }),
      makeSession({ id: 's7', type: 'general', title: 'Eta chat' }),
      makeSession({ id: 's8', type: 'general', title: 'Theta chat' }),
      makeSession({ id: 's9', type: 'general', title: 'Iota chat' }),
    ]);
    renderWithProviders(<Sidebar />);

    const search = screen.getByRole('searchbox', { name: /search sessions/i });
    fireEvent.change(search, { target: { value: 'Alpha' } });

    expect(await screen.findByText('Alpha chat')).toBeInTheDocument();
    expect(screen.queryByText('Iota chat')).toBeNull();
  });
});

describe('SessionsSection — per-row delete', () => {
  it('renders a delete button for each session row', () => {
    renderWithProviders(<Sidebar />);
    expect(screen.getByRole('button', { name: /delete session/i })).toBeInTheDocument();
  });

  it('enters confirm state when the delete button is clicked', async () => {
    renderWithProviders(<Sidebar />);

    fireEvent.click(screen.getByRole('button', { name: /delete session/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm delete/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel delete/i })).toBeInTheDocument();
    });
  });

  it('calls closeSession and refresh when confirm is clicked', async () => {
    renderWithProviders(<Sidebar />);

    fireEvent.click(screen.getByRole('button', { name: /delete session/i }));
    await waitFor(() => screen.getByRole('button', { name: /confirm delete/i }));

    fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

    await waitFor(() => {
      expect(vi.mocked(apiClient.closeSession)).toHaveBeenCalledWith('s1');
      expect(mockRefresh).toHaveBeenCalled();
    });
  });

  it('reverts to idle state when Cancel is clicked', async () => {
    renderWithProviders(<Sidebar />);

    fireEvent.click(screen.getByRole('button', { name: /delete session/i }));
    await waitFor(() => screen.getByRole('button', { name: /cancel delete/i }));

    fireEvent.click(screen.getByRole('button', { name: /cancel delete/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /delete session/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /confirm delete/i })).toBeNull();
    });
    expect(vi.mocked(apiClient.closeSession)).not.toHaveBeenCalled();
  });

  it('reverts UI and does not refresh when closeSession rejects', async () => {
    vi.mocked(apiClient.closeSession).mockRejectedValueOnce(new Error('Network error'));

    renderWithProviders(<Sidebar />);

    fireEvent.click(screen.getByRole('button', { name: /delete session/i }));
    await waitFor(() => screen.getByRole('button', { name: /confirm delete/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /confirm delete/i })).toBeNull();
    });
    expect(mockRefresh).not.toHaveBeenCalled();
  });
});

describe('SessionsSection — View all sessions', () => {
  it('renders "View all sessions" when sessions exist', () => {
    renderWithProviders(<Sidebar />);
    expect(screen.getByRole('button', { name: /view all sessions/i })).toBeInTheDocument();
  });

  it('sets sessionPickerOpenAtom to true when "View all sessions" is clicked', () => {
    const store = createStore();
    renderWithProviders(<Sidebar />, { store });

    expect(store.get(sessionPickerOpenAtom)).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /view all sessions/i }));
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
  });
});
