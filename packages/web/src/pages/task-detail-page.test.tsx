/**
 * task-detail-page.test.tsx
 *
 * Unit tests for defaultTabForTask logic (no network / DOM needed) plus
 * component-level contract tests for the tv-chrome: header, status pill,
 * edit chip, Run/Stop toggle, and Move-to button.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { defaultTabForTask, Component as TaskDetailPage } from '@/pages/task-detail-page';
import { shellTabAtom } from '@/lib/atoms/shell';
import type { WireTask } from '@kagan/shared-api-client';

// ── vi.mock hoisting: factories must not reference outer-scope variables ──────

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getTask: vi.fn(),
    getTaskEvents: vi.fn(),
    getSessions: vi.fn(),
    getSettings: vi.fn(),
    getTasks: vi.fn(),
    runTask: vi.fn(),
    cancelTask: vi.fn(),
    transitionTaskStatus: vi.fn(),
    getTaskWorktree: vi.fn(),
    getChatAgents: vi.fn(),
    detectIntegrationRepo: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

vi.mock('@/lib/hooks/use-task-events', () => ({
  useTaskEvents: vi.fn(),
}));

vi.mock('@/lib/hooks/use-session-overlay', () => ({
  useSessionOverlay: vi.fn(),
}));

vi.mock('@/lib/hooks/use-event-stream', () => ({
  useEventStream: vi.fn(),
}));

// ── Lazy imports after mocks are hoisted ─────────────────────────────────────

const { useTaskEvents } = await import('@/lib/hooks/use-task-events');
const { useSessionOverlay } = await import('@/lib/hooks/use-session-overlay');
const { apiClient } = await import('@/lib/api/client');

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeTask(overrides: Partial<WireTask> = {}): WireTask {
  return {
    id: 'aaaabbbbccccdddd',
    title: 'My Task',
    description: 'A description',
    status: 'BACKLOG',
    priority: 'MEDIUM',
    acceptance_criteria: [],
    review_approved: false,
    has_workspace: false,
    ...overrides,
  };
}

const BASE_TASK_EVENTS = {
  task: null as WireTask | null,
  events: [] as unknown[],
  loading: false,
  runningSince: null as string | null,
  isRunning: false,
  sessions: [] as unknown[],
  sentFollowUps: [] as unknown[],
  queue: [] as unknown[],
  sendingFollowUp: false,
  queuePrompt: vi.fn(),
  removePrompt: vi.fn(),
  editPrompt: vi.fn(),
  interruptAndSend: vi.fn(),
};

function setupTaskEvents(task: WireTask | null, extra: Partial<typeof BASE_TASK_EVENTS> = {}) {
  vi.mocked(useTaskEvents as ReturnType<typeof vi.fn>).mockReturnValue({
    ...BASE_TASK_EVENTS,
    task,
    ...extra,
  });
}

function setupOverlay() {
  const open = vi.fn();
  vi.mocked(useSessionOverlay as ReturnType<typeof vi.fn>).mockReturnValue({
    open,
    close: vi.fn(),
    isOpen: false,
    session: null,
  });
  return { open };
}

function renderPage(
  initialPath = '/task/aaaabbbbccccdddd',
  store?: ReturnType<typeof createStore>,
) {
  return renderWithProviders(<TaskDetailPage />, {
    initialEntries: [initialPath],
    store,
  });
}

/** Create a store with shellTabAtom preset to 'kanban' (Board view). */
function boardStore() {
  const s = createStore();
  s.set(shellTabAtom, 'kanban');
  return s;
}

// ── defaultTabForTask — pure logic ────────────────────────────────────────────

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
          active_session: {
            id: 's1',
            status: 'RUNNING',
            launcher: null,
            agent_backend: 'claude',
            started_at: '2026-01-01',
          },
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

// ── Component-level contract tests ────────────────────────────────────────────

