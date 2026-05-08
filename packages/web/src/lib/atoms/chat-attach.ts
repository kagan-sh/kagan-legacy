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
import { runningAgentsAtom } from '@/lib/atoms/running-agents';

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

export const cycleChatAttachAtom = atom(
  null,
  (get, set, direction: 1 | -1) => {
    const agents = get(runningAgentsAtom).agents;
    const current = get(chatAttachAtom);
    if (agents.length === 0) {
      if (current !== null) set(chatAttachAtom, null);
      return;
    }

    const sessionIds = agents.map((agent) => agent.session_id);
    const currentIndex =
      current === null ? -1 : sessionIds.indexOf(current.attachedSessionId);
    const currentState = currentIndex < 0 ? 0 : currentIndex + 1;
    const nextState = (currentState + direction + agents.length + 1) % (agents.length + 1);

    if (nextState === 0) {
      set(chatAttachAtom, null);
      return;
    }

    const agent = agents[nextState - 1]!;
    set(chatAttachAtom, {
      attachedSessionId: agent.session_id,
      taskTitle: agent.task_title,
      role: agent.agent_role === 'reviewer' ? 'reviewer' : 'worker',
      startedAt: agent.started_at,
      inputTokens: agent.input_tokens ?? null,
      outputTokens: agent.output_tokens ?? null,
    });
  },
);
