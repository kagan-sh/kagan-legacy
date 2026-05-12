/**
 * useEntryStream unit tests.
 *
 * Uses a hand-rolled EventSource stub — no `eventsourcemock` npm dependency
 * needed.  The stub captures the last instantiated EventSource and exposes
 * helpers to fire named events and trigger onerror.
 *
 * vi.mock hoisting rule: factory functions must NOT reference outer-scope
 * variables (vitest hoists vi.mock() calls to the top of the file before
 * imports are evaluated).
 */

import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FrameEntry } from '@kagan/shared-api-client';

// ---------------------------------------------------------------------------
// EventSource stub
// ---------------------------------------------------------------------------

type ESListener = (e: MessageEvent) => void;
type ESErrorListener = (e: Event) => void;

class StubEventSource {
  static instances: StubEventSource[] = [];

  readonly url: string;
  readonly withCredentials: boolean;

  private listeners: Record<string, ESListener[]> = {};
  onerror: ESErrorListener | null = null;
  closed = false;

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = init?.withCredentials ?? false;
    StubEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: ESListener): void {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type]!.push(handler);
  }

  removeEventListener(type: string, handler: ESListener): void {
    if (!this.listeners[type]) return;
    this.listeners[type] = this.listeners[type]!.filter((h) => h !== handler);
  }

  close(): void {
    this.closed = true;
  }

  // --- test helpers ---

  emit(type: string, data: unknown): void {
    const handlers = this.listeners[type] ?? [];
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    for (const h of handlers) h(event);
  }

  triggerError(): void {
    this.onerror?.(new Event('error'));
  }

  static latest(): StubEventSource {
    const inst = StubEventSource.instances.at(-1);
    if (!inst) throw new Error('No StubEventSource instances');
    return inst;
  }

  static reset(): void {
    StubEventSource.instances = [];
  }
}

// Replace the global EventSource with our stub before each test.
beforeEach(() => {
  StubEventSource.reset();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).EventSource = StubEventSource;
});

afterEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (globalThis as any).EventSource;
});

// ---------------------------------------------------------------------------
// Import hook AFTER stub setup is in place (vitest runs imports lazily here).
// ---------------------------------------------------------------------------

// We import dynamically inside each test block would be awkward, so we use a
// top-level import and rely on the globalThis.EventSource assignment happening
// before the hook is invoked (which it does — assignment is in beforeEach and
// the hook only accesses EventSource at effect time, not import time).
import { useEntryStream } from './use-entry-stream';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEntry(idx: number, text = '', finalized = false): FrameEntry {
  return { idx, role: 'assistant', text, finalized, ts: '2026-01-01T00:00:00Z' };
}

