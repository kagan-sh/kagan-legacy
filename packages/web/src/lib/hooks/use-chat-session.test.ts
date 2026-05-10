/**
 * Unit tests for useChatSession.
 *
 * Scenarios covered:
 *   - connect: initial load sets messages, label, agentBackend
 *   - chunk dispatch: assistant_chunk / thinking_chunk engine events set isStreaming + stream entries
 *   - tool start / done: tool_call / tool_call_update / tool_call_result engine events
 *   - error: CHAT_ERROR (transport) and error (engine) clear streaming, append error entry
 *   - takeover: CHAT_TURN_TERMINATED with reason=takeover sets takeoverBanner
 *   - 409 conflict: POST /stream returning 409 sets turnConflict
 *
 * All state assertions use result.current.* — no global jotai atoms.
 *
 * Event shapes:
 *   - Engine events (ChatEngineEvent) use ``type`` field: assistant_chunk, thinking_chunk,
 *     tool_call, tool_call_update, tool_call_result, turn_end, error, etc.
 *   - Transport frames use ``t`` field: CHAT_USER_MESSAGE, CHAT_ASSISTANT_MESSAGE,
 *     CHAT_TURN_STARTED, CHAT_TURN_TERMINATED, CHAT_SESSION_UPDATED, CHAT_ERROR,
 *     CHAT_PERMISSION_REQUEST.
 */

import { describe, expect, it, vi, beforeEach, type Mock } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { createStore, Provider } from 'jotai';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router';

import { useChatSession } from '@/lib/hooks/use-chat-session';
import { CHAT_WATCH_TYPE } from '@kagan/shared-api-client';
import type { ChatWatchEvent } from '@kagan/shared-api-client';

// ---------------------------------------------------------------------------
// Module-level mocks — vi.mock is hoisted; factories must be self-contained.
// No references to outer-scope variables in factories (hoisting constraint).
// ---------------------------------------------------------------------------

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

// The mock for @/lib/api/client re-exports the real ApiError class so that
// instanceof checks in useChatSession work correctly. We use vi.importActual
// so the factory stays self-contained (no outer-scope import references).
vi.mock('@/lib/api/client', async () => {
  const actual = await vi.importActual<typeof import('@kagan/shared-api-client')>('@kagan/shared-api-client');
  return {
    apiClient: {
      getBaseUrl: () => 'http://localhost',
      getChatSession: vi.fn().mockResolvedValue({
        messages: [{ role: 'assistant', content: 'Hello' }],
        label: 'Test Session',
        agent_backend: 'claude',
        project_id: 'project-1',
      }),
      getTurnStatus: vi.fn().mockResolvedValue({ active: false }),
      getChatAgents: vi.fn().mockResolvedValue({ backends: [] }),
      interruptChatTurn: vi.fn().mockResolvedValue(undefined),
      updateChatSession: vi.fn().mockResolvedValue(undefined),
      getChatMessages: vi.fn().mockResolvedValue([]),
    },
    ApiError: actual.ApiError,
  };
});

// streamSSE default is a no-op generator; tests override per-case.
vi.mock('@/lib/api/sse', () => ({
  streamSSE: vi.fn(async function* () {}),
}));

