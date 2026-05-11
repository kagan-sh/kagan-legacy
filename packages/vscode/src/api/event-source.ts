/**
 * KaganEventSource — SSE subscriber for the native frame stream endpoints.
 *
 * Endpoints:
 *   GET /api/sessions/{session_id}/events  (kind=chat)
 *   GET /api/tasks/{task_id}/sse           (kind=task)
 *
 * Frame types from wire.ts: FrameSnapshot | FrameReady | FramePatch | FrameResume.
 *
 * Auth strategy: query-param token appended to the URL so the native
 * EventSource constructor (or polyfill) carries it on every request without
 * needing a custom headers hook.  Cookie-based auth also works because
 * EventSource respects cookies automatically.
 *
 * EventSource polyfill: VS Code runs in Node 18+ where EventSource is NOT a
 * global.  Rather than pulling in an npm dependency we accept a factory
 * parameter so unit tests can inject a fake and production code can pass
 * the Node-built-in EventSource (available since Node 22 via
 * --experimental-eventsource, or a small wrapper around the existing
 * streamRequest fetch path in KaganClient).  Extension callers use
 * KaganClient.subscribeSessionEvents / subscribeTaskEvents which provide
 * the correct factory.  Transport-level reconnect with Last-Event-ID resume
 * lives in that fetch-backed wrapper, not in this class.
 */

import type {
  Frame,
  FrameEntry,
  FramePatch,
  FrameResume,
  FrameSnapshot,
} from "@kagan/shared-api-client";
import { FRAME_EVENT } from "./local.js";

// ── Public types ──────────────────────────────────────────────────────────────

export interface EntryStreamState {
  entries: Map<number, FrameEntry>;
  ready: boolean;
  live: boolean;
  resumeNotice?: { turnActive: boolean };
}

export interface AuthConfig {
  /** Full base URL of the Kagan server, e.g. "http://localhost:8765". */
  baseUrl: string;
  /** Optional bearer token — appended as ?token= query param when present. */
  token?: string;
}

export interface KaganEventSourceOptions {
  url: string;
  auth: AuthConfig;
}

type Listener<T> = (value: T) => void;
type Unsubscribe = () => void;

// ── Pure reducer ──────────────────────────────────────────────────────────────

/**
 * Pure reducer: apply one Frame to the current EntryStreamState.
 * Returns a new state object (never mutates input).
 */
export function applyFrame(state: EntryStreamState, frame: Frame): EntryStreamState {
  switch (frame.type) {
    case "snapshot": {
      const f = frame as FrameSnapshot;
      const entries = new Map<number, FrameEntry>();
      for (const e of f.entries ?? []) {
        entries.set(e.idx, e);
      }
      return { ...state, entries };
    }

    case "ready":
      return { ...state, ready: true, live: true };

    case "patch": {
      const f = frame as FramePatch;
      const entries = new Map(state.entries);

      // Path parsing: /entries/{idx}  or  /entries/{idx}/text
      const match = /^\/entries\/(\d+)(\/text)?$/.exec(f.path);
      if (!match) {
        // Unknown path — ignore silently.
        return state;
      }

      const idx = parseInt(match[1]!, 10);

      switch (f.op) {
        case "create": {
          const value = f.value as FrameEntry | undefined;
          if (value !== undefined && value !== null) {
            entries.set(idx, value);
          }
          return { ...state, entries };
        }

        case "append": {
          const existing = entries.get(idx);
          if (!existing) {
            console.warn("[kagan] event-source: append before create for idx", idx);
            return state;
          }
          entries.set(idx, { ...existing, text: existing.text + (f.value as string) });
          return { ...state, entries };
        }

        case "finalize": {
          const existing = entries.get(idx);
          if (!existing) return state;
          entries.set(idx, { ...existing, finalized: true });
          return { ...state, entries };
        }

        default:
          return state;
      }
    }

    case "resume": {
      const f = frame as FrameResume;
      return { ...state, resumeNotice: { turnActive: f.turn_active } };
    }

    default:
      return state;
  }
}

// ── EventSource-like interface (minimum surface we need) ─────────────────────
// Typed narrowly so unit tests can inject a fake without needing a full
// EventSource implementation.  Exported so callers can cast their concrete
// implementation to this shape when constructing KaganEventSource.

export type SSEEventListener = (event: { type: string; data: string; lastEventId: string }) => void;

export interface EventSourceLike {
  readyState: number;
  addEventListener(type: string, listener: SSEEventListener): void;
  /** Assignment-only property for the error handler. */
  // eslint-disable-next-line @typescript-eslint/method-signature-style
  onerror: ((event: { type: string }) => void) | null;
  close(): void;
}

