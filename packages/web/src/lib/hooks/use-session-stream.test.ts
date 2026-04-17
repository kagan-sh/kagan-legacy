import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useSessionStream } from '@/lib/hooks/use-session-stream';
import type { WireEvent } from '@/lib/api/types';

function dispatchSessionEvent(taskId: string, event: WireEvent) {
  window.dispatchEvent(
    new CustomEvent('kagan:session-event', {
      detail: { task_id: taskId, event },
    }),
  );
}

function mockEvent(overrides: Partial<WireEvent> = {}): WireEvent {
  return {
    id: 'evt-1',
    session_id: 's-1',
    type: 'OUTPUT_CHUNK',
    payload: { text: 'reading files' },
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('useSessionStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('is a no-op when isActive is false', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const { result } = renderHook(() =>
      useSessionStream('s-1', { isActive: false, startedAt: null }),
    );
    expect(result.current).toEqual({ elapsedSeconds: 0, lastLog: null, status: null });
    expect(addSpy).not.toHaveBeenCalledWith('kagan:session-event', expect.any(Function));
    addSpy.mockRestore();
  });

  it('is a no-op when sessionId is null', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    renderHook(() => useSessionStream(null, { isActive: true, startedAt: null }));
    expect(addSpy).not.toHaveBeenCalledWith('kagan:session-event', expect.any(Function));
    addSpy.mockRestore();
  });

  it('seeds elapsed time from startedAt on mount', () => {
    const startedAt = new Date(Date.now() - 75_000).toISOString();
    const { result } = renderHook(() =>
      useSessionStream('s-1', { isActive: true, startedAt }),
    );
    expect(result.current.elapsedSeconds).toBe(75);
    expect(result.current.status).toBe('running');
  });

  it('coalesces multiple SSE events into a single 1 Hz update', () => {
    const startedAt = new Date(Date.now() - 5_000).toISOString();
    const { result } = renderHook(() =>
      useSessionStream('s-1', { isActive: true, startedAt }),
    );

    act(() => {
      dispatchSessionEvent('t-1', mockEvent({ payload: { text: 'first' } }));
      dispatchSessionEvent('t-1', mockEvent({ payload: { text: 'second' } }));
      dispatchSessionEvent('t-1', mockEvent({ payload: { text: 'third' } }));
    });

    // No render yet — events queue until the interval tick.
    expect(result.current.lastLog).toBeNull();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.lastLog).toBe('third');
    expect(result.current.status).toBe('running');
  });

  it('truncates very long log lines to ~60 chars', () => {
    const startedAt = new Date().toISOString();
    const { result } = renderHook(() =>
      useSessionStream('s-1', { isActive: true, startedAt }),
    );
    const longText = 'x'.repeat(120);

    act(() => {
      dispatchSessionEvent('t-1', mockEvent({ payload: { text: longText } }));
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.lastLog).not.toBeNull();
    expect(result.current.lastLog!.length).toBeLessThanOrEqual(60);
    expect(result.current.lastLog!.endsWith('…')).toBe(true);
  });

  it('ignores events from a different session', () => {
    const startedAt = new Date().toISOString();
    const { result } = renderHook(() =>
      useSessionStream('s-1', { isActive: true, startedAt }),
    );

    act(() => {
      dispatchSessionEvent(
        't-1',
        mockEvent({ session_id: 's-2', payload: { text: 'other session' } }),
      );
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.lastLog).toBeNull();
  });

  it('captures terminal status from AGENT_COMPLETED', () => {
    const startedAt = new Date().toISOString();
    const { result } = renderHook(() =>
      useSessionStream('s-1', { isActive: true, startedAt }),
    );

    act(() => {
      dispatchSessionEvent(
        't-1',
        mockEvent({ type: 'AGENT_COMPLETED', payload: {} }),
      );
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.status).toBe('completed');
  });

  it('removes its listener on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = renderHook(() =>
      useSessionStream('s-1', { isActive: true, startedAt: null }),
    );
    unmount();
    expect(removeSpy).toHaveBeenCalledWith('kagan:session-event', expect.any(Function));
    removeSpy.mockRestore();
  });

  it('resets state when isActive flips to false', () => {
    const startedAt = new Date(Date.now() - 30_000).toISOString();
    const { result, rerender } = renderHook(
      ({ active }: { active: boolean }) =>
        useSessionStream('s-1', { isActive: active, startedAt }),
      { initialProps: { active: true } },
    );

    expect(result.current.elapsedSeconds).toBe(30);

    rerender({ active: false });

    expect(result.current).toEqual({ elapsedSeconds: 0, lastLog: null, status: null });
  });
});