// useChatWatch: capture the onEvent callback so tests can fire synthetic events.
let capturedOnEvent: ((event: ChatWatchEvent) => void) | null = null;
vi.mock('@/lib/hooks/use-chat-watch', () => ({
  useChatWatch: vi.fn((_id: unknown, opts: { onEvent: (e: ChatWatchEvent) => void }) => {
    capturedOnEvent = opts.onEvent;
  }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithStore<T>(hook: () => T, store: ReturnType<typeof createStore>) {
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(
      Provider,
      { store },
      createElement(MemoryRouter, { initialEntries: ['/chat/session-1'] }, children),
    );
  return renderHook(hook, { wrapper });
}

function fireWatchEvent(event: ChatWatchEvent) {
  act(() => {
    capturedOnEvent?.(event);
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useChatSession — connect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('loads messages and label from the session API on mount', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);

    await act(async () => {});

    expect(result.current.loading).toBe(false);
    expect(result.current.label).toBe('Test Session');
    expect(result.current.projectId).toBe('project-1');
    expect(result.current.agentBackend).toBe('claude');
    expect(result.current.messages).toEqual([{ role: 'assistant', content: 'Hello' }]);
  });

  it('sets isStreaming and adds reconnect note when turn is active on load', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getTurnStatus as Mock).mockResolvedValueOnce({ active: true });

    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-2'), store);

    await act(async () => {});

    expect(result.current.isStreaming).toBe(true);
    expect(result.current.streamEntries.some((e) => e.kind === 'note')).toBe(true);
  });
});

describe('useChatSession — chunk dispatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('sets isStreaming to true and appends a text entry on assistant_chunk', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ type: 'assistant_chunk', turn_id: 't1', session_id: 's1', message_id: 'm1', delta: 'hello' });

    expect(result.current.isStreaming).toBe(true);
    const textEntry = result.current.streamEntries.find((e) => e.kind === 'text');
    expect(textEntry).toBeDefined();
    expect((textEntry as { kind: 'text'; content: string } | undefined)?.content).toBe('hello');
  });

  it('appends a thought entry on thinking_chunk', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ type: 'thinking_chunk', turn_id: 't1', session_id: 's1', message_id: 'm1', delta: 'thinking…' });

    expect(result.current.streamEntries.some((e) => e.kind === 'thought')).toBe(true);
  });

  it('resets stream entries and isStreaming on turn_end with reason=done', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    // Seed streaming state via a chunk event.
    fireWatchEvent({ type: 'assistant_chunk', turn_id: 't1', session_id: 's1', message_id: 'm1', delta: 'partial' });
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.streamEntries.length).toBeGreaterThan(0);

    fireWatchEvent({ type: 'turn_end', turn_id: 't1', reason: 'done' });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.streamEntries).toHaveLength(0);
  });

  it('drains queued attachments into the next stream after turn_end', async () => {
    vi.useFakeTimers();
    try {
      const { streamSSE } = await import('@/lib/api/sse');
      const store = createStore();
      const { result } = renderWithStore(() => useChatSession('session-1'), store);
      await act(async () => {});

      // Seed the queue via the hook's onEnqueue.
      act(() => {
        result.current.onEnqueue({
          text: 'follow up',
          attachments: [{ id: 'att-1', name: 'notes.txt', type: 'file', content: 'hello' }],
        });
      });

      fireWatchEvent({ type: 'turn_end', turn_id: 't1', reason: 'done' });
      await act(async () => {
        vi.runOnlyPendingTimers();
        await Promise.resolve();
      });

      expect(streamSSE).toHaveBeenCalledWith(
        '/api/chat/session-1/stream',
        expect.objectContaining({
          body: JSON.stringify({
            text: 'follow up',
            attachments: [
              {
                type: 'file',
                name: 'notes.txt',
                mime_type: 'text/plain',
                data: 'hello',
              },
            ],
          }),
        }),
      );
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('useChatSession — tool events', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('adds a running tool entry on tool_call', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ type: 'tool_call', turn_id: 't1', session_id: 's1', tool_call_id: 'tc1', name: 'shell', args: null, title: 'shell', kind: null });

    const tool = result.current.streamEntries.find((e) => e.kind === 'tool');
    expect(tool).toBeDefined();
    if (tool?.kind === 'tool') {
      expect(tool.name).toBe('shell');
      expect(tool.status).toBe('running');
    }
  });

  it('marks a tool as done on tool_call_result with is_error=false', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ type: 'tool_call', turn_id: 't1', session_id: 's1', tool_call_id: 'tc1', name: 'shell', args: null, title: 'shell', kind: null });
    fireWatchEvent({ type: 'tool_call_result', tool_call_id: 'tc1', output: 'ok', is_error: false });

    const tool = result.current.streamEntries.find((e) => e.kind === 'tool');
    if (tool?.kind === 'tool') {
      expect(tool.status).toBe('done');
    }
  });

  it('marks a tool as failed on tool_call_result with is_error=true', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ type: 'tool_call', turn_id: 't1', session_id: 's1', tool_call_id: 'tc1', name: 'shell', args: null, title: 'shell', kind: null });
    fireWatchEvent({ type: 'tool_call_result', tool_call_id: 'tc1', output: null, is_error: true });

    const tool = result.current.streamEntries.find((e) => e.kind === 'tool');
    if (tool?.kind === 'tool') {
      expect(tool.status).toBe('failed');
    }
  });
});

