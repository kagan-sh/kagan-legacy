"""Semantic event rendering — shared protocol for all Kagan clients.

Transforms raw ``(event_type, payload)`` pairs into a client-agnostic
``RenderableEvent`` that carries *kind*, *title*, *body*, and *severity*.
Clients (TUI, web, VS Code, CLI chat) switch on ``RenderableEvent.kind``
instead of repeating event-type mapping logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RenderableKind(StrEnum):
    TEXT = "text"
    THOUGHT = "thought"
    TOOL_START = "tool_start"
    TOOL_UPDATE = "tool_update"
    STATUS_CHANGE = "status_change"
    VERDICT = "verdict"
    NOTE = "note"
    ERROR = "error"
    MERGE = "merge"
    PLAN = "plan"


class Severity(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Renderable event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderableEvent:
    kind: RenderableKind
    title: str
    body: str = ""
    severity: Severity = Severity.INFO
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = ""
    session_id: str = ""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _acp_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the nested ``payload.acp`` dict if present."""
    nested = payload.get("acp")
    if isinstance(nested, dict):
        return nested
    return {}


def _format_tool_name(raw: str) -> str:
    """Human-readable tool name.

    - ``mcp__kagan__task_get`` -> ``kagan / task_get``
    - ``toolu_abc`` / ``call_abc`` -> ``tool call``
    - ``functions__name`` -> ``functions / name``
    - ``snake_case`` -> ``snake case``
    """
    if raw.startswith("toolu_") or raw.startswith("call_"):
        return "tool call"
    if "__" in raw:
        parts = raw.split("__")
        if parts[0] in ("mcp", "functions") and len(parts) >= 3:
            return " / ".join(parts[1:])
        return " / ".join(parts)
    return raw.replace("_", " ")


def _extract_tool_title(payload: dict[str, Any]) -> str:
    """Extract and format the human-readable tool title from a payload."""
    acp = _acp_payload(payload)
    raw = str(
        acp.get("toolName")
        or acp.get("name")
        or acp.get("title")
        or payload.get("tool_name")
        or payload.get("toolName")
        or payload.get("name")
        or payload.get("tool_call_id")
        or payload.get("toolCallId")
        or payload.get("id")
        or "tool call"
    )
    return _format_tool_name(raw)


def _extract_tool_status(payload: dict[str, Any], fallback: str = "done") -> str:
    """Extract tool execution status from a payload."""
    acp = _acp_payload(payload)
    return str(acp.get("status") or payload.get("status") or fallback)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_event(
    event_type: str,
    payload: dict[str, Any],
    event_id: str = "",
    session_id: str = "",
) -> RenderableEvent | None:
    """Map a raw event into a :class:`RenderableEvent`.

    Returns ``None`` for events that should be silently skipped (e.g. a
    ``TOOL_CALL_UPDATE`` whose status is ``"completed"`` or ``"done"``).
    """

    if event_type == "OUTPUT_CHUNK":
        text = str(payload.get("text") or "")
        if not text:
            return None
        thought = bool(payload.get("thought"))
        kind = RenderableKind.THOUGHT if thought else RenderableKind.TEXT
        return RenderableEvent(
            kind=kind,
            title="Thinking" if thought else "Output",
            body=text,
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "TOOL_CALL_START":
        title = _extract_tool_title(payload)
        return RenderableEvent(
            kind=RenderableKind.TOOL_START,
            title=title,
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "TOOL_CALL_UPDATE":
        status = _extract_tool_status(payload, "done")
        if status in ("completed", "done"):
            return None
        title = _extract_tool_title(payload)
        return RenderableEvent(
            kind=RenderableKind.TOOL_UPDATE,
            title=title,
            body=status,
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "AGENT_STATUS":
        return RenderableEvent(
            kind=RenderableKind.NOTE,
            title="Agent status",
            severity=Severity.INFO,
            metadata=dict(payload),
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "TASK_STATUS_CHANGED":
        from_status = str(payload.get("from") or "?")
        to_status = str(payload.get("to") or "?")
        return RenderableEvent(
            kind=RenderableKind.STATUS_CHANGE,
            title=f"{from_status} -> {to_status}",
            metadata={"from": from_status, "to": to_status},
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "CRITERION_VERDICT":
        verdict = str(payload.get("verdict") or "")
        is_pass = verdict == "PASS"
        reason = str(payload.get("reason") or "")
        return RenderableEvent(
            kind=RenderableKind.VERDICT,
            title="PASS" if is_pass else "FAIL",
            body=reason,
            severity=Severity.SUCCESS if is_pass else Severity.WARNING,
            metadata={"verdict": verdict, "reason": reason},
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "AGENT_COMPLETED":
        return RenderableEvent(
            kind=RenderableKind.NOTE,
            title="Agent completed",
            severity=Severity.SUCCESS,
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "AGENT_FAILED":
        error = str(payload.get("error") or payload.get("details") or "Agent failed")
        return RenderableEvent(
            kind=RenderableKind.ERROR,
            title="Agent failed",
            body=error,
            severity=Severity.ERROR,
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "MERGE_COMPLETED":
        return RenderableEvent(
            kind=RenderableKind.MERGE,
            title="Merge completed",
            severity=Severity.SUCCESS,
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "MERGE_FAILED":
        error = str(payload.get("error") or "unknown")
        return RenderableEvent(
            kind=RenderableKind.MERGE,
            title="Merge failed",
            body=error,
            severity=Severity.ERROR,
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "PLAN_UPDATE":
        return RenderableEvent(
            kind=RenderableKind.PLAN,
            title="Plan updated",
            event_id=event_id,
            session_id=session_id,
        )

    if event_type == "AUTO_REVIEW_STARTED":
        return RenderableEvent(
            kind=RenderableKind.NOTE,
            title="Auto-review started",
            event_id=event_id,
            session_id=session_id,
        )

    # Unknown event type — return a generic note so callers can decide
    return RenderableEvent(
        kind=RenderableKind.NOTE,
        title=event_type,
        body=str(payload) if payload else "",
        event_id=event_id,
        session_id=session_id,
    )


__all__ = [
    "RenderableEvent",
    "RenderableKind",
    "Severity",
    "render_event",
]
