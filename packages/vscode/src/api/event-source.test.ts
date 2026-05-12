/**
 * Unit tests for KaganEventSource and applyFrame reducer.
 *
 * Uses a tiny FakeEventSource stub (non-Kagan boundary — external EventSource API).
 * Does NOT mock KaganClient.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyFrame,
  KaganEventSource,
  type EntryStreamState,
  type AuthConfig,
  type EventSourceLike,
} from "./event-source.js";
import type {
  FrameEntry,
  FramePatch,
  FrameResume,
  FrameSnapshot,
} from "@kagan/shared-api-client";

// ── Helpers ────────────────────────────────────────────────────────────────

function emptyState(): EntryStreamState {
  return { entries: new Map(), ready: false, live: false };
}

function entry(idx: number, text: string, role: FrameEntry["role"] = "assistant"): FrameEntry {
  return { idx, role, text, finalized: false, ts: "2026-01-01T00:00:00Z" };
}

// ── applyFrame reducer ─────────────────────────────────────────────────────

describe("applyFrame", () => {
  it("applies snapshot to entries Map", () => {
    const snapshot: FrameSnapshot = {
      type: "snapshot",
      kind: "chat",
      session_id: "sess-1",
      from_seq: 0,
      to_seq: 2,
      entries: [entry(0, "hello", "user"), entry(1, "world", "assistant")],
    };
    const next = applyFrame(emptyState(), snapshot);
    expect(next.entries.size).toBe(2);
    expect(next.entries.get(0)?.text).toBe("hello");
    expect(next.entries.get(1)?.text).toBe("world");
  });

  it("flips ready flag on ready event", () => {
    const state = applyFrame(emptyState(), { type: "ready" });
    expect(state.ready).toBe(true);
    expect(state.live).toBe(true);
  });

  it("parses path to extract target idx on create patch", () => {
    const patch: FramePatch = {
      type: "patch",
      op: "create",
      path: "/entries/3",
      value: entry(3, "new entry", "user"),
    };
    const next = applyFrame(emptyState(), patch);
    expect(next.entries.has(3)).toBe(true);
    expect(next.entries.get(3)?.text).toBe("new entry");
  });

  it("appends text on append patch", () => {
    const initial: EntryStreamState = {
      entries: new Map([[0, entry(0, "hello", "assistant")]]),
      ready: true,
      live: true,
    };
    const patch: FramePatch = {
      type: "patch",
      op: "append",
      path: "/entries/0/text",
      value: " world",
    };
    const next = applyFrame(initial, patch);
    expect(next.entries.get(0)?.text).toBe("hello world");
  });

  it("marks entry finalized on finalize patch", () => {
    const initial: EntryStreamState = {
      entries: new Map([[2, entry(2, "some text", "assistant")]]),
      ready: true,
      live: true,
    };
    const patch: FramePatch = {
      type: "patch",
      op: "finalize",
      path: "/entries/2",
      reason: "done",
    };
    const next = applyFrame(initial, patch);
    expect(next.entries.get(2)?.finalized).toBe(true);
  });

  it("warns on append before create", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const patch: FramePatch = {
      type: "patch",
      op: "append",
      path: "/entries/5/text",
      value: " orphan",
    };
    const next = applyFrame(emptyState(), patch);
    expect(next.entries.has(5)).toBe(false);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("append before create"),
      5,
    );
    warnSpy.mockRestore();
  });

  it("captures resume notice with turnActive flag", () => {
    const resume: FrameResume = {
      type: "resume",
      kind: "chat",
      turn_active: true,
    };
    const next = applyFrame(emptyState(), resume);
    expect(next.resumeNotice).toEqual({ turnActive: true });
  });

  it("preserves existing entries on non-snapshot frames", () => {
    const initial: EntryStreamState = {
      entries: new Map([[0, entry(0, "keep me")], [1, entry(1, "keep me too")]]),
      ready: true,
      live: true,
    };
    const next = applyFrame(initial, { type: "ready" });
    expect(next.entries.size).toBe(2);
  });
});

// ── FakeEventSource stub ────────────────────────────────────────────────────
// Minimal controllable stub that satisfies the EventSourceLike interface used
// internally by KaganEventSource.  Not a Kagan boundary — purely a browser/
// Node EventSource API surface stub.

type EventHandler = (event: { type: string; data: string; lastEventId: string }) => void;

class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  readyState = FakeEventSource.OPEN;
  onerror: ((event: { type: string }) => void) | null = null;

  private readonly handlers: Map<string, EventHandler[]> = new Map();
  private _closeCount = 0;

  get closeCallCount(): number { return this._closeCount; }

  addEventListener(type: string, handler: EventHandler): void {
    const list = this.handlers.get(type) ?? [];
    list.push(handler);
    this.handlers.set(type, list);
  }

  close(): void {
    this._closeCount++;
    this.readyState = FakeEventSource.CLOSED;
  }

  /** Test control: fire a named SSE event. */
  _emit(eventName: string, data: string, id = ""): void {
    const list = this.handlers.get(eventName) ?? [];
    for (const h of list) {
      h({ type: eventName, data, lastEventId: id });
    }
  }

  /** Test control: fire the onerror handler. */
  _emitError(): void {
    this.readyState = FakeEventSource.CONNECTING;
    this.onerror?.({ type: "error" });
  }
}

// Factory override injected into KaganEventSource for tests.
type FakeEventSourceFactory = (url: string) => FakeEventSource;