describe('useChatSession — error', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('appends an error entry and clears isStreaming on CHAT_ERROR (transport frame)', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    // Seed streaming state first.
    fireWatchEvent({ type: 'assistant_chunk', turn_id: 't1', session_id: 's1', message_id: 'm1', delta: 'partial' });
    expect(result.current.isStreaming).toBe(true);

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_ERROR, error: 'backend crashed' });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.streamEntries.some((e) => e.kind === 'error')).toBe(true);
  });

  it('appends an error entry on fatal engine error event', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ type: 'assistant_chunk', turn_id: 't1', session_id: 's1', message_id: 'm1', delta: 'partial' });
    expect(result.current.isStreaming).toBe(true);

    fireWatchEvent({ type: 'error', turn_id: 't1', code: 'ENGINE_ERROR', message: 'engine exploded', fatal: true });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.streamEntries.some((e) => e.kind === 'error')).toBe(true);
  });
});

describe('useChatSession — takeover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('sets takeoverBanner on CHAT_TURN_TERMINATED with reason=takeover', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_TURN_TERMINATED, reason: 'takeover' } as ChatWatchEvent);

    expect(result.current.takeoverBanner).toMatch(/taken over/i);
    expect(result.current.isStreaming).toBe(false);
  });

  it('onDismissTakeover clears the banner', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_TURN_TERMINATED, reason: 'takeover' } as ChatWatchEvent);
    expect(result.current.takeoverBanner).not.toBeNull();

    act(() => { result.current.onDismissTakeover(); });
    expect(result.current.takeoverBanner).toBeNull();
  });
});

