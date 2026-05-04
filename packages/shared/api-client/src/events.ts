// ============================================================================
// SSE Event Handling
// Supports automatic reconnection with exponential backoff
// ============================================================================

import type { SSEMessage } from "./wire";
import { SSEError } from "./errors";

export interface SSEEventMap {
  message: SSEMessage;
  connected: boolean;
  error: Error;
}

export type SSEEventListener<T extends keyof SSEEventMap> = (data: SSEEventMap[T]) => void;

export interface SSEManagerOptions {
  /** Base URL without protocol (e.g., "localhost:8765") */
  baseUrl: string;
  /** Protocol to use */
  protocol?: "http" | "https";
  /** Auth token for Bearer authentication */
  token?: string;
  /** Client type identifier for server tracking */
  clientType?: string;
  /** Client ID (auto-generated if not provided) */
  clientId?: string;
  /** Initial reconnection delay in ms (default: 1000) */
  initialReconnectDelay?: number;
  /** Maximum reconnection delay in ms (default: 30000) */
  maxReconnectDelay?: number;
  /** Polling fallback interval in ms when SSE is disconnected (default: 10000) */
  pollingInterval?: number;
  /** Custom fetch implementation (for testing or environments without native fetch) */
  fetchImpl?: typeof fetch;
}

/**
 * Event callback interface for SSE message handling.
 * Platform-agnostic - works in both browser and Node.js/VS Code contexts.
 */
export interface SSECallbacks {
  onMessage?: (message: SSEMessage) => void;
  onConnected?: (connected: boolean) => void;
  onError?: (error: Error) => void;
  /** Called when SSE is disconnected to trigger manual polling */
  onPollingFallback?: () => void;
}

/**
 * SSE Stream Manager with automatic reconnection.
 *
 * This class manages a Server-Sent Events connection with:
 * - Automatic reconnection with exponential backoff
 * - Auth token support
 * - Polling fallback when connection is lost
 * - Graceful shutdown
 *
 * @example
 * ```typescript
 * const sse = new SSEManager({
 *   baseUrl: "localhost:8765",
 *   token: "my-auth-token",
 *   clientType: "vscode"
 * });
 *
 * sse.connect({
 *   onMessage: (msg) => console.log("Received:", msg),
 *   onConnected: (connected) => console.log("Connected:", connected)
 * });
 *
 * // Later...
 * sse.dispose();
 * ```
 */
export class SSEManager {
  private controller: AbortController | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay: number;
  private disposed = false;
  private pollingTimer: ReturnType<typeof setInterval> | null = null;
  private callbacks: SSECallbacks = {};
  private readonly fetchImpl: typeof fetch;

  // Configuration properties (mutable via setters)
  private baseUrl: string;
  private protocol: "http" | "https";
  private token: string | undefined;
  private readonly clientType: string;
  private readonly clientId: string;
  private readonly initialReconnectDelay: number;
  private readonly maxReconnectDelay: number;
  private readonly pollingInterval: number;

