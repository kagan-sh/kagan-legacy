import { describe, expect, it } from "vitest";
import type { SessionItemResponse } from "@kagan/shared-api-client";
import {
  pickReusableOrchestratorSession,
  resetStickyChatStateIfNewConversation,
  parseSwitchPrompt,
  resolveSwitchSession,
  switchTokenForSession,
} from "./chat.participant.helpers.js";

function makeSessionItem(overrides: Partial<SessionItemResponse> = {}): SessionItemResponse {
  return {
    id: "orch:aabb1111-2222-3333-4444-555555555555",
    type: "orchestrator",
    role: null,
    status: "idle",
    title: "Orchestrator",
    backend: null,
    project_id: null,
    task_id: null,
    session_id: null,
    chat_session_id: "aabb1111-2222-3333-4444-555555555555",
    updated_at: "",
    capabilities: {
      can_chat: true,
      can_stream: true,
      can_replay: true,
      can_stop: true,
      can_close: true,
      has_kagan_tools: true,
    },
    ...overrides,
  };
}

describe("chat participant helpers", () => {
  it("reuses the saved orchestrator session by unified id", () => {
    const session = pickReusableOrchestratorSession("orch:aabb1111-2222", [
      makeSessionItem({
        id: "task:task-1",
        type: "task",
        chat_session_id: null,
        session_id: "task-1",
      }),
      makeSessionItem({ id: "orch:aabb1111-2222" }),
    ]);

    expect(session?.id).toBe("orch:aabb1111-2222");
  });

  it("reuses the saved orchestrator session by raw chat id", () => {
    const session = pickReusableOrchestratorSession("raw-chat-1", [
      makeSessionItem({
        id: "task:task-1",
        type: "task",
        chat_session_id: null,
        session_id: "task-1",
      }),
      makeSessionItem({ id: "orch:raw-chat-1", chat_session_id: "raw-chat-1" }),
    ]);

    expect(session?.id).toBe("orch:raw-chat-1");
  });

  it("returns null when no orchestrator sessions exist", () => {
    const session = pickReusableOrchestratorSession("task-1", [
      makeSessionItem({
        id: "task:task-1",
        type: "task",
        chat_session_id: null,
        session_id: "task-1",
      }),
    ]);

    expect(session).toBeNull();
  });

  it("clears sticky state for a fresh conversation", () => {
    const nextState = resetStickyChatStateIfNewConversation(
      { activeRawChatSessionId: "orch-1" },
      { history: [] },
    );

    expect(nextState).toEqual({
      activeRawChatSessionId: null,
    });
  });

  it("preserves sticky state when the conversation already has history", () => {
    const state = { activeRawChatSessionId: "orch-1" };
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
    expect(parseSwitchPrompt("implement feature x")).toBeNull();
    expect(parseSwitchPrompt("orch:")).toBeNull();
    expect(parseSwitchPrompt(":aabb1111")).toBeNull();
  });

  it("parses an 8-char raw prefix as raw-prefix", () => {
    const result = parseSwitchPrompt("aabb1111");
    expect(result).toEqual({ id: "aabb1111", kind: "raw-prefix" });
  });

  it("parses a full raw UUID as raw-prefix", () => {
    const full = "aabb1111-2222-3333-4444-555555555555";
    const result = parseSwitchPrompt(full);
    expect(result).toEqual({ id: full, kind: "raw-prefix" });
  });

  it("parses displayed kind-scoped switch tokens", () => {
    expect(parseSwitchPrompt("orch:aabb1111")).toEqual({
      id: "orch:aabb1111",
      kind: "scoped-prefix",
    });
    expect(parseSwitchPrompt("gen:bbcc2222")).toEqual({
      id: "gen:bbcc2222",
      kind: "scoped-prefix",
    });
    expect(parseSwitchPrompt("task:ccdd3333")).toEqual({
      id: "task:ccdd3333",
      kind: "scoped-prefix",
    });
  });

  it("trims leading/trailing whitespace before parsing", () => {
    const result = parseSwitchPrompt("  aabb1111  ");
    expect(result).toEqual({ id: "aabb1111", kind: "raw-prefix" });
  });
});

describe("switchTokenForSession", () => {
  it("formats kind-scoped sessions with a usable switch token", () => {
    expect(switchTokenForSession(makeSessionItem())).toBe("orch:aabb1111");
    expect(switchTokenForSession(makeSessionItem({
      id: "gen:bbcc2222-3333-4444-5555-666666666666",
      type: "general",
    }))).toBe("gen:bbcc2222");
    expect(switchTokenForSession(makeSessionItem({
      id: "task:ccdd3333-4444-5555-6666-777777777777",
      type: "task",
      role: "worker",
    }))).toBe("task:ccdd3333");
  });

  it("falls back to a raw prefix for unscoped legacy ids", () => {
    expect(switchTokenForSession(makeSessionItem({ id: "aabb1111-2222" }))).toBe("aabb1111");
  });
});

describe("resolveSwitchSession", () => {
  it("matches displayed scoped prefixes", () => {
    const sessions = [
      makeSessionItem({ id: "orch:aabb1111-2222-3333-4444-555555555555" }),
      makeSessionItem({ id: "gen:bbcc2222-3333-4444-5555-666666666666", type: "general" }),
      makeSessionItem({ id: "task:ccdd3333-4444-5555-6666-777777777777", type: "task" }),
    ];

    expect(resolveSwitchSession(sessions, "orch:aabb1111")?.id).toBe(sessions[0].id);
    expect(resolveSwitchSession(sessions, "gen:bbcc2222")?.id).toBe(sessions[1].id);
    expect(resolveSwitchSession(sessions, "task:ccdd3333")?.id).toBe(sessions[2].id);
  });

  it("matches raw prefixes against unified ids and backing ids", () => {
    const session = makeSessionItem({
      id: "orch:full-visible-id",
      chat_session_id: "aabb1111-2222-3333-4444-555555555555",
    });

    expect(resolveSwitchSession([session], "full-vis")?.id).toBe(session.id);
    expect(resolveSwitchSession([session], "aabb1111")?.id).toBe(session.id);
  });
});
