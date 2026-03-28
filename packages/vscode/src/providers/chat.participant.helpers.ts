import type { WireChatSession } from "../api/types.js";

export function isTaskSession(session: Pick<WireChatSession, "source"> | null | undefined): boolean {
  return (session?.source ?? "").trim().toLowerCase() === "task-session";
}

export function pickReusableChatSessionId(
  globalSessionId: string | undefined,
  sessions: WireChatSession[],
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
