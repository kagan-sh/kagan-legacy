import { atom } from 'jotai';
import type { WireChatMessage } from '@kagan/shared-api-client';

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

// Version counter: incremented whenever entries are mutated in-place so
// subscribers re-render without a full array copy.
export const streamVersionAtom = atom(0);

/**
 * Append a text chunk to the current streaming state.
 * When the last entry is the same kind, mutates it in-place and bumps
 * streamVersionAtom instead of spreading the array — O(1) per token.
 * When appending a new entry, a new array reference is set normally.
 */
export const appendStreamChunkAtom = atom(
  null,
  (get, set, payload: { content: string; thought?: boolean }) => {
    const entries = get(streamEntriesAtom);
    const kind = payload.thought ? 'thought' : 'text';
    const last = entries.at(-1);

    if (last && last.kind === kind) {
      // Mutate the last entry in-place — no array spread per token.
      (last as Extract<ChatStreamEntry, { kind: 'text' | 'thought' }>).content += payload.content;
      set(streamVersionAtom, (v) => v + 1);
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
 * Update the latest matching tool call entry in-place, bump version.
 */
export const updateToolProgressAtom = atom(
  null,
  (get, set, payload: { tool: string; status?: string }) => {
    const entries = get(streamEntriesAtom);
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
    // Entries array was mutated in-place; bump version for re-render.
    set(streamVersionAtom, (v) => v + 1);
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
  set(streamVersionAtom, 0);
  set(isStreamingAtom, false);
});

// ---------------------------------------------------------------------------
// Multi-client / watch state
// ---------------------------------------------------------------------------

/** Non-null when another client took over the session and interrupted this tab. */
export const takeoverBannerAtom = atom<string | null>(null);

/** Non-null when POST /stream returned 409 — holds the conflict details. */
export interface TurnConflict {
  runningSince: string;
  partialChars: number;
  /** The text the user wanted to send (so we can retry after interrupt). */
  pendingText: string;
  pendingAttachments?: unknown[];
}

export const turnConflictAtom = atom<TurnConflict | null>(null);
