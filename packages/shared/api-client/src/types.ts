// ============================================================================
// Shared Types for Kagan API Client
// Consolidated from packages/web/src/lib/api/types.ts and packages/vscode/src/api/types.ts
// ============================================================================

// ----------------------------------------------------------------------------
// Domain Enums & Constants
// ----------------------------------------------------------------------------

export type TaskStatus = "BACKLOG" | "IN_PROGRESS" | "REVIEW" | "DONE";
export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type SessionStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
export type ReviewVerdictState = "PASS" | "FAIL";

export const TASK_COLUMNS: TaskStatus[] = ["BACKLOG", "IN_PROGRESS", "REVIEW", "DONE"];

export const EVENT_TYPE = {
  OUTPUT_CHUNK: "OUTPUT_CHUNK",
  AGENT_STATUS: "AGENT_STATUS",
  TOOL_CALL_START: "TOOL_CALL_START",
  TOOL_CALL_UPDATE: "TOOL_CALL_UPDATE",
  AGENT_COMPLETED: "AGENT_COMPLETED",
  AGENT_FAILED: "AGENT_FAILED",
  PLAN_UPDATE: "PLAN_UPDATE",
  TASK_STATUS_CHANGED: "TASK_STATUS_CHANGED",
  MERGE_COMPLETED: "MERGE_COMPLETED",
  MERGE_FAILED: "MERGE_FAILED",
  CRITERION_VERDICT: "CRITERION_VERDICT",
  AUTO_REVIEW_STARTED: "AUTO_REVIEW_STARTED",
} as const;

export type EventType = (typeof EVENT_TYPE)[keyof typeof EVENT_TYPE];

export const SSE_TYPE = {
  TASK_UPDATED: "TASK_UPDATED",
  SESSION_EVENT: "SESSION_EVENT",
} as const;

export type SSEType = (typeof SSE_TYPE)[keyof typeof SSE_TYPE];

// ----------------------------------------------------------------------------
// Wire Types (Core domain entities)
// ----------------------------------------------------------------------------

export interface ActiveSession {
  id: string;
  status: SessionStatus | string;
  launcher: string | null;
  agent_backend: string;
  agent_role?: string | null;
  started_at: string;
  context_window_used: number | null;
  context_window_size: number | null;
  cost_amount: number | null;
  cost_currency: string | null;
}

export interface ReviewVerdict {
  id: string;
  criterion_id: string;
  session_id?: string | null;
  verdict: ReviewVerdictState;
  reason: string;
}

export interface AcceptanceCriterion {
  id: string;
  task_id: string;
  ordinal: number;
  text: string;
}

export interface DiffSummary {
  files_changed: number;
  additions: number;
  deletions: number;
}

export interface WireTask {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  base_branch: string | null;
  acceptance_criteria: AcceptanceCriterion[];
  agent_backend: string | null;
  launcher: string | null;
  review_approved: boolean;
  review_verdicts: ReviewVerdict[];
  updated_at: string | null;
  last_event_at: string | null;
  has_workspace: boolean;
  review_running: boolean;
  active_session: ActiveSession | null;
  diff_summary?: DiffSummary | null;
}

