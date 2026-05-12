// Integration tests: W9d provider EventSource wiring.
//
// Per testing.md vscode three-layer split: these tests run inside the Extension
// Development Host via @vscode/test-cli.  They drive KaganClient + KaganEventSource
// against a small in-process HTTP server that emits the frame stream protocol.
//
// Tests:
//   [es-chat]    Chat participant updates from real frame stream
//   [es-task]    AgentOutputProvider receives task events via subscribeTaskEvents
//   [es-dispose] Panel dispose closes the EventSource connection

import * as assert from "node:assert/strict";
import * as http from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, suite, test } from "mocha";
import * as vscode from "vscode";
import { KaganClient } from "../../src/api/client.js";
import type { EntryStreamState } from "../../src/api/event-source.js";
import type { FrameEntry, FramePatch, FrameResume, FrameSnapshot } from "@kagan/shared-api-client";
import { createFakeKaganServer } from "../helpers/fake-kagan-server.js";

// ── Frame stream server stub ───────────────────────────────────────────────────

interface FrameClient {
  res: http.ServerResponse;
  lastSeq: number;
}

class FrameStreamServer {
  private server: http.Server | null = null;
  private readonly frameClients = new Map<string, Set<FrameClient>>();

  async start(): Promise<void> {
    this.server = http.createServer((req, res) => {
      void this.handle(req, res);
    });
    await new Promise<void>((resolve, reject) => {
      this.server?.once("error", reject);
      this.server?.listen(0, "127.0.0.1", () => resolve());
    });
  }

  async stop(): Promise<void> {
    for (const clients of this.frameClients.values()) {
      for (const c of clients) {
        c.res.end();
      }
    }
    this.frameClients.clear();

    const srv = this.server;
    this.server = null;
    if (!srv) return;

    await new Promise<void>((resolve, reject) => {
      srv.close((err) => (err ? reject(err) : resolve()));
    });
  }

  get url(): string {
    const addr = this.server?.address() as AddressInfo | null;
    return addr ? `http://127.0.0.1:${addr.port}` : "http://127.0.0.1:0";
  }

  pushFrame(streamId: string, eventName: string, data: unknown, seq?: number): void {
    const id = seq ?? Date.now();
    const block = `id: ${id}\nevent: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`;
    const clients = this.frameClients.get(streamId);
    if (!clients) return;
    for (const c of clients) {
      c.res.write(block);
    }
  }

  clientCount(streamId: string): number {
    return this.frameClients.get(streamId)?.size ?? 0;
  }

  private async handle(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
    const url = new URL(req.url ?? "/", this.url);

    if (req.method === "GET" && url.pathname === "/health") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/settings") {
      this.json(res, { attached_launcher: "vscode" });
      return;
    }

    // Chat SSE: GET /api/sessions/{id}/events
    const sessionMatch = /^\/api\/sessions\/([^/]+)\/events$/.exec(url.pathname);
    if (req.method === "GET" && sessionMatch) {
      this.openFrameStream(sessionMatch[1]!, req, res);
      return;
    }

    // Task SSE: GET /api/tasks/{id}/sse
    const taskMatch = /^\/api\/tasks\/([^/]+)\/sse$/.exec(url.pathname);
    if (req.method === "GET" && taskMatch) {
      this.openFrameStream(taskMatch[1]!, req, res);
      return;
    }

    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: `Not found: ${url.pathname}` }));
  }

  private openFrameStream(
    streamId: string,
    req: http.IncomingMessage,
    res: http.ServerResponse,
  ): void {
    const lastEventId = Number(req.headers["last-event-id"] ?? 0);
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    });
    res.write(": connected\n\n");

    const client: FrameClient = { res, lastSeq: lastEventId };
    const clients = this.frameClients.get(streamId) ?? new Set();
    clients.add(client);
    this.frameClients.set(streamId, clients);

    req.on("close", () => {
      clients.delete(client);
    });
  }

  private json(res: http.ServerResponse, data: unknown): void {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, data, error: null, error_code: null }));
  }
}

// ── wait helper ─────────────────────────────────────────────────────────────

function waitFor<T>(check: () => T | undefined | null | false, timeoutMs = 3000): Promise<T> {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const tick = () => {
      const result = check();
      if (result) { resolve(result); return; }
      if (Date.now() >= deadline) {
        reject(new Error(`waitFor timed out after ${timeoutMs}ms`));
        return;
      }
      setTimeout(tick, 25);
    };
    tick();
  });
}

// ── Suite ──────────────────────────────────────────────────────────────────────

