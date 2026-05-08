import type { WireChatSessionSummary } from "@kagan/shared-api-client";

export interface StickyChatState {
  activeChatSessionId: string | null;
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
  };
}

// ── /switch helpers ────────────────────────────────────────────────────────

/** UUID v4 regex (full or 8-char prefix). */
const UUID_PREFIX_RE = /^[0-9a-f]{8}(?:-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?$/i;

/**
 * Parse the raw prompt argument of `/switch <id>`.
 *
 * Returns `{ id, kind }` when the token looks like a UUID or 8-char prefix,
 * or `null` when the prompt is blank / malformed.
 */
export function parseSwitchPrompt(prompt: string): { id: string; kind: "uuid-prefix" | "full-uuid" } | null {
  const token = prompt.trim();
  if (!token) return null;
  if (!UUID_PREFIX_RE.test(token)) return null;
  return { id: token, kind: token.length === 8 ? "uuid-prefix" : "full-uuid" };
}