export interface WireEvent {
  id: string;
  session_id: string | null;
  type: EventType | string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface WireTaskSession {
  id: string;
  launcher: string | null;
  status: SessionStatus | string;
  agent_backend: string;
  started_at: string;
}

export interface WireProject {
  id: string;
  name: string;
  active: boolean;
}

export interface WireRepository {
  id: string;
  project_id: string;
  name: string;
  path: string;
  default_branch: string;
  selected: boolean;
}

export interface WireChatSession {
  id: string;
  label: string | null;
  agent_backend: string | null;
  source: string;
  updated_at?: string;
  message_count?: number;
  project_id?: string | null;
}

export interface WireChatSessionSummary {
  id: string;
  label: string | null;
  agent_backend: string | null;
  source: string;
  updated_at?: string;
  message_count?: number;
  project_id?: string | null;
}

// ----------------------------------------------------------------------------
// Request Input Types
// ----------------------------------------------------------------------------

export interface CreateTaskInput {
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: Priority;
  base_branch?: string;
  acceptance_criteria?: string[];
  agent_backend?: string;
  launcher?: string;
}

export interface UpdateTaskInput {
  title?: string;
  description?: string;
  priority?: Priority;
  base_branch?: string;
  acceptance_criteria?: string[];
  agent_backend?: string;
  launcher?: string | null;
}

export interface TransitionStatusInput {
  status: TaskStatus;
}

export interface RunTaskInput {
  agent_backend?: string;
  launcher?: string;
  persona?: string;
}

export interface ReviewDecisionInput {
  action: "approve" | "reject" | "merge" | "rebase";
  feedback?: string;
  target_branch?: string;
}

export interface CreateChatSessionInput {
  agent_backend?: string;
  label?: string;
}

export interface CreateProjectInput {
  name: string;
}

// ----------------------------------------------------------------------------
// Response Types
// ----------------------------------------------------------------------------

/**
 * Generic wrapper for all wire responses.
 * ok=true → data carries payload.
 * ok=false → error carries a human-readable message.
 */
export interface WireEnvelope<T = unknown> {
  ok: boolean;
  data: T | null;
  error: string | null;
  error_code: string | null;
}

export interface TaskDeletedResponse {
  task_id: string;
  deleted: boolean;
}

export interface ProjectActivatedResponse {
  project_id: string;
  active: boolean;
}

export interface ProjectDeletedResponse {
  project_id: string;
  deleted: boolean;
}

export interface ReviewStatusResponse {
  task_id: string;
  status: TaskStatus | string;
  review_approved: boolean;
}

export interface ReviewDecideResponse {
  task?: WireTask;
  task_id?: string;
  action: string;
  reason?: string;
  reason_code?: string;
}

export interface ReviewDecisionResponse {
  action: ReviewDecisionInput["action"];
  task?: WireTask;
  task_id?: string;
}

export interface SettingsResponse {
  [key: string]: string | undefined;
}

export interface ResolvedSettingsResponse {
  git_user_name: string;
  git_user_email: string;
  dotfile_overrides: Record<string, string | null>;
  workflow: WorkflowResolvedSettings;
  chat_last_active_session?: string;
}

export interface WorkflowResolvedSettings {
  wip_limits: Record<TaskStatus, number>;
}

export interface AgentBackendResponse {
  name: string;
  available: boolean;
  reference?: boolean;
}

export interface ChatAgentsResponse {
  backends: AgentBackendResponse[];
  default: string;
}

export type AgentBackend = AgentBackendResponse;

export interface PreflightCheck {
  name: string;
  status: string;
  message: string;
  fix_hint: string | null;
  is_blocking: boolean;
}

export interface PreflightResponse {
  checks: PreflightCheck[];
  ok: boolean;
}

export interface TaskCountsResponse {
  BACKLOG?: number;
  IN_PROGRESS?: number;
  REVIEW?: number;
  DONE?: number;
  [key: string]: number | undefined;
}

export interface DiffStats {
  files_changed: number;
  insertions: number;
  deletions: number;
}

export interface DiffFile {
  path: string;
  status: string;
  insertions: number;
  deletions: number;
}

export interface TaskWorktree {
  path: string;
  branch: string;
}

export interface TaskWorktreeResponse {
  task_id: string;
  worktree: TaskWorktree | null;
}

export interface TaskCommit {
  short_hash: string;
  message: string;
}

export interface TaskCommitsResponse {
  task_id: string;
  branch: string | null;
  base_branch: string;
  commits: TaskCommit[];
}

export interface TaskEventOptions {
  limit?: number;
  offset?: number;
  tail?: boolean;
  before?: string;
  before_id?: string;
  after?: string;
  after_id?: string;
  session_id?: string;
}

// ----------------------------------------------------------------------------
// Filesystem Browsing
// ----------------------------------------------------------------------------

export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
  is_git_repo: boolean;
}

export interface FsBrowseResponse {
  path: string;
  entries: FsEntry[];
}

// ----------------------------------------------------------------------------
// Client Presence
// ----------------------------------------------------------------------------

export interface ClientPresence {
  client_id: string;
  client_type: string;
  connected_at: number;
  active_task_id: string | null;
  user_label: string;
}

export interface PresenceHeartbeatInput {
  client_id: string;
  client_type: string;
  active_task_id?: string | null;
  user_label?: string;
}

// ----------------------------------------------------------------------------
// SSE Types
// ----------------------------------------------------------------------------

export interface SSETaskUpdated {
  type: typeof SSE_TYPE.TASK_UPDATED;
  task_id: string;
}

export interface SSESessionEvent {
  type: typeof SSE_TYPE.SESSION_EVENT;
  task_id: string;
  event: WireEvent;
}

export type SSEMessage = SSETaskUpdated | SSESessionEvent;

// ----------------------------------------------------------------------------
// Chat Stream Types
// ----------------------------------------------------------------------------

export interface ChatStreamChunk {
  t: "CHAT_CHUNK";
  content: string;
  thought?: boolean;
}

export interface ChatStreamToolStart {
  t: "CHAT_TOOL_START";
  tool: string;
}

export interface ChatStreamToolProgress {
  t: "CHAT_TOOL_PROGRESS";
  tool: string;
  status: string | null;
}

export interface ChatStreamDone {
  t: "CHAT_DONE";
  full_response: string;
}

export type ChatStreamEvent =
  | ChatStreamChunk
  | ChatStreamToolStart
  | ChatStreamToolProgress
  | ChatStreamDone;

// ----------------------------------------------------------------------------
// Client Configuration
// ----------------------------------------------------------------------------

export interface KaganClientConfig {
  baseUrl: string;
  protocol?: "http" | "https";
  token?: string;
  /**
   * Client type identifier for presence/tracking purposes.
   * @default "unknown"
   */
  clientType?: string;
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}
