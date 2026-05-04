import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRafBatchedMessage } from '@/lib/streaming-message';

// ---------------------------------------------------------------------------
// Deterministic RAF mock — executes callbacks synchronously when flushed.
// ---------------------------------------------------------------------------

let rafCallbacks: FrameRequestCallback[] = [];
let rafId = 0;

function mockRaf(cb: FrameRequestCallback): number {
  rafCallbacks.push(cb);
  return ++rafId;
}

function mockCancelRaf(id: number) {
  // Filter by id to cancel; for simplicity we just clear by position since
  // the hook only ever holds one pending id.
  rafCallbacks = rafCallbacks.filter((_, i) => i !== id - 1);
}

function flushRaf() {
  const cbs = [...rafCallbacks];
  rafCallbacks = [];
  for (const cb of cbs) cb(performance.now());
}

beforeEach(() => {
  rafCallbacks = [];
  rafId = 0;
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(mockRaf);
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(mockCancelRaf);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useRafBatchedMessage', () => {
  it('initialises with the provided text', () => {
    const { result } = renderHook(() => useRafBatchedMessage('hello'));
    const [displayText] = result.current;
    expect(displayText).toBe('hello');
  });

  it('coalesces multiple append calls in one frame into a single state update', () => {
    const { result } = renderHook(() => useRafBatchedMessage(''));

    // Append three tokens without flushing RAF between them.
    act(() => {
      const [, append] = result.current;
      append('foo');
      append('bar');
      append('baz');
    });

    // Before flush: displayText has not changed yet.
    expect(result.current[0]).toBe('');

    // After flush: all three deltas coalesced into one update.
    act(() => {
      flushRaf();
    });

    expect(result.current[0]).toBe('foobarbaz');
  });

  it('accumulates text across multiple frames', () => {
    const { result } = renderHook(() => useRafBatchedMessage(''));

    act(() => {
      const [, append] = result.current;
      append('frame1');
    });
    act(() => { flushRaf(); });
    expect(result.current[0]).toBe('frame1');

    act(() => {
      const [, append] = result.current;
      append(' frame2');
    });
    act(() => { flushRaf(); });
    expect(result.current[0]).toBe('frame1 frame2');
  });

  it('cancels pending RAF on unmount', () => {
    const { result, unmount } = renderHook(() => useRafBatchedMessage(''));

    act(() => {
      const [, append] = result.current;
      append('pending');
    });

    // At this point a RAF is queued but not flushed.
    expect(rafCallbacks.length).toBe(1);

    // Unmount should cancel the pending RAF.
    unmount();

    expect(window.cancelAnimationFrame).toHaveBeenCalled();
  });

  it('only queues one RAF when append is called multiple times before a flush', () => {
    const { result } = renderHook(() => useRafBatchedMessage(''));

    act(() => {
      const [, append] = result.current;
      append('a');
      append('b');
      append('c');
    });

    // Only one RAF should be queued regardless of append call count.
    expect(window.requestAnimationFrame).toHaveBeenCalledTimes(1);
  });
});
