/**
 * WebSocket client for real-time communication with the Kagan server.
 *
 * Wraps native WebSocket with:
 * - Auto-reconnect with exponential backoff (1s → 30s)
 * - Auth-on-connect (AUTH message with stored token)
 * - Typed event emitter pattern
 * - Board subscription + agent control helpers
 */

import type { WireTask, WireEvent } from '@/lib/api/types';

// ---------------------------------------------------------------------------
// Message types
// ---------------------------------------------------------------------------

/** Inbound message from the Kagan WebSocket server. */
export interface WsInboundMessage {
  t: string;
  tasks?: WireTask[];
  task_id?: string;
  session_id?: string;
  event?: WireEvent;
  [key: string]: unknown;
}

/** Outbound message sent to the Kagan WebSocket server. */
export interface WsOutboundMessage {
  t: string;
  token?: string;
  task_id?: string;
  mode?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Event handler type
// ---------------------------------------------------------------------------

/** Known WebSocket event types for compile-time safety. */
export type WsEventName =
  | 'connected'
  | 'disconnected'
  | 'AUTH_OK'
  | 'AUTH_FAIL'
  | 'BOARD_SYNC'
  | 'TASK_UPDATED'
  | 'SESSION_EVENT'
  | 'CHAT_SUBSCRIBED'
  | 'CHAT_CHUNK'
  | 'CHAT_DONE'
  | 'CHAT_ERROR'
  | 'CHAT_TOOL_START'
  | 'CHAT_TOOL_PROGRESS'
  | 'CHAT_BUSY'
  | 'CHAT_INTERRUPTED'
  | 'CHAT_SESSION_UPDATED'
  | 'RUN_STARTED'
  | 'RUN_CANCELLED'
  | 'RUN_ERROR'
  | 'TOOL_PERMISSION_REQUEST'
  | 'FOLLOW_UP_QUEUED'
  | 'FOLLOW_UP_SENT'
  | 'TASK_FOLLOW_UP_ACK'
  | 'TASK_FOLLOW_UP_ERROR';

export type WsEventHandler = (data: WsInboundMessage) => void;

// ---------------------------------------------------------------------------
// KaganWebSocket
// ---------------------------------------------------------------------------

export class KaganWebSocket {
  private ws: WebSocket | null = null;
  private url: string = '';
  private token: string = '';
  private listeners: Map<string, Set<WsEventHandler>> = new Map();
  private reconnectAttempts: number = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private maxReconnectDelay: number = 30_000;
  private shouldReconnect: boolean = true;
  private authenticated: boolean = false;

  // -- Configuration --------------------------------------------------------

  /**
   * Set server URL and auth token.
   * The URL should be the HTTP base URL — it will be converted to ws:// internally.
   */
  configure(baseUrl: string, token: string): void {
    this.url = httpToWs(baseUrl);
    this.token = token;
  }

  // -- Connection lifecycle -------------------------------------------------

  /** Open a WebSocket connection to the server. */
  connect(): void {
    const wsUrl = `${this.url}/ws`;

    if (this.ws) {
      const sameTarget = this.ws.url === wsUrl;
      if (
        sameTarget
        && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)
      ) {
        this.shouldReconnect = true;
        return;
      }
      this.disconnect();
    }

    this.shouldReconnect = true;
    this.authenticated = false;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      if (this.token) {
        // Remote mode: authenticate with token, wait for AUTH_OK
        this.sendRaw({ t: 'AUTH', token: this.token });
      } else {
        // Bundled mode: no auth required, mark as connected immediately
        this.authenticated = true;
        this.reconnectAttempts = 0;
        this.emit('connected', { t: 'connected' });
      }
    };

    this.ws.onmessage = (event: MessageEvent) => {
      this.handleMessage(event);
    };

