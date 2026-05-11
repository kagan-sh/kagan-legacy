#!/usr/bin/env python3
"""Generate TypeScript interfaces from the full wire surface.

Reads the Pydantic ``model_json_schema()`` output for every model in
``src/kagan/server/responses.py`` and ``src/kagan/core/_io/`` and emits
a single ``.ts`` file with matching TypeScript interfaces.  Enums from
``src/kagan/core/enums.py`` and static hand-maintained sections (envelope,
SSE types, chat stream types, constants) are also included.

Usage:
    python scripts/generate_wire_types.py            # writes to stdout
    python scripts/generate_wire_types.py -o FILE    # writes to FILE
    python scripts/generate_wire_types.py --check    # exits 1 if FILE differs
"""

from __future__ import annotations

import argparse
import sys
from enum import EnumMeta
from pathlib import Path

# Ensure the project source is importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kagan.core._io.projects import ProjectCreateRequest, RepoAddRequest  # noqa: E402
from kagan.core._io.reviews import ReviewDecideRequest  # noqa: E402
from kagan.core._io.sessions import ChatSessionCreateRequest, ChatSessionPatchRequest  # noqa: E402
from kagan.core._io.tasks import TaskCreateRequest, TaskUpdateRequest  # noqa: E402
from kagan.core.enums import (  # noqa: E402
    Priority,
    SessionStatus,
    TaskStatus,
)
from kagan.server.responses import RESPONSE_MODELS  # noqa: E402


# ── JSON-Schema → TypeScript mapper ─────────────────────────────────────────


def _ts_type(schema: dict, defs: dict) -> str:  # noqa: C901
    """Convert a JSON-Schema property spec to a TypeScript type string."""
    # Handle $ref
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        return ref

    # Handle anyOf (Pydantic's way of expressing Optional / union)
    if "anyOf" in schema:
        variants = [_ts_type(v, defs) for v in schema["anyOf"] if v.get("type") != "null"]
        has_null = any(v.get("type") == "null" for v in schema["anyOf"])
        base = " | ".join(variants) if variants else "unknown"
        return f"{base} | null" if has_null else base

    # Handle const (e.g. Pydantic Literal["snapshot"] with a default emits
    # {"const": "snapshot", "default": "snapshot", "type": "string"}).
    if "const" in schema:
        v = schema["const"]
        if isinstance(v, str):
            return f"'{v}'"
        return str(v)

    schema_type = schema.get("type")
    if schema_type == "string":
        # Literal enum
        if "enum" in schema:
            return " | ".join(f"'{v}'" for v in schema["enum"])
        return "string"
    if schema_type == "integer" or schema_type == "number":
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "array":
        items = schema.get("items", {})
        return f"{_ts_type(items, defs)}[]"
    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if additional and isinstance(additional, dict):
            return f"Record<string, {_ts_type(additional, defs)}>"
        return "Record<string, unknown>"
    if schema_type == "null":
        return "null"

    return "unknown"


def _generate_definition(name: str, schema: dict, defs: dict) -> list[str]:
    """Generate lines for a single TypeScript definition.

    Pure enum schemas (no properties) become type aliases; object schemas
    become interfaces; schemas that extend another become interface extends.
    """
    lines: list[str] = []

    # Pure enum schema — emit as string type alias.
    # Both StrEnum and IntEnum are serialized as strings on the wire (StrEnum values,
    # IntEnum names).  Downstream code in types.ts can re-export narrower unions.
    schema_type = schema.get("type")
    if "enum" in schema and "properties" not in schema and "allOf" not in schema:
        lines.append(f"export type {name} = string;")
        return lines

    # Object schema (interface)
    extends_name = None
    props: dict = {}
    required: set[str] = set()

    if "allOf" in schema:
        for entry in schema["allOf"]:
            if "$ref" in entry:
                extends_name = entry["$ref"].rsplit("/", 1)[-1]
            if "properties" in entry:
                props.update(entry["properties"])
                required.update(entry.get("required", []))
    else:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))

    extends_clause = f" extends {extends_name}" if extends_name else ""
    lines.append(f"export interface {name}{extends_clause} {{")

    for field_name, field_schema in props.items():
        ts = _ts_type(field_schema, defs)
        # A field is optional in TS if it is not in the JSON Schema ``required``
        # list, UNLESS it is a ``const`` field (discriminator tag like
        # ``type: "snapshot"``), which is always present on the wire.
        is_const = "const" in field_schema
        optional = field_name not in required and not is_const
        opt_mark = "?" if optional else ""
        lines.append(f"  {field_name}{opt_mark}: {ts};")

    lines.append("}")
    return lines


