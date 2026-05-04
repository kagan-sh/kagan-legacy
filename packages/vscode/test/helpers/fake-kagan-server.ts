import * as http from "node:http";
import type { AddressInfo } from "node:net";
import type { WireTask } from "@kagan/shared-api-client";

export const TEST_SERVER_PORT = 47865;
export const TEST_SERVER_URL = `http://127.0.0.1:${TEST_SERVER_PORT}`;

export const TEST_TASK: WireTask = {
  id: "task-1",
  title: "Review extension diff",
  description: "Validate that the VS Code client can open Kagan review artifacts.",
  status: "REVIEW",
  priority: "HIGH",
  base_branch: "main",
  acceptance_criteria: [
    { id: "criterion-1", task_id: "task-1", ordinal: 0, text: "Open the diff view" },
    { id: "criterion-2", task_id: "task-1", ordinal: 1, text: "Open the review summary" },
  ],
  agent_backend: "claude-code",
  launcher: "vscode",
  review_approved: false,
  review_verdicts: [
    {
      id: "verdict-1",
      criterion_id: "criterion-1",
      session_id: "session-1",
      verdict: "PASS",
      reason: "Diff view opens correctly.",
    },
    {
      id: "verdict-2",
      criterion_id: "criterion-2",
      session_id: "session-1",
      verdict: "FAIL",
      reason: "Review still needs a human check.",
    },
  ],
  updated_at: "2026-03-25T12:00:00Z",
  last_event_at: "2026-03-25T12:00:00Z",
  has_workspace: true,
  review_running: false,
  active_session: {
    id: "session-1",
    status: "RUNNING",
    launcher: "vscode",
    agent_backend: "claude-code",
    started_at: "2026-03-25T12:00:00Z",
    context_window_used: null,
    context_window_size: null,
    cost_amount: null,
    cost_currency: null,
  },
};

export const TEST_DIFF = [
  "diff --git a/README.md b/README.md",
  "index 0000000..1111111 100644",
  "--- a/README.md",
  "+++ b/README.md",
  "@@ -1 +1,2 @@",
  "-Old line",
  "+Old line",
  "+New line",
  "",
].join("\n");

export function createFakeKaganServer(port: number = TEST_SERVER_PORT): FakeKaganServer {
  return new FakeKaganServer(port);
}

export class FakeKaganServer {
  private server: http.Server | null = null;
  private readonly sseClients = new Set<http.ServerResponse>();

  constructor(private readonly port: number) {}

  async start(): Promise<void> {
    if (this.server) {
      return;
    }

    this.server = http.createServer((request, response) => {
      this.handleRequest(request, response).catch((error: unknown) => {
        response.writeHead(500, { "content-type": "application/json" });
        response.end(JSON.stringify(envelope(null, false, String(error))));
      });
    });

    await new Promise<void>((resolve, reject) => {
      this.server?.once("error", reject);
      this.server?.listen(this.port, "127.0.0.1", () => resolve());
    });
  }

  async stop(): Promise<void> {
    for (const client of this.sseClients) {
      client.end();
    }
    this.sseClients.clear();

    const server = this.server;
    this.server = null;
    if (!server) {
      return;
    }

    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }

  get url(): string {
    const address = this.server?.address() as AddressInfo | null;
    return address ? `http://127.0.0.1:${address.port}` : TEST_SERVER_URL;
  }

  private async handleRequest(
    request: http.IncomingMessage,
    response: http.ServerResponse,
  ): Promise<void> {
    const url = new URL(request.url ?? "/", TEST_SERVER_URL);

    if (request.method === "GET" && url.pathname === "/health") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ status: "ok" }));
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/tasks/counts") {
      this.json(response, { BACKLOG: 0, IN_PROGRESS: 0, REVIEW: 1, DONE: 0 });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/tasks/task-1") {
      this.json(response, TEST_TASK);
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/tasks/task-1/diff") {
      this.json(response, { files: 1, insertions: 1, deletions: 1 });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/tasks/task-1/diff/files") {
      this.json(response, {
        task_id: TEST_TASK.id,
        files: [
          {
            path: "README.md",
            status: "modified",
            insertions: 1,
            deletions: 1,
          },
        ],
      });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/tasks/task-1/diff/raw") {
      this.json(response, { task_id: TEST_TASK.id, diff: TEST_DIFF });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/settings") {
      this.json(response, { attached_launcher: "vscode" });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/tasks/task-1/worktree") {
      this.json(response, {
        task_id: TEST_TASK.id,
        worktree: { path: "/tmp/kagan-task-1", branch: "task/task-1" },
      });
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/events/stream") {
      response.writeHead(200, {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
        connection: "keep-alive",
      });
      response.write(": connected\n\n");
      this.sseClients.add(response);
      request.on("close", () => {
        this.sseClients.delete(response);
      });
      return;
    }

    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify(envelope(null, false, `Unhandled route: ${request.method} ${url.pathname}`)));
  }

  private json(response: http.ServerResponse, data: unknown): void {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(envelope(data)));
  }
}

function envelope(data: unknown, ok: boolean = true, error: string | null = null) {
  return {
    ok,
    data: ok ? data : null,
    error,
    error_code: null,
  };
}
