import { describe, expect, it } from 'vitest';

import {
  addError,
  addNote,
  addToolStart,
  appendChunk,
  asChatStreamMessage,
  CHAT_STREAM_EVENT,
  updateToolProgress,
} from './use-chat-stream';
import type { ChatStreamEntry } from '@/lib/atoms/chat';

describe('useChatStream pure reducers', () => {
  describe('appendChunk', () => {
    it('starts a new text entry when entries are empty', () => {
      const result = appendChunk([], { content: 'hello' });
      expect(result).toEqual([{ kind: 'text', content: 'hello' }]);
    });

    it('appends to the last entry when kinds match', () => {
      const start: ChatStreamEntry[] = [{ kind: 'text', content: 'hello ' }];
      const result = appendChunk(start, { content: 'world' });
      expect(result).toEqual([{ kind: 'text', content: 'hello world' }]);
    });

    it('starts a new thought entry when transitioning from text', () => {
      const start: ChatStreamEntry[] = [{ kind: 'text', content: 'hi' }];
      const result = appendChunk(start, { content: 'thinking…', thought: true });
      expect(result).toHaveLength(2);
      expect(result[1]).toEqual({ kind: 'thought', content: 'thinking…' });
    });

    it('does not mutate the original array', () => {
      const start: ChatStreamEntry[] = [{ kind: 'text', content: 'hi' }];
      appendChunk(start, { content: ' there' });
      expect(start).toEqual([{ kind: 'text', content: 'hi' }]);
    });
  });

  describe('addToolStart', () => {
    it('appends a running tool entry with a unique id', () => {
      const result = addToolStart([], 'shell');
      expect(result).toHaveLength(1);
      const entry = result[0]!;
      expect(entry.kind).toBe('tool');
      if (entry.kind === 'tool') {
        expect(entry.name).toBe('shell');
        expect(entry.status).toBe('running');
        expect(entry.id).toMatch(/^tool-/);
      }
    });
  });

  describe('updateToolProgress', () => {
    it('marks the matching running tool as done when status is "done"', () => {
      const start: ChatStreamEntry[] = [
        { kind: 'tool', id: 'tool-1', name: 'shell', status: 'running' },
      ];
      const result = updateToolProgress(start, { tool: 'shell', status: 'done' });
      expect(result[0]).toMatchObject({ kind: 'tool', status: 'done', detail: 'done' });
    });

    it('updates only the matching tool by name', () => {
      const start: ChatStreamEntry[] = [
        { kind: 'tool', id: 'tool-1', name: 'shell', status: 'running' },
        { kind: 'tool', id: 'tool-2', name: 'web_search', status: 'running' },
      ];
      const result = updateToolProgress(start, { tool: 'web_search', status: 'fetching' });
      expect(result[0]).toMatchObject({ name: 'shell' });
      expect(result[0] as { detail?: string }).not.toHaveProperty('detail');
      expect(result[1]).toMatchObject({ name: 'web_search', detail: 'fetching' });
    });

    it('updates the most recent matching tool when there are duplicates', () => {
      const start: ChatStreamEntry[] = [
        { kind: 'tool', id: 'tool-1', name: 'shell', status: 'running' },
        { kind: 'tool', id: 'tool-2', name: 'shell', status: 'running' },
      ];
      const result = updateToolProgress(start, { tool: 'shell', status: 'done' });
      expect(result[0]).toMatchObject({ id: 'tool-1', status: 'running' });
      expect(result[1]).toMatchObject({ id: 'tool-2', status: 'done' });
    });

    it('is a no-op when the tool is not in entries', () => {
      const start: ChatStreamEntry[] = [{ kind: 'text', content: 'hi' }];
      const result = updateToolProgress(start, { tool: 'shell', status: 'done' });
      expect(result).toEqual(start);
    });
  });

  describe('addNote', () => {
    it('appends a note entry without disturbing earlier entries', () => {
      const start: ChatStreamEntry[] = [{ kind: 'text', content: 'hi' }];
      const result = addNote(start, 'reconnected');
      expect(result).toEqual([
        { kind: 'text', content: 'hi' },
        { kind: 'note', message: 'reconnected' },
      ]);
    });
  });

  describe('addError', () => {
    it('appends an error entry', () => {
      const result = addError([], 'boom');
      expect(result).toEqual([{ kind: 'error', message: 'boom' }]);
    });
  });
});

describe('asChatStreamMessage field validation', () => {
  it('returns null for unknown event type', () => {
    expect(asChatStreamMessage({ t: 'UNKNOWN' })).toBeNull();
  });

  it('returns null when t is not a string', () => {
    expect(asChatStreamMessage({ t: 42 })).toBeNull();
  });

  it('rejects CHAT_CHUNK when content is a number instead of string', () => {
    expect(asChatStreamMessage({ t: CHAT_STREAM_EVENT.CHUNK, content: 42 })).toBeNull();
  });

  it('rejects CHAT_CHUNK when thought is a string instead of boolean', () => {
    expect(asChatStreamMessage({ t: CHAT_STREAM_EVENT.CHUNK, content: 'hi', thought: 'yes' })).toBeNull();
  });

  it('accepts CHAT_CHUNK with valid string content', () => {
    const msg = asChatStreamMessage({ t: CHAT_STREAM_EVENT.CHUNK, content: 'hello' });
    expect(msg).not.toBeNull();
    expect(msg?.t).toBe(CHAT_STREAM_EVENT.CHUNK);
  });

  it('rejects CHAT_TOOL_START when tool is not a string', () => {
    expect(asChatStreamMessage({ t: CHAT_STREAM_EVENT.TOOL_START, tool: 99 })).toBeNull();
  });

  it('accepts CHAT_DONE with no extra fields', () => {
    const msg = asChatStreamMessage({ t: CHAT_STREAM_EVENT.DONE });
    expect(msg?.t).toBe(CHAT_STREAM_EVENT.DONE);
  });

  it('rejects CHAT_SESSION_UPDATED when label is a number', () => {
    expect(asChatStreamMessage({ t: CHAT_STREAM_EVENT.SESSION_UPDATED, label: 123 })).toBeNull();
  });
});
