/**
 * Baseline accessibility checks via axe-core.
 *
 * Renders key components and asserts zero WCAG violations.
 * Not exhaustive — just a safety net for the most-used surfaces.
 */
import { describe, it, expect, vi } from 'vitest';
import { axe } from 'vitest-axe';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { mockTask, mockTaskInReview, mockEvent } from '@/test/mocks';
import { wsConnectedAtom } from '@/lib/atoms/connection';

// ── Mocks (same as existing test files) ──────────────────────────────────────

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn().mockResolvedValue([]),
    getProjectRepos: vi.fn().mockResolvedValue([]),
    reviewDecide: vi.fn().mockResolvedValue({}),
    runReview: vi.fn().mockResolvedValue({}),
    getTasks: vi.fn().mockResolvedValue([]),
    getHealth: vi.fn().mockResolvedValue({ version: '0.0.0' }),
    getBaseUrl: vi.fn().mockReturnValue('http://localhost:8765'),
  },
}));

vi.mock('@/lib/api/websocket', () => ({
  kaganWs: {
    startRun: vi.fn(),
    cancelRun: vi.fn(),
    on: vi.fn(() => vi.fn()),
    off: vi.fn(),
    disconnect: vi.fn(),
    connect: vi.fn(),
  },
}));

// ── Lazy imports (after mocks) ───────────────────────────────────────────────

const { TaskCard } = await import('@/components/board/task-card');
const { AgentControl } = await import('@/components/board/agent-control');
const { ReviewPanel } = await import('@/components/board/review-panel');
const { StatusBadge } = await import('@/components/shared/status-badge');
const { ChatInputBar } = await import('@/components/chat/chat-input-bar');
const { ChatMessage } = await import('@/components/chat/chat-message');
const { EventStream } = await import('@/components/session/event-stream');
const { ActivityBar } = await import('@/components/layout/activity-bar');
const { HeaderBar } = await import('@/components/layout/header-bar');
const { ConnectionCard } = await import('@/components/settings/connection-card');
const { Empty, EmptyHeader, EmptyTitle, EmptyDescription } = await import('@/components/ui/empty');
const { ErrorBoundary } = await import('@/components/shared/error-boundary');

// ── Helpers ──────────────────────────────────────────────────────────────────

function connectedStore() {
  const store = createStore();
  store.set(wsConnectedAtom, true);
  return store;
}

async function expectNoViolations(container: HTMLElement) {
  const results = await axe(container);
  expect(results).toHaveNoViolations();
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('Accessibility (axe-core)', () => {
  it('TaskCard has no violations', async () => {
    const { container } = renderWithProviders(
      <TaskCard task={mockTask({ title: 'Fix login bug' })} />,
    );
    await expectNoViolations(container);
  });

  it('AgentControl (idle) has no violations', async () => {
    const { container } = renderWithProviders(
      <AgentControl taskId="t1" status="BACKLOG" />,
      { store: connectedStore() },
    );
    await expectNoViolations(container);
  });

  it('AgentControl (running) has no violations', async () => {
    const { container } = renderWithProviders(
      <AgentControl taskId="t1" status="IN_PROGRESS" startedAt="2026-01-01T12:00:00Z" />,
      { store: connectedStore() },
    );
    await expectNoViolations(container);
  });

  it('ReviewPanel has no violations', async () => {
    const task = mockTaskInReview({ acceptance_criteria: ['Criterion one'] });
    const { container } = renderWithProviders(
      <ReviewPanel taskId={task.id} task={task} />,
    );
    await expectNoViolations(container);
  });

  it('StatusBadge has no violations', async () => {
    const { container } = renderWithProviders(
      <StatusBadge status="IN_PROGRESS" />,
    );
    await expectNoViolations(container);
  });

  it('ChatInputBar has no violations', async () => {
    const { container } = renderWithProviders(
      <ChatInputBar onSend={vi.fn()} />,
      { store: connectedStore() },
    );
    await expectNoViolations(container);
  });

  it('ChatMessage (user) has no violations', async () => {
    const { container } = renderWithProviders(
      <ChatMessage message={{ role: 'user', content: 'Hello' }} />,
    );
    await expectNoViolations(container);
  });

  it('ChatMessage (assistant) has no violations', async () => {
    const { container } = renderWithProviders(
      <ChatMessage message={{ role: 'assistant', content: 'Hi there' }} />,
    );
    await expectNoViolations(container);
  });

  it('EventStream (empty) has no violations', async () => {
    const { container } = renderWithProviders(
      <EventStream events={[]} />,
    );
    await expectNoViolations(container);
  });

  it('EventStream (with events) has no violations', async () => {
    const events = [
      mockEvent({ type: 'OUTPUT_CHUNK', payload: { text: 'Working...' } }),
      mockEvent({ type: 'TOOL_CALL_START', payload: { name: 'read_file', id: 'tc-1' } }),
    ];
    const { container } = renderWithProviders(
      <EventStream events={events} isRunning />,
    );
    await expectNoViolations(container);
  });

  it('ActivityBar has no violations', async () => {
    const { container } = renderWithProviders(<ActivityBar />);
    await expectNoViolations(container);
  });

  it('HeaderBar has no violations', async () => {
    const { container } = renderWithProviders(<HeaderBar />);
    await expectNoViolations(container);
  });

  it('ConnectionCard has no violations', async () => {
    const { container } = renderWithProviders(<ConnectionCard />);
    await expectNoViolations(container);
  });

  it('Empty state has no violations', async () => {
    const { container } = renderWithProviders(
      <Empty>
        <EmptyHeader>
          <EmptyTitle>No tasks</EmptyTitle>
          <EmptyDescription>Create one to get started</EmptyDescription>
        </EmptyHeader>
      </Empty>,
    );
    await expectNoViolations(container);
  });

  it('ErrorBoundary fallback has no violations', async () => {
    function Bomb(): never {
      throw new Error('boom');
    }
    // Suppress React error boundary console noise
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = renderWithProviders(
      <ErrorBoundary><Bomb /></ErrorBoundary>,
    );
    spy.mockRestore();
    await expectNoViolations(container);
  });
});
