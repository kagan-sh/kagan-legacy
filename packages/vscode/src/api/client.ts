import {
  KaganApiClient,
  ApiError,
  type AnalyticsExport,
  type BackendStats,
  type ChatMessageDetailResponse,
  type TurnStatusResponse,
  type ChatWatchEvent as LiveChatEvent,
  type DoctorReportResponse,
  type Mention,
  type SearchMentionsInput,
  type SessionTimelineEntry,
  type TurnInProgressResponse,
  type SessionsResponse,
  type SessionItemResponse,
  type CreateSessionRequest,
} from "@kagan/shared-api-client";

export { ApiError };

export interface KaganClientConfig {
  baseUrl: string;
  protocol?: "http" | "https";
  token?: string;
}

/**
 * VS Code KaganClient — extends the shared KaganApiClient.
 *
 * Inherits all HTTP plumbing (auth headers, envelope unwrapping, URL
 * normalisation) from the shared class. This subclass adds:
 *   - chatStream() with 409 TURN_IN_PROGRESS special handling
 *   - followChatSession() with reconnection and catch-up logic for live chat
 *   - VS Code-specific endpoints (analytics, mentions, doctor, github)
 *   - streamRequest() — raw fetch helper for SSE paths that must bypass
 *     envelope unwrapping (streaming SSE, /health raw status)
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

  /**
   * Subscribe to the per-session SSE stream for live orchestrator chat.
   * Returns a dispose function; call it to unsubscribe and close the stream.
   * On unexpected disconnects, waits 3 s then reconnects automatically.
   * After reconnect, catches up via GET /messages?after_id=lastSeenId.
   */
  followChatSession(
    sessionId: string,
    onEvent: (event: LiveChatEvent) => void,
    onError?: (err: Error) => void,
  ): () => void {
    let disposed = false;
    let controller = new AbortController();
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let lastSeenId = 0;

    const clearReconnect = () => {
      if (reconnectTimer !== null) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    };

    const scheduleReconnect = () => {
      if (disposed) return;
      clearReconnect();
      reconnectTimer = setTimeout(() => void reconnect(), 3_000);
    };

    const reconnect = async () => {
      if (disposed) return;
      // Catch up on missed messages before resuming the live chat stream.
      try {
        const missed = await this.getChatMessages(sessionId, lastSeenId);
        for (const msg of missed) {
          lastSeenId = Math.max(lastSeenId, msg.id);
          const event: LiveChatEvent = msg.role === "user"
            ? { t: "CHAT_USER_MESSAGE", message_id: msg.id, content: msg.content }
            : {
                t: "CHAT_ASSISTANT_MESSAGE",
                message_id: msg.id,
                content: msg.content,
                terminated: msg.terminated_at_user_request,
              };
          onEvent(event);
        }
      } catch {
        // Best-effort — don't block reconnect on catch-up failure
      }
      if (!disposed) void startLiveStream();
    };

    const startLiveStream = async () => {
      if (disposed) return;
      controller = new AbortController();
      const { signal } = controller;

      try {
        // Streaming SSE — bypasses envelope unwrapping, auth added by streamRequest()
        const response = await this.streamRequest(
          this.getFullUrl(`/api/chat/sessions/${sessionId}/watch`),
          { headers: { Accept: "text/event-stream" }, signal },
        );

        if (!response.ok || !response.body) {
          throw new Error(`Live chat stream failed: ${response.status}`);
        }

        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";

        try {
          while (!disposed) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += value;
            const parts = buffer.split("\n\n");
            buffer = parts.pop()!;

            for (const part of parts) {
              const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
              if (!dataLine) continue;
              try {
                const event = JSON.parse(dataLine.slice(6)) as LiveChatEvent;
                if ("id" in event && typeof (event as Record<string, unknown>).id === "number") {
                  lastSeenId = Math.max(lastSeenId, (event as Record<string, unknown>).id as number);
                }
                onEvent(event);
              } catch {
                // Malformed JSON or keepalive — skip
              }
            }
          }
        } finally {
          await reader.cancel().catch(() => {});
        }
      } catch (err) {
        if (signal.aborted) return; // Intentional — no reconnect
        onError?.(err instanceof Error ? err : new Error(String(err)));
        scheduleReconnect();
        return;
      }

      // Natural EOF — reconnect
      scheduleReconnect();
    };

    void startLiveStream();

    return () => {
      disposed = true;
      clearReconnect();
      controller.abort();
    };
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

  // ── Unified sessions ───────────────────────────────────────────────────

  /** GET /api/v1/sessions */
  getSessions(): Promise<SessionsResponse> {
    return this.get<SessionsResponse>("/api/v1/sessions");
  }

  /** POST /api/v1/sessions */
  createSession(input: CreateSessionRequest): Promise<SessionItemResponse> {
    return this.post<SessionItemResponse>("/api/v1/sessions", input);
  }

  /** POST /api/v1/sessions/:sessionId/stop */
  stopSession(sessionId: string): Promise<void> {
    return this.post<void>(`/api/v1/sessions/${sessionId}/stop`, {});
  }

  /** POST /api/v1/sessions/:sessionId/close */
  closeSession(sessionId: string): Promise<void> {
    return this.post<void>(`/api/v1/sessions/${sessionId}/close`, {});
  }

}
