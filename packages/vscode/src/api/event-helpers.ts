// ACP payload helpers for event rendering.
// Extracted from chat.participant and events.output to DRY.
// Strong types ensure correct payload access patterns.

/**
 * Extract the nested ACP payload object.
 * ACP events wrap tooling metadata under the `acp` field.
 * This guard ensures we're working with valid nested data.
 */
export function acpPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const nested = payload.acp;
  return typeof nested === "object" && nested !== null
    ? (nested as Record<string, unknown>)
    : {};
}

/**
 * Format a tool name for human-readable display.
 * Handles Claude's internal tool IDs, MCP tool paths, and custom names.
 *
 * Patterns:
 * - "toolu_*", "call_*" → "tool call"
 * - "mcp__provider__tool" → "provider / tool"
 * - "functions__name" → "name"
 * - "snake_case" → "snake case"
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
 * Extract and format the human-readable tool title from an event payload.
 * Tries multiple fallback sources: ACP nested fields, legacy fields, and defaults.
 *
 * Priority:
 * 1. acp.toolName (Anthropic protocol)
 * 2. acp.name (common pattern)
 * 3. acp.title (fallback)
 * 4. tool_name (legacy)
 * 5. title (legacy)
 * 6. "tool call" (safe default)
 */
export function extractToolTitle(payload: Record<string, unknown>): string {
  const acp = acpPayload(payload);
  const raw = String(
    acp.toolName ?? acp.name ?? acp.title ?? payload.tool_name ?? payload.title ?? "tool call",
  );
  return formatToolName(raw);
}

/**
 * Extract tool execution status from event payload.
 * Tries ACP nested field first, then legacy field, then fallback.
 *
 * Used in events.output.ts to render TOOL_CALL_UPDATE progress.
 */
export function extractToolStatus(payload: Record<string, unknown>, fallback: string): string {
  const acp = acpPayload(payload);
  return String(acp.status ?? payload.status ?? fallback);
}
