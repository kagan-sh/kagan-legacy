import { afterEach, describe, expect, it, vi } from "vitest";
import { KaganApiClient } from "@kagan/shared-api-client";
import { KaganClient } from "./client.js";

describe("KaganClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is an instance of the shared KaganApiClient", () => {
    const client = new KaganClient("127.0.0.1:8765");
    expect(client).toBeInstanceOf(KaganApiClient);
  });

  it("sends auth header via streamRequest when token is configured", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("", { status: 200 }),
    );

    const client = new KaganClient("127.0.0.1:8765", "http", "test-token");
    await client.ping();

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/health",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer test-token" }),
      }),
    );
  });

  it("throws ApiError with TURN_IN_PROGRESS error code on 409 from chatStream", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error_code: "TURN_IN_PROGRESS" }), { status: 409 }),
    );

    const client = new KaganClient("127.0.0.1:8765");
    await expect(client.chatStream("session-1", "hello")).rejects.toMatchObject({
      status: 409,
      errorCode: "TURN_IN_PROGRESS",
    });
  });

  it("preserves plain-text HTTP failures from the server", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Unsupported method ('POST')", {
        status: 501,
        statusText: "Unsupported method ('POST')",
        headers: { "content-type": "text/plain" },
      }),
    );

    const client = new KaganClient("127.0.0.1:8765");

    await expect(client.createTask({ title: "Ship it" })).rejects.toMatchObject({
      status: 501,
      detail:
        "Server at 127.0.0.1:8765 does not look like a Kagan API (Unsupported method ('POST')). Check the server URL and protocol.",
    });
  });

  it("verifies the server by reading a real Kagan API endpoint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          data: { attached_launcher: "vscode" },
          error: null,
          error_code: null,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    const client = new KaganClient("127.0.0.1:8765");

    await expect(client.verifyApi()).resolves.toBeUndefined();
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8765/api/settings", {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      body: undefined,
    });
  });

  it("loads chat agent availability from the server", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            backends: [
              { name: "claude-code", available: true, reference: true },
              { name: "codex", available: false, reference: true },
            ],
            default: "claude-code",
          },
          error: null,
          error_code: null,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    const client = new KaganClient("127.0.0.1:8765");

    await expect(client.getChatAgents()).resolves.toEqual({
      backends: [
        { name: "claude-code", available: true, reference: true },
        { name: "codex", available: false, reference: true },
      ],
      default: "claude-code",
    });
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8765/api/chat/agents", {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      body: undefined,
    });
  });

  it("lists unified sessions", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            sessions: [
              {
                id: "sess-1",
                type: "orchestrator",
                role: null,
                status: "RUNNING",
                title: "Orchestrator",
                backend: null,
                project_id: null,
                task_id: null,
                session_id: null,
                chat_session_id: null,
                updated_at: "2026-05-08T10:00:00Z",
                capabilities: {
                  can_chat: true,
                  can_stream: true,
                  can_replay: true,
                  can_stop: true,
                  can_close: true,
                  has_kagan_tools: true,
                },
              },
            ],
          },
          error: null,
          error_code: null,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    const client = new KaganClient("127.0.0.1:8765");
    const result = await client.getSessions();
    expect(result.sessions).toHaveLength(1);
    expect(result.sessions[0].type).toBe("orchestrator");
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/v1/sessions",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("creates a unified session", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            id: "sess-new",
            type: "general",
            role: null,
            status: "RUNNING",
            title: "General",
            backend: "claude-code",
            project_id: null,
            task_id: null,
            session_id: null,
            chat_session_id: null,
            updated_at: "2026-05-08T10:00:00Z",
            capabilities: {
              can_chat: true,
              can_stream: true,
              can_replay: true,
              can_stop: true,
              can_close: true,
              has_kagan_tools: false,
            },
          },
          error: null,
          error_code: null,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    const client = new KaganClient("127.0.0.1:8765");
    const result = await client.createSession({ type: "general", backend: "claude-code" });
    expect(result.type).toBe("general");
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/v1/sessions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("stops a session", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ ok: true, data: {}, error: null, error_code: null }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const client = new KaganClient("127.0.0.1:8765");
    await expect(client.stopSession("sess-1")).resolves.toEqual({});
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/v1/sessions/sess-1/stop",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("closes a session", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ ok: true, data: {}, error: null, error_code: null }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const client = new KaganClient("127.0.0.1:8765");
    await expect(client.closeSession("sess-1")).resolves.toEqual({});
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/v1/sessions/sess-1/close",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
