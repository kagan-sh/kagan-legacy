/**
 * Semantic event rendering — shared protocol for all Kagan clients.
 *
 * Transforms raw `(event_type, payload)` pairs into a client-agnostic
 * `RenderableEvent` that carries kind, title, body, and severity.
 * Mirrors the Python implementation in `kagan.core._event_rendering`.
 */

// ── Enums ────────────────────────────────────────────────────────────────────

export type RenderableKind =
  | "text"
  | "thought"
  | "tool_start"
  | "tool_update"
  | "status_change"
  | "verdict"
  | "note"
  | "error"
  | "merge"
  | "plan";

export type Severity = "info" | "success" | "warning" | "error";

// ── Renderable event ─────────────────────────────────────────────────────────

export interface RenderableEvent {
  kind: RenderableKind;
  title: string;
  body: string;
  severity: Severity;
  metadata: Record<string, unknown>;
  event_id: string;
  session_id: string;
}

// ── Private helpers ──────────────────────────────────────────────────────────

function acpPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const nested = payload.acp;
  return typeof nested === "object" && nested !== null
    ? (nested as Record<string, unknown>)
    : {};
}

/**
 * Format a tool name for human-readable display.
 *
 * - `mcp__kagan__task_get` -> `kagan / task_get`
 * - `toolu_abc` / `call_abc` -> `tool call`
 * - `functions__name` -> `functions / name`
 * - `snake_case` -> `snake case`
 */
export function formatToolName(raw: string): string {
  if (raw.startsWith("toolu_") || raw.startsWith("call_")) return "tool call";
  if (raw.includes("__")) {
    const parts = raw.split("__");
    if ((parts[0] === "mcp" || parts[0] === "functions") && parts.length >= 3) {
      return parts.slice(1).join(" / ");
    }
    return parts.join(" / ");
  }
  return raw.replaceAll("_", " ");
}

/**
 * Extract and format the human-readable tool title from a payload.
 */
export function extractToolTitle(payload: Record<string, unknown>): string {
  const acp = acpPayload(payload);
  const raw = String(
    acp.toolName ??
      acp.name ??
      acp.title ??
      payload.tool_name ??
      payload.toolName ??
      payload.name ??
      payload.tool_call_id ??
      payload.toolCallId ??
      payload.id ??
      "tool call",
  );
  return formatToolName(raw);
}

/**
 * Extract tool execution status from a payload.
 */
export function extractToolStatus(
  payload: Record<string, unknown>,
  fallback: string = "done",
): string {
  const acp = acpPayload(payload);
  return String(acp.status ?? payload.status ?? fallback);
}

// ── Renderable factory helper ────────────────────────────────────────────────

function make(
  kind: RenderableKind,
  title: string,
  opts?: {
    body?: string;
    severity?: Severity;
    metadata?: Record<string, unknown>;
    event_id?: string;
    session_id?: string;
  },
): RenderableEvent {
  return {
    kind,
    title,
    body: opts?.body ?? "",
    severity: opts?.severity ?? "info",
    metadata: opts?.metadata ?? {},
    event_id: opts?.event_id ?? "",
    session_id: opts?.session_id ?? "",
  };
}

// ── Main render function ─────────────────────────────────────────────────────

/**
 * Map a raw event into a {@link RenderableEvent}.
 *
 * Returns `null` for events that should be silently skipped (e.g. a
 * `TOOL_CALL_UPDATE` whose status is `"completed"` or `"done"`).
 */
export function renderEvent(
  eventType: string,
  payload: Record<string, unknown>,
  eventId: string = "",
  sessionId: string = "",
): RenderableEvent | null {
  const ids = { event_id: eventId, session_id: sessionId };

  if (eventType === "OUTPUT_CHUNK") {
    const text = String(payload.text ?? "");
    if (!text) return null;
    const thought = Boolean(payload.thought);
    return make(thought ? "thought" : "text", thought ? "Thinking" : "Output", {
      body: text,
      ...ids,
    });
  }

  if (eventType === "TOOL_CALL_START") {
    return make("tool_start", extractToolTitle(payload), ids);
  }

  if (eventType === "TOOL_CALL_UPDATE") {
    const status = extractToolStatus(payload, "done");
    if (status === "completed" || status === "done") return null;
    return make("tool_update", extractToolTitle(payload), {
      body: status,
      ...ids,
    });
  }

  if (eventType === "AGENT_STATUS") {
    return make("note", "Agent status", {
      metadata: { ...payload },
      ...ids,
    });
  }

  if (eventType === "TASK_STATUS_CHANGED") {
    const from = String(payload.from ?? "?");
    const to = String(payload.to ?? "?");
    return make("status_change", `${from} -> ${to}`, {
      metadata: { from, to },
      ...ids,
    });
  }

  if (eventType === "CRITERION_VERDICT") {
    const verdict = String(payload.verdict ?? "");
    const reason = String(payload.reason ?? "");
    const verdictLabel = verdict === "PASS" ? "PASS" : verdict === "SKIP" ? "SKIP" : "FAIL";
    const verdictSeverity: Severity =
      verdict === "PASS" ? "success" : verdict === "SKIP" ? "info" : "warning";
    return make("verdict", verdictLabel, {
      body: reason,
      severity: verdictSeverity,
      metadata: { verdict, reason },
      ...ids,
    });
  }

  if (eventType === "AGENT_COMPLETED") {
    return make("note", "Agent completed", {
      severity: "success",
      ...ids,
    });
  }

  if (eventType === "AGENT_FAILED") {
    const error = String(payload.error ?? payload.details ?? "Agent failed");
    return make("error", "Agent failed", {
      body: error,
      severity: "error",
      ...ids,
    });
  }

  if (eventType === "MERGE_COMPLETED") {
    return make("merge", "Merge completed", {
      severity: "success",
      ...ids,
    });
  }

  if (eventType === "MERGE_FAILED") {
    const error = String(payload.error ?? "unknown");
    return make("merge", "Merge failed", {
      body: error,
      severity: "error",
      ...ids,
    });
  }

  if (eventType === "PLAN_UPDATE") {
    return make("plan", "Plan updated", ids);
  }

  if (eventType === "AUTO_REVIEW_STARTED") {
    return make("note", "Auto-review started", ids);
  }

  // Unknown event type — return a generic note
  return make("note", eventType, {
    body: Object.keys(payload).length > 0 ? JSON.stringify(payload) : "",
    ...ids,
  });
}
