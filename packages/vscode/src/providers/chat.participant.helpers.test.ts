import { describe, expect, it } from "vitest";
import type { ActiveAgentRowResponse, WireChatSessionSummary } from "@kagan/shared-api-client";
import {
  isTaskSession,
  parseAttachPrompt,
  pickReusableChatSessionId,
  resolveAgentSessionId,
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

// ── /attach helpers ────────────────────────────────────────────────────────

function makeAgent(overrides: Partial<ActiveAgentRowResponse> = {}): ActiveAgentRowResponse {
  return {
    task_id: "aaaa0000-bbbb-cccc-dddd-000000000001",
    task_title: "Implement feature X",
    task_status: "IN_PROGRESS",
    session_id: "11110000-2222-3333-4444-555555555555",
    agent_role: "worker",
    agent_backend: "claude-code",
    session_status: "RUNNING",
    started_at: "2026-05-07T10:00:00Z",
    ...overrides,
  };
}

describe("parseAttachPrompt", () => {
  it("returns null for blank input", () => {
    expect(parseAttachPrompt("")).toBeNull();
    expect(parseAttachPrompt("   ")).toBeNull();
  });

  it("returns null for non-UUID tokens", () => {
    expect(parseAttachPrompt("my-task")).toBeNull();
    expect(parseAttachPrompt("12345")).toBeNull();
    expect(parseAttachPrompt("implement feature x")).toBeNull();
  });

  it("parses an 8-char hex prefix as uuid-prefix", () => {
    const result = parseAttachPrompt("aabb1111");
    expect(result).toEqual({ id: "aabb1111", kind: "uuid-prefix" });
  });

  it("parses a full UUID as full-uuid", () => {
    const full = "aabb1111-2222-3333-4444-555555555555";
    const result = parseAttachPrompt(full);
    expect(result).toEqual({ id: full, kind: "full-uuid" });
  });

  it("trims leading/trailing whitespace before parsing", () => {
    const result = parseAttachPrompt("  aabb1111  ");
    expect(result).toEqual({ id: "aabb1111", kind: "uuid-prefix" });
  });
});

describe("resolveAgentSessionId", () => {
  const agents = [
    makeAgent({
      task_id: "aaaa0000-bbbb-cccc-dddd-000000000001",
      session_id: "11110000-2222-3333-4444-555555555555",
    }),
    makeAgent({
      task_id: "eeee0000-ffff-0000-1111-000000000002",
      session_id: "55550000-6666-7777-8888-000000000002",
      agent_role: "reviewer",
    }),
  ];

  it("resolves by exact session id", () => {
    expect(resolveAgentSessionId("11110000-2222-3333-4444-555555555555", agents)).toBe(
      "11110000-2222-3333-4444-555555555555",
    );
  });

  it("resolves by session id prefix", () => {
    expect(resolveAgentSessionId("55550000", agents)).toBe(
      "55550000-6666-7777-8888-000000000002",
    );
  });

  it("resolves by exact task id to session id", () => {
    expect(resolveAgentSessionId("aaaa0000-bbbb-cccc-dddd-000000000001", agents)).toBe(
      "11110000-2222-3333-4444-555555555555",
    );
  });

  it("resolves by task id prefix to session id", () => {
    expect(resolveAgentSessionId("eeee0000", agents)).toBe(
      "55550000-6666-7777-8888-000000000002",
    );
  });

  it("returns null when nothing matches", () => {
    expect(resolveAgentSessionId("nonexistent", agents)).toBeNull();
    expect(resolveAgentSessionId("zzzzzzzz", agents)).toBeNull();
  });

  it("is case-insensitive", () => {
    expect(resolveAgentSessionId("AAAA0000-BBBB-CCCC-DDDD-000000000001", agents)).toBe(
      "11110000-2222-3333-4444-555555555555",
    );
  });
});
