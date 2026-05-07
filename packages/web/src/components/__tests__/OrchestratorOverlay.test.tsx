/**
 * OrchestratorOverlay component tests.
 *
 * Tests: orchestrator mode, attached mode (breadcrumb, back button detach),
 * reconnect banner, no-session fallback.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, fireEvent, act, waitFor } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { OrchestratorOverlay } from '@/components/session/orchestrator-overlay';
import {
  chatAttachAtom,
  attachChatSessionAtom,
  type ChatAttachTarget,
} from '@/lib/atoms/chat-attach';
import { setRunningAgentsAtom } from '@/lib/atoms/running-agents';

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getRunningAgents: vi.fn().mockResolvedValue({ agents: [] }),
    getSessionReplay: vi.fn().mockResolvedValue({ events: [], has_more: false }),
    getChatSession: vi.fn().mockResolvedValue({
      id: 'session-1',
      label: 'Test session',
      source: 'web',
      updated_at: new Date().toISOString(),
      message_count: 0,
      messages: [],
    }),
    getChatAgents: vi.fn().mockResolvedValue({ backends: [] }),
    getProjects: vi.fn().mockResolvedValue([]),
    getProjectRepos: vi.fn().mockResolvedValue([]),
    getTurnStatus: vi.fn().mockResolvedValue({ status: 'idle' }),
    getChatMessages: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('@/lib/hooks/use-chat-session', () => ({
  useChatSession: vi.fn(() => ({
    messages: [],
    streamEntries: [],
    isStreaming: false,
    loading: false,
    label: 'Orchestrator Chat',
    agentBackend: null,
    availableBackends: [],
    editPrefill: null,
    scrollRef: { current: null },
    onSend: vi.fn(),
    onInterrupt: vi.fn(),
    onSlashCommand: vi.fn(),
    switchBackend: vi.fn(),
    setEditPrefill: vi.fn(),
    setLabel: vi.fn(),
    permissionRequest: null,
    setPermissionRequest: vi.fn(),
  })),
}));

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeAttachTarget(overrides: Partial<ChatAttachTarget> = {}): ChatAttachTarget {
  return {
    attachedSessionId: 'worker-session-1',
    taskTitle: 'Fix the login bug',
    role: 'worker',
    startedAt: new Date(Date.now() - 30_000).toISOString(),
    inputTokens: 5000,
    outputTokens: 1200,
    ...overrides,
  };
}

function renderOverlay(
  store: ReturnType<typeof createStore>,
  props: { chatSessionId?: string | null } = {},
) {
  const { chatSessionId = 'session-1' } = props;
  const onSetLayout = vi.fn();
  const onClose = vi.fn();
  return {
    ...renderWithProviders(
      <OrchestratorOverlay
        chatSessionId={chatSessionId}
        layout="chat-right"
        onSetLayout={onSetLayout}
        onClose={onClose}
      />,
      { store },
    ),
    onSetLayout,
    onClose,
  };
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('OrchestratorOverlay', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  describe('orchestrator mode', () => {
    it('renders orchestrator chat panel when not attached', async () => {
      renderOverlay(store);
      // OrchestratorChatPanel renders with a "Sessions" button
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /sessions/i })).toBeInTheDocument();
      });
    });

    it('shows no agents running in the bar', async () => {
      renderOverlay(store);
      await waitFor(() => {
        expect(screen.getByLabelText('No agents running')).toBeInTheDocument();
      });
    });

    it('shows agent rows in the bar when agents are running', async () => {
      store.set(setRunningAgentsAtom, [
        {
          task_id: 'task-1',
          task_title: 'Build feature',
          task_status: 'IN_PROGRESS',
          session_id: 'sess-worker',
          agent_role: 'worker',
          agent_backend: 'claude-code',
          session_status: 'running',
          started_at: new Date(Date.now() - 10_000).toISOString(),
          last_event_at: null,
          input_tokens: 1000,
          output_tokens: 200,
        },
      ]);

      renderOverlay(store);
      await waitFor(() => {
        expect(screen.getByLabelText('Attach to worker agent: Build feature')).toBeInTheDocument();
      });
    });

    it('renders fallback when chatSessionId is null', () => {
      renderOverlay(store, { chatSessionId: null });
      expect(screen.getByRole('button', { name: /select a session/i })).toBeInTheDocument();
    });
  });

  describe('attached mode', () => {
    it('shows breadcrumb with role, elapsed time, and tokens when attached', async () => {
      act(() => {
        store.set(attachChatSessionAtom, makeAttachTarget());
      });

      renderOverlay(store);

      // Breadcrumb: "Worker · <elapsed> · ↑5.0k ↓1.2k"
      await waitFor(() => {
        expect(screen.getByText(/Worker · /)).toBeInTheDocument();
        expect(screen.getByText(/↑5\.0k ↓1\.2k/)).toBeInTheDocument();
      });
    });

    it('shows reviewer breadcrumb for reviewer role', async () => {
      act(() => {
        store.set(attachChatSessionAtom, makeAttachTarget({ role: 'reviewer' }));
      });

      renderOverlay(store);

      await waitFor(() => {
        expect(screen.getByText(/Reviewer · /)).toBeInTheDocument();
      });
    });

    it('shows task title in the header', async () => {
      act(() => {
        store.set(attachChatSessionAtom, makeAttachTarget({ taskTitle: 'Fix the login bug' }));
      });

      renderOverlay(store);

      await waitFor(() => {
        expect(screen.getByText('Fix the login bug')).toBeInTheDocument();
      });
    });

    it('back button detaches and returns to orchestrator mode', async () => {
      act(() => {
        store.set(attachChatSessionAtom, makeAttachTarget());
      });

      renderOverlay(store);

      await waitFor(() => {
        expect(screen.getByText(/Worker · /)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /detach from agent/i }));
      expect(store.get(chatAttachAtom)).toBeNull();
    });

    it('close button calls onClose', async () => {
      act(() => {
        store.set(attachChatSessionAtom, makeAttachTarget());
      });

      const { onClose } = renderOverlay(store);
      await waitFor(() => expect(screen.getByRole('button', { name: /close overlay/i })).toBeInTheDocument());

      fireEvent.click(screen.getByRole('button', { name: /close overlay/i }));
      expect(onClose).toHaveBeenCalledOnce();
    });
  });

  describe('mode switching', () => {
    it('switches from orchestrator to attached mode when atom changes', async () => {
      renderOverlay(store);

      // Initially in orchestrator mode
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /sessions/i })).toBeInTheDocument();
      });

      // Attach to an agent
      act(() => {
        store.set(attachChatSessionAtom, makeAttachTarget({ taskTitle: 'New task' }));
      });

      await waitFor(() => {
        expect(screen.getByText('New task')).toBeInTheDocument();
      });
    });
  });
});
