import { EventEmitter } from "node:events";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getLocalServerTarget,
  LocalServerSupervisor,
  type ServerClient,
  type ServerLogSink,
  type SpawnedProcess,
} from "./supervisor.js";

describe("getLocalServerTarget", () => {
  it("builds a launch command for localhost URLs", () => {
    expect(getLocalServerTarget("http://localhost:8765", "kagan")).toEqual({
      command: "kagan",
      args: ["web", "--host", "127.0.0.1", "--port", "8765", "--no-open"],
      displayHost: "localhost",
      port: "8765",
    });
  });

  it("refuses remote URLs", () => {
    expect(getLocalServerTarget("http://10.0.0.20:8765", "kagan")).toBeNull();
    expect(getLocalServerTarget("https://localhost:8765", "kagan")).toBeNull();
  });
});

describe("LocalServerSupervisor", () => {
  let log: TestLogSink;

  beforeEach(() => {
    log = new TestLogSink();
  });

  it("starts the server when localhost is unreachable and becomes healthy", async () => {
    const child = new FakeProcess();
    const spawn = vi.fn(() => child);
    const client = new SequenceClient("http://127.0.0.1:8765", [false, false, true]);
    const supervisor = new LocalServerSupervisor(log, spawn);

    await expect(supervisor.ensureRunning(client, "kagan")).resolves.toBe(true);
    expect(spawn).toHaveBeenCalledWith(
      "kagan",
      ["web", "--host", "127.0.0.1", "--port", "8765", "--no-open"],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
  });

  it("does not try to start remote servers", async () => {
    const spawn = vi.fn();
    const client = new SequenceClient("http://10.0.0.20:8765", [false]);
    const supervisor = new LocalServerSupervisor(log, spawn);

    await expect(supervisor.ensureRunning(client, "kagan")).resolves.toBe(false);
    expect(spawn).not.toHaveBeenCalled();
  });

  it("surfaces spawn failures clearly", async () => {
    const child = new FakeProcess();
    const spawn = vi.fn(() => {
      queueMicrotask(() => child.emit("error", new Error("ENOENT")));
      return child;
    });
    const client = new SequenceClient("http://127.0.0.1:8765", [false, false, false]);
    const supervisor = new LocalServerSupervisor(log, spawn);

    await expect(supervisor.ensureRunning(client, "kagan")).rejects.toThrow(
      /Failed to start Kagan server via "kagan"/,
    );
  });
});

class TestLogSink implements ServerLogSink {
  readonly lines: string[] = [];

  appendLine(message: string): void {
    this.lines.push(message);
  }

  show(): void {}
}

class SequenceClient implements ServerClient {
  private index = 0;

  constructor(
    private readonly baseUrl: string,
    private readonly results: boolean[],
  ) {}

  getBaseUrl(): string {
    return this.baseUrl;
  }

  async ping(): Promise<boolean> {
    const value = this.results[Math.min(this.index, this.results.length - 1)] ?? false;
    this.index += 1;
    return value;
  }
}

class FakeProcess extends EventEmitter implements SpawnedProcess {
  readonly stdout = new EventEmitter() as unknown as NodeJS.ReadableStream;
  readonly stderr = new EventEmitter() as unknown as NodeJS.ReadableStream;

  kill(): boolean {
    this.emit("exit", 0, null);
    return true;
  }
}
