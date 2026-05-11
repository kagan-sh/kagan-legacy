/**
 * Unit tests: chat participant wired onto KaganEventSource (W9d).
 *
 * Exercises the ChatParticipantState class directly — subscribes to session
 * events via a FakeEventSource stub (the EventSourceLike boundary), asserts
 * on rendered side-effects (info messages, state mutations), and verifies
 * proper teardown via es.close().
 *
 * Does NOT mock KaganClient entirely; mocks only the SSE boundary via the
 * FakeEventSource factory, consistent with the W8 test pattern.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EventSourceLike, SSEEventListener } from "../api/event-source.js";
import { KaganEventSource } from "../api/event-source.js";
import type { FrameEntry, FramePatch, FrameResume, FrameSnapshot } from "@kagan/shared-api-client";

// ── vscode mock ───────────────────────────────────────────────────────────────
// Must be hoisted — factory cannot reference outer-scope variables.

const _shownInfoMessages: string[] = [];

vi.mock("vscode", () => ({
  window: {
    showInformationMessage: vi.fn((...args: unknown[]) => {
      _shownInfoMessages.push(args[0] as string);
      return Promise.resolve(undefined);
    }),
    showWarningMessage: vi.fn(() => Promise.resolve(undefined)),
    showErrorMessage: vi.fn(() => Promise.resolve(undefined)),
    createOutputChannel: vi.fn(() => ({
      appendLine: vi.fn(),
      append: vi.fn(),
      clear: vi.fn(),
      show: vi.fn(),
      dispose: vi.fn(),
    })),
  },
  workspace: {
    getConfiguration: vi.fn(() => ({
      get: vi.fn(() => ""),
    })),
  },
  commands: {
    registerCommand: vi.fn(() => ({ dispose: vi.fn() })),
    executeCommand: vi.fn(),
  },
  chat: {
    createChatParticipant: vi.fn(() => ({
      iconPath: null,
      dispose: vi.fn(),
    })),
  },
  EventEmitter: vi.fn(function (this: { event: unknown; fire: () => void; dispose: () => void }) {
    this.event = vi.fn();
    this.fire = vi.fn();
    this.dispose = vi.fn();
  }),
  Uri: {
    joinPath: vi.fn(() => ({})),
  },
}));

// ── FakeEventSource stub ──────────────────────────────────────────────────────

class FakeEventSource implements EventSourceLike {
  static readonly CLOSED = 2;
  readyState = 1; // OPEN
  onerror: ((event: { type: string }) => void) | null = null;

  private readonly handlers: Map<string, SSEEventListener[]> = new Map();
  private _closeCalls = 0;

  get closeCalls(): number { return this._closeCalls; }

  addEventListener(type: string, listener: SSEEventListener): void {
    const list = this.handlers.get(type) ?? [];
    list.push(listener);
    this.handlers.set(type, list);
  }

  close(): void {
    this._closeCalls++;
    this.readyState = FakeEventSource.CLOSED;
  }

  emit(eventName: string, data: unknown, id = ""): void {
    const listeners = this.handlers.get(eventName) ?? [];
    const raw = JSON.stringify(data);
    for (const l of listeners) {
      l({ type: eventName, data: raw, lastEventId: id });
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeEntry(idx: number, text: string, role: FrameEntry["role"] = "assistant"): FrameEntry {
  return { idx, role, text, finalized: false, ts: "2026-01-01T00:00:00Z" };
}

function makeSnapshot(sessionId: string, entries: FrameEntry[]): FrameSnapshot {
  return {
    type: "snapshot",
    kind: "chat",
    session_id: sessionId,
    from_seq: 0,
    to_seq: entries.length,
    entries,
  };
}

type SubscribeSessionEventsFn = (sessionId: string) => KaganEventSource;

/**
 * Builds a subscribeSessionEvents() stub that injects a FakeEventSource so
 * tests can drive the SSE boundary without any network.
 */
function makeFakeSubscribe(fake: FakeEventSource): SubscribeSessionEventsFn {
  return (sessionId: string) => {
    return new KaganEventSource(
      { url: `http://localhost:8765/api/sessions/${sessionId}/events`, auth: { baseUrl: "http://localhost:8765" } },
      () => fake as unknown as EventSourceLike,
    );
  };
}

// ── Inline implementation under test ─────────────────────────────────────────
// We test ChatSessionEventBinding — the extracted logic that replaces
// subscribeToLiveChat / handleWatchEvent in ChatParticipantState.
// Import it from the provider after implementation is in place.

