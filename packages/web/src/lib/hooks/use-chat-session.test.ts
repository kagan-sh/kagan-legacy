/**
 * Unit tests for useChatSession.
 *
 * Scenarios covered:
 *   - connect: initial load sets messages, label, agentBackend
 *   - chunk dispatch: CHAT_CHUNK events set isStreaming + append stream entries
 *   - tool start / done: CHAT_TOOL_START / CHAT_TOOL_PROGRESS via handleWatchEvent
 *   - error: CHAT_ERROR clears streaming, appends error entry
 *   - takeover: CHAT_TURN_TERMINATED with reason=takeover sets takeoverBanner
 *   - 409 conflict: POST /stream returning 409 sets turnConflict
 */

import { describe, expect, it, vi, beforeEach, type Mock } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { createStore, Provider } from 'jotai';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router';

import { useChatSession } from '@/lib/hooks/use-chat-session';
import {
  isStreamingAtom,
  streamEntriesAtom,
  takeoverBannerAtom,
  turnConflictAtom,
  chatMessagesAtom,
  enqueuePendingAtom,
} from '@/lib/atoms/chat';
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
    expect(store.get(chatMessagesAtom)).toEqual([{ role: 'assistant', content: 'Hello' }]);
  });

  it('sets isStreaming and adds reconnect note when turn is active on load', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getTurnStatus as Mock).mockResolvedValueOnce({ active: true });

    const store = createStore();
    renderWithStore(() => useChatSession('session-2'), store);

    await act(async () => {});

    expect(store.get(isStreamingAtom)).toBe(true);
    const entries = store.get(streamEntriesAtom);
    expect(entries.some((e) => e.kind === 'note')).toBe(true);
  });
});

describe('useChatSession — chunk dispatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('sets isStreaming to true and appends a text entry on CHAT_CHUNK', async () => {
    const store = createStore();
    renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_CHUNK, content: 'hello', thought: false });

    expect(store.get(isStreamingAtom)).toBe(true);
    const entries = store.get(streamEntriesAtom);
    const textEntry = entries.find((e) => e.kind === 'text');
    expect(textEntry).toBeDefined();
    expect((textEntry as { kind: 'text'; content: string } | undefined)?.content).toBe('hello');
  });

  it('appends a thought entry when thought flag is true', async () => {
    const store = createStore();
    renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_CHUNK, content: 'thinking…', thought: true });

    const entries = store.get(streamEntriesAtom);
    expect(entries.some((e) => e.kind === 'thought')).toBe(true);
  });

  it('resets stream entries and isStreaming on CHAT_DONE', async () => {
    const store = createStore();
    store.set(isStreamingAtom, true);
    renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_DONE, full_response: 'final text' });

    expect(store.get(isStreamingAtom)).toBe(false);
    expect(store.get(streamEntriesAtom)).toHaveLength(0);
  });

  it('drains queued attachments into the next stream after CHAT_DONE', async () => {
    vi.useFakeTimers();
    try {
      const { streamSSE } = await import('@/lib/api/sse');
      const store = createStore();
      store.set(enqueuePendingAtom, {
        text: 'follow up',
        attachments: [{ id: 'att-1', name: 'notes.txt', type: 'file', content: 'hello' }],
      });
      renderWithStore(() => useChatSession('session-1'), store);
      await act(async () => {});

      fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_DONE, full_response: 'final text' });
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

describe('useChatSession — tool start / done', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('adds a running tool entry on CHAT_TOOL_START', async () => {
    const store = createStore();
    renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_TOOL_START, tool: 'shell' });

    const entries = store.get(streamEntriesAtom);
    const tool = entries.find((e) => e.kind === 'tool');
    expect(tool).toBeDefined();
    if (tool?.kind === 'tool') {
      expect(tool.name).toBe('shell');
      expect(tool.status).toBe('running');
    }
  });

  it('marks a tool as done on CHAT_TOOL_PROGRESS with status=done', async () => {
    const store = createStore();
    renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_TOOL_START, tool: 'shell' });
    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_TOOL_PROGRESS, tool: 'shell', status: 'done' });

    const entries = store.get(streamEntriesAtom);
    const tool = entries.find((e) => e.kind === 'tool');
    if (tool?.kind === 'tool') {
      expect(tool.status).toBe('done');
    }
  });
});

describe('useChatSession — error', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('appends an error entry and clears isStreaming on CHAT_ERROR', async () => {
    const store = createStore();
    store.set(isStreamingAtom, true);
    renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_ERROR, error: 'backend crashed' });

    expect(store.get(isStreamingAtom)).toBe(false);
    const entries = store.get(streamEntriesAtom);
    expect(entries.some((e) => e.kind === 'error')).toBe(true);
  });
});

describe('useChatSession — takeover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('sets takeoverBanner on CHAT_TURN_TERMINATED with reason=takeover', async () => {
    const store = createStore();
    renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_TURN_TERMINATED, reason: 'takeover' });

    expect(store.get(takeoverBannerAtom)).toMatch(/taken over/i);
    expect(store.get(isStreamingAtom)).toBe(false);
  });

  it('onDismissTakeover clears the banner', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    fireWatchEvent({ t: CHAT_WATCH_TYPE.CHAT_TURN_TERMINATED, reason: 'takeover' });
    expect(store.get(takeoverBannerAtom)).not.toBeNull();

    act(() => { result.current.onDismissTakeover(); });
    expect(store.get(takeoverBannerAtom)).toBeNull();
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

    const conflict = store.get(turnConflictAtom);
    expect(conflict).not.toBeNull();
    expect(conflict?.pendingText).toBe('hello world');
    expect(conflict?.partialChars).toBe(42);
    expect(store.get(isStreamingAtom)).toBe(false);
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

    expect(store.get(turnConflictAtom)?.pendingAttachments).toEqual([attachment]);
  });

  it('onDismissConflict clears the conflict state', async () => {
    const store = createStore();
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    store.set(turnConflictAtom, {
      runningSince: '2026-01-01T00:00:00Z',
      partialChars: 0,
      pendingText: 'test',
    });

    act(() => { result.current.onDismissConflict(); });
    expect(store.get(turnConflictAtom)).toBeNull();
  });
});

describe('useChatSession — slash commands', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
  });

  it('/clear resets messages', async () => {
    const store = createStore();
    store.set(chatMessagesAtom, [{ role: 'user', content: 'hi' }]);
    const { result } = renderWithStore(() => useChatSession('session-1'), store);
    await act(async () => {});

    act(() => { result.current.onSlashCommand('/clear'); });
    expect(store.get(chatMessagesAtom)).toHaveLength(0);
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
