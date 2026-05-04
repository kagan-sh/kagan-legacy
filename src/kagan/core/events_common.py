"""Shared Pydantic discriminated-union variants for agent and chat event surfaces.

Both ``ChatEvent`` (kagan.core.chat.events) and ``AgentEvent``
(kagan.core.agent_events) compose from these base variants so that consumers
can pattern-match on a common shape regardless of which session type produced
the event.

Rules:
- Only put a variant here if it appears in **both** chat and agent surfaces.
- Keep variant fields minimal — they are the intersection, not the union.
- All variants are frozen Pydantic models with ``extra="forbid"`` so that
  deserialization failures are loud rather than silently truncating fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _CommonEventBase(BaseModel):
    """Shared config inherited by every common variant."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ── Message lifecycle ─────────────────────────────────────────────────────────


class MessageStart(_CommonEventBase):
    """The agent has started emitting a new message block."""

    kind: Literal["message_start"] = "message_start"
    message_id: str


class MessageUpdate(_CommonEventBase):
    """An incremental text delta from an in-progress message."""

    kind: Literal["message_update"] = "message_update"
    message_id: str
    delta: str


class MessageEnd(_CommonEventBase):
    """The message block is complete; ``full_text`` is the assembled content."""

    kind: Literal["message_end"] = "message_end"
    message_id: str
    full_text: str


# ── Tool execution lifecycle ──────────────────────────────────────────────────


class ToolExecutionStart(_CommonEventBase):
    """A tool call has been dispatched by the agent.

    ``tool_id`` is stable across progress and end events for the same call.
    ``args`` is included when the backend exposes structured arguments
    (may be ``None`` for backends that only stream name + result).
    """

    kind: Literal["tool_execution_start"] = "tool_execution_start"
    tool_id: str
    name: str
    args: dict[str, Any] | None = None


class ToolExecutionUpdate(_CommonEventBase):
    """Partial result / progress from a long-running tool execution."""

    kind: Literal["tool_execution_update"] = "tool_execution_update"
    tool_id: str
    partial_result: str


class ToolExecutionEnd(_CommonEventBase):
    """A tool call has completed.

    ``status`` is one of ``"success"``, ``"error"``, or ``"cancelled"``.
    ``result`` carries the final output string when available.
    """

    kind: Literal["tool_execution_end"] = "tool_execution_end"
    tool_id: str
    status: Literal["success", "error", "cancelled"]
    result: str | None = None


# ── Public re-exports ─────────────────────────────────────────────────────────

__all__ = [
    "MessageEnd",
    "MessageStart",
    "MessageUpdate",
    "ToolExecutionEnd",
    "ToolExecutionStart",
    "ToolExecutionUpdate",
]