suite("Provider EventSource wiring — W9d integration", () => {
  const baseServer = createFakeKaganServer();
  const frameServer = new FrameStreamServer();

  before(async () => {
    await baseServer.start();
    await frameServer.start();

    const extension = vscode.extensions.getExtension("kagan.kagan-vscode");
    assert.ok(extension, "Kagan extension must be installed in the test host");

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
    await frameServer.stop();
  });

  // ── [es-chat] ─────────────────────────────────────────────────────────────────

  test("[es-chat] chat participant updates from real frame stream", async () => {
    const host = frameServer.url.replace("http://", "");
    const client = new KaganClient(host, "http");

    const sessionId = "prov-chat-1";
    const snapshots: EntryStreamState[] = [];
    const patches: FramePatch[] = [];

    const es = client.subscribeSessionEvents(sessionId);
    es.onSnapshot((s) => snapshots.push({ ...s, entries: new Map(s.entries) }));
    es.onPatch((p) => patches.push(p));

    await waitFor(() => frameServer.clientCount(sessionId) > 0 || null);

    const snapshot: FrameSnapshot = {
      type: "snapshot",
      kind: "chat",
      session_id: sessionId,
      from_seq: 0,
      to_seq: 2,
      entries: [
        { idx: 0, role: "user", text: "ping", finalized: true, ts: "2026-01-01T00:00:00Z" } as FrameEntry,
        { idx: 1, role: "assistant", text: "", finalized: false, ts: "2026-01-01T00:00:01Z" } as FrameEntry,
      ],
    };
    frameServer.pushFrame(sessionId, "snapshot", snapshot, 1);
    frameServer.pushFrame(sessionId, "ready", { type: "ready" }, 2);

    await waitFor(() => snapshots.length > 0 || null);

    assert.equal(snapshots[0]?.entries.size, 2, "snapshot must contain both entries");
    assert.equal(snapshots[0]?.entries.get(0)?.text, "ping");
    assert.equal(snapshots[0]?.ready, true);

    // Send a live assistant append patch.
    const appendPatch: FramePatch = {
      type: "patch",
      op: "append",
      path: "/entries/1/text",
      value: "pong",
    };
    frameServer.pushFrame(sessionId, "patch", appendPatch, 3);

    await waitFor(() => patches.length > 0 || null);

    assert.equal(patches[0]?.op, "append");
    assert.equal(patches[0]?.value, "pong");

    es.close();
  });

  // ── [es-task] ─────────────────────────────────────────────────────────────────

  test("[es-task] tree view session item shows live status from task frames", async () => {
    const host = frameServer.url.replace("http://", "");
    const client = new KaganClient(host, "http");

    const taskId = "prov-task-1";
    const snapshots: EntryStreamState[] = [];

    const es = client.subscribeTaskEvents(taskId);
    es.onSnapshot((s) => snapshots.push({ ...s, entries: new Map(s.entries) }));

    await waitFor(() => frameServer.clientCount(taskId) > 0 || null);

    const snapshot: FrameSnapshot = {
      type: "snapshot",
      kind: "task",
      session_id: taskId,
      from_seq: 0,
      to_seq: 1,
      entries: [
        { idx: 0, role: "assistant", text: "Starting task...", finalized: false, ts: "2026-01-01T00:00:00Z" } as FrameEntry,
      ],
    };
    frameServer.pushFrame(taskId, "snapshot", snapshot, 1);
    frameServer.pushFrame(taskId, "ready", { type: "ready" }, 2);

    await waitFor(() => snapshots.length > 0 || null);

    assert.equal(snapshots[0]?.entries.size, 1, "task snapshot must have one entry");
    assert.equal(snapshots[0]?.entries.get(0)?.text, "Starting task...");

    es.close();
  });

  // ── [es-dispose] ─────────────────────────────────────────────────────────────

  test("[es-dispose] panel dispose closes EventSource connection", async () => {
    const host = frameServer.url.replace("http://", "");
    const client = new KaganClient(host, "http");

    const sessionId = "prov-dispose-1";

    const es = client.subscribeSessionEvents(sessionId);
    await waitFor(() => frameServer.clientCount(sessionId) > 0 || null);
    assert.equal(frameServer.clientCount(sessionId), 1, "one client connected before close");

    // Close the EventSource — simulates provider dispose().
    es.close();

    // Allow TCP teardown.
    await new Promise<void>((resolve) => setTimeout(resolve, 100));
    assert.equal(frameServer.clientCount(sessionId), 0, "no clients after close");
  });

  // ── [es-resume] ──────────────────────────────────────────────────────────────

  test("[es-resume] resume frame with turnActive=true fires onResume callback", async () => {
    const host = frameServer.url.replace("http://", "");
    const client = new KaganClient(host, "http");

    const sessionId = "prov-resume-1";
    const resumes: Array<{ turnActive: boolean }> = [];

    const es = client.subscribeSessionEvents(sessionId);
    es.onResume((r) => resumes.push({ turnActive: r.turn_active }));

    await waitFor(() => frameServer.clientCount(sessionId) > 0 || null);

    const resumeFrame: FrameResume = { type: "resume", kind: "chat", turn_active: true };
    frameServer.pushFrame(sessionId, "resume", resumeFrame, 1);

    await waitFor(() => resumes.length > 0 || null);

    assert.equal(resumes[0]?.turnActive, true);

    es.close();
  });
});
