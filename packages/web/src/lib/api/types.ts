/**
 * Wire types — generated from Python response models.
 * Canonical definitions live in generated-wire-types.ts (auto-generated).
 * This file re-exports them with legacy aliases and adds hand-written types.
 */

import type {
    ActiveSessionResponse,
    AgentBackendResponse,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummaryResponse,
    EventResponse,
    ProjectResponse,
    RepositoryResponse,
    ReviewVerdictResponse,
    TaskResponse,
    TaskSessionResponse,
} from "./generated-wire-types";

// Re-export generated types under their canonical names
export type {
    ActiveSessionResponse,
    AgentBackendResponse,
    ChatAgentsResponse,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummaryResponse,
    EventResponse,
    ProjectResponse,
    RepositoryResponse,
    ReviewVerdictResponse,
    TaskResponse,
    TaskSessionResponse,
} from "./generated-wire-types";

// ---------------------------------------------------------------------------
// Legacy aliases (used throughout the web app)
// ---------------------------------------------------------------------------

export type WireTaskActiveSession = ActiveSessionResponse;
export type WireTaskSession = TaskSessionResponse;
export type ReviewVerdict = ReviewVerdictResponse;
export type WireTask = TaskResponse;
export type WireProject = ProjectResponse;
export type WireRepository = RepositoryResponse;
export type WireChatMessage = ChatMessageResponse;
export type WireChatSessionSummary = ChatSessionSummaryResponse;
export type WireChatSession = ChatSessionResponse;
export type WireEvent = EventResponse;
export type AgentBackend = AgentBackendResponse;

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

export type TaskStatus = "BACKLOG" | "IN_PROGRESS" | "REVIEW" | "DONE";
export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

// ---------------------------------------------------------------------------
// Request bodies
// ---------------------------------------------------------------------------

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

export interface CreateChatSessionInput {
    agent_backend?: string;
    label?: string;
}

export interface UpdateTaskInput {
    title?: string;
    description?: string;
    priority?: Priority;
    base_branch?: string;
    acceptance_criteria?: string[];
    agent_backend?: string;
    launcher?: string;
}

export interface TransitionStatusInput {
    status: TaskStatus;
}

export interface ReviewDecisionInput {
    action: "approve" | "reject" | "merge" | "rebase";
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

// ---------------------------------------------------------------------------
// Client presence
// ---------------------------------------------------------------------------

export interface ClientPresence {
    client_id: string;
    client_type: string;
    connected_at: number;
    active_task_id: string | null;
    user_label: string;
}
