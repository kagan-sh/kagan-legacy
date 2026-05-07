// Integration tests for the /attach and /detach chat participant commands.
//
// These tests run inside the Extension Development Host via @vscode/test-cli.
// They use a custom fake server that adds /api/v1/agents/running and
// /api/v1/sessions/:id/replay routes on top of the base fake server.
//
// TODO(vscode-chat-invoke): VS Code stable (1.96+) does not expose a public
// API to programmatically submit a prompt to a registered chat participant.
// The tests below verify the fake-server routes and the commands registration.
// When vscode.chat.sendRequest() is available, extend these tests to drive the
// participant directly.

import * as assert from "node:assert/strict";
import * as http from "node:http";
import { after, before, suite, test } from "mocha";
import * as vscode from "vscode";
import {
  TEST_SERVER_URL,
  createFakeKaganServer,
} from "../helpers/fake-kagan-server.js";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RUNNING_SESSION_ID = "sess-aaaa-bbbb-cccc-dddddddddddd";
const RUNNING_TASK_ID = "task-1111-2222-3333-444444444444";

const RUNNING_AGENTS_RESPONSE = {
  agents: [
    {
      task_id: RUNNING_TASK_ID,
      task_title: "Implement /attach feature",
      task_status: "IN_PROGRESS",
      session_id: RUNNING_SESSION_ID,
      agent_role: "worker",
      agent_backend: "claude-code",
      session_status: "RUNNING",
      started_at: "2026-05-07T10:00:00Z",
      last_event_at: "2026-05-07T10:05:00Z",
      input_tokens: 5000,
      output_tokens: 1200,
    },
  ],
};

const SESSION_REPLAY_RESPONSE = {
  events: [
    {
      id: "event-001",
      session_id: RUNNING_SESSION_ID,
      event_type: "AGENT_STARTED",
      payload: {},
      created_at: "2026-05-07T10:00:00Z",
    },
    {
      id: "event-002",
      session_id: RUNNING_SESSION_ID,
      event_type: "TEXT_DELTA",
      payload: { text: "Starting work on /attach feature." },
      created_at: "2026-05-07T10:01:00Z",
    },
  ],
  next_cursor: null,
  has_more: false,
};

// ---------------------------------------------------------------------------
// Attach-aware fake server (port 47869)
// ---------------------------------------------------------------------------

const ATTACH_SERVER_PORT = 47869;

function createAttachRouteServer(port: number): {
  start: () => Promise<void>;
  stop: () => Promise<void>;
} {
  let server: http.Server | null = null;

  return {
    async start() {
      if (server) return;
      server = http.createServer((req, res) => {
        void handleAttachRequest(req, res);
      });
      await new Promise<void>((resolve, reject) => {
        server!.once("error", reject);
        server!.listen(port, "127.0.0.1", resolve);
      });
    },

    async stop() {
      const s = server;
      server = null;
      if (!s) return;
      await new Promise<void>((resolve, reject) => {
        s.close((err) => (err ? reject(err) : resolve()));
      });
    },
  };
}

async function handleAttachRequest(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const base = `http://127.0.0.1:${ATTACH_SERVER_PORT}`;
  const url = new URL(req.url ?? "/", base);

  // GET /health
  if (req.method === "GET" && url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  // GET /api/settings
  if (req.method === "GET" && url.pathname === "/api/settings") {
    jsonOk(res, {});
    return;
  }

  // GET /api/tasks/counts
  if (req.method === "GET" && url.pathname === "/api/tasks/counts") {
    jsonOk(res, { BACKLOG: 0, IN_PROGRESS: 1, REVIEW: 0, DONE: 0 });
    return;
  }

  // GET /api/v1/agents/running
  if (req.method === "GET" && url.pathname === "/api/v1/agents/running") {
    jsonOk(res, RUNNING_AGENTS_RESPONSE);
    return;
  }

  // GET /api/v1/sessions/:id/replay
  const replayMatch = /^\/api\/v1\/sessions\/([^/]+)\/replay$/.exec(url.pathname);
  if (req.method === "GET" && replayMatch) {
    jsonOk(res, SESSION_REPLAY_RESPONSE);
    return;
  }

  // GET /api/events/stream — SSE keep-alive
  if (req.method === "GET" && url.pathname === "/api/events/stream") {
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    });
    res.write(": connected\n\n");
    req.on("close", () => res.end());
    return;
  }

  res.writeHead(404, { "content-type": "application/json" });
  res.end(
    JSON.stringify({
      ok: false,
      data: null,
      error: `attach-server: unhandled ${req.method} ${url.pathname}`,
      error_code: null,
    }),
  );
}

function jsonOk(res: http.ServerResponse, data: unknown): void {
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ ok: true, data, error: null, error_code: null }));
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

function httpGet(host: string, port: number, path: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = http.request({ host, port, path, method: "GET" }, (res) => {
      let body = "";
      res.on("data", (chunk: Buffer) => { body += chunk.toString(); });
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
    });
    req.on("error", reject);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

suite("Chat participant: /attach and /detach", () => {
  const baseServer = createFakeKaganServer();
  const attachServer = createAttachRouteServer(ATTACH_SERVER_PORT);

  before(async () => {
    await baseServer.start();
    await attachServer.start();

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
    await attachServer.stop();
  });

  test("kagan.attachToSession command is registered after activation", async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(
      commands.includes("kagan.attachToSession"),
      "expected kagan.attachToSession to be registered",
    );
  });

  test("kagan.detachFromSession command is registered after activation", async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(
      commands.includes("kagan.detachFromSession"),
      "expected kagan.detachFromSession to be registered",
    );
  });

  test("fake attach-server returns running agents", async () => {
    const { status, body } = await httpGet(
      "127.0.0.1",
      ATTACH_SERVER_PORT,
      "/api/v1/agents/running",
    );
    assert.equal(status, 200);
    const env = JSON.parse(body) as { ok: boolean; data: typeof RUNNING_AGENTS_RESPONSE };
    assert.equal(env.ok, true);
    assert.equal(env.data.agents.length, 1);
    assert.equal(env.data.agents[0].session_id, RUNNING_SESSION_ID);
  });

  test("fake attach-server returns session replay events", async () => {
    const { status, body } = await httpGet(
      "127.0.0.1",
      ATTACH_SERVER_PORT,
      `/api/v1/sessions/${RUNNING_SESSION_ID}/replay`,
    );
    assert.equal(status, 200);
    const env = JSON.parse(body) as { ok: boolean; data: typeof SESSION_REPLAY_RESPONSE };
    assert.equal(env.ok, true);
    assert.equal(env.data.events.length, 2);
    assert.equal(env.data.events[0].event_type, "AGENT_STARTED");
  });

  test("fake attach-server returns 404 for unknown routes", async () => {
    const { status } = await httpGet("127.0.0.1", ATTACH_SERVER_PORT, "/api/unknown");
    assert.equal(status, 404);
  });

  // TODO(vscode-chat-invoke): The following test cases require
  // vscode.chat.sendRequest() which is not available in VS Code 1.96 stable.
  //
  // When available, un-skip and wire these scenarios:
  //  1. /attach <session-id> → verify chat thread receives replay events + detach button.
  //  2. /attach <task-id-prefix> → verify resolution via running agents API.
  //  3. /attach <bad-id> → verify error message "Unknown task or session".
  //  4. /detach when not attached → verify "Not currently attached" message.
  //  5. /detach after attach → verify state cleared and detach confirmation.
  test.skip(
    "streams replay then live tail after /attach <session-id>",
    async () => {
      // Blocked: vscode.chat.sendRequest() not available in VS Code 1.96 stable.
    },
  );
});
