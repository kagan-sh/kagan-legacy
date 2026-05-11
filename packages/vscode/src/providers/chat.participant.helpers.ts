import type { SessionItemResponse } from "@kagan/shared-api-client";

export interface StickyChatState {
  activeRawChatSessionId: string | null;
}

export function pickReusableOrchestratorSession(
  globalSessionId: string | undefined,
  sessions: SessionItemResponse[],
): SessionItemResponse | null {
  const orchestratorSessions = sessions.filter((session) => session.type === "orchestrator");
  const trimmedGlobalSessionId = globalSessionId?.trim();
  if (
    trimmedGlobalSessionId
  ) {
    const saved = orchestratorSessions.find((session) =>
      session.id.trim() === trimmedGlobalSessionId ||
      session.chat_session_id?.trim() === trimmedGlobalSessionId
    );
    if (saved) return saved;
  }
  return orchestratorSessions[0] ?? null;
}

export function resetStickyChatStateIfNewConversation(
  state: StickyChatState,
  chatCtx: { history: ArrayLike<unknown> },
): StickyChatState {
  if (chatCtx.history.length > 0) {
    return state;
  }
  return {
    activeRawChatSessionId: null,
  };
}

// ── /switch helpers ────────────────────────────────────────────────────────

const SCOPED_SWITCH_RE = /^(orch|gen|task):[A-Za-z0-9][A-Za-z0-9_-]*$/;
const RAW_SWITCH_RE = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;

/**
 * Parse the raw prompt argument of `/switch <id>`.
 *
 * Accepts displayed unified tokens (`orch:<prefix>`, `gen:<prefix>`,
 * `task:<prefix>`) and raw prefixes for older output that did not include the
 * session kind.
 */
export function parseSwitchPrompt(prompt: string): { id: string; kind: "scoped-prefix" | "raw-prefix" } | null {
  const token = prompt.trim();
  if (!token) return null;
  if (SCOPED_SWITCH_RE.test(token)) return { id: token, kind: "scoped-prefix" };
  if (RAW_SWITCH_RE.test(token)) return { id: token, kind: "raw-prefix" };
  return null;
}

export function switchTokenForSession(session: Pick<SessionItemResponse, "id">): string {
  const [scope, raw] = splitScopedId(session.id);
  if (!scope) return session.id.slice(0, 8);
  return `${scope}:${raw.slice(0, 8)}`;
}

export function resolveSwitchSession(
  sessions: SessionItemResponse[],
  token: string,
): SessionItemResponse | null {
  const parsed = parseSwitchPrompt(token);
  if (!parsed) return null;

  const lower = parsed.id.toLowerCase();
  if (parsed.kind === "scoped-prefix") {
    return sessions.find((session) => session.id.toLowerCase().startsWith(lower)) ?? null;
  }

  return sessions.find((session) => rawSwitchCandidates(session).some((candidate) =>
    candidate.toLowerCase().startsWith(lower)
  )) ?? null;
}

function rawSwitchCandidates(session: SessionItemResponse): string[] {
  const [, rawId] = splitScopedId(session.id);
  return [
    rawId,
    session.chat_session_id,
    session.session_id,
    session.task_id,
  ].filter((value): value is string => Boolean(value));
}

function splitScopedId(id: string): [scope: string | null, raw: string] {
  const match = /^(orch|gen|task):(.+)$/.exec(id);
  if (!match) return [null, id];
  return [match[1], match[2]];
}
