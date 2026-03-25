import { afterEach, describe, expect, it, vi } from "vitest";
import { KaganClient } from "./client.js";

describe("KaganClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preserves plain-text HTTP failures from the server", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Unsupported method ('POST')", {
        status: 501,
        statusText: "Unsupported method ('POST')",
        headers: { "content-type": "text/plain" },
      }),
    );

    const client = new KaganClient("http://127.0.0.1:8765");

    await expect(client.createTask({ title: "Ship it" })).rejects.toMatchObject({
      status: 501,
      detail:
        "Server at http://127.0.0.1:8765 does not look like a Kagan API (Unsupported method ('POST')). Check kagan.serverUrl.",
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

    const client = new KaganClient("http://127.0.0.1:8765");

    await expect(client.verifyApi()).resolves.toBeUndefined();
    expect(globalThis.fetch).toHaveBeenCalledWith("http://127.0.0.1:8765/api/settings", {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      body: undefined,
    });
  });
});