# ── Enum generation ───────────────────────────────────────────────────────────

# Wire-facing enums only — those that appear in the JSON wire surface.
WIRE_ENUMS: list[tuple[str, type]] = [
    ("TaskStatus", TaskStatus),
    ("SessionStatus", SessionStatus),
    ("Priority", Priority),
]


def _generate_enum_section() -> list[str]:
    """Emit TS string-literal union types for the wire-facing Python enums."""
    lines: list[str] = [
        "// ── Domain enums (derived from src/kagan/core/enums.py) ─────────────────────",
    ]
    for ts_name, enum_cls in WIRE_ENUMS:
        assert isinstance(enum_cls, EnumMeta)
        # For IntEnum (Priority) emit the name; for StrEnum emit the value.
        members = list(enum_cls)
        values = [m.value for m in members]
        # Detect IntEnum: if all values are int, use names instead
        if all(isinstance(v, int) for v in values):
            literals = " | ".join(f'"{m.name}"' for m in members)
        else:
            literals = " | ".join(f'"{v}"' for v in values)
        lines.append(f"export type {ts_name} = {literals};")
    lines.append("")
    return lines


# ── Event constants ───────────────────────────────────────────────────────────


def _generate_constants_section() -> list[str]:
    """Emit EVENT_TYPE, SSE_TYPE, and CHAT_WATCH_TYPE const objects.

    EVENT_TYPE is derived from the ``type`` Literal fields on each variant in
    ``kagan.core.events.Event`` (the new unified chat-event union).

    SSE_TYPE covers the task-board SSE transport (TASK_UPDATED / SESSION_EVENT)
    and is still used by the HTTP transport layer.

    CHAT_WATCH_TYPE covers the transport-layer lifecycle frames that the server
    emits with a ``t`` key on the /watch SSE channel.  These are distinct from
    the engine events (which use the ``type`` key).
    """
    import dataclasses
    import re

    import kagan.core.events as _events_mod

    # Collect all dataclass types in the Event union by inspecting the module.
    # We read ``get_type_hints`` to avoid importing each class by name.
    event_classes: list[type] = []
    for name in _events_mod.__all__:
        obj = getattr(_events_mod, name)
        if dataclasses.is_dataclass(obj) and isinstance(obj, type):
            event_classes.append(obj)

    lines: list[str] = [
        "// ── Event type constants (derived from src/kagan/core/events.py) ────────────",
    ]

    # EVENT_TYPE — two groups merged into one const:
    #   1. Chat engine events from kagan.core.events (new union, ``type`` field).
    #   2. Task session DB event kinds from agent_events (legacy; still in DB
    #      even though agent_events.py is deleted).  These are the ``kind``
    #      strings stored in SessionEvent.event_type and emitted on the
    #      SSE_TYPE.SESSION_EVENT channel.
    lines.append("export const EVENT_TYPE = {")

    # Group 1: chat engine events (derived from kagan.core.events dataclasses).
    lines.append("  // Chat engine events (kagan.core.events)")
    for cls in event_classes:
        type_field = next(
            (f for f in dataclasses.fields(cls) if f.name == "type"),
            None,
        )
        if type_field is None:
            continue
        wire_value: str = type_field.default  # type: ignore[assignment]
        snake = re.sub(r"([A-Z])", r"_\1", cls.__name__).lstrip("_").upper()
        lines.append(f'  {snake}: "{wire_value}",')

    # Group 2: legacy task session DB event kinds (agent_events.py is deleted;
    # these strings are still persisted in SessionEvent.event_type rows).
    # Only add entries that were NOT already emitted by the chat engine group.
    chat_engine_snakes = set()
    for cls in event_classes:
        ts_name = cls.__name__
        snake = re.sub(r"([A-Z])", r"_\1", ts_name).lstrip("_").upper()
        chat_engine_snakes.add(snake)

    legacy_entries = [
        ("OUTPUT_CHUNK", "output_chunk"),
        ("TOOL_CALL_START", "tool_call_start"),
        ("TOOL_CALL_UPDATE", "tool_call_update"),
        ("AGENT_STATUS", "agent_status"),
        ("TASK_STATUS_CHANGED", "task_status_changed"),
        ("AGENT_COMPLETED", "agent_completed"),
        ("AGENT_FAILED", "agent_failed"),
        ("MERGE_COMPLETED", "merge_completed"),
        ("MERGE_FAILED", "merge_failed"),
        ("CRITERION_VERDICT", "criterion_verdict"),
        ("AUTO_REVIEW_STARTED", "auto_review_started"),
        ("PLAN_UPDATE", "plan_update"),
        ("STEP_VERIFIED", "step_verified"),
        ("CHECKPOINT_CREATED", "checkpoint_created"),
        ("SESSION_REWOUND", "session_rewound"),
        ("HOOK_BLOCKED", "hook_blocked"),
        ("COMPACTION_OCCURRED", "compaction_occurred"),
        ("COMPACTION_TRIGGERED", "compaction_triggered"),
        ("DOCTOR_WARNED", "doctor_warned"),
        ("FIRST_SESSION_SUCCESS", "first_session_success"),
        ("BACKEND_AUTO_PROMOTED", "backend_auto_promoted"),
        ("INSIGHT_EXTRACTED", "insight_extracted"),
    ]
    has_legacy = [entry for entry in legacy_entries if entry[0] not in chat_engine_snakes]
    if has_legacy:
        lines.append("  // Legacy task session event kinds (persisted in DB by agent runner)")
        for key, value in has_legacy:
            lines.append(f'  {key}: "{value}",')


    lines.append("} as const;")
    lines.append("")
    lines.append("export type EventType = (typeof EVENT_TYPE)[keyof typeof EVENT_TYPE];")
    lines.append("")

    # SSE_TYPE — task-board transport channel constants (HTTP layer, not chat).
    lines.extend([
        "export const SSE_TYPE = {",
        '  TASK_UPDATED: "TASK_UPDATED",',
        '  SESSION_EVENT: "SESSION_EVENT",',
        "} as const;",
        "",
        "export type SSEType = (typeof SSE_TYPE)[keyof typeof SSE_TYPE];",
        "",
    ])

    # CHAT_WATCH_TYPE — transport-layer lifecycle frames on the /watch SSE channel.
    # These use the ``t`` key (not ``type``).  Engine events use ``type`` instead
    # and are covered by EVENT_TYPE above.
    lines.extend([
        "export const CHAT_WATCH_TYPE = {",
        '  CHAT_USER_MESSAGE: "CHAT_USER_MESSAGE",',
        '  CHAT_ASSISTANT_MESSAGE: "CHAT_ASSISTANT_MESSAGE",',
        '  CHAT_TURN_STARTED: "CHAT_TURN_STARTED",',
        '  CHAT_TURN_TERMINATED: "CHAT_TURN_TERMINATED",',
        '  CHAT_SESSION_UPDATED: "CHAT_SESSION_UPDATED",',
        '  CHAT_ERROR: "CHAT_ERROR",',
        '  CHAT_PERMISSION_REQUEST: "CHAT_PERMISSION_REQUEST",',
        "} as const;",
        "",
        "export type ChatWatchType = (typeof CHAT_WATCH_TYPE)[keyof typeof CHAT_WATCH_TYPE];",
        "",
    ])

    # TASK_COLUMNS helper
    lines.extend([
        "export const TASK_COLUMNS: TaskStatus[] = [",
        '  "BACKLOG",',
        '  "IN_PROGRESS",',
        '  "REVIEW",',
        '  "DONE",',
        "];",
        "",
    ])

    return lines


