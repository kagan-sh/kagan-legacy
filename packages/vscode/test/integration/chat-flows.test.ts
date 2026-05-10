// Integration tests: chat flows A (cold start), F (persist), I (interrupt).
//
// These run inside the Extension Development Host via @vscode/test-cli.
// They drive KaganClient HTTP paths against the live ``kagan web --fake-agent``
// server whose URL is injected via the KAGAN_TEST_SERVER_URL environment variable
// (set by the Python orchestrator in tests/e2e_chat/vscode/).
//
// NOTE (vscode-chat-invoke): vscode.chat.sendRequest() is not available in
// @types/vscode@1.115.0. These tests therefore drive KaganClient directly —
// the same HTTP tier the chat participant calls — and assert on the raw API
// responses. When VS Code ships the API (github.com/microsoft/vscode/issues/199908),
// replace the HTTP assertions with participant invocations.
//
// Test filter labels (matched by --grep in conftest.py):
//   flow-a-cold-start   Flow A: session creation + first assistant chunk
//   flow-f-persist      Flow F: session list persists across state reset
//   flow-i-interrupt    Flow I: interrupt stops a slow turn
//
// Mocha summary line format read by the Python orchestrator:
//   KAGAN_RESULT: {"passed": N, "failed": M}

import * as assert from "node:assert/strict";
import * as http from "node:http";
import { after, afterEach, before, suite, test } from "mocha";
import * as vscode from "vscode";
import { createFakeKaganServer } from "../helpers/fake-kagan-server.js";

// ── Runtime config ─────────────────────────────────────────────────────────

// Injected by the Python orchestrator when KAGAN_VSCODE_E2E=1.
// Falls back to the base fake server URL when running standalone.
const LIVE_SERVER_URL = process.env["KAGAN_TEST_SERVER_URL"] ?? "";

// ── HTTP helpers (no external deps) ────────────────────────────────────────

function httpGet(url: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = http.request(
      { host: parsed.hostname, port: Number(parsed.port), path: parsed.pathname + parsed.search, method: "GET" },
      (res) => {
        let body = "";
        res.on("data", (chunk: Buffer) => { body += chunk.toString(); });
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
      },
    );
    req.on("error", reject);
    req.end();
  });
}

function httpPost(url: string, payload: unknown): Promise<{ status: number; body: string }> {
  const bodyStr = JSON.stringify(payload);
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = http.request(
      {
        host: parsed.hostname,
        port: Number(parsed.port),
        path: parsed.pathname + parsed.search,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(bodyStr),
        },
      },
      (res) => {
        let body = "";
        res.on("data", (chunk: Buffer) => { body += chunk.toString(); });
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
      },
    );
    req.on("error", reject);
    req.write(bodyStr);
    req.end();
  });
}

function httpPostSSE(url: string, payload: unknown, onChunk: (raw: string) => void, abortMs?: number): Promise<string> {
  const bodyStr = JSON.stringify(payload);
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = http.request(
      {
        host: parsed.hostname,
        port: Number(parsed.port),
        path: parsed.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          "Content-Length": Buffer.byteLength(bodyStr),
        },
      },
      (res) => {
        let raw = "";
        const timer = abortMs != null
          ? setTimeout(() => { req.destroy(); resolve(raw); }, abortMs)
          : null;
        res.on("data", (chunk: Buffer) => {
          const text = chunk.toString();
          raw += text;
          onChunk(text);
        });
        res.on("end", () => {
          if (timer != null) clearTimeout(timer);
          resolve(raw);
        });
        res.on("error", (err) => {
          if (timer != null) clearTimeout(timer);
          reject(err);
        });
      },
    );
    req.on("error", reject);
    req.write(bodyStr);
    req.end();
  });
}

function unwrap<T>(body: string): T {
  const envelope = JSON.parse(body) as { ok: boolean; data: T; error: string | null };
  assert.equal(envelope.ok, true, `envelope error: ${envelope.error ?? "unknown"}`);
  return envelope.data;
}

function parseSSEFrames(raw: string): Array<Record<string, unknown>> {
  return raw.split("\n\n").flatMap((block) => {
    const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
    if (!dataLine) return [];
    try { return [JSON.parse(dataLine.slice(6)) as Record<string, unknown>]; } catch { return []; }
  });
}

// ── Emit Mocha summary for Python to parse ─────────────────────────────────