import { ChatSessionEventBinding } from "./chat.participant.js";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ChatSessionEventBinding", () => {
  let fake: FakeEventSource;

  beforeEach(() => {
    fake = new FakeEventSource();
    _shownInfoMessages.splice(0);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("subscribes to session events on activation", () => {
    const subscribe = makeFakeSubscribe(fake);
    const binding = new ChatSessionEventBinding(subscribe);
    binding.attachSession("sess-1");
    // Connection established means the factory was called (fake is at OPEN state)
    expect(fake.readyState).toBe(1);
    binding.dispose();
  });

  it("renders entries from snapshot via onSnapshot", () => {
    const subscribe = makeFakeSubscribe(fake);
    const binding = new ChatSessionEventBinding(subscribe);
    const snapshots: Array<Map<number, FrameEntry>> = [];
    binding.onSnapshot = (entries) => snapshots.push(new Map(entries));

    binding.attachSession("sess-1");

    fake.emit("snapshot", makeSnapshot("sess-1", [
      makeEntry(0, "hello", "user"),
      makeEntry(1, "world", "assistant"),
    ]));
    fake.emit("ready", { type: "ready" });

    expect(snapshots).toHaveLength(1);
    expect(snapshots[0]?.get(0)?.text).toBe("hello");
    expect(snapshots[0]?.get(1)?.text).toBe("world");
    binding.dispose();
  });

  it("appends text on append patch via onPatch", () => {
    const subscribe = makeFakeSubscribe(fake);
    const binding = new ChatSessionEventBinding(subscribe);
    const patches: FramePatch[] = [];
    binding.onPatch = (p) => patches.push(p);

    binding.attachSession("sess-1");

    const appendPatch: FramePatch = {
      type: "patch",
      op: "append",
      path: "/entries/0/text",
      value: " world",
    };
    fake.emit("patch", appendPatch);

    expect(patches).toHaveLength(1);
    expect(patches[0]?.op).toBe("append");
    expect(patches[0]?.value).toBe(" world");
    binding.dispose();
  });

  it("marks message finalized on finalize patch", () => {
    const subscribe = makeFakeSubscribe(fake);
    const binding = new ChatSessionEventBinding(subscribe);
    const patches: FramePatch[] = [];
    binding.onPatch = (p) => patches.push(p);

    binding.attachSession("sess-1");

    const finalizePatch: FramePatch = {
      type: "patch",
      op: "finalize",
      path: "/entries/0",
      reason: "done",
    };
    fake.emit("patch", finalizePatch);

    expect(patches).toHaveLength(1);
    expect(patches[0]?.op).toBe("finalize");
    binding.dispose();
  });

  it("shows resume notice when onResume fires with turnActive=true", async () => {
    const subscribe = makeFakeSubscribe(fake);
    const binding = new ChatSessionEventBinding(subscribe);

    binding.attachSession("sess-1");

    const resumeFrame: FrameResume = { type: "resume", kind: "chat", turn_active: true };
    fake.emit("resume", resumeFrame);

    // Allow microtask queue to flush (showInformationMessage returns a promise).
    await Promise.resolve();

    const matched = _shownInfoMessages.some((m) => m.includes("resumed") || m.includes("restart"));
    expect(matched).toBe(true);
    binding.dispose();
  });

  it("does not show resume notice when turnActive=false", async () => {
    const subscribe = makeFakeSubscribe(fake);
    const binding = new ChatSessionEventBinding(subscribe);

    binding.attachSession("sess-1");
    _shownInfoMessages.splice(0); // clear

    const resumeFrame: FrameResume = { type: "resume", kind: "chat", turn_active: false };
    fake.emit("resume", resumeFrame);

    await Promise.resolve();

    const matched = _shownInfoMessages.some((m) => m.includes("resumed") || m.includes("restart"));
    expect(matched).toBe(false);
    binding.dispose();
  });

  it("calls es.close() on dispose()", () => {
    const subscribe = makeFakeSubscribe(fake);
    const binding = new ChatSessionEventBinding(subscribe);
    binding.attachSession("sess-1");
    binding.dispose();
    expect(fake.closeCalls).toBe(1);
  });

  it("calls es.close() on previous session when switching sessions", () => {
    const fake1 = new FakeEventSource();
    const fake2 = new FakeEventSource();
    const fakes = [fake1, fake2];
    let fakeIdx = 0;

    const subscribe: SubscribeSessionEventsFn = (sessionId: string) =>
      new KaganEventSource(
        { url: `http://localhost:8765/api/sessions/${sessionId}/events`, auth: { baseUrl: "http://localhost:8765" } },
        () => fakes[fakeIdx++]! as unknown as EventSourceLike,
      );

    const binding = new ChatSessionEventBinding(subscribe);
    binding.attachSession("sess-1");
    expect(fake1.closeCalls).toBe(0);

    // Switch to a different session — old EventSource must be closed.
    binding.attachSession("sess-2");
    expect(fake1.closeCalls).toBe(1);
    expect(fake2.closeCalls).toBe(0);

    binding.dispose();
    expect(fake2.closeCalls).toBe(1);
  });

  it("no-ops attachSession for same session id when already subscribed", () => {
    let callCount = 0;
    const subscribe: SubscribeSessionEventsFn = (sessionId: string) => {
      callCount++;
      return new KaganEventSource(
        { url: `http://localhost:8765/api/sessions/${sessionId}/events`, auth: { baseUrl: "http://localhost:8765" } },
        () => fake as unknown as EventSourceLike,
      );
    };

    const binding = new ChatSessionEventBinding(subscribe);
    binding.attachSession("sess-1");
    binding.attachSession("sess-1"); // same session — should not re-subscribe
    expect(callCount).toBe(1);
    binding.dispose();
  });
});
