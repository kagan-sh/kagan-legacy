/**
 * Wire types for the web package.
 *
 * All types are re-exported from the generated @kagan/shared-api-client wire surface.
 * Do NOT add hand-written types here — extend scripts/generate_wire_types.py instead.
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

  // Domain constants (re-exported as values)
} from "@kagan/shared-api-client";

export {
  EVENT_TYPE,
  SSE_TYPE,
  TASK_COLUMNS,
} from "@kagan/shared-api-client";

export type {
  // Response models (generated from Python RESPONSE_MODELS)
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

  // Request models (generated from Python core/_io/ models)
  TaskCreateRequest,
  TaskUpdateRequest,
  ChatSessionCreateRequest,
  ChatSessionPatchRequest,
  ProjectCreateRequest,
  RepoAddRequest,
  ReviewDecideRequest,

  // Input aliases (matching legacy names)
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
  BackendRecommendation,
  RoleStats,
  TaskTypeStats,
  CombinedStats,
  AnalyticsByRole,
  AnalyticsByTaskType,
  BackendTaskRecommendation,

  // Presence
  ClientPresence,

  // Diff / worktree / commit shapes
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
  PreflightCheck,
  PreflightResponse,
  TaskCountsResponse,
  WorkflowResolvedSettings,
  ResolvedSettingsResponse,

  // Client config
  KaganClientConfig,
  RequestOptions,

  // Mention autocomplete
  Mention,

  // Settings
  SettingsResponse,

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
  WireDiffSummary,
  AgentBackend,
  WireChatMessage,
  FsEntry,
} from "@kagan/shared-api-client";

export { CHAT_WATCH_TYPE } from "@kagan/shared-api-client";
