import { atom } from 'jotai';
import type { WireChatMessage } from '@/lib/api/types';

// ---------------------------------------------------------------------------
// Persisted history (loaded on session open, refreshed on CHAT_DONE)
// ---------------------------------------------------------------------------

export const chatMessagesAtom = atom<WireChatMessage[]>([]);

// ---------------------------------------------------------------------------
// Stream entries — rich real-time events (tool calls, thinking, text)
// ---------------------------------------------------------------------------

export type ChatStreamEntry =
  | { kind: 'text'; content: string }
  | { kind: 'thought'; content: string }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done'; detail?: string }
  | { kind: 'note'; message: string }
  | { kind: 'error'; message: string };

export const streamEntriesAtom = atom<ChatStreamEntry[]>([]);
export const isStreamingAtom = atom(false);

/**
 * Append a text chunk to the current streaming state.
 * Merges with the last entry if both are the same kind.
 */
export const appendStreamChunkAtom = atom(
  null,
  (get, set, payload: { content: string; thought?: boolean }) => {
    const entries = get(streamEntriesAtom);
    const kind = payload.thought ? 'thought' : 'text';
    const last = entries.at(-1);

    if (last && last.kind === kind) {
      // Merge into the last entry of the same kind
      const updated = [...entries];
      updated[updated.length - 1] = { ...last, content: last.content + payload.content };
      set(streamEntriesAtom, updated);
    } else {
      set(streamEntriesAtom, [...entries, { kind, content: payload.content }]);
    }
  },
);

/**
 * Record a tool call start event.
 */
export const addToolStartAtom = atom(
  null,
  (get, set, payload: { tool: string }) => {
    const id = `tool-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    set(streamEntriesAtom, [
      ...get(streamEntriesAtom),
      { kind: 'tool' as const, id, name: payload.tool, status: 'running' as const },
    ]);
  },
);

/**
 * Update the latest matching tool call entry.
 */
export const updateToolProgressAtom = atom(
  null,
  (get, set, payload: { tool: string; status?: string }) => {
    const entries = [...get(streamEntriesAtom)];
    // Find the last tool entry with matching name
    for (let i = entries.length - 1; i >= 0; i--) {
      const entry = entries[i]!;
      if (entry.kind === 'tool' && entry.name === payload.tool) {
        entries[i] = {
          ...entry,
          status: (payload.status === 'done' ? 'done' : entry.status),
          detail: payload.status ?? entry.detail,
        };
        break;
      }
    }
    set(streamEntriesAtom, entries);
  },
);

/**
 * Record an error event.
 */
export const addStreamErrorAtom = atom(
  null,
  (get, set, payload: { message: string }) => {
    set(streamEntriesAtom, [
      ...get(streamEntriesAtom),
      { kind: 'error' as const, message: payload.message },
    ]);
  },
);

export const addStreamNoteAtom = atom(
  null,
  (get, set, payload: { message: string }) => {
    set(streamEntriesAtom, [
      ...get(streamEntriesAtom),
      { kind: 'note' as const, message: payload.message },
    ]);
  },
);

/**
 * Reset all streaming state.
 */
export const resetStreamAtom = atom(null, (_get, set) => {
  set(streamEntriesAtom, []);
  set(isStreamingAtom, false);
});
