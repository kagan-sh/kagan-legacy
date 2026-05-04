// ============================================================================
// Shared API Client for Kagan
//
// A unified, platform-agnostic TypeScript API client that works in:
// - Browsers (via native fetch)
// - VS Code extensions (Node.js with native fetch)
// - Any environment with fetch support
// ============================================================================

// ----------------------------------------------------------------------------
// Wire types — single source of truth (auto-generated from Python models)
// ----------------------------------------------------------------------------

export * from "./wire";

// ----------------------------------------------------------------------------
// Core Client
// ----------------------------------------------------------------------------

export { KaganApiClient, KaganClient } from "./client";

// ----------------------------------------------------------------------------
// Event Rendering
// ----------------------------------------------------------------------------

export {
  renderEvent,
  formatToolName,
  extractToolTitle,
  extractToolStatus,
  type RenderableEvent,
  type RenderableKind,
  type Severity,
} from "./event-rendering";

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
} from "./events";

// ----------------------------------------------------------------------------
// Errors
// ----------------------------------------------------------------------------

export {
  ApiError,
  SSEError,
  ConfigurationError,
  type ApiErrorDetail,
} from "./errors";
