import { describe, expect, it } from "vitest";
import type { WireChatSessionSummary } from "@kagan/shared-api-client";
import {
  isTaskSession,
  pickReusableChatSessionId,
  resetStickyChatStateIfNewConversation,
} from "./chat.participant.helpers.js";

function makeSession(id: string, source: string): WireChatSessionSummary {
  return { id, label: "", source, agent_backend: null, updated_at: "", message_count: 0 };
}

describe("chat participant helpers", () => {
  it("treats task-session sources as task-scoped", () => {
    expect(isTaskSession({ source: "task-session" })).toBe(true);
    expect(isTaskSession({ source: "TASK-SESSION" })).toBe(true);
    expect(isTaskSession({ source: "vscode" })).toBe(false);
  });

  it("reuses the saved session only when it is not task-scoped", () => {
    const sessionId = pickReusableChatSessionId("orch-1", [
      makeSession("task-1", "task-session"),
      makeSession("orch-1", "vscode"),
    ]);

    expect(sessionId).toBe("orch-1");
  });

  it("ignores a saved task session and falls back to the latest orchestrator session", () => {
    const sessionId = pickReusableChatSessionId("task-1", [
      makeSession("task-1", "task-session"),
      makeSession("orch-2", "vscode"),
      makeSession("orch-1", "web"),
    ]);

    expect(sessionId).toBe("orch-2");
  });

  it("returns null when no orchestrator sessions exist", () => {
    const sessionId = pickReusableChatSessionId("task-1", [
      makeSession("task-1", "task-session"),
    ]);

    expect(sessionId).toBeNull();
  });

  it("clears sticky watch state for a fresh conversation", () => {
    const nextState = resetStickyChatStateIfNewConversation(
      { activeChatSessionId: "orch-1", watchingTaskId: "task-1" },
      { history: [] },
    );

    expect(nextState).toEqual({
      activeChatSessionId: null,
      watchingTaskId: null,
    });
  });

  it("preserves sticky watch state when the conversation already has history", () => {
    const state = { activeChatSessionId: "orch-1", watchingTaskId: "task-1" };
    const nextState = resetStickyChatStateIfNewConversation(state, {
      history: [{}],
    });

    expect(nextState).toEqual(state);
  });
});
