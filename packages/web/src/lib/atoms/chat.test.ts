import { describe, it, expect } from 'vitest';
import { createStore } from 'jotai';
import {
  chatMessagesAtom,
  streamEntriesAtom,
  isStreamingAtom,
  appendStreamChunkAtom,
  addToolStartAtom,
  updateToolProgressAtom,
  addStreamErrorAtom,
  addStreamNoteAtom,
  resetStreamAtom,
} from '@/lib/atoms/chat';

describe('chat atoms', () => {
  it('keeps persisted chat messages independently from stream entries', () => {
    const store = createStore();
    store.set(chatMessagesAtom, [{ role: 'user', content: 'hello' }]);
    store.set(appendStreamChunkAtom, { content: 'leftover' });

    const messages = store.get(chatMessagesAtom);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toEqual({ role: 'user', content: 'hello' });
  });

  it('appendStreamChunkAtom merges consecutive text chunks', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'Hello ' });
    store.set(appendStreamChunkAtom, { content: 'world' });

    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({ kind: 'text', content: 'Hello world' });
  });

  it('appendStreamChunkAtom separates text and thought chunks', () => {
    const store = createStore();
    store.set(appendStreamChunkAtom, { content: 'text part' });
    store.set(appendStreamChunkAtom, { content: 'thinking...', thought: true });
    store.set(appendStreamChunkAtom, { content: 'more text' });

    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(3);
    expect(entries[0]).toEqual({ kind: 'text', content: 'text part' });
    expect(entries[1]).toEqual({ kind: 'thought', content: 'thinking...' });
    expect(entries[2]).toEqual({ kind: 'text', content: 'more text' });
  });

  it('addToolStartAtom adds a tool entry', () => {
    const store = createStore();
    store.set(addToolStartAtom, { tool: 'Read' });

    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    const first = entries[0]!;
    expect(first.kind).toBe('tool');
    if (first.kind === 'tool') {
      expect(first.name).toBe('Read');
      expect(first.status).toBe('running');
    }
  });

  it('updateToolProgressAtom updates the latest matching tool', () => {
    const store = createStore();
    store.set(addToolStartAtom, { tool: 'Read' });
    store.set(updateToolProgressAtom, { tool: 'Read', status: 'done' });

    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    const first = entries[0]!;
    if (first.kind === 'tool') {
      expect(first.status).toBe('done');
    }
  });

  it('addStreamErrorAtom adds an error entry', () => {
    const store = createStore();
    store.set(addStreamErrorAtom, { message: 'Something broke' });

    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({ kind: 'error', message: 'Something broke' });
  });

  it('addStreamNoteAtom adds a neutral note entry', () => {
    const store = createStore();
    store.set(addStreamNoteAtom, { message: 'Interrupted by user.' });

    const entries = store.get(streamEntriesAtom);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({ kind: 'note', message: 'Interrupted by user.' });
  });

  it('resetStreamAtom clears all stream state', () => {
    const store = createStore();
    store.set(isStreamingAtom, true);
    store.set(appendStreamChunkAtom, { content: 'data' });
    store.set(addToolStartAtom, { tool: 'Write' });

    store.set(resetStreamAtom);

    expect(store.get(streamEntriesAtom)).toHaveLength(0);
    expect(store.get(isStreamingAtom)).toBe(false);
  });

});
