/**
 * Unit tests for useSessionActions.
 */

import { describe, expect, it, vi, beforeEach, type Mock } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { useSessionActions } from '@/lib/hooks/use-session-actions';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    stopSession: vi.fn(),
    closeSession: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSession(
  overrides: Partial<{
    id: string;
    can_stop: boolean;
    can_close: boolean;
  }> = {},
) {
  return {
    id: overrides.id ?? 'sess-1',
    type: 'chat',
    role: null,
    status: 'active',
    title: 'Session',
    backend: null,
    project_id: null,
    task_id: null,
    session_id: null,
    chat_session_id: null,
    updated_at: '2026-05-08T12:00:00Z',
    capabilities: {
      can_chat: true,
      can_stream: true,
      can_replay: true,
      can_stop: overrides.can_stop ?? true,
      can_close: overrides.can_close ?? true,
      has_kagan_tools: true,
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useSessionActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reflects can_stop from session capabilities', () => {
    const { result } = renderHook(() => useSessionActions());

    const stoppable = makeSession({ can_stop: true });
    const nonStoppable = makeSession({ can_stop: false });

    expect(result.current.canStop(stoppable)).toBe(true);
    expect(result.current.canStop(nonStoppable)).toBe(false);
  });

  it('reflects can_close from session capabilities', () => {
    const { result } = renderHook(() => useSessionActions());

    const closable = makeSession({ can_close: true });
    const nonClosable = makeSession({ can_close: false });

    expect(result.current.canClose(closable)).toBe(true);
    expect(result.current.canClose(nonClosable)).toBe(false);
  });

  it('calls stopSession when acting on a stoppable session', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.stopSession as Mock).mockResolvedValue(undefined);

    const { result } = renderHook(() => useSessionActions());
    const session = makeSession({ id: 'sess-stop', can_stop: true });

    act(() => {
      void result.current.stop(session);
    });

    expect(result.current.isStopping).toBe(true);

    await waitFor(() => expect(result.current.isStopping).toBe(false));

    expect(apiClient.stopSession).toHaveBeenCalledWith('sess-stop');
  });

  it('does not call stopSession when session lacks can_stop', async () => {
    const { apiClient } = await import('@/lib/api/client');

    const { result } = renderHook(() => useSessionActions());
    const session = makeSession({ id: 'sess-no-stop', can_stop: false });

    await act(async () => {
      await result.current.stop(session);
    });

    expect(apiClient.stopSession).not.toHaveBeenCalled();
    expect(result.current.isStopping).toBe(false);
  });

  it('calls closeSession when acting on a closable session', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.closeSession as Mock).mockResolvedValue(undefined);

    const { result } = renderHook(() => useSessionActions());
    const session = makeSession({ id: 'sess-close', can_close: true });

    act(() => {
      void result.current.close(session);
    });

    expect(result.current.isClosing).toBe(true);

    await waitFor(() => expect(result.current.isClosing).toBe(false));

    expect(apiClient.closeSession).toHaveBeenCalledWith('sess-close');
  });

  it('does not call closeSession for a task session that cannot be closed', async () => {
    const { apiClient } = await import('@/lib/api/client');

    const { result } = renderHook(() => useSessionActions());
    const session = makeSession({
      id: 'task-sess',
      can_stop: true,
      can_close: false,
    });

    await act(async () => {
      await result.current.close(session);
    });

    expect(apiClient.closeSession).not.toHaveBeenCalled();
    expect(result.current.isClosing).toBe(false);
  });
});
