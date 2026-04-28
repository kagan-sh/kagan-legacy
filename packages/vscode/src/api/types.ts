export type TaskStatus = "BACKLOG" | "IN_PROGRESS" | "REVIEW" | "DONE";
export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type SessionStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
export type ReviewVerdictState = "PASS" | "FAIL";
export type LauncherBackend =
  | "tmux"
  | "nvim"
  | "vscode"
  | "cursor"
  | "windsurf"
  | "kiro"
  | "antigravity";

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
} as const;

export type EventType = (typeof EVENT_TYPE)[keyof typeof EVENT_TYPE];

export const SSE_TYPE = {
  TASK_UPDATED: "TASK_UPDATED",
  SESSION_EVENT: "SESSION_EVENT",
} as const;

export type SSEType = (typeof SSE_TYPE)[keyof typeof SSE_TYPE];

export const TASK_COLUMNS: TaskStatus[] = ["BACKLOG", "IN_PROGRESS", "REVIEW", "DONE"];

export const PRIORITY_ICONS: Record<Priority, string> = {
  LOW: "arrow-down",
  MEDIUM: "dash",
  HIGH: "arrow-up",
  CRITICAL: "flame",
};

export const STATUS_ICONS: Record<TaskStatus, string> = {
  BACKLOG: "inbox",
  IN_PROGRESS: "play-circle",
  REVIEW: "eye",
  DONE: "check",
};

export interface ActiveSession {
  id: string;
  status: SessionStatus | string;
  launcher: string | null;
  agent_backend: string;
  started_at: string;
  context_window_used: number | null;
  context_window_size: number | null;
  cost_amount: number | null;
  cost_currency: string | null;
}

export interface ReviewVerdict {
  criterion_index: number;
  verdict: ReviewVerdictState;
  reason: string;
}

export interface WireTask {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  base_branch: string | null;
  acceptance_criteria: string[];
  agent_backend: string | null;
  launcher: string | null;
  review_approved: boolean;
  review_verdicts: ReviewVerdict[];
  updated_at: string | null;
  last_event_at: string | null;
  has_workspace: boolean;
  review_running: boolean;
  active_session: ActiveSession | null;
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

export interface DiffFile {
  path: string;
  status: string;
  insertions: number;
  deletions: number;
}

export interface DiffStats {
  files_changed: number;
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

export interface ReviewStatusResponse {
  task_id: string;
  status: TaskStatus | string;
  review_approved: boolean;
}

export interface CreateTaskInput {
  title: string;
  description?: string;
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

export interface RunTaskInput {
  agent_backend?: string;
  launcher?: string;
  persona?: string;
}

export interface ReviewDecisionInput {
  action: "approve" | "reject" | "merge" | "rebase";
  feedback?: string;
}

export interface ReviewDecisionResponse {
  action: ReviewDecisionInput["action"];
  task?: WireTask;
  task_id?: string;
}

export interface SettingsResponse {
  [key: string]: string | undefined;
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

// ── Chat / Orchestrator ───────────────────────────────────────────────────

export interface WireChatSession {
  id: string;
  label: string | null;
  agent_backend: string | null;
  source: string;
  updated_at?: string;
  message_count?: number;
  project_id?: string | null;
}

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

export interface WireEnvelope<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
  error_code: string | null;
}

// Analytics
export interface BackendStats {
  agent_backend: string;
  count: number;
  success_rate: number;
  avg_duration_seconds: number | null;
  retry_rate: number;
}

export interface SessionTimelineEntry {
  date: string;
  total: number;
  completed: number;
  failed: number;
  cancelled: number;
  running: number;
  pending: number;
}

export interface AnalyticsExport {
  exported_at: string | null;
  period_days: number;
  backend_stats: BackendStats[];
  session_timeline: SessionTimelineEntry[];
}

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

// Doctor / preflight
export interface DoctorCheckResponse {
  name: string;
  status: string;
  message: string;
  fix_hint: string;
  verify_hint: string;
  category: string;
  is_blocking: boolean;
}

export interface DoctorReportResponse {
  checks: DoctorCheckResponse[];
  ok: boolean;
  fail_count: number;
  warn_count: number;
}

// ── Chat multi-client / watch types ──────────────────────────────────────────

export const CHAT_WATCH_TYPE = {
  CHAT_CHUNK: "CHAT_CHUNK",
  CHAT_TOOL_START: "CHAT_TOOL_START",
  CHAT_TOOL_PROGRESS: "CHAT_TOOL_PROGRESS",
  CHAT_DONE: "CHAT_DONE",
  CHAT_USER_MESSAGE: "CHAT_USER_MESSAGE",
  CHAT_ASSISTANT_MESSAGE: "CHAT_ASSISTANT_MESSAGE",
  CHAT_TURN_STARTED: "CHAT_TURN_STARTED",
  CHAT_TURN_TERMINATED: "CHAT_TURN_TERMINATED",
  CHAT_SESSION_UPDATED: "CHAT_SESSION_UPDATED",
  CHAT_ERROR: "CHAT_ERROR",
} as const;

export type ChatWatchType = (typeof CHAT_WATCH_TYPE)[keyof typeof CHAT_WATCH_TYPE];

/** A persisted chat message returned by GET /api/chat/sessions/{id}/messages */
export interface ChatMessageDetailResponse {
  id: number;
  session_id: string;
  role: string;
  content: string;
  terminated_at_user_request: boolean;
  created_at: string;
}

/** Body returned by POST /api/chat/{id}/stream when status 409 */
export interface TurnInProgressResponse {
  ok: false;
  error_code: "TURN_IN_PROGRESS";
  running_since: string;
  partial_chars: number;
}

/** Full turn status returned by GET /api/chat/{id}/turn-status */
export interface TurnStatusResponse {
  active: boolean;
  partial_chars: number | null;
  running_since: string | null;
}

// Watch event shapes from GET /api/chat/sessions/{id}/watch

export interface ChatWatchChunk {
  t: "CHAT_CHUNK";
  content: string;
  thought?: boolean;
}

export interface ChatWatchToolStart {
  t: "CHAT_TOOL_START";
  tool: string;
}

export interface ChatWatchToolProgress {
  t: "CHAT_TOOL_PROGRESS";
  tool: string;
  status: string | null;
}

export interface ChatWatchDone {
  t: "CHAT_DONE";
  full_response: string;
}

export interface ChatWatchUserMessage {
  t: "CHAT_USER_MESSAGE";
  message_id: number;
  content: string;
}

export interface ChatWatchAssistantMessage {
  t: "CHAT_ASSISTANT_MESSAGE";
  message_id: number;
  content: string;
  terminated: boolean;
}

export interface ChatWatchTurnStarted {
  t: "CHAT_TURN_STARTED";
  at: string;
  by_source: string | null;
}

export interface ChatWatchTurnTerminated {
  t: "CHAT_TURN_TERMINATED";
  reason: "user" | "takeover" | string;
}

export interface ChatWatchSessionUpdated {
  t: "CHAT_SESSION_UPDATED";
  session: WireChatSession;
}

export interface ChatWatchError {
  t: "CHAT_ERROR";
  error: string;
}

export type ChatWatchEvent =
  | ChatWatchChunk
  | ChatWatchToolStart
  | ChatWatchToolProgress
  | ChatWatchDone
  | ChatWatchUserMessage
  | ChatWatchAssistantMessage
  | ChatWatchTurnStarted
  | ChatWatchTurnTerminated
  | ChatWatchSessionUpdated
  | ChatWatchError;
