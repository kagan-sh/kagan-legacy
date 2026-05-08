// Integration tests for the @kagan chat participant and the KaganClient chat
// streaming path it relies on.
//
// These tests run inside the Extension Development Host via @vscode/test-cli.
// They use the fake Kagan server from test/helpers/ — a real HTTP/SSE server,
// not a pile of mocks.
//
// TODO(vscode-chat-invoke): As of 2026-05-08, @types/vscode@1.115.0 exposes only
// vscode.chat.createChatParticipant — there is no vscode.chat.sendRequest() or any
// equivalent test-host API to programmatically submit a prompt to a registered chat
// participant and collect its response stream. Participant requests can only be
// initiated from the Chat panel UI in the Extension Development Host.
// Investigated: vscode.commands.executeCommand, executeWorkbench, and the
// @vscode/test-electron 2.5.2 API surface — none provide a programmatic path.
// When the VS Code team ships a stable sendRequest()-equivalent (tracked at
// https://github.com/microsoft/vscode/issues/199908), replace the skip block with
// a real participant invocation against the fake chat server defined above.
// See: https://code.visualstudio.com/api/extension-guides/chat

import * as assert from "node:assert/strict";
import * as http from "node:http";
import { after, before, suite, test } from "mocha";
import * as vscode from "vscode";
import {
  TEST_SERVER_URL,
  createFakeKaganServer,
} from "../helpers/fake-kagan-server.js";

// ---------------------------------------------------------------------------
// Chat-session fixtures
// ---------------------------------------------------------------------------

const CHAT_SESSION_ID = "chat-session-1";

const TEST_CHAT_SESSION = {
  id: CHAT_SESSION_ID,
  label: "E2E smoke session",
  agent_backend: "claude-code",
  source: "vscode",
  message_count: 0,
};

/** Scripted SSE frames that the fake stream endpoint emits. */
const CHAT_STREAM_FRAMES = [
  `data: ${JSON.stringify({ t: "CHAT_CHUNK", content: "Hello" })}\n\n`,
  `data: ${JSON.stringify({ t: "CHAT_CHUNK", content: ", world" })}\n\n`,
  `data: ${JSON.stringify({ t: "CHAT_DONE", full_response: "Hello, world" })}\n\n`,
];

// ---------------------------------------------------------------------------
// Chat-aware fake server
//
// The base FakeKaganServer (test/helpers/) handles tasks, diffs, events, and
// the global SSE stream. We add a second, standalone HTTP server on port 47867
// that serves the chat-specific routes:
//   GET  /api/settings
//   GET  /api/v1/sessions
//   GET  /api/chat/sessions/:id/watch (live orchestrator chat SSE)
//   GET  /api/chat/sessions/:id/messages
//   POST /api/chat/:id/stream
//
// Both servers are started before the suite and stopped after.
// ---------------------------------------------------------------------------

const CHAT_SERVER_PORT = 47867;

function createChatRouteServer(port: number): {
  start: () => Promise<void>;
  stop: () => Promise<void>;
} {
  let server: http.Server | null = null;
  const sseClients = new Set<http.ServerResponse>();

  return {
    async start() {
      if (server) return;
      server = http.createServer((req, res) => {
        void handleChatRequest(req, res, sseClients);
      });
      await new Promise<void>((resolve, reject) => {
        server!.once("error", reject);
        server!.listen(port, "127.0.0.1", resolve);
      });
    },

    async stop() {
      for (const client of sseClients) client.end();
      sseClients.clear();
      const s = server;
      server = null;
      if (!s) return;
      await new Promise<void>((resolve, reject) => {
        s.close((err) => (err ? reject(err) : resolve()));
      });
    },
  };
}