# ── Static wire sections ──────────────────────────────────────────────────────

_STATIC_WIRE_SECTIONS = """\
// ── Chat engine events (from src/kagan/core/events.py) ───────────────────────
// Discriminated on the ``type`` field.  Emitted by the engine over the /watch
// SSE channel alongside the transport-layer lifecycle frames (which use ``t``).

export interface ChatEventTurnStart {
  type: "turn_start";
  turn_id: string;
  session_id: string;
  agent_id: string;
}
export interface ChatEventTurnEnd {
  type: "turn_end";
  turn_id: string;
  reason: "done" | "cancelled" | "error" | "max_turns" | "refusal" | "permission_denied";
}
export interface ChatEventAssistantChunk {
  type: "assistant_chunk";
  turn_id: string;
  session_id: string;
  message_id: string;
  delta: string;
}
export interface ChatEventThinkingChunk {
  type: "thinking_chunk";
  turn_id: string;
  session_id: string;
  message_id: string;
  delta: string;
}
export interface ChatEventToolCall {
  type: "tool_call";
  turn_id: string;
  session_id: string;
  tool_call_id: string;
  name: string;
  args: string | null;
  title: string;
  kind: string | null;
}
export interface ChatEventToolCallUpdate {
  type: "tool_call_update";
  tool_call_id: string;
  content: string | null;
  progress: string | null;
}
export interface ChatEventToolCallResult {
  type: "tool_call_result";
  tool_call_id: string;
  output: string | null;
  is_error: boolean;
}
export interface ChatEventUsageUpdate {
  type: "usage_update";
  turn_id: string;
  input: number | null;
  output: number | null;
  cached: number | null;
  cost: number | null;
}
export interface ChatEventError {
  type: "error";
  turn_id: string | null;
  code: string;
  message: string;
  fatal: boolean;
}
export interface ChatEventAgentLifecycle {
  type: "agent_lifecycle";
  session_id: string;
  task_id: string | null;
  kind: "started" | "finished" | "stopped" | "failed";
  detail: string | null;
}
export interface ChatEventAssistantMessage {
  type: "assistant_message";
  message_id: number;
  content: string;
  terminated: boolean;
}
export interface ChatEventUserMessage {
  type: "user_message";
  message_id: number;
  content: string;
}

/** Engine events — discriminated on ``type``. */
export type ChatEngineEvent =
  | ChatEventTurnStart
  | ChatEventTurnEnd
  | ChatEventAssistantChunk
  | ChatEventThinkingChunk
  | ChatEventToolCall
  | ChatEventToolCallUpdate
  | ChatEventToolCallResult
  | ChatEventUsageUpdate
  | ChatEventError
  | ChatEventAgentLifecycle
  | ChatEventAssistantMessage
  | ChatEventUserMessage;

// ── Chat /watch transport-layer lifecycle frames ──────────────────────────────
// These are emitted directly by the server transport (not the engine).
// Discriminated on the ``t`` field.

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
  session: ChatSessionSummaryResponse;
}
export interface ChatWatchError {
  t: "CHAT_ERROR";
  error: string;
}
export interface ChatWatchPermissionRequest {
  t: "CHAT_PERMISSION_REQUEST";
  future_id: string;
  tool_name: string;
}

/**
 * All events that can arrive on the GET /api/chat/sessions/{id}/watch SSE channel.
 *
 * Two discriminator keys are in play:
 *   - ``type`` — engine events from ``kagan.core.events`` (ChatEngineEvent union).
 *   - ``t``    — transport-layer lifecycle frames emitted by the server directly.
 *
 * Consumers should handle both.  A narrow switch on ``type`` covers engine
 * events; a switch on ``t`` covers lifecycle frames.
 */
export type ChatWatchEvent = ChatEngineEvent | ChatWatchUserMessage | ChatWatchAssistantMessage | ChatWatchTurnStarted | ChatWatchTurnTerminated | ChatWatchSessionUpdated | ChatWatchError | ChatWatchPermissionRequest;

// ── Chat POST /stream response events ────────────────────────────────────────
// The POST /api/chat/{id}/stream endpoint also uses ``t``-keyed frames for
// compatibility with the orchestrator streaming path.

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
export interface ChatStreamError {
  t: "CHAT_ERROR";
  error?: string;
}
export interface ChatStreamSessionUpdated {
  t: "CHAT_SESSION_UPDATED";
  session?: ChatSessionSummaryResponse;
}

export type ChatStreamEvent =
  | ChatStreamChunk
  | ChatStreamToolStart
  | ChatStreamToolProgress
  | ChatStreamDone
  | ChatStreamError
  | ChatStreamSessionUpdated;

/** Abbreviated-key constant map for the POST /api/chat/{id}/stream event types. */
export const CHAT_STREAM_EVENT = {
  CHUNK: "CHAT_CHUNK",
  TOOL_START: "CHAT_TOOL_START",
  TOOL_PROGRESS: "CHAT_TOOL_PROGRESS",
  DONE: "CHAT_DONE",
  ERROR: "CHAT_ERROR",
  SESSION_UPDATED: "CHAT_SESSION_UPDATED",
} as const;

export type ChatStreamEventType = (typeof CHAT_STREAM_EVENT)[keyof typeof CHAT_STREAM_EVENT];

// ── Envelope ─────────────────────────────────────────────────────────────────

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

// ── SSE envelope types ────────────────────────────────────────────────────────

export interface SSETaskUpdated {
  type: typeof SSE_TYPE.TASK_UPDATED;
  task_id: string;
  /**
   * Inline task payload — present when the server can build it (the common
   * case). Absent on the cross-process DB-poll fallback path; clients should
   * fall back to refetching when it is missing.
   */
  task?: TaskResponse;
}

export interface SSESessionEvent {
  type: typeof SSE_TYPE.SESSION_EVENT;
  task_id: string;
  event: EventResponse;
}

export type SSEMessage = SSETaskUpdated | SSESessionEvent;

// ── Turn status ───────────────────────────────────────────────────────────────

/** Full turn status returned by GET /api/chat/{id}/turn-status */
export interface TurnStatusResponse {
  active: boolean;
  partial_chars: number | null;
  running_since: string | null;
}

// ── Analytics (informal — server returns raw dicts, no Pydantic model) ────────

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

// ── Client presence (informal — no Pydantic model) ───────────────────────────

export interface ClientPresence {
  client_id: string;
  client_type: string;
  connected_at: number;
  active_task_id: string | null;
  user_label: string;
}

// ── Client-side diff/worktree/commit shapes (informal) ───────────────────────

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

// ── Simple ad-hoc response shapes ────────────────────────────────────────────

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
  task?: TaskResponse;
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

export interface WorkflowResolvedSettings {
  wip_limits: Record<TaskStatus, number>;
}

export interface ResolvedSettingsResponse {
  git_user_name: string;
  git_user_email: string;
  dotfile_overrides: Record<string, string | null>;
  workflow: WorkflowResolvedSettings;
  chat_last_active_session?: string;
}

// ── Client configuration ──────────────────────────────────────────────────────

export interface KaganClientConfig {
  baseUrl: string;
  protocol?: "http" | "https";
  token?: string;
  /** Client type identifier for presence/tracking. @default "unknown" */
  clientType?: string;
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

// ── Mention autocomplete (informal) ──────────────────────────────────────────

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

// ── Task event query options ──────────────────────────────────────────────────

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

// ── Presence heartbeat input ──────────────────────────────────────────────────

export interface PresenceHeartbeatInput {
  client_id: string;
  client_type: string;
  active_task_id?: string | null;
  user_label?: string;
}

// ── Run task input ────────────────────────────────────────────────────────────

export interface RunTaskInput {
  agent_backend?: string;
  launcher?: string;
  persona?: string;
}

// ── Transition status input ───────────────────────────────────────────────────

export interface TransitionStatusInput {
  status: TaskStatus;
}

// ── Request model aliases (canonical names used in TS clients) ────────────────

export type CreateTaskInput = TaskCreateRequest;
export type UpdateTaskInput = TaskUpdateRequest;
export type CreateChatSessionInput = ChatSessionCreateRequest;
export type CreateProjectInput = ProjectCreateRequest;
/** @deprecated Use ReviewDecideRequest */
export type ReviewDecisionInput = ReviewDecideRequest;

/** Alias for ReviewDecideResponse (legacy naming used by VS Code extension). */
export type ReviewDecisionResponse = ReviewDecideResponse;

// ── Review verdict state ──────────────────────────────────────────────────────

export type ReviewVerdictState = "PASS" | "FAIL" | "SKIP";

// ── Legacy aliases ────────────────────────────────────────────────────────────

/** @deprecated Use ActiveSessionResponse */
export type ActiveSession = ActiveSessionResponse;
/** @deprecated Use ReviewVerdictResponse */
export type ReviewVerdict = ReviewVerdictResponse;
/** @deprecated Use TaskResponse */
export type WireTask = TaskResponse;
/** @deprecated Use TaskSessionResponse */
export type WireTaskSession = TaskSessionResponse;
/** @deprecated Use ProjectResponse */
export type WireProject = ProjectResponse;
/** @deprecated Use RepositoryResponse */
export type WireRepository = RepositoryResponse;
/** @deprecated Use ChatSessionSummaryResponse */
export type WireChatSessionSummary = ChatSessionSummaryResponse;
/** @deprecated Use ChatSessionResponse */
export type WireChatSession = ChatSessionResponse;
/** @deprecated Use EventResponse */
export type WireEvent = EventResponse;
/** @deprecated Use DiffSummaryResponse */
export type WireDiffSummary = DiffSummaryResponse;
/** @deprecated Use AgentBackendResponse */
export type AgentBackend = AgentBackendResponse;
/** @deprecated Use ChatMessageDetailResponse */
export type WireChatMessage = ChatMessageResponse;
/** @deprecated Use FsEntryResponse */
export type FsEntry = FsEntryResponse;
// SettingsResponse is informal — server returns Record<string, string>
export type SettingsResponse = Record<string, string | undefined>;
// Preflight/doctor aliases
export type DoctorCheck = DoctorCheckResponse;
export type DoctorReport = DoctorReportResponse;
"""


