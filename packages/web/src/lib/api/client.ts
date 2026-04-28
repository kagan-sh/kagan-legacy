import type {
  AnalyticsExport,
  AnalyticsByRole,
  AnalyticsByTaskType,
  BackendRecommendation,
  BackendStats,
  BackendTaskRecommendation,
  ChatAgentsResponse,
  ChatMessageDetailResponse,
  ClientPresence,
  CombinedStats,
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
  RoleStats,
  SessionTimelineEntry,
  TaskCommitsResponse,
  TaskDeletedResponse,
  TaskStatus,
  TaskTypeStats,
  TaskWorktreeResponse,
  TransitionStatusInput,
  TurnStatusResponse,
  UpdateTaskInput,
  WorkflowResolvedSettings,
  WireChatSession,
  WireChatSessionSummary,
  WireEnvelope,
  WireEvent,
  WireProject,
  WireRepository,
  WireTask,
  WireTaskSession,
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
    baseUrl = baseUrl.replace(/\/+$/, '');
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
    if (envelope?.data === undefined || envelope?.data === null) {
      throw new ApiError(response.status, 'Response missing data');
    }
    return envelope.data as T;
  }

  /**
   * All server responses are wrapped in {@link WireEnvelope}.
   * This method unwraps the envelope, throwing on errors.
   */
  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    return this._doRequest<T>(path, options);
  }

  // -- Tasks ----------------------------------------------------------------

  /** GET /api/tasks?status=...&repo_id=... */
  async getTasks(status?: TaskStatus, repoId?: string): Promise<WireTask[]> {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (repoId) params.set('repo_id', repoId);
    const query = params.toString() ? `?${params.toString()}` : '';
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

  async runTask(
    taskId: string,
    options?: {
      agent_backend?: string;
      persona?: string;
      launcher?: string;
    },
  ): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}/run`, {
      method: 'POST',
      body: options ?? {},
    });
  }

  async runReview(taskId: string, options?: { agent_backend?: string }): Promise<WireTask> {
    return this.runTask(taskId, options);
  }

  /** POST /api/tasks/:taskId/cancel — Cancel/stop a running session */
  async cancelTask(taskId: string): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}/cancel`, {
      method: 'POST',
      body: {},
    });
  }

  /** POST /api/tasks/:taskId/follow-up — Cancel + restart with follow-up text */
  async sendTaskFollowUp(taskId: string, text: string): Promise<WireTask> {
    return this.request<WireTask>(`/api/tasks/${taskId}/follow-up`, {
      method: 'POST',
      body: { text },
    });
  }

  async detachTask(taskId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/tasks/${taskId}/detach`, {
      method: 'POST',
      body: {},
    });
  }

  async getTaskEvents(
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
    if (options?.limit !== undefined) params.set('limit', String(options.limit));
    if (options?.offset !== undefined) params.set('offset', String(options.offset));
    if (options?.tail) params.set('tail', '1');
    if (options?.before) params.set('before', options.before);
    if (options?.before_id) params.set('before_id', options.before_id);
    if (options?.after) params.set('after', options.after);
    if (options?.after_id) params.set('after_id', options.after_id);
    if (options?.session_id) params.set('session_id', options.session_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    return this.request<WireEvent[]>(`/api/tasks/${taskId}/events${query}`);
  }

  async getTaskSessions(taskId: string): Promise<WireTaskSession[]> {
    return this.request<WireTaskSession[]>(`/api/tasks/${taskId}/sessions`);
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
    chat_last_active_session?: string;
  }> {
    return this.request('/api/settings/resolved');
  }

  /** GET /api/presence — list connected clients. */
  async getPresence(): Promise<ClientPresence[]> {
    return this.request<ClientPresence[]>('/api/presence');
  }

  /** POST /api/presence/heartbeat — refresh presence and optional task focus. */
  async sendPresenceHeartbeat(input: {
    client_id: string;
    client_type: string;
    active_task_id?: string | null;
    user_label?: string;
  }): Promise<void> {
    await this.request('/api/presence/heartbeat', {
      method: 'POST',
      body: input,
    });
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
  async getChatSessions(projectId?: string): Promise<WireChatSessionSummary[]> {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return this.request<WireChatSessionSummary[]>(`/api/chat/sessions${query}`);
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

  /** PATCH /api/chat/sessions/:sessionId */
  async updateChatSession(
    sessionId: string,
    input: { agent_backend?: string },
  ): Promise<WireChatSession> {
    return this.request<WireChatSession>(`/api/chat/sessions/${sessionId}`, {
      method: 'PATCH',
      body: input,
    });
  }

  /** DELETE /api/chat/sessions/:sessionId */
  async deleteChatSession(sessionId: string): Promise<{ session_id: string; deleted: boolean }> {
    return this.request<{ session_id: string; deleted: boolean }>(
      `/api/chat/sessions/${sessionId}`,
      { method: 'DELETE' },
    );
  }

  /** GET /api/chat/:sessionId/turn-status — check if a turn is still running */
  async getTurnStatus(sessionId: string): Promise<TurnStatusResponse> {
    return this.request<TurnStatusResponse>(`/api/chat/${sessionId}/turn-status`);
  }

  /** POST /api/chat/:sessionId/interrupt — cancel the running turn */
  async interruptChatTurn(sessionId: string, reason: 'user' | 'takeover'): Promise<void> {
    await this.request(`/api/chat/${sessionId}/interrupt`, {
      method: 'POST',
      body: { reason },
    });
  }

  /** GET /api/chat/sessions/:sessionId/messages?after_id=N — cursor-tail for missed messages */
  async getChatMessages(sessionId: string, afterId?: number): Promise<ChatMessageDetailResponse[]> {
    const query = afterId !== undefined ? `?after_id=${afterId}` : '';
    return this.request<ChatMessageDetailResponse[]>(`/api/chat/sessions/${sessionId}/messages${query}`);
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

  // -- Analytics -------------------------------------------------------------

  /** GET /api/analytics/backend-stats */
  async getBackendStats(params?: { days?: number }): Promise<BackendStats[]> {
    const query = params?.days ? `?days=${params.days}` : '';
    return this.request<BackendStats[]>(`/api/analytics/backend-stats${query}`);
  }

  /** GET /api/analytics/session-timeline?days=... */
  async getSessionTimeline(params?: { days?: number }): Promise<SessionTimelineEntry[]> {
    const query = params?.days ? `?days=${params.days}` : '';
    return this.request<SessionTimelineEntry[]>(`/api/analytics/session-timeline${query}`);
  }

  /** GET /api/analytics/export?days=... */
  async getAnalyticsExport(params?: { days?: number }): Promise<AnalyticsExport> {
    const query = params?.days ? `?days=${params.days}` : '';
    return this.request<AnalyticsExport>(`/api/analytics/export${query}`);
  }

  /** GET /api/analytics/recommended-backend */
  async getRecommendedBackend(): Promise<BackendRecommendation> {
    return this.request<BackendRecommendation>('/api/analytics/recommended-backend');
  }

  /** GET /api/analytics/by-role - Returns backend stats grouped by agent role */
  async getAnalyticsByRole(params?: { days?: number }): Promise<AnalyticsByRole> {
    const query = params?.days ? `?days=${params.days}` : '';
    return this.request<AnalyticsByRole>(`/api/analytics/by-role${query}`);
  }

  /** GET /api/analytics/by-task-type - Returns backend stats grouped by task type */
  async getAnalyticsByTaskType(params?: { days?: number }): Promise<AnalyticsByTaskType> {
    const query = params?.days ? `?days=${params.days}` : '';
    return this.request<AnalyticsByTaskType>(`/api/analytics/by-task-type${query}`);
  }

  /** GET /api/analytics/by-role-and-task-type - Returns filtered backend stats */
  async getAnalyticsByRoleAndTaskType(params?: { role?: string; task_type?: string; days?: number }): Promise<CombinedStats[]> {
    const qs = new URLSearchParams();
    if (params?.role) qs.set('role', params.role);
    if (params?.task_type) qs.set('task_type', params.task_type);
    if (params?.days) qs.set('days', String(params.days));
    const query = qs.toString() ? `?${qs.toString()}` : '';
    return this.request<CombinedStats[]>(`/api/analytics/by-role-and-task-type${query}`);
  }

  /** GET /api/analytics/recommend-for-task - Get intelligent backend recommendation */
  async recommendBackendForTask(params: { title: string; description?: string; role?: string }): Promise<BackendTaskRecommendation> {
    const qs = new URLSearchParams();
    qs.set('title', params.title);
    if (params.description) qs.set('description', params.description);
    if (params.role) qs.set('role', params.role);
    return this.request<BackendTaskRecommendation>(`/api/analytics/recommend-for-task?${qs.toString()}`);
  }

  /** GET /api/analytics/by-role (legacy) */
  async getStatsByRole(): Promise<RoleStats[]> {
    const grouped = await this.getAnalyticsByRole();
    return Object.values(grouped).flat();
  }

  /** GET /api/analytics/by-task-type (legacy) */
  async getStatsByTaskType(): Promise<TaskTypeStats[]> {
    const grouped = await this.getAnalyticsByTaskType();
    return Object.values(grouped).flat();
  }

  /** GET /api/analytics/combined (legacy) */
  async getCombinedStats(): Promise<CombinedStats[]> {
    return this.getAnalyticsByRoleAndTaskType();
  }

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

  /** GET /api/plugins/:name/preview */
  async previewPluginIssues(
    name: string,
    params: { repo_slug: string; state?: string; labels?: string; limit?: number },
  ): Promise<{ plugin: string; issues: Array<{ number: number; title: string; state: string; labels: string[]; url: string; already_synced: boolean }>; total: number }> {
    const qs = new URLSearchParams();
    qs.set('repo_slug', params.repo_slug);
    if (params.state) qs.set('state', params.state);
    if (params.labels) qs.set('labels', params.labels);
    if (params.limit) qs.set('limit', String(params.limit));
    return this.request(`/api/plugins/${name}/preview?${qs.toString()}`);
  }

  /** POST /api/plugins/:name/import */
  async runPluginImport(name: string, config: Record<string, unknown>): Promise<{ created: number; updated: number; skipped: number; errors: string[] }> {
    return this.request(`/api/plugins/${name}/import`, { method: 'POST', body: config });
  }

  // -- Doctor ---------------------------------------------------------------

  /** GET /api/doctor — run backend preflight checks, returns DoctorReportResponse */
  async getDoctorReport(): Promise<import('@/lib/api/generated-wire-types').DoctorReportResponse> {
    return this.request('/api/doctor');
  }
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------

export const apiClient = new KaganApiClient();
