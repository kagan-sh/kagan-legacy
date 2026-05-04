/**
 * Wire types for the VS Code extension.
 *
 * All types are re-exported from @kagan/shared-api-client (generated from
 * Python source models). Do NOT add hand-written wire types here.
 *
 * VS Code-specific type augmentations (LauncherBackend, PRIORITY_ICONS,
 * STATUS_ICONS) live in ./local.ts.
 *
 * @see packages/shared/api-client/src/wire.ts (generated source)
 * @see scripts/generate_wire_types.py (generator)
 */
export type {
  // Domain enums
  TaskStatus,
  Priority,
  SessionStatus,
  SessionEventType,
  EventType,
  SSEType,

  // Response models
  ActiveSessionResponse,
  AcceptanceCriterionResponse,
  ReviewVerdictResponse,
  DiffSummaryResponse,
  BackendSelectionResponse,
  TaskResponse,
  TaskSessionResponse,
  ProjectResponse,
  RepositoryResponse,
  ProjectFolderResolutionResponse,
  EventResponse,
  AgentBackendResponse,
  ChatAgentsResponse,
  ChatMessageResponse,
  ChatMessageDetailResponse,
  ChatSessionSummaryResponse,
  ChatSessionResponse,
  TurnInProgressResponse,
  DoctorCheckResponse,
  DoctorReportResponse,
  FsEntryResponse,
  FsBrowseResponse,
  IntegrationInfo,
  IntegrationSyncResult,
  MentionResponse,

  // Request models
  TaskCreateRequest,
  TaskUpdateRequest,
  ChatSessionCreateRequest,
  ChatSessionPatchRequest,
  ProjectCreateRequest,
  RepoAddRequest,
  ReviewDecideRequest,

  // Input aliases
  CreateTaskInput,
  UpdateTaskInput,
  CreateChatSessionInput,
  CreateProjectInput,
  ReviewDecisionInput,
  TransitionStatusInput,
  RunTaskInput,
  TaskEventOptions,
  PresenceHeartbeatInput,
  SearchMentionsInput,

  // Envelope
  WireEnvelope,

  // SSE types
  SSETaskUpdated,
  SSESessionEvent,
  SSEMessage,

  // Chat watch / stream types
  ChatWatchChunk,
  ChatWatchToolStart,
  ChatWatchToolProgress,
  ChatWatchDone,
  ChatWatchUserMessage,
  ChatWatchAssistantMessage,
  ChatWatchTurnStarted,
  ChatWatchTurnTerminated,
  ChatWatchSessionUpdated,
  ChatWatchError,
  ChatWatchEvent,
  ChatStreamChunk,
  ChatStreamToolStart,
  ChatStreamToolProgress,
  ChatStreamDone,
  ChatStreamEvent,

  // Turn status
  TurnStatusResponse,

  // Analytics
  BackendStats,
  SessionTimelineEntry,
  AnalyticsExport,

  // Presence
  ClientPresence,

  // Diff / worktree / commit
  DiffStats,
  DiffFile,
  TaskWorktree,
  TaskWorktreeResponse,
  TaskCommit,
  TaskCommitsResponse,

  // Ad-hoc response shapes
  TaskDeletedResponse,
  ProjectActivatedResponse,
  ProjectDeletedResponse,
  ReviewStatusResponse,
  ReviewDecideResponse,
  ReviewDecisionResponse,
  PreflightCheck,
  PreflightResponse,
  TaskCountsResponse,
  WorkflowResolvedSettings,
  ResolvedSettingsResponse,
  SettingsResponse,

  // Mention autocomplete
  Mention,

  // Review verdict state literal type
  ReviewVerdictState,

  // Legacy aliases
  ActiveSession,
  ReviewVerdict,
  WireTask,
  WireTaskSession,
  WireProject,
  WireRepository,
  WireChatSessionSummary,
  WireChatSession,
  WireEvent,
  AgentBackend,
} from "@kagan/shared-api-client";

export {
  EVENT_TYPE,
  SSE_TYPE,
  TASK_COLUMNS,
  CHAT_WATCH_TYPE,
} from "@kagan/shared-api-client";