async function handleChatRequest(
  req: http.IncomingMessage,
  res: http.ServerResponse,
  sseClients: Set<http.ServerResponse>,
): Promise<void> {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${CHAT_SERVER_PORT}`);

  // GET /api/settings — needed by getOrCreateSession
  if (req.method === "GET" && url.pathname === "/api/settings") {
    jsonOk(res, { chat_last_active_session: CHAT_SESSION_ID });
    return;
  }

  // GET /api/v1/sessions
  if (req.method === "GET" && url.pathname === "/api/v1/sessions") {
    jsonOk(res, {
      sessions: [{
        id: `orch:${TEST_CHAT_SESSION.id}`,
        type: "orchestrator",
        role: null,
        status: "idle",
        title: TEST_CHAT_SESSION.label,
        backend: TEST_CHAT_SESSION.agent_backend,
        project_id: null,
        task_id: null,
        session_id: null,
        chat_session_id: TEST_CHAT_SESSION.id,
        updated_at: TEST_CHAT_SESSION.updated_at,
        capabilities: {
          can_chat: true,
          can_stream: true,
          can_replay: false,
          can_stop: true,
          can_close: true,
          has_kagan_tools: true,
        },
      }],
    });
    return;
  }

  // GET /api/chat/sessions/:id/messages?after_id=N — catch-up for live chat SSE
  if (
    req.method === "GET" &&
    /^\/api\/chat\/sessions\/[^/]+\/messages$/.test(url.pathname)
  ) {
    jsonOk(res, []);
    return;
  }

  // GET /api/chat/sessions/:id/watch — live orchestrator chat keep-alive SSE
  if (
    req.method === "GET" &&
    /^\/api\/chat\/sessions\/[^/]+\/watch$/.test(url.pathname)
  ) {
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    });
    res.write(": connected\n\n");
    sseClients.add(res);
    req.on("close", () => {
      sseClients.delete(res);
    });
    return;
  }

  // POST /api/chat/:id/stream — scripted CHAT_CHUNK × 2 then CHAT_DONE
  if (
    req.method === "POST" &&
    /^\/api\/chat\/[^/]+\/stream$/.test(url.pathname)
  ) {
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
    });
    let i = 0;
    const sendNext = () => {
      if (i >= CHAT_STREAM_FRAMES.length) {
        res.end();
        return;
      }
      res.write(CHAT_STREAM_FRAMES[i]);
      i++;
      setTimeout(sendNext, 10);
    };
    sendNext();
    return;
  }

  res.writeHead(404, { "content-type": "application/json" });
  res.end(
    JSON.stringify({
      ok: false,
      data: null,
      error: `chat-route-server: unhandled ${req.method} ${url.pathname}`,
      error_code: null,
    }),
  );
}

function jsonOk(res: http.ServerResponse, data: unknown): void {
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ ok: true, data, error: null, error_code: null }));
}

// ---------------------------------------------------------------------------
// HTTP helpers (no external deps)
// ---------------------------------------------------------------------------

function httpGet(host: string, port: number, path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const req = http.request({ host, port, path, method: "GET" }, (res) => {
      let body = "";
      res.on("data", (chunk: Buffer) => {
        body += chunk.toString();
      });
      res.on("end", () => resolve(body));
    });
    req.on("error", reject);
    req.end();
  });
}

function httpPostSSE(
  host: string,
  port: number,
  path: string,
  body: string,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host,
        port,
        path,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        let raw = "";
        res.on("data", (chunk: Buffer) => {
          raw += chunk.toString();
        });
        res.on("end", () => resolve(raw));
      },
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function parseSSEFrames(raw: string): Record<string, unknown>[] {
  return raw.split("\n\n").flatMap((block) => {
    const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
    if (!dataLine) return [];
    try {
      return [JSON.parse(dataLine.slice(6)) as Record<string, unknown>];
    } catch {
      return [];
    }
  });
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

suite("Chat participant", () => {
  const baseServer = createFakeKaganServer();
  const chatServer = createChatRouteServer(CHAT_SERVER_PORT);

  before(async () => {
    await baseServer.start();
    await chatServer.start();

    const extension = vscode.extensions.getExtension("kagan.kagan-vscode");
    assert.ok(extension, "expected the Kagan extension to be installed");

    await vscode.workspace
      .getConfiguration("kagan")
      .update("serverUrl", TEST_SERVER_URL, vscode.ConfigurationTarget.Workspace);
    await vscode.workspace
      .getConfiguration("kagan")
      .update("autoConnect", false, vscode.ConfigurationTarget.Workspace);

    await extension.activate();
  });

  after(async () => {
    await baseServer.stop();
    await chatServer.stop();
  });

  test("kagan.chat.open command is registered after extension activation", async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(
      commands.includes("kagan.chat.open"),
      "expected kagan.chat.open to be registered after activation",
    );
  });

  test("fake server chat/stream endpoint emits CHAT_CHUNK frames and a CHAT_DONE frame", async () => {
    // Exercise the HTTP route that KaganClient.chatStream() calls. This validates
    // the fake server wiring and the SSE frame format the participant consumes.
    const raw = await httpPostSSE(
      "127.0.0.1",
      CHAT_SERVER_PORT,
      `/api/chat/${CHAT_SESSION_ID}/stream`,
      JSON.stringify({ text: "hello" }),
    );

    const events = parseSSEFrames(raw);
    assert.ok(events.length >= 3, `expected at least 3 SSE frames, got ${events.length}`);

    const chunkEvents = events.filter((e) => e.t === "CHAT_CHUNK");
    assert.ok(chunkEvents.length >= 2, "expected at least 2 CHAT_CHUNK frames");

    const doneEvent = events.find((e) => e.t === "CHAT_DONE");
    assert.ok(doneEvent, "expected a CHAT_DONE frame in the stream");
    assert.equal(
      (doneEvent as { t: string; full_response: string }).full_response,
      "Hello, world",
      "CHAT_DONE.full_response should equal the concatenated chunks",
    );
  });

  test("fake server unified sessions endpoint returns the test session", async () => {
    // Exercise the route that KaganClient.getSessions() calls.
    const raw = await httpGet("127.0.0.1", CHAT_SERVER_PORT, "/api/v1/sessions");
    const envelope = JSON.parse(raw) as {
      ok: boolean;
      data: { sessions: Array<{ id: string; chat_session_id: string }> };
    };
    assert.equal(envelope.ok, true);
    assert.equal(envelope.data.sessions.length, 1);
    assert.equal(envelope.data.sessions[0].id, `orch:${CHAT_SESSION_ID}`);
    assert.equal(envelope.data.sessions[0].chat_session_id, CHAT_SESSION_ID);
  });

  // TODO(vscode-chat-invoke): As of 2026-05-08, vscode.chat.sendRequest() is not
  // available in @types/vscode@1.115.0 or @vscode/test-electron@2.5.2.
  // The vscode.chat namespace exports only createChatParticipant — there is no
  // test-host path to invoke a participant and collect its response stream.
  // When the API ships, un-skip and implement per the shape described below:
  //   1. Point the extension at the chat-aware fake server on port 47867.
  //   2. Call vscode.chat.sendRequest("kagan.agent", { prompt: "hello" }, token).
  //   3. Collect all MarkdownPart items from the response stream.
  //   4. Assert concatenated text contains "Hello, world".
  //   5. Assert no error event was emitted during the stream.
  test.skip(
    "streams a response from the fake Kagan server via the @kagan chat participant",
    async () => {
      // Blocked (2026-05-08): vscode.chat.sendRequest() not in @types/vscode@1.115.0.
    },
  );
});