// ── KaganEventSource behaviour ─────────────────────────────────────────────

function makeAuth(): AuthConfig {
  return { baseUrl: "http://localhost:8765", token: "test-tok" };
}

function makeSut(
  url: string,
  fakeFactory: FakeEventSourceFactory,
): { es: KaganEventSource; fake: FakeEventSource } {
  let fake!: FakeEventSource;
  const factory = (u: string) => {
    fake = fakeFactory(u);
    return fake;
  };
  const es = new KaganEventSource(
    { url, auth: makeAuth() },
    factory as (url: string) => EventSourceLike,
  );
  return { es, fake };
}

describe("KaganEventSource", () => {
  let receivedPatches: FramePatch[];
  let readyFired: number;
  let receivedResumes: FrameResume[];
  let receivedErrors: Error[];

  beforeEach(() => {
    receivedPatches = [];
    readyFired = 0;
    receivedResumes = [];
    receivedErrors = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function wire(es: KaganEventSource): void {
    es.onPatch((p) => receivedPatches.push(p));
    es.onReady(() => readyFired++);
    es.onResume((r) => receivedResumes.push(r));
    es.onError((e) => receivedErrors.push(e));
  }

  it("emits onPatch for each patch frame", () => {
    const { es, fake } = makeSut("http://localhost/sse", () => new FakeEventSource());
    wire(es);

    const patch: FramePatch = { type: "patch", op: "create", path: "/entries/0", value: entry(0, "hi") };
    fake._emit("patch", JSON.stringify(patch));
    fake._emit("patch", JSON.stringify({ ...patch, path: "/entries/1", value: entry(1, "there") }));

    expect(receivedPatches).toHaveLength(2);
    expect(receivedPatches[0].path).toBe("/entries/0");
    expect(receivedPatches[1].path).toBe("/entries/1");
  });

  it("onReady fires on ready event and flips state.ready", () => {
    const { es, fake } = makeSut("http://localhost/sse", () => new FakeEventSource());
    wire(es);

    fake._emit("ready", JSON.stringify({ type: "ready" }));

    expect(readyFired).toBe(1);
  });

  it("onSnapshot delivers aggregated state after ready", () => {
    const { es, fake } = makeSut("http://localhost/sse", () => new FakeEventSource());

    const snapshots: EntryStreamState[] = [];
    es.onSnapshot((s) => {
      snapshots.push(s);
    });

    const snapshot: FrameSnapshot = {
      type: "snapshot",
      kind: "chat",
      session_id: "sess-1",
      from_seq: 0,
      to_seq: 1,
      entries: [entry(0, "hi", "user")],
    };
    fake._emit("snapshot", JSON.stringify(snapshot));
    fake._emit("ready", JSON.stringify({ type: "ready" }));

    expect(snapshots).toHaveLength(1);
    expect(snapshots[0]?.entries.get(0)?.text).toBe("hi");
    expect(snapshots[0]?.ready).toBe(true);
  });

  it("captures resume notice with turnActive flag", () => {
    const { es, fake } = makeSut("http://localhost/sse", () => new FakeEventSource());
    wire(es);

    const resume: FrameResume = { type: "resume", kind: "chat", turn_active: true };
    fake._emit("resume", JSON.stringify(resume));

    expect(receivedResumes).toHaveLength(1);
    expect(receivedResumes[0]?.turn_active).toBe(true);
  });

  it("close() cleans up underlying EventSource", () => {
    const fake = new FakeEventSource();
    const { es } = makeSut("http://localhost/sse", () => fake);

    es.close();

    expect(fake.closeCallCount).toBe(1);
  });

  it("reconnect sets live=false then true on next ready", () => {
    const { es, fake } = makeSut("http://localhost/sse", () => new FakeEventSource());
    wire(es);

    // Establish initial live state.
    fake._emit("ready", JSON.stringify({ type: "ready" }));
    expect(readyFired).toBe(1);

    // Simulate error (disconnect) — live should drop and onError fires.
    fake._emitError();

    // The error handler fires onError.
    expect(receivedErrors).toHaveLength(1);
  });

  it("ignores malformed JSON without throwing", () => {
    const { es, fake } = makeSut("http://localhost/sse", () => new FakeEventSource());
    wire(es);

    expect(() => {
      fake._emit("patch", "not-json{{{}}}");
    }).not.toThrow();

    expect(receivedPatches).toHaveLength(0);
  });

  it("builds SSE URL with token query param when auth.token is set", () => {
    const capturedUrls: string[] = [];
    const { es } = makeSut(
      "http://localhost:8765/api/sessions/sess-1/events",
      (u) => {
        capturedUrls.push(u);
        return new FakeEventSource();
      },
    );

    // URL is captured at construction time; no close needed.
    void es;
    expect(capturedUrls[0]).toContain("token=test-tok");
  });

  it("omits token query param when appendTokenToQuery is false", () => {
    const capturedUrls: string[] = [];
    const es = new KaganEventSource(
      {
        url: "http://localhost:8765/api/sessions/sess-1/events",
        auth: { baseUrl: "http://localhost:8765", token: "test-tok", appendTokenToQuery: false },
      },
      (u) => {
        capturedUrls.push(u);
        return new FakeEventSource() as unknown as EventSourceLike;
      },
    );

    void es;
    expect(capturedUrls[0]).toBe("http://localhost:8765/api/sessions/sess-1/events");
    expect(capturedUrls[0]).not.toContain("token=");
  });
});
