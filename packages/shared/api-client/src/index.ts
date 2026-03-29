// ============================================================================
// Shared API Client for Kagan
// 
// A unified, platform-agnostic TypeScript API client that works in:
// - Browsers (via native fetch)
// - VS Code extensions (Node.js with native fetch)
// - Any environment with fetch support
//
// Features:
// - Full type safety with TypeScript
// - Automatic auth token handling (Bearer)
// - Typed errors (ApiError, SSEError, ConfigurationError)
// - SSE support with automatic reconnection
// - Platform-agnostic design
// ============================================================================

// ----------------------------------------------------------------------------
// Core Client
// ----------------------------------------------------------------------------

export { KaganApiClient, KaganClient } from "./client.js";

// ----------------------------------------------------------------------------
// SSE/Event Handling
// ----------------------------------------------------------------------------

export {
  SSEManager,
  streamSSE,
  type SSECallbacks,
  type SSEManagerOptions,
  type SSEEventMap,
  type SSEEventListener,
} from "./events.js";

// ----------------------------------------------------------------------------
// Errors
// ----------------------------------------------------------------------------

export {
  ApiError,
  SSEError,
  ConfigurationError,
  type ApiErrorDetail,
} from "./errors.js";

// ----------------------------------------------------------------------------
// Types (Everything from types.ts)
// ----------------------------------------------------------------------------

export type {
  // Domain
  TaskStatus,
  Priority,
  SessionStatus,
  ReviewVerdictState,
  EventType,
  SSEType,

  // Wire entities
  ActiveSession,
  ReviewVerdict,
  WireTask,
  WireEvent,
  WireTaskSession,
  WireProject,
  WireRepository,
  WireChatSession,
  WireChatSessionSummary,

  // Inputs
  CreateTaskInput,
  UpdateTaskInput,
  TransitionStatusInput,
  RunTaskInput,
  ReviewDecisionInput,
  CreateChatSessionInput,
  CreateProjectInput,

  // Responses
  WireEnvelope,
  TaskDeletedResponse,
  ProjectActivatedResponse,
  ProjectDeletedResponse,
  ReviewStatusResponse,
  ReviewDecideResponse,
  ReviewDecisionResponse,
  SettingsResponse,
  ResolvedSettingsResponse,
  WorkflowResolvedSettings,
  AgentBackendResponse,
  ChatAgentsResponse,
  AgentBackend,
  PreflightCheck,
  PreflightResponse,
  TaskCountsResponse,
  DiffStats,
  DiffFile,
  TaskWorktree,
  TaskWorktreeResponse,
  TaskCommit,
  TaskCommitsResponse,
  TaskEventOptions,

  // Filesystem
  FsEntry,
  FsBrowseResponse,

  // Presence
  ClientPresence,
  PresenceHeartbeatInput,

  // SSE
  SSETaskUpdated,
  SSESessionEvent,
  SSEMessage,

  // Chat streaming
  ChatStreamChunk,
  ChatStreamToolStart,
  ChatStreamToolProgress,
  ChatStreamDone,
  ChatStreamEvent,

  // Client config
  KaganClientConfig,
  RequestOptions,
} from "./types.js";

// ----------------------------------------------------------------------------
// Constants
// ----------------------------------------------------------------------------

export { EVENT_TYPE, SSE_TYPE, TASK_COLUMNS } from "./types.js";
