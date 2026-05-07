/**
 * Chat attach atom — tracks which agent session (if any) is attached in the
 * orchestrator overlay.
 *
 * Transitions:
 *   null            → orchestrator mode (default)
 *   { sessionId }   → attached to worker or reviewer stream
 *
 * The URL query param `?chat=task:<taskId>:<sessionId>` is the external source
 * of truth on page load; the app-layout reads it and calls attachChatSessionAtom.
 */

import { atom } from 'jotai';

export type ChatAttachRole = 'worker' | 'reviewer';

export interface ChatAttachTarget {
  /** The running agent session ID being observed. */
  attachedSessionId: string;
  /** Human-readable task title (for breadcrumb). */
  taskTitle: string;
  /** Agent role. */
  role: ChatAttachRole;
  /** ISO timestamp from ActiveAgentRowResponse.started_at */
  startedAt: string;
  /** Input tokens (may be null for new sessions). */
  inputTokens: number | null;
  /** Output tokens (may be null for new sessions). */
  outputTokens: number | null;
}

/** Null → orchestrator mode.  Non-null → attached to agent stream. */
export const chatAttachAtom = atom<ChatAttachTarget | null>(null);

/** Attach to an agent session. */
export const attachChatSessionAtom = atom(
  null,
  (_get, set, target: ChatAttachTarget) => {
    set(chatAttachAtom, target);
  },
);

/** Detach and return to orchestrator mode. */
export const detachChatSessionAtom = atom(null, (_get, set) => {
  set(chatAttachAtom, null);
});
