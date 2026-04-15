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
  type: string;
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
