import { describe, it, expect } from 'vitest';
import { createStore } from 'jotai';
import {
  isStreamingAtom,
  streamEntriesAtom,
  streamVersionAtom,
  appendStreamChunkAtom,
  addToolStartAtom,
  updateToolProgressAtom,
  addStreamErrorAtom,
  addStreamNoteAtom,
  resetStreamAtom,
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

  it('merges consecutive text chunks in-place without a new array per token', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'Hello' });
    const refBefore = store.get(streamEntriesAtom);
    store.set(appendStreamChunkAtom, { content: ' world' });
    const entries = store.get(streamEntriesAtom);
    // Same array reference: in-place mutation path
    expect(entries).toBe(refBefore);
    expect(entries[0]).toMatchObject({ kind: 'text', content: 'Hello world' });
  });

  it('bumps streamVersionAtom on in-place merge', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'A' });
    const v0 = store.get(streamVersionAtom);
    store.set(appendStreamChunkAtom, { content: 'B' });
    expect(store.get(streamVersionAtom)).toBeGreaterThan(v0);
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

  it('bumps streamVersionAtom on progress update', () => {
    const store = createStore();
    store.set(addToolStartAtom, { tool: 'bash' });
    const v0 = store.get(streamVersionAtom);
    store.set(updateToolProgressAtom, { tool: 'bash', status: 'done' });
    expect(store.get(streamVersionAtom)).toBeGreaterThan(v0);
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
  it('clears entries, resets version, and sets streaming to false', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'hello' });
    store.set(isStreamingAtom, true);
    store.set(resetStreamAtom);
    expect(store.get(streamEntriesAtom)).toHaveLength(0);
    expect(store.get(streamVersionAtom)).toBe(0);
    expect(store.get(isStreamingAtom)).toBe(false);
  });
});