    this.ws.onclose = () => {
      this.authenticated = false;
      this.emit('disconnected', { t: 'disconnected' });
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose fires after onerror — reconnect handled there
    };
  }

  /** Close the connection and stop auto-reconnect. */
  disconnect(): void {
    this.shouldReconnect = false;
    this.authenticated = false;

    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }

    this.emit('disconnected', { t: 'disconnected' });
  }

  /** Send a typed message to the server. Only works when authenticated. */
  send(message: WsOutboundMessage): void {
    this.sendRaw(message);
  }

  /** Whether the connection is open and authenticated. */
  isConnected(): boolean {
    return this.authenticated && this.ws?.readyState === WebSocket.OPEN;
  }

  // -- Event emitter --------------------------------------------------------

  /**
   * Subscribe to a message type. Returns an unsubscribe function.
   *
   * Special types: 'connected', 'disconnected' — lifecycle events.
   * Server types: 'AUTH_OK', 'BOARD_SYNC', 'TASK_UPDATED', 'SESSION_EVENT', etc.
   */
  on(type: WsEventName, handler: WsEventHandler): () => void {
    let handlers = this.listeners.get(type);
    if (!handlers) {
      handlers = new Set();
      this.listeners.set(type, handlers);
    }
    handlers.add(handler);

    return () => {
      handlers.delete(handler);
      if (handlers.size === 0) {
        this.listeners.delete(type);
      }
    };
  }

  /** Remove a specific handler for a message type. */
  off(type: WsEventName, handler: WsEventHandler): void {
    const handlers = this.listeners.get(type);
    if (handlers) {
      handlers.delete(handler);
      if (handlers.size === 0) {
        this.listeners.delete(type);
      }
    }
  }

  // -- Convenience methods --------------------------------------------------

  /** Subscribe to board-level updates (task list sync). */
  subscribeToBoardUpdates(): void {
    this.send({ t: 'BOARD_SUBSCRIBE' });
  }

  /** Start an agent run on a task. */
  startRun(taskId: string, mode: string = 'AUTO'): void {
    this.send({ t: 'RUN_START', task_id: taskId, mode });
  }

  /** Cancel a running agent on a task. */
  cancelRun(taskId: string): void {
    this.send({ t: 'RUN_CANCEL', task_id: taskId });
  }

  // -- Chat methods --------------------------------------------------------

  /** Subscribe to a chat session's history. Server responds with CHAT_SUBSCRIBED. */
  subscribeToChatSession(sessionId: string): void {
    this.send({ t: 'CHAT_SUBSCRIBE', session_id: sessionId });
  }

  /** Send a chat message with optional attachments. Server streams CHAT_CHUNK events back. */
  sendChatMessage(
    sessionId: string,
    text: string,
    agentBackend?: string,
    attachments?: Array<{ type: string; name: string; mime_type: string; data: string }>,
  ): void {
    this.send({
      t: 'CHAT_SEND',
      session_id: sessionId,
      text,
      ...(agentBackend ? { agent_backend: agentBackend } : {}),
      ...(attachments?.length ? { attachments } : {}),
    });
  }

  interruptChatSession(sessionId: string): void {
    this.send({ t: 'CHAT_INTERRUPT', session_id: sessionId });
  }

  /** Send a follow-up message for a running task. Server cancels + restarts agent. */
  sendTaskFollowUp(taskId: string, text: string): void {
    this.send({ t: 'TASK_FOLLOW_UP', task_id: taskId, text });
  }

  // -- Internals ------------------------------------------------------------

  private emit(type: string, data: WsInboundMessage): void {
    const handlers = this.listeners.get(type);
    if (handlers) {
      for (const handler of handlers) {
        handler(data);
      }
    }
  }

  private sendRaw(message: WsOutboundMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  private handleMessage(event: MessageEvent): void {
    let msg: WsInboundMessage;
    try {
      msg = JSON.parse(String(event.data)) as WsInboundMessage;
    } catch {
      return; // Ignore malformed messages
    }

    const type = msg.t;
    if (!type) {
      return;
    }

    // Handle auth flow
    if (type === 'AUTH_OK') {
      this.authenticated = true;
      this.reconnectAttempts = 0;
      this.emit('connected', msg);
      this.emit('AUTH_OK', msg);
      return;
    }

    if (type === 'AUTH_FAIL') {
      this.shouldReconnect = false; // Don't reconnect on auth failure
      this.emit('AUTH_FAIL', msg);
      this.disconnect();
      return;
    }

    // Dispatch all other message types to listeners
    this.emit(type, msg);
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) {
      return;
    }

    const delay = Math.min(
      1000 * Math.pow(2, this.reconnectAttempts),
      this.maxReconnectDelay,
    );
    this.reconnectAttempts += 1;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert an HTTP(S) URL to a WS(S) URL. */
function httpToWs(url: string): string {
  return url.replace(/^http/, 'ws');
}

// ---------------------------------------------------------------------------
// Singleton — configured lazily after bundled-web bootstrap
// ---------------------------------------------------------------------------

export const kaganWs = new KaganWebSocket();
