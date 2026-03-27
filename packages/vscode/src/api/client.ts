import type {
  CreateTaskInput,
  DiffFile,
  DiffStats,
  ReviewDecisionInput,
  ReviewDecisionResponse,
  ReviewStatusResponse,
  RunTaskInput,
  SettingsResponse,
  TaskStatus,
  TaskWorktreeResponse,
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

  // ── Orchestrator chat ──────────────────────────────────────────────────

  getChatSessions(): Promise<WireChatSession[]> {
    return this.get<WireChatSession[]>("/api/chat/sessions");
  }

  createChatSession(label?: string, agentBackend?: string): Promise<WireChatSession> {
    return this.post<WireChatSession>("/api/chat/sessions", {
      label: label ?? null,
      agent_backend: agentBackend ?? null,
    });
  }

  /** POST to chat stream endpoint and return the raw SSE Response for streaming. */
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
    if (!response.ok || !response.body) {
      throw new ApiError(response.status, `Chat stream failed: ${response.status}`);
    }
    return response;
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

    if (!envelope?.ok || envelope.data === null) {
      throw new ApiError(
        response.status,
        envelope?.error ?? "Unknown API error",
        envelope?.error_code ?? null,
      );
    }

    return envelope.data;
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
