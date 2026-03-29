// ============================================================================
// Core API Client
// Consolidated from web and VS Code implementations
// ============================================================================

import type {
  ChatAgentsResponse,
  CreateChatSessionInput,
  CreateProjectInput,
  CreateTaskInput,
  DiffFile,
  DiffStats,
  FsBrowseResponse,
  PreflightResponse,
  ProjectActivatedResponse,
  ProjectDeletedResponse,
  ResolvedSettingsResponse,
  ReviewDecideResponse,
  ReviewDecisionInput,
  ReviewStatusResponse,
  RunTaskInput,
  SettingsResponse,
  TaskCommitsResponse,
  TaskDeletedResponse,
  TaskEventOptions,
  TaskStatus,
  TaskWorktreeResponse,
  TransitionStatusInput,
  UpdateTaskInput,
  WireChatSession,
  WireChatSessionSummary,
  WireEnvelope,
  WireEvent,
  WireProject,
  WireRepository,
  WireTask,
  WireTaskSession,
  KaganClientConfig,
  ClientPresence,
  PresenceHeartbeatInput,
  TaskCountsResponse,
  ChatStreamEvent,
} from "./types.js";
import { ApiError } from "./errors.js";

// ----------------------------------------------------------------------------
// Configuration & Utilities
// ----------------------------------------------------------------------------

function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function withQuery(params: URLSearchParams): string {
  const query = params.toString();
  return query ? `?${query}` : "";
}

interface FailureContext {
  baseUrl: string;
  path: string;
  status: number;
  statusText: string;
  envelopeError: string | null;
  rawBody: string;
}

function describeHttpFailure(input: FailureContext): string {
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

  return `Server at ${input.baseUrl} does not look like a Kagan API (${rawDetail}). Check the server URL and protocol.`;
}

// ----------------------------------------------------------------------------
// Kagan API Client
// ----------------------------------------------------------------------------

/**
 * Unified Kagan API Client.
 * 
 * Works in both browser and Node.js/VS Code extension contexts.
 * Uses native fetch API for maximum compatibility.
 * 
 * @example
 * ```typescript
 * // Browser/VS Code usage
 * const client = new KaganApiClient({
 *   baseUrl: "localhost:8765",
 *   protocol: "http",
 *   token: "optional-auth-token",
 *   clientType: "vscode" // or "web"
 * });
 * 
 * const tasks = await client.getTasks();
 * ```
 */
export class KaganApiClient {
  private _baseUrl: string;
  private _protocol: "http" | "https";
  private _token: string | undefined;
  private _clientType: string;
  private _fetchImpl: typeof fetch;

  constructor(config: KaganClientConfig) {
    this._baseUrl = normalizeBaseUrl(config.baseUrl);
    this._protocol = config.protocol ?? "http";
    this._token = config.token;
    this._clientType = config.clientType ?? "unknown";
    this._fetchImpl = globalThis.fetch.bind(globalThis);
  }

  // -- Configuration --------------------------------------------------------

  /**
   * Create a client from a config object.
   */
  static fromConfig(config: KaganClientConfig): KaganApiClient {
    return new KaganApiClient(config);
  }

  getBaseUrl(): string {
    return `${this._protocol}://${this._baseUrl}`;
  }

  getHostPort(): string {
    return this._baseUrl;
  }

  setBaseUrl(url: string): void {
    this._baseUrl = normalizeBaseUrl(url);
  }

  setProtocol(protocol: "http" | "https"): void {
    this._protocol = protocol;
  }

  setToken(token: string | undefined): void {
    this._token = token;
  }

  setClientType(clientType: string): void {
    this._clientType = clientType;
  }

  isConfigured(): boolean {
    return Boolean(this._baseUrl);
  }

  // -- Core HTTP Methods ----------------------------------------------------

  private getFullUrl(path: string): string {
    return `${this._protocol}://${this._baseUrl}${path}`;
  }

