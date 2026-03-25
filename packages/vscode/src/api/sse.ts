// SSE stream reader for Kagan real-time events.
// "Readability counts." — async generator, no callbacks, no event bus.

import * as vscode from "vscode";
import type { SSEMessage } from "./types.js";

export class SSEStream implements vscode.Disposable {
  private controller: AbortController | null = null;
  private reconnectDelay = 1000;
  private disposed = false;

  private readonly _onMessage = new vscode.EventEmitter<SSEMessage>();
  readonly onMessage = this._onMessage.event;

  private readonly _onConnected = new vscode.EventEmitter<boolean>();
  readonly onConnected = this._onConnected.event;

  constructor(private baseUrl: string) {}

  setBaseUrl(url: string): void {
    this.baseUrl = url.replace(/\/+$/, "");
  }

  start(): void {
    if (this.controller) return;
    this.connect();
  }

  stop(): void {
    this.controller?.abort();
    this.controller = null;
    this._onConnected.fire(false);
  }

  dispose(): void {
    this.disposed = true;
    this.stop();
    this._onMessage.dispose();
    this._onConnected.dispose();
  }

  // ── Connection loop ──────────────────────────────────────────────────────
  // "Errors should never pass silently." — reconnect on failure, notify on state change.

  private async connect(): Promise<void> {
    if (this.disposed) return;

    this.controller = new AbortController();
    const { signal } = this.controller;

    try {
      const response = await fetch(`${this.baseUrl}/api/events/stream`, {
        headers: { Accept: "text/event-stream" },
        signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`SSE failed: ${response.status}`);
      }

      this._onConnected.fire(true);
      this.reconnectDelay = 1000;

      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";

      while (!this.disposed) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += value;
        const parts = buffer.split("\n\n");
        buffer = parts.pop()!;

        for (const part of parts) {
          const dataLine = part.split("\n").find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const message = JSON.parse(dataLine.slice(6)) as SSEMessage;
            this._onMessage.fire(message);
          } catch {
            // Malformed JSON — skip silently (keepalives, etc.)
          }
        }
      }
    } catch (err) {
      if (signal.aborted) return; // Intentional disconnect
      this._onConnected.fire(false);
    }

    // Reconnect with backoff
    if (!this.disposed && !signal.aborted) {
      this.controller = null;
      setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    }
  }
}