# ── Request models ────────────────────────────────────────────────────────────

# Request models from core/_io/ to include in the wire surface.
REQUEST_MODELS: dict[str, type] = {
    "TaskCreateRequest": TaskCreateRequest,
    "TaskUpdateRequest": TaskUpdateRequest,
    "ChatSessionCreateRequest": ChatSessionCreateRequest,
    "ChatSessionPatchRequest": ChatSessionPatchRequest,
    "ProjectCreateRequest": ProjectCreateRequest,
    "RepoAddRequest": RepoAddRequest,
    "ReviewDecideRequest": ReviewDecideRequest,
}


# ── Main generator ────────────────────────────────────────────────────────────


def generate_ts(*, include_header: bool = True) -> str:
    """Return full TypeScript source for the complete wire surface."""
    # Collect all schemas in a combined $defs dict
    all_defs: dict[str, dict] = {}
    root_order: list[str] = []

    all_models = {**RESPONSE_MODELS, **REQUEST_MODELS}

    for name, model in all_models.items():
        schema = model.model_json_schema(mode="serialization")
        # Gather nested $defs
        for def_name, def_schema in schema.get("$defs", {}).items():
            all_defs[def_name] = def_schema
        # The root schema itself
        all_defs[name] = schema
        root_order.append(name)

    # Determine emission order: $defs first (deps), then roots
    emitted: set[str] = set()
    output_lines: list[str] = []

    if include_header:
        output_lines.extend([
            "/**",
            " * AUTO-GENERATED by scripts/generate_wire_types.py",
            " * DO NOT EDIT — regenerate with:",
            " *   uv run python scripts/generate_wire_types.py -o packages/shared/api-client/src/wire.ts",
            " */",
            "",
        ])

    # Section 1: enums
    output_lines.extend(_generate_enum_section())

    # Section 2: constants (EVENT_TYPE, SSE_TYPE, TASK_COLUMNS)
    output_lines.extend(_generate_constants_section())

    # Section 3: generated interfaces from Pydantic models
    output_lines.append(
        "// ── Response models (from src/kagan/server/responses.py) ────────────────────"
    )
    output_lines.append("")

    # Emit dependency defs first
    for name in list(all_defs):
        if name not in root_order and name not in emitted:
            output_lines.extend(_generate_definition(name, all_defs[name], all_defs))
            output_lines.append("")
            emitted.add(name)

    # Emit root models in declaration order
    for name in root_order:
        if name not in emitted:
            output_lines.extend(_generate_definition(name, all_defs[name], all_defs))
            output_lines.append("")
            emitted.add(name)

    # Section 4: static hand-maintained sections
    output_lines.append(
        "// ── Static wire sections (maintained in scripts/generate_wire_types.py) ──────"
    )
    output_lines.append("")
    output_lines.append(_STATIC_WIRE_SECTIONS)

    return "\n".join(output_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TypeScript from wire surface")
    parser.add_argument("-o", "--output", type=Path, help="Output file path")
    parser.add_argument("--check", action="store_true", help="Check mode: exit 1 if file differs")
    args = parser.parse_args()

    ts_source = generate_ts()

    if args.check:
        if args.output is None:
            print("ERROR: --check requires -o FILE", file=sys.stderr)
            return 1
        if not args.output.exists():
            print(f"DRIFT: {args.output} does not exist")
            return 1
        existing = args.output.read_text()
        if existing != ts_source:
            print(f"DRIFT: {args.output} is out of date. Regenerate with:")
            print(f"  uv run python scripts/generate_wire_types.py -o {args.output}")
            return 1
        print(f"OK: {args.output} is up to date")
        return 0

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(ts_source)
        print(f"Wrote {args.output}")
    else:
        print(ts_source, end="")

    return 0


if __name__ == "__main__":
    sys.exit(main())
