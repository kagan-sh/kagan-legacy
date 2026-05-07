import type { ActiveAgentRowResponse, WireChatSessionSummary } from "@kagan/shared-api-client";

export interface StickyChatState {
  activeChatSessionId: string | null;
  watchingTaskId: string | null;
}

export function isTaskSession(session: Pick<WireChatSessionSummary, "source"> | null | undefined): boolean {
  return (session?.source ?? "").trim().toLowerCase() === "task-session";
}

export function pickReusableChatSessionId(
  globalSessionId: string | undefined,
  sessions: WireChatSessionSummary[],
): string | null {
  const orchestratorSessions = sessions.filter((session) => !isTaskSession(session));
  const trimmedGlobalSessionId = globalSessionId?.trim();
  if (
    trimmedGlobalSessionId &&
    orchestratorSessions.some((session) => session.id.trim() === trimmedGlobalSessionId)
  ) {
    return trimmedGlobalSessionId;
  }
  return orchestratorSessions[0]?.id?.trim() || null;
}

export function resetStickyChatStateIfNewConversation(
  state: StickyChatState,
  chatCtx: { history: ArrayLike<unknown> },
): StickyChatState {
  if (chatCtx.history.length > 0) {
    return state;
  }
  return {
    activeChatSessionId: null,
    watchingTaskId: null,
  };
}

// ── /attach helpers ────────────────────────────────────────────────────────

/** UUID v4 regex (full or 8-char prefix). */
const UUID_PREFIX_RE = /^[0-9a-f]{8}(?:-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?$/i;

/**
 * Parse the raw prompt argument of `/attach <id>`.
 *
 * Returns `{ id, kind }` when the token looks like a UUID or 8-char prefix,
 * or `null` when the prompt is blank / malformed.
 */
export function parseAttachPrompt(prompt: string): { id: string; kind: "uuid-prefix" | "full-uuid" } | null {
  const token = prompt.trim();
  if (!token) return null;
  if (!UUID_PREFIX_RE.test(token)) return null;
  return { id: token, kind: token.length === 8 ? "uuid-prefix" : "full-uuid" };
}

/**
 * Given a raw id token and the list of running agents, resolve to a session id.
 *
 * Matching priority:
 *  1. Exact session_id match.
 *  2. session_id starts-with prefix (8-char shorthand).
 *  3. task_id exact match.
 *  4. task_id starts-with prefix.
 *
 * Returns `null` when nothing matches.
 */
export function resolveAgentSessionId(
  id: string,
  agents: ActiveAgentRowResponse[],
): string | null {
  const lower = id.toLowerCase();

  // Exact session match
  const exactSession = agents.find((a) => a.session_id.toLowerCase() === lower);
  if (exactSession) return exactSession.session_id;

  // Prefix session match
  const prefixSession = agents.find((a) => a.session_id.toLowerCase().startsWith(lower));
  if (prefixSession) return prefixSession.session_id;

  // Exact task match
  const exactTask = agents.find((a) => a.task_id.toLowerCase() === lower);
  if (exactTask) return exactTask.session_id;

  // Prefix task match
  const prefixTask = agents.find((a) => a.task_id.toLowerCase().startsWith(lower));
  if (prefixTask) return prefixTask.session_id;

  return null;
}