describe('useChatSession — 409 conflict', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('sets turnConflict when POST /stream returns 409', async () => {
    const { apiClient, ApiError } = await import('@/lib/api/client');
    const { streamSSE } = await import('@/lib/api/sse');

    (apiClient.getTurnStatus as Mock).mockResolvedValue({
      active: true,
      running_since: '2026-01-01T00:00:00Z',
      partial_chars: 42,
    });

    // ApiError constructor: (status: number, detail: string)
    (streamSSE as Mock).mockImplementation(async function* () {
      throw new ApiError(409, 'Turn in progress');
    });

    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    await act(async () => {
      result.current.onSend('hello world');
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.turnConflict).not.toBeNull();
    expect(result.current.turnConflict?.pendingText).toBe('hello world');
    expect(result.current.turnConflict?.partialChars).toBe(42);
    expect(result.current.isStreaming).toBe(false);
  });

  it('stores original attachments for takeover retry after a 409', async () => {
    const { apiClient, ApiError } = await import('@/lib/api/client');
    const { streamSSE } = await import('@/lib/api/sse');
    const attachment = { id: 'att-1', name: 'notes.txt', type: 'file', content: 'hello' };

    (apiClient.getTurnStatus as Mock).mockResolvedValue({
      active: true,
      running_since: '2026-01-01T00:00:00Z',
      partial_chars: 42,
    });
    (streamSSE as Mock).mockImplementation(async function* () {
      throw new ApiError(409, 'Turn in progress');
    });

    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    await act(async () => {
      result.current.onSend('hello world', [attachment]);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.turnConflict?.pendingAttachments).toEqual([attachment]);
  });

  it('onDismissConflict clears the conflict state', async () => {
    const { ApiError } = await import('@/lib/api/client');
    const { streamSSE } = await import('@/lib/api/sse');

    (streamSSE as Mock).mockImplementation(async function* () {
      throw new ApiError(409, 'Turn in progress');
    });

    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    // Trigger 409 to set the conflict state via onSend.
    await act(async () => {
      result.current.onSend('test message');
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.turnConflict).not.toBeNull();

    act(() => { result.current.onDismissConflict(); });
    expect(result.current.turnConflict).toBeNull();
  });
});

describe('useChatSession — slash commands', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('/clear resets messages', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    // After mount, API provides [{ role: 'assistant', content: 'Hello' }].
    expect(result.current.messages.length).toBeGreaterThan(0);

    act(() => { result.current.onSlashCommand('/clear'); });
    expect(result.current.messages).toHaveLength(0);
  });

  it('/new calls extra.onNew when provided instead of navigating', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    const onNew = vi.fn();
    act(() => { result.current.onSlashCommand('/new', { onNew }); });
    expect(onNew).toHaveBeenCalledOnce();
  });

  it('setEditPrefill / onPrefillConsumed round-trip', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    act(() => { result.current.setEditPrefill('prefilled text'); });
    expect(result.current.editPrefill).toBe('prefilled text');

    act(() => { result.current.onPrefillConsumed(); });
    expect(result.current.editPrefill).toBeNull();
  });
});

describe('useChatSession — agent_lifecycle', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    capturedOnEvent = null;
    // Reset getTurnStatus to inactive so no reconnect note is injected on load.
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getTurnStatus as Mock).mockResolvedValue({ active: false });
  });

  it('appends a note entry with checkmark on agent_lifecycle finished', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({
      type: 'agent_lifecycle',
      session_id: 'sess-1',
      task_id: 'abcdef12xyz',
      kind: 'finished',
      detail: null,
    } as ChatWatchEvent);

    const note = result.current.streamEntries.find((e) => e.kind === 'note');
    expect(note).toBeDefined();
    if (note?.kind === 'note') {
      expect(note.message).toContain('✓');
      expect(note.message).toContain('#abcdef12');
      expect(note.message).toContain('finished');
    }
  });

  it('appends a note entry with cross on agent_lifecycle failed', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({
      type: 'agent_lifecycle',
      session_id: 'sess-1',
      task_id: 'abcdef12xyz',
      kind: 'failed',
      detail: 'exit code 1',
    } as ChatWatchEvent);

    const note = result.current.streamEntries.find((e) => e.kind === 'note');
    expect(note).toBeDefined();
    if (note?.kind === 'note') {
      expect(note.message).toContain('✗');
      expect(note.message).toContain('failed');
      expect(note.message).toContain('exit code 1');
    }
  });

  it('appends a note entry with circle on agent_lifecycle stopped', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({
      type: 'agent_lifecycle',
      session_id: 'sess-1',
      task_id: 'abcdef12xyz',
      kind: 'stopped',
      detail: null,
    } as ChatWatchEvent);

    const note = result.current.streamEntries.find((e) => e.kind === 'note');
    expect(note).toBeDefined();
    if (note?.kind === 'note') {
      expect(note.message).toContain('◯');
      expect(note.message).toContain('stopped');
    }
  });

  it('appends a note entry with arrow on agent_lifecycle started', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({
      type: 'agent_lifecycle',
      session_id: 'sess-1',
      task_id: 'abcdef12xyz',
      kind: 'started',
      detail: null,
    } as ChatWatchEvent);

    const note = result.current.streamEntries.find((e) => e.kind === 'note');
    expect(note).toBeDefined();
    if (note?.kind === 'note') {
      expect(note.message).toContain('▸');
      expect(note.message).toContain('started');
    }
  });
});
