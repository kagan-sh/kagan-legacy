/**
 * Wire types matching packages/wire/src/generated.ts exactly.
 * Defined inline so the mobile app doesn't need npm workspace resolution.
 */

// ---------------------------------------------------------------------------
// Wire types (from @kagan/wire)
// ---------------------------------------------------------------------------

export interface WireTaskActiveSession {
  id: string;
  status: string;
  mode: string;
  agent_backend: string;
  started_at: string;
  context_window_used?: number | null;
  context_window_size?: number | null;
  cost_amount?: number | null;
  cost_currency?: string | null;
}

export interface WireTaskSession {
  id: string;
  mode: string;
  status: string;
  agent_backend: string;
  started_at: string;
  context_window_used?: number | null;
  context_window_size?: number | null;
  cost_amount?: number | null;
  cost_currency?: string | null;
}

export type ReviewVerdict = {
  criterion_index: number;
  verdict: 'PASS' | 'FAIL';
  reason: string;
};

/** Serialisable representation of a Kagan task. */
export interface WireTask {
  id: string;
  title: string;
  description?: string;
  /** Value of TaskStatus enum, e.g. 'BACKLOG'. */
  status: string;
  /** Name of Priority enum, e.g. 'HIGH'. */
  priority: string;
  /** Value of WorkMode enum, e.g. 'AUTO'. */
  execution_mode: string;
  base_branch?: string | null;
  acceptance_criteria?: string[];
  agent_backend?: string | null;
  launcher?: string | null;
  review_approved?: boolean;
  review_verdicts?: ReviewVerdict[];
  updated_at?: string | null;
  last_event_at?: string | null;
  has_workspace?: boolean;
  review_running?: boolean;
  active_session?: WireTaskActiveSession | null;
}

/** Serialisable representation of a Kagan project. */
export interface WireProject {
  id: string;
  name: string;
  active?: boolean;
}

/** Serialisable representation of a Kagan repository linked to a project. */
export interface WireRepository {
  id: string;
  project_id: string;
  name: string;
  path: string;
  default_branch: string;
  selected?: boolean;
}

/** Serialisable representation of a chat message. */
export interface WireChatMessage {
  role: string;
  content: string;
}

/** Serialisable representation of a chat session (summary, no messages). */
export interface WireChatSessionSummary {
  id: string;
  label: string;
  source: string;
  agent_backend?: string | null;
  updated_at: string;
  message_count: number;
}

/** Serialisable representation of a chat session (with messages). */
export interface WireChatSession extends WireChatSessionSummary {
  messages: WireChatMessage[];
}

/** Serialisable representation of a Kagan event. */
export interface WireEvent {
  id: string;
  session_id: string;
  type: string;
  payload?: Record<string, unknown>;
  created_at: string;
}

/**
 * Generic wrapper for all wire responses.
 * ok=true → data carries payload.
 * ok=false → error carries a human-readable message.
 */
export interface WireEnvelope<T = unknown> {
  ok: boolean;
  data?: T | null;
  error?: string | null;
  error_code?: string | null;
}

// ---------------------------------------------------------------------------
// Domain aliases (used throughout the mobile app)
// ---------------------------------------------------------------------------

export type TaskStatus = 'BACKLOG' | 'IN_PROGRESS' | 'REVIEW' | 'DONE';
export type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type WorkMode = 'AUTO' | 'PAIR';

// ---------------------------------------------------------------------------
// Request bodies
// ---------------------------------------------------------------------------

export interface CreateTaskInput {
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: Priority;
  execution_mode?: WorkMode;
  base_branch?: string;
  acceptance_criteria?: string[];
  agent_backend?: string;
  launcher?: string;
}

export interface CreateChatSessionInput {
  agent_backend?: string;
  label?: string;
}

export interface ChatAgentsResponse {
  backends: string[];
  default: string;
}

export interface UpdateTaskInput {
  title?: string;
  description?: string;
  priority?: Priority;
  execution_mode?: WorkMode;
  base_branch?: string;
  acceptance_criteria?: string[];
  agent_backend?: string;
  launcher?: string;
}

export interface TransitionStatusInput {
  status: TaskStatus;
}

export interface ReviewDecisionInput {
  action: 'approve' | 'reject' | 'merge' | 'rebase';
  feedback?: string;
  target_branch?: string;
}

// ---------------------------------------------------------------------------
// Response shapes (unwrapped from WireEnvelope.data)
// ---------------------------------------------------------------------------

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
  status: string;
  review_approved: boolean;
}

export interface ReviewDecideResponse {
  task?: WireTask;
  task_id?: string;
  action: string;
  reason?: string;
  reason_code?: string;
}

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
  insertions: number;
  deletions: number;
  status: string;
}

export interface TaskWorktreeResponse {
  task_id: string;
  worktree: {
    path: string;
    branch: string;
  } | null;
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

export interface WorkflowResolvedSettings {
  wip_limits: Record<TaskStatus, number>;
}

// ---------------------------------------------------------------------------
// Filesystem browsing
// ---------------------------------------------------------------------------

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