  constructor(options: SSEManagerOptions) {
    this.baseUrl = normalizeBaseUrl(options.baseUrl);
    this.protocol = options.protocol ?? "http";
    this.token = options.token;
    this.clientType = options.clientType ?? "unknown";
    this.clientId = options.clientId ?? generateClientId();
    this.initialReconnectDelay = options.initialReconnectDelay ?? 1000;
    this.maxReconnectDelay = options.maxReconnectDelay ?? 30000;
    this.pollingInterval = options.pollingInterval ?? 10000;
    this.reconnectDelay = this.initialReconnectDelay;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  /**
   * Update the base URL. Takes effect on next reconnection.
   */
  setBaseUrl(url: string): void {
    this.baseUrl = normalizeBaseUrl(url);
  }

  /**
   * Update the protocol. Takes effect on next reconnection.
   */
  setProtocol(protocol: "http" | "https"): void {
    this.protocol = protocol;
  }

  /**
   * Update the auth token. Takes effect on next reconnection.
   */
  setToken(token: string | undefined): void {
    this.token = token;
  }

  /**
   * Check if currently connected.
   */
  get isConnected(): boolean {
    return this.controller !== null && !this.controller.signal.aborted;
  }

  /**
   * Start the SSE connection.
   */
  connect(callbacks: SSECallbacks): void {
    if (this.disposed) {
      throw new SSEError("Cannot connect: SSEManager has been disposed");
    }
    if (this.controller) {
      // Already connected or connecting
      return;
    }
    this.callbacks = callbacks;
    this.doConnect();
  }

  /**
   * Stop the SSE connection without disposing.
   * Connection can be restarted with connect().
   */
  stop(): void {
    this.clearReconnectTimer();
    this.stopPolling();
    this.controller?.abort();
    this.controller = null;
    this.callbacks.onConnected?.(false);
  }

  /**
   * Dispose the manager and clean up all resources.
   * After disposal, the manager cannot be reused.
   */
  dispose(): void {
    this.disposed = true;
    this.stop();
    this.callbacks = {};
  }

  private getFullUrl(path: string): string {
    return `${this.protocol}://${this.baseUrl}${path}`;
  }

  private getAuthHeaders(): Record<string, string> {
    if (!this.token) return {};
    return { Authorization: `Bearer ${this.token}` };
  }

  private startPolling(): void {
    if (this.pollingTimer || !this.callbacks.onPollingFallback) return;
    const cb = this.callbacks.onPollingFallback;
    this.pollingTimer = setInterval(() => cb(), this.pollingInterval);
  }

  private stopPolling(): void {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private async doConnect(): Promise<void> {
    if (this.disposed) return;

    this.controller = new AbortController();
    const { signal } = this.controller;

    try {
      const query = new URLSearchParams({
        client_type: this.clientType,
        client_id: this.clientId,
      });

      const response = await this.fetchImpl(
        this.getFullUrl(`/api/events/stream?${query.toString()}`),
        {
          headers: {
            Accept: "text/event-stream",
            ...this.getAuthHeaders(),
          },
          signal,
        }
      );

      if (!response.ok || !response.body) {
        throw new SSEError(`SSE request failed: ${response.status} ${response.statusText}`);
      }

      this.callbacks.onConnected?.(true);
      this.stopPolling();
      this.reconnectDelay = this.initialReconnectDelay;

      // Read the stream
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";

      try {
        while (!this.disposed && !signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += value;
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            const dataLine = part.split("\n").find((line) => line.startsWith("data: "));
            if (!dataLine) continue;

            try {
              const message = JSON.parse(dataLine.slice(6)) as SSEMessage;
              this.callbacks.onMessage?.(message);
            } catch {
              // Malformed JSON - skip silently (keepalives, etc.)
            }
          }
        }
      } finally {
        await reader.cancel().catch(() => {});
      }
    } catch (err) {
      if (signal.aborted) return; // Intentional disconnect

      const error = err instanceof Error ? err : new Error(String(err));
      this.callbacks.onError?.(error);
      this.callbacks.onConnected?.(false);
      this.startPolling();
    }

    // Reconnect with backoff if not disposed and not intentionally stopped
    if (!this.disposed && !signal.aborted) {
      this.controller = null;
      this.reconnectTimer = setTimeout(() => {
        this.doConnect();
      }, this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
    }
  }
}

/**
 * Simple SSE stream reader for one-off requests.
 * Yields parsed data events as an async generator.
 *
 * @example
 * ```typescript
 * for await (const event of streamSSE<ChatStreamEvent>("http://localhost:8765/api/chat/123/stream", {
 *   method: "POST",
 *   body: JSON.stringify({ text: "Hello" }),
 *   headers: { Authorization: "Bearer token" }
 * })) {
 *   console.log(event);
 * }
 * ```
 */
export async function* streamSSE<T>(
  url: string,
  options?: RequestInit,
  fetchImpl?: typeof fetch,
): AsyncGenerator<T> {
  const fetchFn = fetchImpl ?? globalThis.fetch.bind(globalThis);

  const response = await fetchFn(url, {
    ...options,
    headers: {
      ...options?.headers,
      Accept: "text/event-stream",
    },
  });

  if (!response.ok) {
    throw new SSEError(`SSE request failed: ${response.status} ${response.statusText}`);
  }

  if (!response.body) {
    throw new SSEError("SSE response has no body");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += value;
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        // Skip comments (keepalive lines starting with :)
        const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
        if (dataLine) {
          yield JSON.parse(dataLine.slice(6)) as T;
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}

// ----------------------------------------------------------------------------
// Utilities
// ----------------------------------------------------------------------------

function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function generateClientId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `client-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}
