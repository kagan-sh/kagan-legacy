import type {
  ChatAgentsResponse,
  CreateChatSessionInput,
  CreateTaskInput,
  DiffFile,
  DiffStats,
  FsBrowseResponse,
  PreflightResponse,
  ProjectActivatedResponse,
  ProjectDeletedResponse,
  ReviewDecideResponse,
  ReviewDecisionInput,
  ReviewStatusResponse,
  TaskCommitsResponse,
  TaskDeletedResponse,
  TaskStatus,
  TaskWorktreeResponse,
  TransitionStatusInput,
  UpdateTaskInput,
  WorkflowResolvedSettings,
  WireChatSession,
  WireChatSessionSummary,
  WireEnvelope,
  WireEvent,
  WireProject,
  WireRepository,
  WireTask,
} from '@/lib/api/types';

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

// ---------------------------------------------------------------------------
// Request helpers
// ---------------------------------------------------------------------------

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
};

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class KaganApiClient {
  private baseUrl: string;
  private _bundledWeb: boolean = false;

  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
  }

  // -- Configuration --------------------------------------------------------

  setBaseUrl(url: string): void {
    this.baseUrl = url;
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * Mark this client as running in bundled-web mode.
   * In this mode the app is served from the same origin as the API,
   * so no base URL or auth token is needed.
   */
  configureBundledWeb(): void {
    this._bundledWeb = true;
    this.baseUrl = '';
  }

  get isBundledWeb(): boolean {
    return this._bundledWeb;
  }

  isConfigured(): boolean {
    if (this._bundledWeb) return true;
    return Boolean(this.baseUrl);
  }

  // -- Core request ---------------------------------------------------------

  /** Perform the actual HTTP fetch and unwrap the WireEnvelope. Throws ApiError on failure. */
  private async _doRequest<T>(path: string, options: RequestOptions): Promise<T> {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> ?? {}),
    };

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    const isJson = response.headers.get('content-type')?.includes('application/json');
    const envelope = isJson ? ((await response.json()) as WireEnvelope<T>) : null;

    if (!response.ok) {
      const detail = envelope?.error ?? 'Request failed';
      throw new ApiError(response.status, detail);
    }

    if (envelope && envelope.ok === false) {
      throw new ApiError(response.status, envelope.error ?? 'Unknown error');
    }

    // Unwrap envelope — data lives inside .data
    return (envelope?.data as T) ?? ({} as T);
  }

  /**
   * All server responses are wrapped in {@link WireEnvelope}.
   * This method unwraps the envelope, throwing on errors.
   */
  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    return this._doRequest<T>(path, options);
  }

  // -- Tasks ----------------------------------------------------------------

  /** GET /api/tasks?status=... */
  async getTasks(status?: TaskStatus): Promise<WireTask[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return this.request<WireTask[]>(`/api/tasks${query}`);
  }

  /** POST /api/tasks */
  async createTask(input: CreateTaskInput): Promise<WireTask> {
    return this.request<WireTask>('/api/tasks', {
      method: 'POST',
      body: input,
    });
  }

  /** GET /api/tasks/:taskId */
  async getTask(taskId: string): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}`);
  }

  /** PATCH /api/tasks/:taskId */
  async updateTask(taskId: string, input: UpdateTaskInput): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}`, {
      method: 'PATCH',
      body: input,
    });
  }

  /** DELETE /api/tasks/:taskId */
  async deleteTask(taskId: string): Promise<TaskDeletedResponse> {
    return this.request<TaskDeletedResponse>(`/api/tasks/${taskId}`, {
      method: 'DELETE',
    });
  }

  /** POST /api/tasks/:taskId/status */
  async transitionTaskStatus(taskId: string, status: TaskStatus): Promise<WireTask> {
    const input: TransitionStatusInput = { status };
    return this.request<WireTask>(`/api/tasks/${taskId}/status`, {
      method: 'POST',
      body: input,
    });
  }

  /** POST /api/tasks/:taskId/run — Start an AUTO agent session */
  async runTask(taskId: string, options?: { agent_backend?: string; persona?: string }): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}/run`, {
      method: 'POST',
      body: options ?? {},
    });
  }

  async runReview(taskId: string, options?: { agent_backend?: string }): Promise<WireTask> {
    return this.runTask(taskId, options);
  }

  /** POST /api/tasks/:taskId/pair — Start a PAIR agent session */
  async pairTask(taskId: string, options?: { agent_backend?: string; persona?: string }): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}/pair`, {
      method: 'POST',
      body: options ?? {},
    });
  }

  /** POST /api/tasks/:taskId/cancel — Cancel/stop a running session */
  async cancelTask(taskId: string): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}/cancel`, {
      method: 'POST',
      body: {},
    });
  }

  /** POST /api/tasks/:taskId/end-pairing — End a PAIR session */
  async endPairing(taskId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/tasks/${taskId}/end-pairing`, {
      method: 'POST',
      body: {},
    });
  }

  async getTaskEvents(
    taskId: string,
    options?: { limit?: number; offset?: number; tail?: boolean; before?: string; session_id?: string },
  ): Promise<WireEvent[]> {
    const params = new URLSearchParams();
    if (options?.limit !== undefined) params.set('limit', String(options.limit));
    if (options?.offset !== undefined) params.set('offset', String(options.offset));
    if (options?.tail) params.set('tail', '1');
    if (options?.before) params.set('before', options.before);
    if (options?.session_id) params.set('session_id', options.session_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    return this.request<WireEvent[]>(`/api/tasks/${taskId}/events${query}`);
  }

  async getDiffStats(taskId: string): Promise<DiffStats> {
    const parseStats = (stats: {
      files_changed?: number;
      files?: number;
      insertions?: number;
      deletions?: number;
    }): DiffStats => ({
      files_changed: stats.files_changed ?? stats.files ?? 0,
      insertions: stats.insertions ?? 0,
      deletions: stats.deletions ?? 0,
    });

    try {
      const stats = await this.request<{
        files_changed?: number;
        files?: number;
        insertions?: number;
        deletions?: number;
      }>(`/api/tasks/${taskId}/diff/stats`);
      return parseStats(stats);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        const stats = await this.request<{
          files_changed?: number;
          files?: number;
          insertions?: number;
          deletions?: number;
        }>(`/api/tasks/${taskId}/diff`);
        return parseStats(stats);
      }
      throw error;
    }
  }

  async getDiffFiles(taskId: string): Promise<DiffFile[]> {
    const payload = await this.request<{ files?: DiffFile[] } | DiffFile[]>(
      `/api/tasks/${taskId}/diff/files`,
    );

    const files = Array.isArray(payload) ? payload : payload.files ?? [];
    return files.map((file) => ({
      path: file.path,
      insertions: file.insertions ?? 0,
      deletions: file.deletions ?? 0,
      status: file.status,
    }));
  }

  async getDiffRaw(taskId: string): Promise<string> {
    try {
      const payload = await this.request<{ task_id: string; diff?: string }>(
        `/api/tasks/${taskId}/diff/raw`,
      );
      return payload.diff ?? '';
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return '';
      }
      throw error;
    }
  }

  async getTaskWorktree(taskId: string): Promise<TaskWorktreeResponse> {
    return this.request<TaskWorktreeResponse>(`/api/tasks/${taskId}/worktree`);
  }

  async getTaskCommits(taskId: string): Promise<TaskCommitsResponse> {
    return this.request<TaskCommitsResponse>(`/api/tasks/${taskId}/commits`);
  }

  // -- Projects -------------------------------------------------------------

  /** GET /api/projects */
  async getProjects(): Promise<WireProject[]> {
    return this.request<WireProject[]>('/api/projects');
  }

  /** POST /api/projects */
  async createProject(name: string): Promise<WireProject> {
    return this.request<WireProject>('/api/projects', {
      method: 'POST',
      body: { name },
    });
  }

  /** POST /api/projects/:projectId/activate */
  async activateProject(projectId: string): Promise<ProjectActivatedResponse> {
    return this.request<ProjectActivatedResponse>(
      `/api/projects/${projectId}/activate`,
      { method: 'POST' },
    );
  }

  /** DELETE /api/projects/:projectId */
  async deleteProject(projectId: string): Promise<ProjectDeletedResponse> {
    return this.request<ProjectDeletedResponse>(`/api/projects/${projectId}`, {
      method: 'DELETE',
    });
  }

  // -- Repos ----------------------------------------------------------------

  /** GET /api/projects/:projectId/repos */
  async getProjectRepos(projectId: string): Promise<WireRepository[]> {
    return this.request<WireRepository[]>(`/api/projects/${projectId}/repos`);
  }

  /** POST /api/projects/:projectId/repos */
  async addProjectRepo(projectId: string, path: string): Promise<WireRepository> {
    return this.request<WireRepository>(`/api/projects/${projectId}/repos`, {
      method: 'POST',
      body: { path },
    });
  }

  /** DELETE /api/projects/:projectId/repos/:repoId */
  async deleteProjectRepo(projectId: string, repoId: string): Promise<void> {
    await this.request(`/api/projects/${projectId}/repos/${repoId}`, {
      method: 'DELETE',
    });
  }

  /** POST /api/projects/:projectId/repos/:repoId/select */
  async selectProjectRepo(projectId: string, repoId: string): Promise<{ repo_id: string; selected: boolean }> {
    return this.request<{ repo_id: string; selected: boolean }>(
      `/api/projects/${projectId}/repos/${repoId}/select`,
      { method: 'POST' },
    );
  }

  // -- Reviews --------------------------------------------------------------

  /** GET /api/tasks/:taskId/review */
  async getReview(taskId: string): Promise<ReviewStatusResponse> {
    return this.request<ReviewStatusResponse>(`/api/tasks/${taskId}/review`);
  }

  /** POST /api/tasks/:taskId/review/decide */
  async reviewDecide(
    taskId: string,
    input: ReviewDecisionInput,
  ): Promise<ReviewDecideResponse> {
    return this.request<ReviewDecideResponse>(
      `/api/tasks/${taskId}/review/decide`,
      { method: 'POST', body: input },
    );
  }

  /** GET /api/tasks/:taskId/review/conflicts */
  async getConflicts(taskId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      `/api/tasks/${taskId}/review/conflicts`,
    );
  }

  // -- Settings & Preflight -------------------------------------------------

  /** GET /api/settings */
  async getSettings(): Promise<Record<string, string>> {
    return this.request<Record<string, string>>('/api/settings');
  }

  /** GET /api/settings/resolved */
  async getResolvedSettings(): Promise<{
    git_user_name: string;
    git_user_email: string;
    dotfile_overrides: Record<string, string | null>;
    workflow: WorkflowResolvedSettings;
  }> {
    return this.request('/api/settings/resolved');
  }

  async setSettings(input: Record<string, string>): Promise<Record<string, string>> {
    return this.request<Record<string, string>>('/api/settings', {
      method: 'POST',
      body: input,
    });
  }

  /** GET /health — auth-exempt, returns server status and package version. */
  async getHealth(): Promise<{ status: string; version: string }> {
    const response = await fetch(`${this.baseUrl}/health`, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new ApiError(response.status, 'Health check failed');
    return response.json() as Promise<{ status: string; version: string }>;
  }

  /** GET /api/preflight?agent_backend=... */
  async getPreflight(agentBackend?: string): Promise<PreflightResponse> {
    const query = agentBackend
      ? `?agent_backend=${encodeURIComponent(agentBackend)}`
      : '';
    return this.request<PreflightResponse>(`/api/preflight${query}`);
  }

  // -- Chat Sessions -------------------------------------------------------

  /** GET /api/chat/sessions */
  async getChatSessions(): Promise<WireChatSessionSummary[]> {
    return this.request<WireChatSessionSummary[]>('/api/chat/sessions');
  }

  /** POST /api/chat/sessions */
  async createChatSession(input: CreateChatSessionInput): Promise<WireChatSession> {
    return this.request<WireChatSession>('/api/chat/sessions', {
      method: 'POST',
      body: input,
    });
  }

  /** GET /api/chat/sessions/:sessionId */
  async getChatSession(sessionId: string): Promise<WireChatSession> {
    return this.request<WireChatSession>(`/api/chat/sessions/${sessionId}`);
  }

  /** DELETE /api/chat/sessions/:sessionId */
  async deleteChatSession(sessionId: string): Promise<{ session_id: string; deleted: boolean }> {
    return this.request<{ session_id: string; deleted: boolean }>(
      `/api/chat/sessions/${sessionId}`,
      { method: 'DELETE' },
    );
  }

  /** GET /api/chat/agents */
  async getChatAgents(): Promise<ChatAgentsResponse> {
    return this.request<ChatAgentsResponse>('/api/chat/agents');
  }

  // -- Filesystem Browsing --------------------------------------------------

  /** GET /api/fs/browse?path=... */
  async browsePath(path?: string): Promise<FsBrowseResponse> {
    const query = path ? `?path=${encodeURIComponent(path)}` : '';
    return this.request<FsBrowseResponse>(`/api/fs/browse${query}`);
  }

  // -- Plugins ---------------------------------------------------------------

  /** GET /api/plugins */
  async getPlugins(): Promise<{ plugins: Array<{ name: string; builtin: boolean; package: string | null; version: string | null }> }> {
    return this.request('/api/plugins');
  }

  /** GET /api/plugins/:name/preflight */
  async getPluginPreflight(name: string): Promise<{ plugin: string; checks: Array<{ ok: boolean; message: string; fix_hint: string | null }>; ready: boolean }> {
    return this.request(`/api/plugins/${name}/preflight`);
  }

  /** GET /api/plugins/:name/detect-repo */
  async detectPluginRepo(name: string): Promise<{ repo_slug: string | null }> {
    return this.request(`/api/plugins/${name}/detect-repo`);
  }

  /** POST /api/plugins/:name/import */
  async runPluginImport(name: string, config: Record<string, unknown>): Promise<{ created: number; updated: number; skipped: number; errors: string[] }> {
    return this.request(`/api/plugins/${name}/import`, { method: 'POST', body: config });
  }
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------

export const apiClient = new KaganApiClient();