function snapshotFrame(entries: FrameEntry[]) {
  return { type: 'snapshot', kind: 'chat', session_id: 's1', from_seq: 0, to_seq: 0, entries };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useEntryStream', () => {
  const TEST_URL = '/api/sessions/s1/events';

  it('replaces entries on snapshot event', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    act(() => {
      StubEventSource.latest().emit('snapshot', snapshotFrame([
        makeEntry(0, 'hello'),
        makeEntry(1, 'world'),
      ]));
    });

    expect(result.current.entries.size).toBe(2);
    expect(result.current.entries.get(0)?.text).toBe('hello');
    expect(result.current.entries.get(1)?.text).toBe('world');
  });

  it('flips isReady on ready event', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    expect(result.current.isReady).toBe(false);

    act(() => {
      StubEventSource.latest().emit('snapshot', snapshotFrame([]));
    });
    expect(result.current.isReady).toBe(false);

    act(() => {
      StubEventSource.latest().emit('ready', { type: 'ready' });
    });
    expect(result.current.isReady).toBe(true);
  });

  it('isLive becomes true only after ready', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    expect(result.current.isLive).toBe(false);

    act(() => {
      StubEventSource.latest().emit('snapshot', snapshotFrame([]));
    });
    expect(result.current.isLive).toBe(false);

    act(() => {
      StubEventSource.latest().emit('ready', { type: 'ready' });
    });
    expect(result.current.isLive).toBe(true);
  });

  it('applies create patch by parsing path idx', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    act(() => {
      StubEventSource.latest().emit('patch', {
        type: 'patch',
        op: 'create',
        path: '/entries/3',
        value: makeEntry(3, 'created'),
      });
    });

    expect(result.current.entries.get(3)?.text).toBe('created');
  });

  it('applies append patch appending to existing entry text', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    act(() => {
      StubEventSource.latest().emit('patch', {
        op: 'create',
        path: '/entries/0',
        value: makeEntry(0, 'Hello'),
      });
    });

    act(() => {
      StubEventSource.latest().emit('patch', {
        op: 'append',
        path: '/entries/0/text',
        value: ', world',
      });
    });

    expect(result.current.entries.get(0)?.text).toBe('Hello, world');
  });

  it('applies finalize patch marking entry finalized', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    act(() => {
      StubEventSource.latest().emit('patch', {
        op: 'create',
        path: '/entries/0',
        value: makeEntry(0, 'done'),
      });
    });

    expect(result.current.entries.get(0)?.finalized).toBe(false);

    act(() => {
      StubEventSource.latest().emit('patch', {
        op: 'finalize',
        path: '/entries/0',
      });
    });

    expect(result.current.entries.get(0)?.finalized).toBe(true);
  });

  it('warns on append before create', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    act(() => {
      StubEventSource.latest().emit('patch', {
        op: 'append',
        path: '/entries/99/text',
        value: 'orphan',
      });
    });

    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('append before create'),
    );
    expect(result.current.entries.has(99)).toBe(false);
    warn.mockRestore();
  });

  it('captures resume notice with turnActive flag', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    expect(result.current.resumeNotice).toBeUndefined();

    act(() => {
      StubEventSource.latest().emit('resume', {
        type: 'resume',
        kind: 'chat',
        turn_active: true,
      });
    });

    expect(result.current.resumeNotice).toEqual({ turnActive: true });
  });

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useEntryStream({ url: TEST_URL }));
    const es = StubEventSource.latest();

    expect(es.closed).toBe(false);
    unmount();
    expect(es.closed).toBe(true);
  });

  it('re-opens EventSource on url change', () => {
    const { rerender } = renderHook(
      ({ url }: { url: string }) => useEntryStream({ url }),
      { initialProps: { url: '/api/sessions/s1/events' } },
    );

    expect(StubEventSource.instances).toHaveLength(1);

    rerender({ url: '/api/sessions/s2/events' });

    expect(StubEventSource.instances).toHaveLength(2);
    expect(StubEventSource.instances[0]!.closed).toBe(true);
    expect(StubEventSource.instances[1]!.url).toBe('/api/sessions/s2/events');
  });

  it('idempotent re-apply of same path does not double-append text when seq monotonic guarded', () => {
    // Simulate a resume window where the same 'create' patch arrives twice.
    // Under normal Last-Event-ID operation the server won't replay, but if it
    // does the spec says we trust server seq monotonicity — the test documents
    // that a double-create (same idx) simply overwrites the entry.
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    const entry = makeEntry(0, 'original');
    act(() => {
      StubEventSource.latest().emit('patch', { op: 'create', path: '/entries/0', value: entry });
    });
    act(() => {
      StubEventSource.latest().emit('patch', { op: 'create', path: '/entries/0', value: { ...entry, text: 'overwritten' } });
    });

    // Second create overwrites — no duplication.
    expect(result.current.entries.get(0)?.text).toBe('overwritten');
    expect(result.current.entries.size).toBe(1);
  });

  it('sets error and isLive false on onerror', () => {
    const { result } = renderHook(() => useEntryStream({ url: TEST_URL }));

    // First bring it live.
    act(() => {
      StubEventSource.latest().emit('snapshot', snapshotFrame([]));
      StubEventSource.latest().emit('ready', { type: 'ready' });
    });
    expect(result.current.isLive).toBe(true);

    act(() => {
      StubEventSource.latest().triggerError();
    });

    expect(result.current.isLive).toBe(false);
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('does not open EventSource when enabled is false', () => {
    renderHook(() => useEntryStream({ url: TEST_URL, enabled: false }));
    expect(StubEventSource.instances).toHaveLength(0);
  });
});
