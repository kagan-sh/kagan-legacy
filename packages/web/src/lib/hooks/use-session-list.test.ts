/**
 * Unit tests for useSessionList.
 */

import { describe, expect, it, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { useSessionList } from '@/lib/hooks/use-session-list';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getSessions: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSession(overrides: Partial<{
  id: string;
  updated_at: string;
  type: string;
  title: string;
}> = {}) {
  return {
    id: overrides.id ?? 'sess-1',
    type: overrides.type ?? 'chat',
    role: null,
    status: 'active',
    title: overrides.title ?? 'Session',
    backend: null,
    project_id: null,
    task_id: null,
    session_id: null,
    chat_session_id: null,
    updated_at: overrides.updated_at ?? '2026-05-08T12:00:00Z',
    capabilities: {
      can_chat: true,
      can_stream: true,
      can_replay: true,
      can_stop: true,
      can_close: true,
      has_kagan_tools: true,
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useSessionList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts in loading state with empty sessions', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getSessions as Mock).mockResolvedValue({ sessions: [] });

    const { result } = renderHook(() => useSessionList());

    expect(result.current.loading).toBe(true);
    expect(result.current.sessions).toEqual([]);
    expect(result.current.error).toBeNull();

    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('fetches sessions on mount and sorts by updated_at desc', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getSessions as Mock).mockResolvedValue({
      sessions: [
        makeSession({ id: 'sess-a', updated_at: '2026-05-08T10:00:00Z', title: 'A' }),
        makeSession({ id: 'sess-b', updated_at: '2026-05-08T14:00:00Z', title: 'B' }),
        makeSession({ id: 'sess-c', updated_at: '2026-05-08T12:00:00Z', title: 'C' }),
      ],
    });

    const { result } = renderHook(() => useSessionList());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.sessions.map((s) => s.id)).toEqual(['sess-b', 'sess-c', 'sess-a']);
    expect(result.current.error).toBeNull();
  });

  it('polls every 5 seconds', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getSessions as Mock).mockResolvedValue({ sessions: [] });

    renderHook(() => useSessionList());

    await act(async () => {
      await Promise.resolve();
    });

    expect(apiClient.getSessions).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(apiClient.getSessions).toHaveBeenCalledTimes(2);
  });

  it('exposes refresh as a manual trigger', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getSessions as Mock).mockResolvedValue({ sessions: [] });

    const { result } = renderHook(() => useSessionList());

    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      void result.current.refresh();
    });

    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(apiClient.getSessions).toHaveBeenCalledTimes(2);
  });

  it('sets error when the API throws', async () => {
    const { apiClient } = await import('@/lib/api/client');
    (apiClient.getSessions as Mock).mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => useSessionList());

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('network down');
    expect(result.current.sessions).toEqual([]);
  });
});
