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
  | { kind: 'thought'; content: string; startedAt: number }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done'; detail?: string }
  | { kind: 'note'; message: string }
  | { kind: 'error'; message: string };

export const streamEntriesAtom = atom<ChatStreamEntry[]>([]);
export const isStreamingAtom = atom(false);

export const appendStreamChunkAtom = atom(
  null,
  (get, set, payload: { content: string; thought?: boolean; startedAt?: number }) => {
    const entries = get(streamEntriesAtom);
    const kind = payload.thought ? 'thought' : 'text';
    const last = entries.at(-1);

    if (last && last.kind === kind) {
      const updated = entries.slice(0, -1);
      updated.push({ ...last, content: last.content + payload.content });
      set(streamEntriesAtom, updated);
    } else if (kind === 'thought') {
      const startedAt = payload.startedAt ?? Date.now();
      set(streamEntriesAtom, [...entries, { kind, content: payload.content, startedAt }]);
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

export const updateToolProgressAtom = atom(
  null,
  (get, set, payload: { tool: string; status?: string }) => {
    const entries = get(streamEntriesAtom);
    for (let i = entries.length - 1; i >= 0; i--) {
      const entry = entries[i]!;
      if (entry.kind === 'tool' && entry.name === payload.tool) {
        const updated = entries.slice();
        updated[i] = {
          ...entry,
          status: payload.status === 'done' ? 'done' : entry.status,
          detail: payload.status ?? entry.detail,
        };
        set(streamEntriesAtom, updated);
        return;
      }
    }
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

// ---------------------------------------------------------------------------
// Multi-turn message queue — messages submitted while the agent is streaming
// ---------------------------------------------------------------------------

/** Max messages allowed in the pending queue. */
export const PENDING_QUEUE_MAX = 10;

/** A single message waiting to be sent after the current stream completes. */
export interface PendingMessage {
  id: string;
  text: string;
}

/** Queue of messages submitted while the agent was streaming. Drained FIFO. */
export const pendingQueueAtom = atom<PendingMessage[]>([]);

/** Derived read: number of items in the queue. */
export const pendingQueueLengthAtom = atom((get) => get(pendingQueueAtom).length);

/** Append a message to the queue. No-op if the queue is already at max depth. */
export const enqueuePendingAtom = atom(
  null,
  (get, set, text: string): boolean => {
    const queue = get(pendingQueueAtom);
    if (queue.length >= PENDING_QUEUE_MAX) return false;
    const id = `pq-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    set(pendingQueueAtom, [...queue, { id, text }]);
    return true;
  },
);

/** Remove and return the first item from the queue, or null if empty. */
export const dequeuePendingAtom = atom(
  null,
  (get, set): PendingMessage | null => {
    const queue = get(pendingQueueAtom);
    if (queue.length === 0) return null;
    const [first, ...rest] = queue;
    set(pendingQueueAtom, rest);
    return first ?? null;
  },
);

/** Clear the entire pending queue. */
export const clearPendingQueueAtom = atom(null, (_get, set) => {
  set(pendingQueueAtom, []);
});
