import type { Attachment } from '@/lib/chat-attachments';

// ---------------------------------------------------------------------------
// Stream entries — rich real-time events (tool calls, thinking, text)
// ---------------------------------------------------------------------------

export type ChatStreamEntry =
  | { kind: 'text'; content: string }
  | { kind: 'thought'; content: string; startedAt: number }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done' | 'failed'; detail?: string; args: Record<string, unknown> | null; startedAt: number }
  | { kind: 'note'; message: string }
  | { kind: 'error'; message: string }
  /** A collapsible "Worked for Ns" accordion grouping a batch of tool steps. */
  | { kind: 'worked'; label: string; steps: string[]; done: boolean; startedAt: number }
  /** A list of filenames changed during the agent's last action. */
  | { kind: 'files'; items: string[] };

// ---------------------------------------------------------------------------
// Multi-client / watch state
// ---------------------------------------------------------------------------

/** Non-null when another client took over the session and interrupted this tab. */
export interface TurnConflict {
  runningSince: string;
  partialChars: number;
  /** The text the user wanted to send (so we can retry after interrupt). */
  pendingText: string;
  pendingAttachments?: Attachment[];
}

// ---------------------------------------------------------------------------
// Multi-turn message queue — messages submitted while the agent is streaming
// ---------------------------------------------------------------------------

/** Max messages allowed in the pending queue. */
export const PENDING_QUEUE_MAX = 10;

/** A single message waiting to be sent after the current stream completes. */
export interface PendingMessage {
  id: string;
  text: string;
  attachments?: Attachment[];
}

export interface PendingMessageInput {
  text: string;
  attachments?: Attachment[];
}
