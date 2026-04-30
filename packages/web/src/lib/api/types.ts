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
    DiffSummaryResponse,
    EventResponse,
    FsEntryResponse,
    ProjectResponse,
    RepositoryResponse,
    ReviewVerdictResponse,
    TaskResponse,
    TaskSessionResponse,
} from "./generated-wire-types";

// Re-export generated types under their canonical names
export type {
    AcceptanceCriterionResponse,
    ActiveSessionResponse,
    AgentBackendResponse,
    ChatAgentsResponse,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummaryResponse,
    DiffSummaryResponse,
    EventResponse,
    ProjectResponse,
    ProjectFolderResolutionResponse,
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
export type WireDiffSummary = DiffSummaryResponse;
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

export interface Mention {
    source: "kagan" | "github";
    id: string;
    title: string;
    state: string | null;
}

export interface SearchMentionsInput {
    projectId: string;
    q: string;
    limit?: number;
}

export interface CreateTaskInput {
    title: string;
    description?: string;
    status?: TaskStatus;
    priority?: Priority;
    base_branch?: string;
    acceptance_criteria?: string[];
    agent_backend?: string;
    launcher?: string;
    repo_id?: string;
    github_issue?: string;
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
    github_issue?: string;
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

export type FsEntry = FsEntryResponse;
export type { FsBrowseResponse } from "./generated-wire-types";

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

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

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

export interface BackendRecommendation {
    backend?: string;
    success_rate?: number;
    count?: number;
}

export interface RoleStats {
    agent_backend: string;
    agent_role: string;
    count: number;
    success_rate: number;
    avg_duration_seconds: number | null;
}

export interface TaskTypeStats {
    agent_backend: string;
    task_type: string;
    count: number;
    success_rate: number;
    avg_duration_seconds: number | null;
}

export interface CombinedStats {
    agent_backend: string;
    agent_role: string;
    task_type: string;
    count: number;
    success_rate: number;
    avg_duration_seconds: number | null;
}

export interface AnalyticsByRole {
    [role: string]: RoleStats[];
}

export interface AnalyticsByTaskType {
    [taskType: string]: TaskTypeStats[];
}

export interface BackendTaskRecommendation {
    backend: string;
    reason: string;
    confidence: number;
    alternatives: string[];
}

// ---------------------------------------------------------------------------
// Chat watch / multi-client types
// ---------------------------------------------------------------------------

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
    error_code: 'TURN_IN_PROGRESS';
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
    t: 'CHAT_CHUNK';
    content: string;
    thought?: boolean;
}

export interface ChatWatchToolStart {
    t: 'CHAT_TOOL_START';
    tool: string;
}

export interface ChatWatchToolProgress {
    t: 'CHAT_TOOL_PROGRESS';
    tool: string;
    status: string | null;
}

export interface ChatWatchDone {
    t: 'CHAT_DONE';
    full_response: string;
}

export interface ChatWatchUserMessage {
    t: 'CHAT_USER_MESSAGE';
    message_id: number;
    content: string;
}

export interface ChatWatchAssistantMessage {
    t: 'CHAT_ASSISTANT_MESSAGE';
    message_id: number;
    content: string;
    terminated: boolean;
}

export interface ChatWatchTurnStarted {
    t: 'CHAT_TURN_STARTED';
    at: string;
    by_source: string | null;
}

export interface ChatWatchTurnTerminated {
    t: 'CHAT_TURN_TERMINATED';
    reason: 'user' | 'takeover' | string;
}

export interface ChatWatchSessionUpdated {
    t: 'CHAT_SESSION_UPDATED';
    session: WireChatSession;
}

export interface ChatWatchError {
    t: 'CHAT_ERROR';
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
