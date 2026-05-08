import { describe, expect, it } from "vitest";
import type { WireChatSessionSummary } from "@kagan/shared-api-client";
import {
  isTaskSession,
  pickReusableChatSessionId,
  resetStickyChatStateIfNewConversation,
  parseSwitchPrompt,
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

  it("clears sticky state for a fresh conversation", () => {
    const nextState = resetStickyChatStateIfNewConversation(
      { activeChatSessionId: "orch-1" },
      { history: [] },
    );

    expect(nextState).toEqual({
      activeChatSessionId: null,
    });
  });

  it("preserves sticky state when the conversation already has history", () => {
    const state = { activeChatSessionId: "orch-1" };
    const nextState = resetStickyChatStateIfNewConversation(state, {
      history: [{}],
    });

    expect(nextState).toEqual(state);
  });
});

// ── /switch helpers ────────────────────────────────────────────────────────

describe("parseSwitchPrompt", () => {
  it("returns null for blank input", () => {
    expect(parseSwitchPrompt("")).toBeNull();
    expect(parseSwitchPrompt("   ")).toBeNull();
  });

  it("returns null for non-UUID tokens", () => {
    expect(parseSwitchPrompt("my-task")).toBeNull();
    expect(parseSwitchPrompt("12345")).toBeNull();
    expect(parseSwitchPrompt("implement feature x")).toBeNull();
  });

  it("parses an 8-char hex prefix as uuid-prefix", () => {
    const result = parseSwitchPrompt("aabb1111");
    expect(result).toEqual({ id: "aabb1111", kind: "uuid-prefix" });
  });

  it("parses a full UUID as full-uuid", () => {
    const full = "aabb1111-2222-3333-4444-555555555555";
    const result = parseSwitchPrompt(full);
    expect(result).toEqual({ id: full, kind: "full-uuid" });
  });

  it("trims leading/trailing whitespace before parsing", () => {
    const result = parseSwitchPrompt("  aabb1111  ");
    expect(result).toEqual({ id: "aabb1111", kind: "uuid-prefix" });
  });
});
