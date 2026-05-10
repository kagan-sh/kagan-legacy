/**
 * Web API client — thin subclass of the shared KaganApiClient.
 *
 * Adds browser-specific behaviour:
 *   - Bundled-web mode: same-origin relative URLs, no auth token needed.
 *   - configureBundledWeb() / isBundledWeb for the auth hydration flow.
 *   - Compatibility aliases for legacy method names used across the web codebase.
 *
 * All HTTP plumbing (envelope unwrapping, error handling, retry) lives in the
 * shared base. Do not duplicate it here.
 */

import {
  KaganApiClient as BaseClient,
  ApiError,
} from '@kagan/shared-api-client';
import type {
  TaskStatus,
  WireTask,
  UpdateTaskInput,
  SessionItemResponse,
  SessionsResponse,
  CreateSessionRequest,
} from '@kagan/shared-api-client';

export { ApiError, CHAT_STREAM_EVENT } from '@kagan/shared-api-client';
export type {
  ChatStreamEvent,
  ChatStreamEventType,
  ChatStreamChunk,
  ChatStreamToolStart,
  ChatStreamToolProgress,
  ChatStreamDone,
  ChatStreamError,
  ChatStreamSessionUpdated,
} from '@kagan/shared-api-client';

// ---------------------------------------------------------------------------
// Web subclass
// ---------------------------------------------------------------------------

export class KaganApiClient extends BaseClient {
  private _bundledWeb = false;

  /**
   * In the web app the client is instantiated once at module load with no
   * arguments (bundled-web mode is configured later via configureBundledWeb).
   * When the user provides a remote URL in settings, setBaseUrl is called.
   */
  constructor(baseUrl = '') {
    // Pass an empty baseUrl; protocol is irrelevant in bundled mode.
    super({ baseUrl, protocol: 'http', clientType: 'web' });
  }

  // -- Bundled-web helpers --------------------------------------------------

  /**
   * Mark this client as running in bundled-web mode.
   * Clears the base URL so all requests use relative paths (same origin).
   */
  configureBundledWeb(): void {
    this._bundledWeb = true;
    this.setBaseUrl('');
  }

  get isBundledWeb(): boolean {
    return this._bundledWeb;
  }

  override isConfigured(): boolean {
    if (this._bundledWeb) return true;
    return super.isConfigured();
  }

  /**
   * In bundled-web mode return '' so that fetch() uses same-origin relative
   * paths. Otherwise delegate to the base implementation.
   */
  override getBaseUrl(): string {
    if (this._bundledWeb || !super.isConfigured()) return '';
    return super.getBaseUrl();
  }

  /**
   * Override to return a relative path (no protocol + host) in bundled mode.
   * The base class always prepends `${protocol}://${host}`.
   */
  override getFullUrl(path: string): string {
    if (this._bundledWeb || !super.isConfigured()) return path;
    return super.getFullUrl(path);
  }

  /**
   * Health check — hits /health directly (auth-exempt).
   * In bundled mode the base URL is '' so we use the relative path.
   */
  override async getHealth(): Promise<{ status: string; version: string }> {
    const baseUrl = this.getBaseUrl();
    const url = baseUrl ? `${baseUrl}/health` : '/health';
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new ApiError(response.status, 'Health check failed');
    return response.json() as Promise<{ status: string; version: string }>;
  }

  // -- Web-specific method aliases ------------------------------------------
  // The shared base uses concise canonical names; the web codebase predates
  // that naming and callers use the names below. Aliases avoid a mass rename.

  /** Alias for transitionStatus (legacy web name). */
  transitionTaskStatus(taskId: string, status: TaskStatus): Promise<WireTask> {
    return this.transitionStatus(taskId, status);
  }

  /** Alias for sendFollowUp (legacy web name). */
  sendTaskFollowUp(taskId: string, text: string): Promise<WireTask> {
    return this.sendFollowUp(taskId, text);
  }

  /**
   * Alias for updateSettings (legacy web name).
   * The web codebase passes Record<string, string> rather than SettingsResponse.
   */
  setSettings(input: Record<string, string>): Promise<Record<string, string>> {
    return this.updateSettings(input) as Promise<Record<string, string>>;
  }

  /** Alias for updateTask (web consumers pass UpdateTaskInput directly). */
  override updateTask(taskId: string, input: UpdateTaskInput): Promise<WireTask> {
    return super.updateTask(taskId, input);
  }

  /** POST /api/chat/sessions/:sessionId/permission/:futureId */
  async resolvePermission(sessionId: string, futureId: string, outcome: string, feedback?: string): Promise<void> {
    await this.post<void>(`/api/chat/sessions/${sessionId}/permission/${futureId}`, { outcome, feedback });
  }

  // -- Unified sessions API (Agent D) ----------------------------------------

  /** GET /api/v1/sessions */
  async getSessions(): Promise<SessionsResponse> {
    return this.get<SessionsResponse>('/api/v1/sessions');
  }

  /** POST /api/v1/sessions */
  async createSession(request: CreateSessionRequest): Promise<SessionItemResponse> {
    return this.post<SessionItemResponse>('/api/v1/sessions', request);
  }

  /** POST /api/v1/sessions/:sessionId/message */
  async sendSessionMessage(
    sessionId: string,
    text: string,
    options?: { agent_backend?: string; attachments?: unknown[] },
  ): Promise<Response> {
    const response = await this._fetchImpl(this.getFullUrl(`/api/v1/sessions/${encodeURIComponent(sessionId)}/message`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this.getAuthHeaders(),
      },
      body: JSON.stringify({ text, ...options }),
    });
    if (!response.ok) {
      throw new ApiError(response.status, `Session message failed: ${response.status}`);
    }
    return response;
  }

  /** POST /api/v1/sessions/:sessionId/stop */
  async stopSession(sessionId: string): Promise<void> {
    await this.post<void>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/stop`, {});
  }

  /** POST /api/v1/sessions/:sessionId/close */
  async closeSession(sessionId: string): Promise<void> {
    await this.post<void>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/close`, {});
  }
}

// ---------------------------------------------------------------------------
// Singleton instance used throughout the web app via @/lib/api/client
// ---------------------------------------------------------------------------

export const apiClient = new KaganApiClient();
