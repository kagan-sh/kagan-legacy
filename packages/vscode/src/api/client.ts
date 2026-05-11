import {
  KaganApiClient,
  ApiError,
  type AnalyticsExport,
  type BackendStats,
  type ChatMessageDetailResponse,
  type TurnStatusResponse,
  type DoctorReportResponse,
  type Mention,
  type SearchMentionsInput,
  type SessionTimelineEntry,
  type TurnInProgressResponse,
} from "@kagan/shared-api-client";
import { KaganEventSource, type AuthConfig, type EventSourceLike } from "./event-source.js";

export { ApiError };

// ── FetchBackedEventSource ────────────────────────────────────────────────────
// A minimal EventSource-like implementation backed by fetch/streamRequest.
// Satisfies the EventSourceLike interface in event-source.ts so KaganEventSource
// can use it without touching a native global EventSource (unavailable in Node).
//
// Lifecycle: construction starts a reconnect loop.  On EOF or transport failure
// the loop waits SSE_RECONNECT_MS and opens a new stream, sending Last-Event-ID
// only after at least one SSE `id:` line has been observed (never `""`).

const SSE_RECONNECT_MS = 3_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

type SSEListener = (event: { type: string; data: string; lastEventId: string }) => void;

class FetchBackedEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  readyState: number = FetchBackedEventSource.CONNECTING;
  onerror: ((e: { type: string }) => void) | null = null;

  private readonly listeners: Map<string, SSEListener[]> = new Map();
  private controller = new AbortController();
  private lastEventId = "";

  constructor(
    private readonly client: KaganClient,
    private readonly url: string,
  ) {
    void this.connectLoop();
  }

  addEventListener(type: string, handler: SSEListener): void {
    const list = this.listeners.get(type) ?? [];
    list.push(handler);
    this.listeners.set(type, list);
  }

  close(): void {
    this.readyState = FetchBackedEventSource.CLOSED;
    this.controller.abort();
  }

  private async connectLoop(): Promise<void> {
    while (this.readyState !== FetchBackedEventSource.CLOSED) {
      const { signal } = this.controller;
      if (signal.aborted) {
        return;
      }

      this.readyState = FetchBackedEventSource.CONNECTING;
      try {
        const headers: Record<string, string> = { Accept: "text/event-stream" };
        if (this.lastEventId) {
          headers["Last-Event-ID"] = this.lastEventId;
        }

        const response = await this.client.streamRequest(this.url, {
          headers,
          signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE frame stream failed: ${response.status}`);
        }

        this.readyState = FetchBackedEventSource.OPEN;
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";

        try {
          while (this.readyState === FetchBackedEventSource.OPEN) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }

            buffer += value;
            const blocks = buffer.split("\n\n");
            buffer = blocks.pop()!;

            for (const block of blocks) {
              this.dispatchBlock(block);
            }
          }
        } finally {
          await reader.cancel().catch(() => {});
        }
      } catch {
        if (signal.aborted || this.readyState === FetchBackedEventSource.CLOSED) {
          return;
        }
      }

      if (this.readyState === FetchBackedEventSource.CLOSED) {
        return;
      }

      await sleep(SSE_RECONNECT_MS);
    }
  }

  private dispatchBlock(block: string): void {
    // Parse SSE block: event:, data:, id: lines.
    let eventType = "message";
    let data = "";
    let id = "";

    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data = data ? `${data}\n${line.slice(5).trim()}` : line.slice(5).trim();
      } else if (line.startsWith("id:")) {
        id = line.slice(3).trim();
      }
    }

    if (!data) return; // No data = keepalive or comment.

    if (id) this.lastEventId = id;

    const handlers = this.listeners.get(eventType) ?? [];
    for (const h of handlers) {
      h({ type: eventType, data, lastEventId: this.lastEventId });
    }
  }
}

export interface KaganClientConfig {
  baseUrl: string;
  protocol?: "http" | "https";
  token?: string;
}

/**
 * VS Code KaganClient — extends the shared KaganApiClient.
 *
 * Inherits all HTTP plumbing (auth headers, envelope unwrapping, URL
 * normalisation, session/task/project/analytics CRUD) from the shared class.
 * `streamRequest()` is also inherited — it is a base-class helper for raw SSE
 * paths that bypass envelope unwrapping.
 *
 * This subclass adds only VS Code-specific behaviour:
 *   - chatStream() override — 409 TURN_IN_PROGRESS detection before the base
 *     class error path, using streamRequest() for auth-aware raw fetch
 *   - ping() override — forwards auth headers via streamRequest() (the base
 *     implementation issues a no-auth GET /health)
 *   - GitHub integration endpoints (preflight, detect-repo, preview, sync)
 *   - getDoctor() convenience alias for getDoctorReport()
 */
export class KaganClient extends KaganApiClient {
  constructor(
    baseUrl: string,
    protocol: "http" | "https" = "http",
    token?: string,
  ) {
    super({ baseUrl, protocol, token, clientType: "vscode" });
  }

  static fromConfig(config: KaganClientConfig): KaganClient {
    return new KaganClient(config.baseUrl, config.protocol ?? "http", config.token);
  }

  // ── Chat turn-level operations ─────────────────────────────────────────

  /** GET /api/chat/{sessionId}/turn-status */
  getChatTurnStatus(sessionId: string): Promise<TurnStatusResponse> {
    return this.get<TurnStatusResponse>(`/api/chat/${sessionId}/turn-status`);
  }

  /** GET /api/chat/sessions/{sessionId}/messages?after_id=N */
  getChatMessages(sessionId: string, afterId: number): Promise<ChatMessageDetailResponse[]> {
    return this.get<ChatMessageDetailResponse[]>(
      `/api/chat/sessions/${sessionId}/messages?after_id=${afterId}`,
    );
  }

  /** POST /api/chat/{sessionId}/interrupt */
  interruptChatTurn(sessionId: string, reason: "user" | "takeover"): Promise<void> {
    return this.post<void>(`/api/chat/${sessionId}/interrupt`, { reason });
  }

  /**
   * POST to chat stream endpoint and return the raw SSE Response for streaming.
   *
   * Bypasses envelope unwrapping because streaming responses are raw SSE frames,
   * not JSON envelopes. Uses streamRequest() to add auth headers.
   *
   * Throws ApiError for non-2xx responses EXCEPT 409 (TURN_IN_PROGRESS) —
   * that is thrown as ApiError with errorCode === "TURN_IN_PROGRESS". Callers
   * should check for that code before showing an interrupt prompt.
   */
  override async chatStream(
    sessionId: string,
    text: string,
    signal?: AbortSignal,
  ): Promise<Response> {
    const response = await this.streamRequest(
      this.getFullUrl(`/api/chat/${sessionId}/stream`),
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ text }),
        signal,
      },
    );

    if (response.status === 409) {
      const rawBody = await response.text();
      let body: TurnInProgressResponse | null = null;
      try { body = JSON.parse(rawBody) as TurnInProgressResponse; } catch { /* ignore */ }
      throw new ApiError(
        409,
        body?.error_code ?? "TURN_IN_PROGRESS",
        body?.error_code ?? "TURN_IN_PROGRESS",
      );
    }

    if (!response.ok || !response.body) {
      throw new ApiError(response.status, `Chat stream failed: ${response.status}`);
    }
    return response;
  }

  // ── Analytics ──────────────────────────────────────────────────────────

  getBackendStats(params?: { days?: number }): Promise<BackendStats[]> {
    const query = params?.days ? `?days=${params.days}` : "";
    return this.get<BackendStats[]>(`/api/analytics/backend-stats${query}`);
  }

  getSessionTimeline(params?: { days?: number }): Promise<SessionTimelineEntry[]> {
    const days = params?.days ?? 30;
    return this.get<SessionTimelineEntry[]>(`/api/analytics/session-timeline?days=${days}`);
  }

  getAnalyticsExport(params?: { days?: number }): Promise<AnalyticsExport> {
    const query = params?.days ? `?days=${params.days}` : "";
    return this.get<AnalyticsExport>(`/api/analytics/export${query}`);
  }

  // ── Mentions ───────────────────────────────────────────────────────────

  /** GET /api/mentions/search?project_id=&q=&limit= */
  async searchMentions(input: SearchMentionsInput): Promise<Mention[]> {
    const params = new URLSearchParams();
    params.set("project_id", input.projectId);
    params.set("q", input.q);
    if (input.limit !== undefined) params.set("limit", String(input.limit));
    const envelope = await this.get<{ mentions: Mention[]; total: number }>(
      `/api/mentions/search?${params.toString()}`,
    );
    return envelope.mentions;
  }

  // ── GitHub integration ─────────────────────────────────────────────────

  /** GET /api/integrations/github/preflight */
  getGithubPreflight(): Promise<{ id: string; checks: Array<{ ok: boolean; message: string; fix_hint: string | null }>; ready: boolean }> {
    return this.get("/api/integrations/github/preflight");
  }

  /** GET /api/integrations/github/detect-repo */
  detectGithubRepo(): Promise<{ id: string; repo_slug: string | null }> {
    return this.get("/api/integrations/github/detect-repo");
  }

  /** GET /api/integrations/github/preview */
  previewGithubIssues(params: {
    repo_slug: string;
    state?: string;
    labels?: string;
    limit?: number;
  }): Promise<{ id: string; issues: Array<{ number: number; title: string; state: string; labels: string[]; url: string; already_synced: boolean }>; total: number }> {
    const qs = new URLSearchParams();
    qs.set("repo_slug", params.repo_slug);
    if (params.state) qs.set("state", params.state);
    if (params.labels) qs.set("labels", params.labels);
    if (params.limit) qs.set("limit", String(params.limit));
    return this.get(`/api/integrations/github/preview?${qs.toString()}`);
  }

  /** POST /api/integrations/github/sync */
  syncGithubIssues(config: Record<string, unknown>): Promise<{ id: string; created: number; updated: number; skipped: number; errors: string[] }> {
    return this.post("/api/integrations/github/sync", config);
  }

  // ── Health ─────────────────────────────────────────────────────────────

  /**
   * GET /health — connectivity check.
   *
   * Bypasses envelope unwrapping via streamRequest() so the raw HTTP status
   * code is inspectable even when the server returns a non-JSON body. Auth
   * headers are still sent via streamRequest().
   */
  override async ping(): Promise<boolean> {
    try {
      const response = await this.streamRequest(this.getFullUrl("/health"), {
        headers: { Accept: "application/json" },
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  getDoctor(): Promise<DoctorReportResponse> {
    return this.get<DoctorReportResponse>("/api/doctor");
  }

  // ── Frame stream subscriptions ─────────────────────────────────────────────

  /**
   * Subscribe to the per-session frame stream.
   * GET /api/sessions/{sessionId}/events (kind=chat)
   *
   * Returns a KaganEventSource that emits snapshot/ready/patch/resume frames.
   * Centralises URL construction — providers must not build this URL directly.
   */
  subscribeSessionEvents(sessionId: string): KaganEventSource {
    const url = this.getFullUrl(`/api/sessions/${sessionId}/events`);
    const auth = this.getAuthConfig();
    return new KaganEventSource({ url, auth }, this.makeFetchEventSource());
  }

  /**
   * Subscribe to the per-task frame stream.
   * GET /api/tasks/{taskId}/sse (kind=task)
   *
   * Uses /sse suffix to avoid collision with the paginated history endpoint.
   * Returns a KaganEventSource that emits snapshot/ready/patch/resume frames.
   * Centralises URL construction — providers must not build this URL directly.
   */
  subscribeTaskEvents(taskId: string): KaganEventSource {
    const url = this.getFullUrl(`/api/tasks/${taskId}/sse`);
    const auth = this.getAuthConfig();
    return new KaganEventSource({ url, auth }, this.makeFetchEventSource());
  }

  /**
   * Returns an EventSource-compatible factory backed by streamRequest.
   *
   * This keeps all HTTP through KaganClient rather than using a naked
   * EventSource constructor (which would bypass auth headers).  The factory
   * creates a FetchBackedEventSource per URL that uses Node's readable-stream
   * fetch API to parse SSE frames.
   */
  private makeFetchEventSource(): (url: string) => EventSourceLike {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const client = this;
    return (url: string) => new FetchBackedEventSource(client, url);
  }

  /**
   * Returns an AuthConfig snapshot for use in KaganEventSource.
   * The token is included so KaganEventSource can append it as a query param
   * to the SSE URL — required because EventSource does not support custom
   * request headers natively.
   */
  getAuthConfig(): AuthConfig {
    return {
      baseUrl: this.getFullUrl(""),
      token: this._token,
    };
  }

}
