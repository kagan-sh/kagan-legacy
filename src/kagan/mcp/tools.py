"""MCP tool implementations for Kagan -- SDKTransport over IPC."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kagan.core.domain.errors import TASK_NOT_FOUND_CODE, task_not_found_message
from kagan.core.scalars import float_or_none

if TYPE_CHECKING:
    from kagan.sdk._transport import SDKTransport

logger = logging.getLogger(__name__)
_AUTH_FAILED_CODE = "AUTH_FAILED"
_QUERY_UNAVAILABLE_CODES = {"UNKNOWN_METHOD", "UNAUTHORIZED"}
_TASK_WAIT_IPC_WINDOW_SECONDS = 45.0  # must match core _MAX_WAIT_WINDOW_SECONDS
_TASK_WAIT_IPC_TIMEOUT_BUFFER_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class MCPBridgeError(ValueError):
    """Structured bridge error with machine-readable code and request context."""

    code: str
    message: str
    kind: str | None = None
    capability: str | None = None
    method: str | None = None
    hint: str | None = None

    def __str__(self) -> str:
        if self.kind is not None and self.capability is not None and self.method is not None:
            return (
                f"Core {self.kind} {self.capability}.{self.method} failed "
                f"[{self.code}]: {self.message}"
            )
        return f"[{self.code}] {self.message}"

    @classmethod
    def core_failure(
        cls,
        *,
        kind: str,
        capability: str,
        method: str,
        code: str,
        message: str,
        hint: str | None = None,
    ) -> MCPBridgeError:
        return cls(
            code=code,
            message=message,
            kind=kind,
            capability=capability,
            method=method,
            hint=hint,
        )

    @classmethod
    def task_not_found(cls, task_id: str) -> MCPBridgeError:
        return cls(
            code=TASK_NOT_FOUND_CODE,
            message=task_not_found_message(task_id),
            capability="tasks",
            method="get",
        )


# --- Standalone transport-based functions for MCP tools ---


async def mcp_get_scratchpad(transport: SDKTransport, task_id: str) -> str:
    """Get a task's scratchpad content."""
    result = await transport.query("tasks", "scratchpad", {"task_id": task_id})
    return result.get("content", "")


async def mcp_update_scratchpad(transport: SDKTransport, task_id: str, content: str) -> dict:
    """Append to task scratchpad."""
    raw = await transport.request(
        "tasks", "update_scratchpad", {"task_id": task_id, "content": content}
    )
    return {
        "success": bool(raw.get("success", True)),
        "message": raw.get("message", "Scratchpad updated"),
        "code": raw.get("code"),
        "hint": raw.get("hint"),
        "next_tool": raw.get("next_tool"),
        "next_arguments": raw.get("next_arguments"),
        "task_id": raw.get("task_id", task_id),
    }


async def mcp_append_task_note(transport: SDKTransport, task_id: str, note: str) -> dict:
    """Append a structured, timestamped reasoning note to the task scratchpad.

    Use this to record agent decisions, tradeoffs, and observations during task
    execution. Each call appends a new timestamped entry without overwriting
    existing notes.
    """
    from datetime import UTC, datetime

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"\n---\n[{timestamp}] {note.strip()}"
    raw = await transport.request(
        "tasks", "update_scratchpad", {"task_id": task_id, "content": entry}
    )
    return {
        "success": bool(raw.get("success", True)),
        "message": raw.get("message", "Note appended"),
        "code": raw.get("code"),
        "hint": raw.get("hint"),
        "next_tool": raw.get("next_tool"),
        "next_arguments": raw.get("next_arguments"),
        "task_id": raw.get("task_id", task_id),
    }


async def mcp_request_review(transport: SDKTransport, task_id: str, summary: str) -> dict:
    """Mark task ready for review."""
    raw = await transport.request("review", "request", {"task_id": task_id, "summary": summary})
    success = bool(raw.get("success", False))
    status = str(raw.get("status") or ("review" if success else "error"))
    message = raw.get("message", "Ready for merge" if success else "Review request failed")
    return {
        "success": success,
        "message": message,
        "code": raw.get("code"),
        "hint": raw.get("hint"),
        "next_tool": raw.get("next_tool"),
        "next_arguments": raw.get("next_arguments"),
        "status": status,
    }


