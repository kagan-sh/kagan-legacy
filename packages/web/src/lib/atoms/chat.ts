import { atom } from 'jotai';

/**
 * Shared streaming indicator. Written by ChatPage / OrchestratorChatPanel when
 * an SSE turn is active; read by ChatInputBar (a sibling tree) to disable the
 * send button and show the interrupt affordance.
 *
 * All other chat state (messages, stream entries, action helpers) lives in
 * component-local useState so it doesn't pollute the global atom graph.
 */
export const isStreamingAtom = atom(false);

// ---------------------------------------------------------------------------
// Stream entry type — shared between ChatPage, OrchestratorChatPanel, and
// the ChatStreamEntries renderer.
// ---------------------------------------------------------------------------

export type ChatStreamEntry =
  | { kind: 'text'; content: string }
  | { kind: 'thought'; content: string }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done'; detail?: string }
  | { kind: 'note'; message: string }
  | { kind: 'error'; message: string };
