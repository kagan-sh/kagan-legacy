import { spawn } from "node:child_process";

export interface ServerLogSink {
  appendLine(message: string): void;
  show(preserveFocus?: boolean): void;
}

export interface ServerClient {
  getBaseUrl(): string;
  ping(): Promise<boolean>;
}

export interface SpawnedProcess {
  pid?: number;
  stdout?: NodeJS.ReadableStream | null;
  stderr?: NodeJS.ReadableStream | null;
  once(event: "error", listener: (error: Error) => void): this;
  once(event: "exit", listener: (code: number | null, signal: NodeJS.Signals | null) => void): this;
  kill(signal?: NodeJS.Signals | number): boolean;
}

export type SpawnProcess = (
  command: string,
  args: string[],
  options: { stdio: ["ignore", "pipe", "pipe"] },
) => SpawnedProcess;

interface LocalServerTarget {
  command: string;
  args: string[];
  displayHost: string;
  port: string;
}

const STARTUP_TIMEOUT_MS = 12_000;
const STARTUP_POLL_MS = 250;
const SHUTDOWN_TIMEOUT_MS = 3_000;

export class LocalServerSupervisor {
  private child: SpawnedProcess | null = null;
  private startPromise: Promise<void> | null = null;
  private lastErrorLine: string | null = null;

  constructor(
    private readonly log: ServerLogSink,
    private readonly spawnProcess: SpawnProcess = defaultSpawnProcess,
  ) {}

  async ensureRunning(client: ServerClient, command: string): Promise<boolean> {
    const target = getLocalServerTarget(client.getBaseUrl(), command);
    if (!target) {
      return false;
    }

    if (await client.ping()) {
      return false;
    }

    if (this.startPromise) {
      await this.startPromise;
      return true;
    }

    this.startPromise = this.start(client, target).finally(() => {
      this.startPromise = null;
    });
    await this.startPromise;
    return true;
  }

  dispose(): void {
    const child = this.child;
    if (!child) {
      return;
    }
    this.child = null;
    child.kill("SIGTERM");
    child.kill("SIGKILL");
  }

  async stop(): Promise<void> {
    await this.stopChild(this.child);
  }

  private async start(client: ServerClient, target: LocalServerTarget): Promise<void> {
    this.lastErrorLine = null;
    this.log.appendLine(
      `[kagan] starting local server: ${target.command} ${target.args.join(" ")}`,
    );

    const child = this.spawnProcess(target.command, target.args, {
      stdio: ["ignore", "pipe", "pipe"],
    });
    this.attachOutput(child);

    let startupDone = false;
    const startupFailure = new Promise<never>((_, reject) => {
      child.once("error", (error) => {
        if (startupDone) return;
        reject(
          new Error(
            `Failed to start Kagan server via "${target.command}". ${error.message}. ` +
              `Set kagan.serverCommand if the CLI is installed under a different name.`,
          ),
        );
      });
      child.once("exit", (code, signal) => {
        if (startupDone) return;
        const detail =
          this.lastErrorLine ??
          (signal
            ? `process terminated with signal ${signal}`
            : `process exited with code ${code ?? "unknown"}`);
        reject(
          new Error(
            `Kagan server exited during startup on ${target.displayHost}:${target.port}: ${detail}`,
          ),
        );
      });
    });

    const healthy = await Promise.race([waitForHealthy(client), startupFailure]);
    startupDone = true;

    if (!healthy) {
      await this.stopChild(child);
      throw new Error(
        `Timed out waiting for Kagan server on ${target.displayHost}:${target.port}. ` +
          `Check the Kagan Server output for details.`,
      );
    }

    this.child = child;
    child.once("exit", () => {
      if (this.child === child) {
        this.child = null;
      }
    });
    this.log.appendLine(`[kagan] local server is ready at ${client.getBaseUrl()}`);
  }

  private attachOutput(child: SpawnedProcess): void {
    child.stdout?.on("data", (chunk) => {
      for (const line of splitLines(chunk)) {
        this.log.appendLine(`[server] ${line}`);
      }
    });
    child.stderr?.on("data", (chunk) => {
      for (const line of splitLines(chunk)) {
        this.lastErrorLine = line;
        this.log.appendLine(`[server:stderr] ${line}`);
      }
    });
  }

  private async stopChild(child: SpawnedProcess | null): Promise<void> {
    if (!child) {
      return;
    }
    if (this.child === child) {
      this.child = null;
    }
    const exited = new Promise<void>((resolve) => {
      child.once("exit", () => resolve());
      child.once("error", () => resolve());
    });
    let fallback: NodeJS.Timeout | null = null;
    const forced = new Promise<void>((resolve) => {
      fallback = setTimeout(() => {
        child.kill("SIGKILL");
        resolve();
      }, SHUTDOWN_TIMEOUT_MS);
    });

    child.kill("SIGTERM");
    try {
      await Promise.race([exited, forced]);
    } finally {
      if (fallback) {
        clearTimeout(fallback);
      }
    }
  }
}

export function getLocalServerTarget(
  baseUrl: string,
  command: string,
): LocalServerTarget | null {
  let url: URL;
  try {
    url = new URL(baseUrl);
  } catch {
    return null;
  }

  if (url.protocol !== "http:") {
    return null;
  }

  const host = normalizeLocalHost(url.hostname);
  if (host === null) {
    return null;
  }

  const port = url.port || "80";
  return {
    command,
    args: ["serve", "--host", host, "--port", port],
    displayHost: url.hostname,
    port,
  };
}

function normalizeLocalHost(hostname: string): string | null {
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return "127.0.0.1";
  }
  if (hostname === "::1" || hostname === "[::1]") {
    return "::1";
  }
  return null;
}

async function waitForHealthy(client: ServerClient): Promise<boolean> {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await client.ping()) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, STARTUP_POLL_MS));
  }
  return false;
}

function defaultSpawnProcess(
  command: string,
  args: string[],
  options: { stdio: ["ignore", "pipe", "pipe"] },
): SpawnedProcess {
  return spawn(command, args, options);
}

function splitLines(chunk: unknown): string[] {
  return String(chunk)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}