describe('TaskDetailPage chrome', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupOverlay();
    vi.mocked(apiClient.getSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      attached_launcher: null,
      skip_attached_instructions_popup: false,
    });
    vi.mocked(apiClient.getTasks as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    vi.mocked(apiClient.getSessions as ReturnType<typeof vi.fn>).mockResolvedValue({
      sessions: [],
    });
    vi.mocked(apiClient.getChatAgents as ReturnType<typeof vi.fn>).mockResolvedValue({
      backends: [],
    });
    vi.mocked(apiClient.detectIntegrationRepo as ReturnType<typeof vi.fn>).mockResolvedValue({
      repo_slug: null,
    });
  });

  // 1. Back button: when navigating from the Board (shellTabAtom = 'kanban'), label is "Board"
  it('renders tv-head back button with "Board" label when coming from Board', () => {
    setupTaskEvents(makeTask());
    renderPage('/task/aaaabbbbccccdddd', boardStore());
    expect(screen.getByRole('button', { name: /Back to Board/i })).toBeInTheDocument();
  });

  it('renders tv-head back button with "Workspace" label when coming from Workspace', () => {
    setupTaskEvents(makeTask());
    renderPage(); // default shellTabAtom = 'workspace'
    expect(screen.getByRole('button', { name: /Back to Workspace/i })).toBeInTheDocument();
  });

  // 2. Status pill renders canonical label, never the raw enum value
  it('renders canonical "Backlog" label in status pill — never "BACKLOG"', () => {
    setupTaskEvents(makeTask({ status: 'BACKLOG' }));
    renderPage();
    const pill = screen.getByLabelText(/Status: Backlog/i);
    expect(pill).toBeInTheDocument();
    expect(pill.textContent).toBe('Backlog');
  });

  it('renders canonical "In Progress" label for IN_PROGRESS status', () => {
    setupTaskEvents(makeTask({ status: 'IN_PROGRESS' }));
    renderPage();
    const pill = screen.getByLabelText(/Status: In Progress/i);
    expect(pill.textContent).toBe('In Progress');
  });

  it('renders canonical "Review" label for REVIEW status', () => {
    setupTaskEvents(makeTask({ status: 'REVIEW' }));
    renderPage();
    const pill = screen.getByLabelText(/Status: Review/i);
    expect(pill.textContent).toBe('Review');
  });

  it('renders canonical "Done" label for DONE status', () => {
    setupTaskEvents(makeTask({ status: 'DONE', review_approved: true }));
    renderPage();
    const pill = screen.getByLabelText(/Status: Done/i);
    expect(pill.textContent).toBe('Done');
  });

  // 3. Edit chip opens EditTaskDialog
  it('edit chip opens EditTaskDialog when clicked', async () => {
    setupTaskEvents(makeTask({ title: 'My Editable Task' }));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: /Edit task/i }));
    expect(screen.getByRole('dialog', { name: /Edit Task/i })).toBeInTheDocument();
  });

  // 4. Run/Stop button — Start shown when BACKLOG, Stop shown when IN_PROGRESS
  it('shows Start button for BACKLOG task', () => {
    setupTaskEvents(makeTask({ status: 'BACKLOG' }));
    renderPage();
    expect(screen.getByRole('button', { name: /Start/i })).toBeInTheDocument();
  });

  it('shows Stop button for IN_PROGRESS task', () => {
    setupTaskEvents(
      makeTask({
        status: 'IN_PROGRESS',
        active_session: {
          id: 's1',
          status: 'running',
          launcher: null,
          agent_backend: 'claude-code',
          started_at: new Date().toISOString(),
        },
      }),
    );
    renderPage();
    expect(screen.getByRole('button', { name: /Stop/i })).toBeInTheDocument();
  });

  // 5. Move-to button renders for tasks with allowed transitions
  it('renders Move-to combobox for a BACKLOG task', () => {
    setupTaskEvents(makeTask({ status: 'BACKLOG' }));
    renderPage();
    expect(
      screen.getByRole('combobox', { name: /Move task to another status/i }),
    ).toBeInTheDocument();
  });
});
