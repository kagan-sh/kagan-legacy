import type {
  AnalyticsExport,
  BackendStats,
  ChatAgentsResponse,
  ChatMessageDetailResponse,
  TurnStatusResponse,
  ChatWatchEvent,
  CreateTaskInput,
  DiffFile,
  DiffStats,
  DoctorReportResponse,
  Mention,
  ReviewDecisionInput,
  ReviewDecisionResponse,
  ReviewStatusResponse,
  RunTaskInput,
  SearchMentionsInput,
  SessionTimelineEntry,
  SettingsResponse,
  TaskStatus,
  TaskWorktreeResponse,
  TurnInProgressResponse,
  UpdateTaskInput,
  WireChatSession,
  WireEnvelope,
  WireEvent,
  WireProject,
  WireRepository,
  WireTask,
  WireTaskSession,
} from "./types.js";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly errorCode: string | null = null,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export interface KaganClientConfig {
  baseUrl: string;
  protocol?: "http" | "https";
  token?: string;
}

export class KaganClient {
  private token: string | undefined;

  constructor(
    private baseUrl: string,
    private protocol: "http" | "https" = "http",
    token?: string,
  ) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
    this.token = token;
  }

  /**
   * Create a KaganClient from a config object.
   * Enables clean separation of protocol/auth concerns.
   */
  static fromConfig(config: KaganClientConfig): KaganClient {
    return new KaganClient(config.baseUrl, config.protocol ?? "http", config.token);
  }

  getBaseUrl(): string {
    return `${this.protocol}://${this.baseUrl}`;
  }

  getHostPort(): string {
    return this.baseUrl;
  }

  setBaseUrl(url: string): void {
    this.baseUrl = normalizeBaseUrl(url);
  }

  setToken(token: string | undefined): void {
    this.token = token;
  }

  setProtocol(protocol: "http" | "https"): void {
    this.protocol = protocol;
  }

  /**
   * Get the full URL with protocol prefix.
   * Always uses configured protocol — never auto-upgrades to HTTPS.
   */
  private getFullUrl(path: string): string {
    return `${this.protocol}://${this.baseUrl}${path}`;
  }

  getTasks(status?: TaskStatus): Promise<WireTask[]> {
    const params = new URLSearchParams();
    if (status) {
      params.set("status", status);
    }
    return this.get<WireTask[]>(`/api/tasks${withQuery(params)}`);
  }

  getTask(taskId: string): Promise<WireTask> {
    return this.get<WireTask>(`/api/tasks/${taskId}`);
  }

  createTask(input: CreateTaskInput): Promise<WireTask> {
    return this.post<WireTask>("/api/tasks", input);
  }

  updateTask(taskId: string, input: UpdateTaskInput): Promise<WireTask> {
    return this.patch<WireTask>(`/api/tasks/${taskId}`, input);
  }

  deleteTask(taskId: string): Promise<{ task_id: string; deleted: boolean }> {
    return this.del<{ task_id: string; deleted: boolean }>(`/api/tasks/${taskId}`);
  }

  transitionStatus(taskId: string, status: TaskStatus): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/status`, { status });
  }

  runTask(taskId: string, input?: RunTaskInput): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/run`, input ?? {});
  }

  cancelTask(taskId: string): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/cancel`, {});
  }

  sendFollowUp(taskId: string, text: string): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/follow-up`, { text });
  }

  getTaskCounts(): Promise<Record<string, number>> {
    return this.get<Record<string, number>>("/api/tasks/counts");
  }

  getTaskEvents(
    taskId: string,
    options?: {
      limit?: number;
      offset?: number;
      tail?: boolean;
      before?: string;
      before_id?: string;
      after?: string;
      after_id?: string;
      session_id?: string;
    },
  ): Promise<WireEvent[]> {
    const params = new URLSearchParams();
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    if (options?.tail) params.set("tail", "1");
    if (options?.before) params.set("before", options.before);
    if (options?.before_id) params.set("before_id", options.before_id);
    if (options?.after) params.set("after", options.after);
    if (options?.after_id) params.set("after_id", options.after_id);
    if (options?.session_id) params.set("session_id", options.session_id);
    return this.get<WireEvent[]>(`/api/tasks/${taskId}/events${withQuery(params)}`);
  }

  getTaskSessions(taskId: string): Promise<WireTaskSession[]> {
    return this.get<WireTaskSession[]>(`/api/tasks/${taskId}/sessions`);
  }

  async getDiffStats(taskId: string): Promise<DiffStats> {
    const stats = await this.get<{
      files_changed?: number;
      files?: number;
      insertions?: number;
      deletions?: number;
    }>(`/api/tasks/${taskId}/diff`);

    return {
      files_changed: stats.files_changed ?? stats.files ?? 0,
      insertions: stats.insertions ?? 0,
      deletions: stats.deletions ?? 0,
    };
  }

  async getDiffFiles(taskId: string): Promise<DiffFile[]> {
    const payload = await this.get<{ task_id: string; files: DiffFile[] }>(`/api/tasks/${taskId}/diff/files`);
    return payload.files ?? [];
  }

  async getDiffRaw(taskId: string): Promise<string> {
    const payload = await this.get<{ task_id: string; diff: string }>(`/api/tasks/${taskId}/diff/raw`);
    return payload.diff ?? "";
  }

  getTaskWorktree(taskId: string): Promise<TaskWorktreeResponse> {
    return this.get<TaskWorktreeResponse>(`/api/tasks/${taskId}/worktree`);
  }

  getReview(taskId: string): Promise<ReviewStatusResponse> {
    return this.get<ReviewStatusResponse>(`/api/tasks/${taskId}/review`);
  }

  reviewDecide(taskId: string, input: ReviewDecisionInput): Promise<ReviewDecisionResponse> {
    return this.post<ReviewDecisionResponse>(`/api/tasks/${taskId}/review/decide`, input);
  }

  getProjects(): Promise<WireProject[]> {
    return this.get<WireProject[]>("/api/projects");
  }

  getProjectRepos(projectId: string): Promise<WireRepository[]> {
    return this.get<WireRepository[]>(`/api/projects/${projectId}/repos`);
  }

  getSettings(): Promise<SettingsResponse> {
    return this.get<SettingsResponse>("/api/settings");
  }

  updateSettings(input: SettingsResponse): Promise<SettingsResponse> {
    return this.post<SettingsResponse>("/api/settings", input);
  }

  /** GET /api/chat/agents */
  getChatAgents(): Promise<ChatAgentsResponse> {
    return this.get<ChatAgentsResponse>("/api/chat/agents");
  }

  // ── Orchestrator chat ──────────────────────────────────────────────────

  getChatSessions(): Promise<WireChatSession[]> {
    return this.get<WireChatSession[]>("/api/chat/sessions");
  }

  createChatSession(
    label?: string,
    agentBackend?: string,
    source: string = "vscode",
  ): Promise<WireChatSession> {
    return this.post<WireChatSession>("/api/chat/sessions", {
      label: label ?? null,
      agent_backend: agentBackend ?? null,
      source,
    });
  }

  /**
   * POST to chat stream endpoint and return the raw SSE Response for streaming.
   * Throws ApiError for non-2xx responses EXCEPT 409 (TURN_IN_PROGRESS) — that
   * is returned as a TurnInProgressResponse via a rejected ApiError with
   * errorCode === "TURN_IN_PROGRESS". Callers should check for that code.
   */
  async chatStream(
    sessionId: string,
    text: string,
    signal?: AbortSignal,
  ): Promise<Response> {
    const response = await fetch(this.getFullUrl(`/api/chat/${sessionId}/stream`), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...this.getAuthHeaders(),
      },
      body: JSON.stringify({ text }),
      signal,
    });

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
   * Subscribe to the per-session SSE watch stream.
   * Returns a dispose function; call it to unsubscribe and close the stream.
   * On unexpected disconnects, waits 3 s then reconnects automatically.
   * After reconnect, catches up via GET /messages?after_id=lastSeenId.
   */
  watchChatSession(
    sessionId: string,
    onEvent: (event: ChatWatchEvent) => void,
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
      // Catch up on missed messages before resuming the watch stream
      try {
        const missed = await this.getChatMessages(sessionId, lastSeenId);
        for (const msg of missed) {
          lastSeenId = Math.max(lastSeenId, msg.id);
          const event: ChatWatchEvent = msg.role === "user"
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
      if (!disposed) void startWatch();
    };

    const startWatch = async () => {
      if (disposed) return;
      controller = new AbortController();
      const { signal } = controller;

      try {
        const response = await fetch(
          this.getFullUrl(`/api/chat/sessions/${sessionId}/watch`),
          {
            headers: { Accept: "text/event-stream", ...this.getAuthHeaders() },
            signal,
          },
        );

        if (!response.ok || !response.body) {
          throw new Error(`Watch stream failed: ${response.status}`);
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
                const event = JSON.parse(dataLine.slice(6)) as ChatWatchEvent;
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

    void startWatch();

    return () => {
      disposed = true;
      clearReconnect();
      controller.abort();
    };
  }

  /** POST /api/chat/{sessionId}/interrupt */
  interruptChatTurn(sessionId: string, reason: "user" | "takeover"): Promise<void> {
    return this.post<void>(`/api/chat/${sessionId}/interrupt`, { reason });
  }

  /** GET /api/chat/sessions/{sessionId}/messages?after_id=N */
  getChatMessages(sessionId: string, afterId: number): Promise<ChatMessageDetailResponse[]> {
    return this.get<ChatMessageDetailResponse[]>(
      `/api/chat/sessions/${sessionId}/messages?after_id=${afterId}`,
    );
  }

  /** GET /api/chat/{sessionId}/turn-status */
  getChatTurnStatus(sessionId: string): Promise<TurnStatusResponse> {
    return this.get<TurnStatusResponse>(`/api/chat/${sessionId}/turn-status`);
  }

  /** GET /api/chat/sessions/{sessionId} */
  getChatSession(sessionId: string): Promise<WireChatSession> {
    return this.get<WireChatSession>(`/api/chat/sessions/${sessionId}`);
  }

  // ── Analytics ──────────────────────────────────────────────────────

  getBackendStats(params?: { days?: number }): Promise<BackendStats[]> {
    const query = params?.days ? `?days=${params.days}` : '';
    return this.get<BackendStats[]>(`/api/analytics/backend-stats${query}`);
  }

  getSessionTimeline(params?: { days?: number }): Promise<SessionTimelineEntry[]> {
    const days = params?.days ?? 30;
    return this.get<SessionTimelineEntry[]>(`/api/analytics/session-timeline?days=${days}`);
  }

  getAnalyticsExport(params?: { days?: number }): Promise<AnalyticsExport> {
    const query = params?.days ? `?days=${params.days}` : '';
    return this.get<AnalyticsExport>(`/api/analytics/export${query}`);
  }

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

  async ping(): Promise<boolean> {
    try {
      const response = await fetch(this.getFullUrl("/health"), {
        headers: {
          Accept: "application/json",
          ...this.getAuthHeaders(),
        },
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async verifyApi(): Promise<void> {
    await this.getSettings();
  }

  getDoctor(): Promise<DoctorReportResponse> {
    return this.get<DoctorReportResponse>("/api/doctor");
  }

  private async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }

  private async patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("PATCH", path, body);
  }

  private async del<T>(path: string): Promise<T> {
    return this.request<T>("DELETE", path);
  }

  private getAuthHeaders(): Record<string, string> {
    if (!this.token) return {};
    return { Authorization: `Bearer ${this.token}` };
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetch(this.getFullUrl(path), {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...this.getAuthHeaders(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    const rawBody = await response.text();
    let envelope: WireEnvelope<T> | null = null;
    try {
      envelope = rawBody ? (JSON.parse(rawBody) as WireEnvelope<T>) : null;
    } catch {
      envelope = null;
    }

    if (!response.ok) {
      const detail = describeHttpFailure({
        baseUrl: this.baseUrl,
        path,
        status: response.status,
        statusText: response.statusText,
        envelopeError: envelope?.error ?? null,
        rawBody,
      });
      throw new ApiError(
        response.status,
        detail,
        envelope?.error_code ?? null,
      );
    }

    if (!envelope?.ok || envelope.data == null) {
      throw new ApiError(
        response.status,
        envelope?.error ?? "Unknown API error",
        envelope?.error_code ?? null,
      );
    }

    return envelope.data as T;
  }
}

function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function withQuery(params: URLSearchParams): string {
  const query = params.toString();
  return query ? `?${query}` : "";
}

function describeHttpFailure(input: {
  baseUrl: string;
  path: string;
  status: number;
  statusText: string;
  envelopeError: string | null;
  rawBody: string;
}): string {
  const rawDetail =
    input.envelopeError !== null
      ? input.envelopeError
      : input.rawBody.trim() || input.statusText || `HTTP ${input.status}`;
  const looksLikeWrongServer =
    input.path.startsWith("/api/") &&
    (input.status === 404 ||
      input.status === 405 ||
      input.status === 501 ||
      /unsupported method|method not allowed|not found/i.test(rawDetail));

  if (!looksLikeWrongServer) {
    return rawDetail;
  }

  return `Server at ${input.baseUrl} does not look like a Kagan API (${rawDetail}). Check kagan.serverUrl and kagan.protocol.`;
}