  private getAuthHeaders(): Record<string, string> {
    if (!this._token) return {};
    return { Authorization: `Bearer ${this._token}` };
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await this._fetchImpl(this.getFullUrl(path), {
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
        baseUrl: this._baseUrl,
        path,
        status: response.status,
        statusText: response.statusText,
        envelopeError: envelope?.error ?? null,
        rawBody,
      });
      throw new ApiError(response.status, detail, envelope?.error_code ?? null);
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

  // -- Tasks ----------------------------------------------------------------

  /** GET /api/tasks */
  getTasks(status?: TaskStatus): Promise<WireTask[]> {
    const params = new URLSearchParams();
    if (status) {
      params.set("status", status);
    }
    return this.get<WireTask[]>(`/api/tasks${withQuery(params)}`);
  }

  /** GET /api/tasks/counts */
  getTaskCounts(): Promise<TaskCountsResponse> {
    return this.get<TaskCountsResponse>("/api/tasks/counts");
  }

  /** GET /api/tasks/:taskId */
  getTask(taskId: string): Promise<WireTask> {
    return this.get<WireTask>(`/api/tasks/${taskId}`);
  }

  /** POST /api/tasks */
  createTask(input: CreateTaskInput): Promise<WireTask> {
    return this.post<WireTask>("/api/tasks", input);
  }

  /** PATCH /api/tasks/:taskId */
  updateTask(taskId: string, input: UpdateTaskInput): Promise<WireTask> {
    return this.patch<WireTask>(`/api/tasks/${taskId}`, input);
  }

  /** DELETE /api/tasks/:taskId */
  deleteTask(taskId: string): Promise<TaskDeletedResponse> {
    return this.del<TaskDeletedResponse>(`/api/tasks/${taskId}`);
  }

  /** POST /api/tasks/:taskId/status */
  transitionStatus(taskId: string, status: TaskStatus): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/status`, { status } as TransitionStatusInput);
  }

  /** POST /api/tasks/:taskId/run */
  runTask(taskId: string, input?: RunTaskInput): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/run`, input ?? {});
  }

  /** POST /api/tasks/:taskId/cancel */
  cancelTask(taskId: string): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/cancel`, {});
  }

  /** POST /api/tasks/:taskId/follow-up */
  sendFollowUp(taskId: string, text: string): Promise<WireTask> {
    return this.post<WireTask>(`/api/tasks/${taskId}/follow-up`, { text });
  }

  /** POST /api/tasks/:taskId/detach */
  detachTask(taskId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/api/tasks/${taskId}/detach`, {});
  }

  /** GET /api/tasks/:taskId/events */
  getTaskEvents(taskId: string, options?: TaskEventOptions): Promise<WireEvent[]> {
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

  /** GET /api/tasks/:taskId/sessions */
  getTaskSessions(taskId: string): Promise<WireTaskSession[]> {
    return this.get<WireTaskSession[]>(`/api/tasks/${taskId}/sessions`);
  }

  /** GET /api/tasks/:taskId/diff */
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

  /** GET /api/tasks/:taskId/diff/files */
  async getDiffFiles(taskId: string): Promise<DiffFile[]> {
    const payload = await this.get<{ files?: DiffFile[] } | DiffFile[]>(
      `/api/tasks/${taskId}/diff/files`,
    );
    return Array.isArray(payload) ? payload : payload.files ?? [];
  }

  /** GET /api/tasks/:taskId/diff/raw */
  async getDiffRaw(taskId: string): Promise<string> {
    try {
      const payload = await this.get<{ task_id: string; diff?: string }>(
        `/api/tasks/${taskId}/diff/raw`,
      );
      return payload.diff ?? "";
    } catch (error) {
      if (ApiError.isApiError(error) && error.isNotFound()) {
        return "";
      }
      throw error;
    }
  }

  /** GET /api/tasks/:taskId/worktree */
  getTaskWorktree(taskId: string): Promise<TaskWorktreeResponse> {
    return this.get<TaskWorktreeResponse>(`/api/tasks/${taskId}/worktree`);
  }

  /** GET /api/tasks/:taskId/commits */
  getTaskCommits(taskId: string): Promise<TaskCommitsResponse> {
    return this.get<TaskCommitsResponse>(`/api/tasks/${taskId}/commits`);
  }

  // -- Projects -------------------------------------------------------------

  /** GET /api/projects */
  getProjects(): Promise<WireProject[]> {
    return this.get<WireProject[]>("/api/projects");
  }

  /** POST /api/projects */
  createProject(name: string): Promise<WireProject> {
    return this.post<WireProject>("/api/projects", { name } as CreateProjectInput);
  }

  /** POST /api/projects/:projectId/activate */
  activateProject(projectId: string): Promise<ProjectActivatedResponse> {
    return this.post<ProjectActivatedResponse>(`/api/projects/${projectId}/activate`, {});
  }

  /** DELETE /api/projects/:projectId */
  deleteProject(projectId: string): Promise<ProjectDeletedResponse> {
    return this.del<ProjectDeletedResponse>(`/api/projects/${projectId}`);
  }

  // -- Repos ----------------------------------------------------------------

  /** GET /api/projects/:projectId/repos */
  getProjectRepos(projectId: string): Promise<WireRepository[]> {
    return this.get<WireRepository[]>(`/api/projects/${projectId}/repos`);
  }

  /** POST /api/projects/:projectId/repos */
  addProjectRepo(projectId: string, path: string): Promise<WireRepository> {
    return this.post<WireRepository>(`/api/projects/${projectId}/repos`, { path });
  }

  /** DELETE /api/projects/:projectId/repos/:repoId */
  deleteProjectRepo(projectId: string, repoId: string): Promise<void> {
    return this.del<void>(`/api/projects/${projectId}/repos/${repoId}`);
  }

  /** POST /api/projects/:projectId/repos/:repoId/select */
  selectProjectRepo(projectId: string, repoId: string): Promise<{ repo_id: string; selected: boolean }> {
    return this.post<{ repo_id: string; selected: boolean }>(
      `/api/projects/${projectId}/repos/${repoId}/select`,
      {},
    );
  }

  // -- Reviews --------------------------------------------------------------

  /** GET /api/tasks/:taskId/review */
  getReview(taskId: string): Promise<ReviewStatusResponse> {
    return this.get<ReviewStatusResponse>(`/api/tasks/${taskId}/review`);
  }

  /** POST /api/tasks/:taskId/review/decide */
  reviewDecide(taskId: string, input: ReviewDecisionInput): Promise<ReviewDecideResponse> {
    return this.post<ReviewDecideResponse>(`/api/tasks/${taskId}/review/decide`, input);
  }

  /** GET /api/tasks/:taskId/review/conflicts */
  getConflicts(taskId: string): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>(`/api/tasks/${taskId}/review/conflicts`);
  }

  // -- Settings -------------------------------------------------------------

  /** GET /api/settings */
  getSettings(): Promise<SettingsResponse> {
    return this.get<SettingsResponse>("/api/settings");
  }

  /** GET /api/settings/resolved */
  getResolvedSettings(): Promise<ResolvedSettingsResponse> {
    return this.get<ResolvedSettingsResponse>("/api/settings/resolved");
  }

  /** POST /api/settings */
  updateSettings(input: SettingsResponse): Promise<SettingsResponse> {
    return this.post<SettingsResponse>("/api/settings", input);
  }

  // -- Chat Sessions --------------------------------------------------------

  /** GET /api/chat/sessions */
  getChatSessions(projectId?: string): Promise<WireChatSessionSummary[]> {
    const params = new URLSearchParams();
    if (projectId) params.set("project_id", projectId);
    return this.get<WireChatSessionSummary[]>(`/api/chat/sessions${withQuery(params)}`);
  }

  /** POST /api/chat/sessions */
  createChatSession(input: CreateChatSessionInput & { source?: string }): Promise<WireChatSession> {
    return this.post<WireChatSession>("/api/chat/sessions", {
      source: this._clientType,
      ...input,
    });
  }

  /** GET /api/chat/sessions/:sessionId */
  getChatSession(sessionId: string): Promise<WireChatSession> {
    return this.get<WireChatSession>(`/api/chat/sessions/${sessionId}`);
  }

  /** PATCH /api/chat/sessions/:sessionId */
  updateChatSession(sessionId: string, input: { agent_backend?: string }): Promise<WireChatSession> {
    return this.patch<WireChatSession>(`/api/chat/sessions/${sessionId}`, input);
  }

  /** DELETE /api/chat/sessions/:sessionId */
  deleteChatSession(sessionId: string): Promise<{ session_id: string; deleted: boolean }> {
    return this.del<{ session_id: string; deleted: boolean }>(`/api/chat/sessions/${sessionId}`);
  }

  /** GET /api/chat/:sessionId/turn-status */
  getTurnStatus(sessionId: string): Promise<{ active: boolean }> {
    return this.get<{ active: boolean }>(`/api/chat/${sessionId}/turn-status`);
  }

  /** GET /api/chat/agents */
  getChatAgents(): Promise<ChatAgentsResponse> {
    return this.get<ChatAgentsResponse>("/api/chat/agents");
  }

  /**
   * POST to chat stream endpoint and return the raw SSE Response for streaming.
   * Use with streamSSE() for consuming events.
   */
  async chatStream(sessionId: string, text: string, signal?: AbortSignal): Promise<Response> {
    const response = await this._fetchImpl(this.getFullUrl(`/api/chat/${sessionId}/stream`), {
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

  /**
   * Stream chat events as an async generator.
   * @example
   * ```typescript
   * for await (const event of client.streamChat(sessionId, "Hello")) {
   *   if (event.t === "CHAT_CHUNK") console.log(event.content);
   * }
   * ```
   */
  async *streamChat(sessionId: string, text: string, signal?: AbortSignal): AsyncGenerator<ChatStreamEvent> {
    const response = await this.chatStream(sessionId, text, signal);
    
    if (!response.body) {
      throw new ApiError(0, "Chat stream response has no body");
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
          const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
          if (dataLine) {
            yield JSON.parse(dataLine.slice(6)) as ChatStreamEvent;
          }
        }
      }
    } finally {
      await reader.cancel().catch(() => {});
    }
  }

  // -- Filesystem -----------------------------------------------------------

  /** GET /api/fs/browse */
  browsePath(path?: string): Promise<FsBrowseResponse> {
    const params = new URLSearchParams();
    if (path) params.set("path", path);
    return this.get<FsBrowseResponse>(`/api/fs/browse${withQuery(params)}`);
  }

  // -- Plugins --------------------------------------------------------------

  /** GET /api/plugins */
  getPlugins(): Promise<{ plugins: Array<{ name: string; builtin: boolean; package: string | null; version: string | null }> }> {
    return this.get("/api/plugins");
  }

  /** GET /api/plugins/:name/preflight */
  getPluginPreflight(name: string): Promise<{ plugin: string; checks: Array<{ ok: boolean; message: string; fix_hint: string | null }>; ready: boolean }> {
    return this.get(`/api/plugins/${name}/preflight`);
  }

  /** GET /api/plugins/:name/detect-repo */
  detectPluginRepo(name: string): Promise<{ repo_slug: string | null }> {
    return this.get(`/api/plugins/${name}/detect-repo`);
  }

  /** POST /api/plugins/:name/import */
  runPluginImport(name: string, config: Record<string, unknown>): Promise<{ created: number; updated: number; skipped: number; errors: string[] }> {
    return this.post(`/api/plugins/${name}/import`, config);
  }

  // -- Preflight ------------------------------------------------------------

  /** GET /api/preflight */
  getPreflight(agentBackend?: string): Promise<PreflightResponse> {
    const params = new URLSearchParams();
    if (agentBackend) params.set("agent_backend", agentBackend);
    return this.get<PreflightResponse>(`/api/preflight${withQuery(params)}`);
  }

  // -- Presence -------------------------------------------------------------

  /** GET /api/presence */
  getPresence(): Promise<ClientPresence[]> {
    return this.get<ClientPresence[]>("/api/presence");
  }

  /** POST /api/presence/heartbeat */
  sendPresenceHeartbeat(input: PresenceHeartbeatInput): Promise<void> {
    return this.post<void>("/api/presence/heartbeat", input);
  }

  // -- Health ---------------------------------------------------------------

  /**
   * GET /health - Auth-exempt endpoint for connectivity checking.
   * Returns true if server is reachable.
   */
  async ping(): Promise<boolean> {
    try {
      const response = await this._fetchImpl(this.getFullUrl("/health"), {
        headers: { Accept: "application/json" },
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * GET /health with full response.
   */
  async getHealth(): Promise<{ status: string; version: string }> {
    const response = await this._fetchImpl(this.getFullUrl("/health"), {
      headers: { Accept: "application/json" },
    });
    
    if (!response.ok) {
      throw new ApiError(response.status, "Health check failed");
    }
    
    return response.json() as Promise<{ status: string; version: string }>;
  }

  /**
   * Verify API is accessible with current configuration.
   * Throws ApiError if not accessible.
   */
  async verifyApi(): Promise<void> {
    await this.getSettings();
  }
}

// ----------------------------------------------------------------------------
// Legacy export name alias for compatibility
// ----------------------------------------------------------------------------

export { KaganApiClient as KaganClient };