// ── KaganEventSource ──────────────────────────────────────────────────────────

export class KaganEventSource {
  private state: EntryStreamState = { entries: new Map(), ready: false, live: false };
  private es: EventSourceLike | null = null;

  private readonly snapshotListeners: Set<Listener<EntryStreamState>> = new Set();
  private readonly patchListeners: Set<Listener<FramePatch>> = new Set();
  private readonly readyListeners: Set<Listener<void>> = new Set();
  private readonly resumeListeners: Set<Listener<FrameResume>> = new Set();
  private readonly errorListeners: Set<Listener<Error>> = new Set();

  /**
   * @param opts          URL + auth config for the SSE endpoint.
   * @param esFactory     EventSource constructor/factory (injected for testability).
   *                      Production callers pass a thin wrapper; tests pass a fake.
   */
  constructor(
    private readonly opts: KaganEventSourceOptions,
    private readonly esFactory: (url: string) => EventSourceLike,
  ) {
    this.open();
  }

  // ── Subscription API (returns unsubscribe) ──────────────────────────────────

  onSnapshot(cb: Listener<EntryStreamState>): Unsubscribe {
    this.snapshotListeners.add(cb);
    return () => this.snapshotListeners.delete(cb);
  }

  onPatch(cb: Listener<FramePatch>): Unsubscribe {
    this.patchListeners.add(cb);
    return () => this.patchListeners.delete(cb);
  }

  onReady(cb: Listener<void>): Unsubscribe {
    this.readyListeners.add(cb);
    return () => this.readyListeners.delete(cb);
  }

  onResume(cb: Listener<FrameResume>): Unsubscribe {
    this.resumeListeners.add(cb);
    return () => this.resumeListeners.delete(cb);
  }

  onError(cb: Listener<Error>): Unsubscribe {
    this.errorListeners.add(cb);
    return () => this.errorListeners.delete(cb);
  }

  close(): void {
    this.es?.close();
    this.es = null;
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  private open(): void {
    const url = buildUrl(this.opts.url, this.opts.auth.token);
    const es = this.esFactory(url);
    this.es = es;

    es.addEventListener(FRAME_EVENT.SNAPSHOT, (event) => this.handleEvent(FRAME_EVENT.SNAPSHOT, event.data));
    es.addEventListener(FRAME_EVENT.READY, (event) => this.handleEvent(FRAME_EVENT.READY, event.data));
    es.addEventListener(FRAME_EVENT.PATCH, (event) => this.handleEvent(FRAME_EVENT.PATCH, event.data));
    es.addEventListener(FRAME_EVENT.RESUME, (event) => this.handleEvent(FRAME_EVENT.RESUME, event.data));

    es.onerror = () => {
      this.state = { ...this.state, live: false };
      this.emit(this.errorListeners, new Error("[kagan] SSE frame stream error"));
    };
  }

  private handleEvent(eventType: string, raw: string): void {
    let frame: Frame;
    try {
      frame = JSON.parse(raw) as Frame;
    } catch {
      // Malformed JSON or keepalive — skip silently.
      return;
    }

    // Use the declared event name as the discriminator; the JSON type field
    // may be absent in keepalives or differ in future wire versions.
    const normalised: Frame = { ...frame, type: eventType } as Frame;
    const prev = this.state;
    this.state = applyFrame(this.state, normalised);

    switch (eventType) {
      case FRAME_EVENT.SNAPSHOT:
        // Snapshot arrives before ready; we emit the aggregated state after
        // the next ready event.  Internal state is updated; snapshot listeners
        // fire when ready arrives.
        break;

      case FRAME_EVENT.READY:
        this.emit(this.readyListeners, undefined);
        this.emit(this.snapshotListeners, { ...this.state, entries: new Map(this.state.entries) });
        break;

      case FRAME_EVENT.PATCH:
        this.emit(this.patchListeners, normalised as FramePatch);
        break;

      case FRAME_EVENT.RESUME:
        this.emit(this.resumeListeners, normalised as FrameResume);
        break;

      default:
        break;
    }

    // Suppress unused-variable warning for `prev` — kept for future delta use.
    void prev;
  }

  private emit<T>(listeners: Set<Listener<T>>, value: T): void {
    for (const cb of listeners) {
      try {
        cb(value);
      } catch {
        // Listener errors must not crash the event loop.
      }
    }
  }
}

// ── URL builder ───────────────────────────────────────────────────────────────

function buildUrl(url: string, token?: string): string {
  if (!token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}
