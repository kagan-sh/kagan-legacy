import { describe, it, expect } from 'vitest';
import { createStore } from 'jotai';
import {
  isStreamingAtom,
  streamEntriesAtom,
  appendStreamChunkAtom,
  addToolStartAtom,
  updateToolProgressAtom,
  addStreamErrorAtom,
  addStreamNoteAtom,
  resetStreamAtom,
  pendingQueueAtom,
  pendingQueueLengthAtom,
  enqueuePendingAtom,
  dequeuePendingAtom,
  clearPendingQueueAtom,
  PENDING_QUEUE_MAX,
} from '@/lib/atoms/chat';

describe('isStreamingAtom', () => {
  it('defaults to false', () => {
    const store = createStore();
    expect(store.get(isStreamingAtom)).toBe(false);
  });

  it('can be set to true', () => {
    const store = createStore();
    store.set(isStreamingAtom, true);
    expect(store.get(isStreamingAtom)).toBe(true);
  });

  it('can be reset to false', () => {
    const store = createStore();
    store.set(isStreamingAtom, true);
    store.set(isStreamingAtom, false);
    expect(store.get(isStreamingAtom)).toBe(false);
  });
});

describe('appendStreamChunkAtom (WV8: O(1) in-place merge)', () => {
  it('appends first chunk as new text entry', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'Hello' });
    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: 'text', content: 'Hello' });
  });

  it('merges consecutive text chunks into the last entry', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'Hello' });
    store.set(appendStreamChunkAtom, { content: ' world' });
    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: 'text', content: 'Hello world' });
  });

  it('appends new thought entry when kind changes', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'text' });
    store.set(appendStreamChunkAtom, { content: 'thought', thought: true });
    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(2);
    expect(entries[1]).toMatchObject({ kind: 'thought', content: 'thought' });
  });

  it('merges consecutive thought chunks', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'A', thought: true });
    store.set(appendStreamChunkAtom, { content: 'B', thought: true });
    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: 'thought', content: 'AB' });
  });
});

describe('addToolStartAtom', () => {
  it('adds a tool entry with running status', () => {
    const store = createStore();
    store.set(addToolStartAtom, { tool: 'bash' });
    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: 'tool', name: 'bash', status: 'running' });
  });
});

describe('updateToolProgressAtom', () => {
  it('marks the last matching tool entry as done', () => {
    const store = createStore();
    store.set(addToolStartAtom, { tool: 'bash' });
    store.set(updateToolProgressAtom, { tool: 'bash', status: 'done' });
    const entries = store.get(streamEntriesAtom);
    const tool = entries.find((e) => e.kind === 'tool');
    expect(tool).toMatchObject({ status: 'done' });
  });

});

describe('addStreamErrorAtom', () => {
  it('appends an error entry', () => {
    const store = createStore();
    store.set(addStreamErrorAtom, { message: 'oops' });
    const entries = store.get(streamEntriesAtom);
    expect(entries[0]).toMatchObject({ kind: 'error', message: 'oops' });
  });
});

describe('addStreamNoteAtom', () => {
  it('appends a note entry', () => {
    const store = createStore();
    store.set(addStreamNoteAtom, { message: 'note' });
    const entries = store.get(streamEntriesAtom);
    expect(entries[0]).toMatchObject({ kind: 'note', message: 'note' });
  });
});

describe('resetStreamAtom', () => {
  it('clears entries and sets streaming to false', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'hello' });
    store.set(isStreamingAtom, true);
    store.set(resetStreamAtom);
    expect(store.get(streamEntriesAtom)).toHaveLength(0);
    expect(store.get(isStreamingAtom)).toBe(false);
  });
});

// ── pendingQueueAtom ──────────────────────────────────────────────────────────

describe('pendingQueueAtom', () => {
  it('starts empty', () => {
    const store = createStore();
    expect(store.get(pendingQueueAtom)).toHaveLength(0);
    expect(store.get(pendingQueueLengthAtom)).toBe(0);
  });

  it('enqueue appends a message', () => {
    const store = createStore();
    const ok = store.set(enqueuePendingAtom, 'hello');
    expect(ok).toBe(true);
    expect(store.get(pendingQueueAtom)).toHaveLength(1);
    expect(store.get(pendingQueueAtom)[0]?.text).toBe('hello');
  });

  it('enqueue preserves attachments with the pending message', () => {
    const store = createStore();
    const ok = store.set(enqueuePendingAtom, {
      text: 'hello',
      attachments: [{ id: 'att-1', name: 'notes.txt', type: 'file', content: 'body' }],
    });
    expect(ok).toBe(true);
    expect(store.get(pendingQueueAtom)[0]).toMatchObject({
      text: 'hello',
      attachments: [{ name: 'notes.txt', type: 'file', content: 'body' }],
    });
  });

  it('dequeue returns attachments with the first pending message', () => {
    const store = createStore();
    store.set(enqueuePendingAtom, {
      text: 'first',
      attachments: [{ id: 'att-1', name: 'notes.txt', type: 'file', content: 'body' }],
    });
    const msg = store.set(dequeuePendingAtom);
    expect(msg).toMatchObject({
      text: 'first',
      attachments: [{ name: 'notes.txt', type: 'file', content: 'body' }],
    });
  });

  it('dequeue removes and returns the first message', () => {
    const store = createStore();
    store.set(enqueuePendingAtom, 'first');
    store.set(enqueuePendingAtom, 'second');
    const msg = store.set(dequeuePendingAtom);
    expect(msg?.text).toBe('first');
    expect(store.get(pendingQueueAtom)).toHaveLength(1);
    expect(store.get(pendingQueueAtom)[0]?.text).toBe('second');
  });

  it('dequeue returns null when queue is empty', () => {
    const store = createStore();
    const msg = store.set(dequeuePendingAtom);
    expect(msg).toBeNull();
  });

  it('clear empties the queue', () => {
    const store = createStore();
    store.set(enqueuePendingAtom, 'a');
    store.set(enqueuePendingAtom, 'b');
    store.set(clearPendingQueueAtom);
    expect(store.get(pendingQueueAtom)).toHaveLength(0);
  });

  it(`rejects enqueue when queue exceeds max depth of ${PENDING_QUEUE_MAX}`, () => {
    const store = createStore();
    for (let i = 0; i < PENDING_QUEUE_MAX; i++) {
      store.set(enqueuePendingAtom, `msg-${i}`);
    }
    const ok = store.set(enqueuePendingAtom, 'overflow');
    expect(ok).toBe(false);
    expect(store.get(pendingQueueAtom)).toHaveLength(PENDING_QUEUE_MAX);
  });
});