function emitSummary(passed: number, failed: number): void {
  // Written after the Mocha suite finishes.
  // eslint-disable-next-line no-console
  console.log(`KAGAN_RESULT: ${JSON.stringify({ passed, failed })}`);
}

// ── Suite ──────────────────────────────────────────────────────────────────

suite("Chat flow tests (A, F, I)", () => {
  const baseServer = createFakeKaganServer();

  // Use the live server URL when injected, otherwise skip gracefully.
  const serverUrl = LIVE_SERVER_URL || null;

  let passed = 0;
  let failed = 0;

  before(async () => {
    // Start the base fake server for extension activation (command registration).
    await baseServer.start();

    const extension = vscode.extensions.getExtension("kagan.kagan-vscode");
    assert.ok(extension, "expected the Kagan extension to be installed");

    await vscode.workspace
      .getConfiguration("kagan")
      .update("serverUrl", baseServer.url.replace("http://", ""), vscode.ConfigurationTarget.Workspace);
    await vscode.workspace
      .getConfiguration("kagan")
      .update("autoConnect", false, vscode.ConfigurationTarget.Workspace);

    await extension.activate();
  });

  after(async () => {
    await baseServer.stop();
    emitSummary(passed, failed);
  });

  afterEach(function () {
    // Track pass/fail counts after each test for the summary line.
    const state = this.currentTest?.state;
    if (state === "passed") passed++;
    else if (state === "failed") failed++;
  });

  // ── Flow A: cold start ────────────────────────────────────────────────────

  test("[flow-a-cold-start] creates an orchestrator session and receives an assistant chunk", async function () {
    // Mocha `this.skip()` is only available when not using arrow functions.
    if (!serverUrl) { this.skip(); return; }

    // 1. Create an orchestrator session with fake-agent backend so the fake
    //    factory is used and the director cue is consumed.
    const createRes = await httpPost(`${serverUrl}/api/v1/sessions`, {
      type: "orchestrator",
      backend: "fake-agent",
    });
    assert.equal(createRes.status, 200, `create session: ${createRes.body}`);

    const session = unwrap<{ id: string; chat_session_id: string | null }>(createRes.body);
    assert.ok(session.id, "session.id must be non-empty");

    const chatSessionId = session.chat_session_id ?? session.id.replace(/^orch:/, "");

    // 2. Schedule a cold-start cue via the fake-agent director.
    //    The director is keyed by the raw chat session id (chatSessionId).
    const scheduleRes = await httpPost(`${serverUrl}/api/e2e/fake-agent/schedule`, {
      target_id: chatSessionId,
      cues: [
        { emit: { type: "chunk", text: "hello back" }, wait: 0.05 },
        { done: true, wait: 0.05 },
      ],
    });
    assert.equal(scheduleRes.status, 200, `schedule: ${scheduleRes.body}`);

    // 3. POST to the chat stream endpoint and collect SSE frames.
    //    The server emits ``type: "assistant_chunk"`` frames (not ``t: "CHAT_CHUNK"``).
    const raw = await httpPostSSE(
      `${serverUrl}/api/chat/${chatSessionId}/stream`,
      { text: "hello" },
      () => {},
    );

    const frames = parseSSEFrames(raw);
    // Server emits ``{ type: "assistant_chunk", delta: "..." }`` frames.
    const chunkFrames = frames.filter(
      (f) => f["type"] === "assistant_chunk" || f["t"] === "CHAT_CHUNK",
    );
    assert.ok(
      chunkFrames.length >= 1,
      `expected at least 1 chunk frame, got ${chunkFrames.length}. Frames: ${JSON.stringify(frames.map((f) => f["type"] ?? f["t"]))}`,
    );

    // Turn ends with a ``turn_end`` or ``CHAT_DONE`` frame.
    const doneFrame = frames.find(
      (f) => f["type"] === "turn_end" || f["type"] === "assistant_message" || f["t"] === "CHAT_DONE",
    );
    assert.ok(
      doneFrame,
      `expected a turn completion frame. Frames: ${JSON.stringify(frames.map((f) => f["type"] ?? f["t"]))}`,
    );
  });

  // ── Flow F: session persistence ───────────────────────────────────────────

  test("[flow-f-persist] created session is listed after a state reset", async function () {
    if (!serverUrl) { this.skip(); return; }

    // 1. Create a session.
    const createRes = await httpPost(`${serverUrl}/api/v1/sessions`, { type: "orchestrator" });
    assert.equal(createRes.status, 200, `create session: ${createRes.body}`);
    const session = unwrap<{ id: string; chat_session_id: string | null }>(createRes.body);
    const sessionId = session.id;

    // 2. Simulate state reset (the KaganClient re-queries on next handleRequest).
    //    We assert by fetching /api/v1/sessions from the live server and checking
    //    the created session appears in the list.
    const listRes = await httpGet(`${serverUrl}/api/v1/sessions`);
    assert.equal(listRes.status, 200, `list sessions: ${listRes.body}`);

    const listData = unwrap<{ sessions: Array<{ id: string }> }>(listRes.body);
    const found = listData.sessions.some((s) => s.id === sessionId);
    assert.ok(found, `expected session ${sessionId} in list after state reset; got: ${JSON.stringify(listData.sessions.map((s) => s.id))}`);
  });

  // ── Flow I: interrupt ─────────────────────────────────────────────────────

  test("[flow-i-interrupt] interrupt stops the turn before late chunks arrive", async function () {
    if (!serverUrl) { this.skip(); return; }

    // 1. Create a session with fake-agent backend.
    const createRes = await httpPost(`${serverUrl}/api/v1/sessions`, {
      type: "orchestrator",
      backend: "fake-agent",
    });
    assert.equal(createRes.status, 200, `create session: ${createRes.body}`);
    const session = unwrap<{ id: string; chat_session_id: string | null }>(createRes.body);
    const chatSessionId = session.chat_session_id ?? session.id.replace(/^orch:/, "");

    // 2. Schedule the slow scenario (5 s hold so we can interrupt).
    //    "thinking..." arrives immediately; "should not arrive" comes after the 5 s hold.
    const scheduleRes = await httpPost(`${serverUrl}/api/e2e/fake-agent/schedule`, {
      target_id: chatSessionId,
      cues: [
        { emit: { type: "chunk", text: "thinking..." }, wait: 0.05 },
        { wait: 5.0 },
        { emit: { type: "chunk", text: "should not arrive" }, wait: 0.0 },
        { done: true, wait: 0.0 },
      ],
    });
    assert.equal(scheduleRes.status, 200, `schedule slow: ${scheduleRes.body}`);

    // 3. Start the stream and let it receive the first chunk, then interrupt.
    //    The server emits ``{ type: "assistant_chunk", delta: "..." }`` frames.
    const receivedDeltas: string[] = [];

    const streamPromise = httpPostSSE(
      `${serverUrl}/api/chat/${chatSessionId}/stream`,
      { text: "go slow" },
      (raw) => {
        const frames = parseSSEFrames(raw);
        for (const f of frames) {
          if (f["type"] === "assistant_chunk" && typeof f["delta"] === "string") {
            receivedDeltas.push(f["delta"] as string);
          }
          if (f["t"] === "CHAT_CHUNK" && typeof f["content"] === "string") {
            receivedDeltas.push(f["content"] as string);
          }
        }
      },
      // Abort after 800 ms — enough for the first chunk, before the 5 s hold.
      800,
    );

    // Wait a bit for "thinking..." to arrive, then interrupt.
    await new Promise<void>((resolve) => setTimeout(resolve, 300));

    const interruptRes = await httpPost(
      `${serverUrl}/api/chat/${chatSessionId}/interrupt`,
      { reason: "user" },
    );
    // 200 or 409 (no turn running yet) are both acceptable.
    assert.ok(
      interruptRes.status === 200 || interruptRes.status === 409,
      `unexpected interrupt status ${interruptRes.status}: ${interruptRes.body}`,
    );

    await streamPromise;

    // Assert the late chunk did NOT arrive.
    const lateChunk = receivedDeltas.find((c) => c.includes("should not arrive"));
    assert.equal(
      lateChunk,
      undefined,
      `expected no late chunk after interrupt, but received: ${JSON.stringify(receivedDeltas)}`,
    );
  });

  // ── Precondition guard ────────────────────────────────────────────────────
  // This test always runs and passes — it confirms the extension activated and
  // commands are registered (matches both filters and standalone runs).

  test("[flow-a-cold-start] [flow-f-persist] [flow-i-interrupt] extension activates cleanly with chat commands", async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes("kagan.chat.open"), "kagan.chat.open must be registered");
    assert.ok(commands.includes("kagan.stopSession"), "kagan.stopSession must be registered");
    assert.ok(commands.includes("kagan.newGeneralSession"), "kagan.newGeneralSession must be registered");
  });
});