async def mcp_get_instrumentation_snapshot(transport: SDKTransport) -> dict:
    """Get internal core instrumentation snapshot."""
    raw = await transport.query("diagnostics", "instrumentation", {})
    data = raw.get("instrumentation")
    return dict(data) if isinstance(data, dict) else {}


async def mcp_wait_task(
    transport: SDKTransport,
    task_id: str,
    *,
    timeout_seconds: float | str | None = None,
    wait_for_status: list[str] | str | None = None,
    from_updated_at: str | None = None,
) -> dict:
    """Block until target task changes or timeout elapses."""

    params: dict[str, Any] = {"task_id": task_id}
    if timeout_seconds is not None:
        parsed_timeout = float_or_none(timeout_seconds)
        if parsed_timeout is not None:
            params["timeout_seconds"] = parsed_timeout
        else:
            params["timeout_seconds"] = timeout_seconds
    if wait_for_status is not None:
        params["wait_for_status"] = wait_for_status
    if from_updated_at is not None:
        params["from_updated_at"] = from_updated_at

    # Each IPC call is bounded by a single wait-window + buffer.
    per_call_timeout = _TASK_WAIT_IPC_WINDOW_SECONDS + _TASK_WAIT_IPC_TIMEOUT_BUFFER_SECONDS

    while True:
        result = await transport.query(
            "tasks",
            "wait",
            params,
            request_timeout_seconds=per_call_timeout,
        )
        if result.get("code") != "WAIT_WINDOW":
            return result
        # Continuation: server window expired, re-poll with remaining budget.
        remaining = result.get("remaining_seconds", 0)
        if remaining <= 0:
            return result
        params["timeout_seconds"] = remaining
        # Use changed_at from the previous task snapshot (if any) to avoid
        # missing events between calls; fall back to existing cursor.
        cursor = result.get("changed_at") or params.get("from_updated_at")
        if cursor is not None:
            params["from_updated_at"] = cursor


async def mcp_get_task(
    transport: SDKTransport,
    task_id: str,
    *,
    include_scratchpad: bool | None = None,
    include_logs: bool | None = None,
    include_review: bool | None = None,
    mode: str = "summary",
) -> dict:
    """Get task details with optional extended context (simplified for MCP tools)."""
    params: dict[str, Any] = {"task_id": task_id}
    if include_scratchpad is not None:
        params["include_scratchpad"] = include_scratchpad
    if include_logs is not None:
        params["include_logs"] = include_logs
    if include_review is not None:
        params["include_review"] = include_review
    if mode != "summary":
        params["mode"] = mode

    result = await transport.query("tasks", "get", params)
    task_data = result.get("task")
    if not result.get("found") or task_data is None:
        return {
            "success": False,
            "code": TASK_NOT_FOUND_CODE,
            "message": task_not_found_message(task_id),
        }

    return result


def _format_review_feedback(review_result: object) -> str | None:
    """Format review result dict into a human-readable string."""
    if not isinstance(review_result, dict):
        return None
    summary = str(review_result.get("summary") or "").strip()
    status = review_result.get("status")
    approved = review_result.get("approved")
    if status is None and isinstance(approved, bool):
        status = "approved" if approved else "rejected"
    status_label = str(status).strip().lower() if status is not None else ""
    if summary:
        return f"{status_label}: {summary}" if status_label else summary
    if status_label:
        return f"Review {status_label}."
    return None


__all__ = [
    "MCPBridgeError",
    "_format_review_feedback",
    "mcp_append_task_note",
    "mcp_get_instrumentation_snapshot",
    "mcp_get_scratchpad",
    "mcp_get_task",
    "mcp_request_review",
    "mcp_update_scratchpad",
    "mcp_wait_task",
]
