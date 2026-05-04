"""ChatEvent — discriminated union of every event the chat surface emits.

The four chat surfaces (CLI REPL, TUI, server SSE, orchestrator ACP client)
historically each defined their own event shapes. R1 collapses them onto this
single pydantic union. New variants live here; transports translate to/from
their wire shape at the edge.

The ``kind`` literal is the discriminator. Pydantic's
``Annotated[Union[...], Field(discriminator="kind")]`` machinery validates that
incoming dicts always resolve to a single concrete variant.

Shared variants (MessageStart, MessageUpdate, MessageEnd, ToolExecutionStart,
ToolExecutionUpdate, ToolExecutionEnd) live in ``kagan.core.events_common`` and
are composed here by re-export.  Chat-specific tool-call variants (ToolCallStart,
ToolCallProgress) are kept here because they carry chat-specific fields
(``title``, ``kind_hint``) that do not appear in the agent surface.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — runtime-required by pydantic
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

from kagan.core.events_common import (
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
)


class _ChatEventBase(BaseModel):
    """Common config for every variant."""

    model_config = {"frozen": True, "extra": "forbid"}


class AssistantChunk(_ChatEventBase):
    """A streamed text chunk from the assistant.

    ``thought=True`` flags the chunk as a reasoning trace (corresponds to
    ACP's ``AgentThoughtChunk``); the CLI/TUI render these dimmed.
    """

    kind: Literal["assistant_chunk"] = "assistant_chunk"
    text: str
    thought: bool = False


class ToolCallStart(_ChatEventBase):
    """Tool call dispatched by the agent. ``tool_id`` is stable across progress events."""

    kind: Literal["tool_call_start"] = "tool_call_start"
    tool_id: str
    title: str
    kind_hint: str | None = None
    args: str | None = None


class ToolCallProgress(_ChatEventBase):
    """Tool call progress / completion."""

    kind: Literal["tool_call_progress"] = "tool_call_progress"
    tool_id: str
    status: Literal["running", "completed", "failed"]
    result: str | None = None


class PermissionRequest(_ChatEventBase):
    """Agent is asking the user to allow or deny a tool call."""

    kind: Literal["permission_request"] = "permission_request"
    future_id: str
    tool_call: dict[str, Any]
    options: list[dict[str, Any]]


class PermissionResolved(_ChatEventBase):
    """Resolution of a previously emitted ``PermissionRequest``."""

    kind: Literal["permission_resolved"] = "permission_resolved"
    future_id: str
    outcome: Literal["allow_once", "allow_always", "deny", "deny_feedback"]
    feedback: str | None = None


class UsageUpdate(_ChatEventBase):
    """Token / cost usage snapshot, mirrored from ACP's ``UsageUpdate``."""

    kind: Literal["usage"] = "usage"
    used: int | None = None
    size: int | None = None
    cost: float | None = None
    cost_currency: str | None = None


class TurnStarted(_ChatEventBase):
    """Marks the start of an assistant turn."""

    kind: Literal["turn_started"] = "turn_started"
    at: datetime


# NOTE: ``UserMessagePersisted`` is emitted by transport-layer route handlers
# (currently the server SSE producer in ``kagan.server._chat_routes``) right
# after they call ``ChatEngine.push_user``. The engine itself does not emit it
# because the user row is persisted *before* ``stream_assistant`` runs — the
# transport that owns the persist call also owns the broadcast.
class UserMessagePersisted(_ChatEventBase):
    """The user message row was just written to the DB."""

    kind: Literal["user_message"] = "user_message"
    message_id: int
    content: str


class AssistantMessagePersisted(_ChatEventBase):
    """The assistant message row was just written to the DB.

    ``terminated=True`` indicates a partial save after a user-initiated cancel.
    """

    kind: Literal["assistant_message"] = "assistant_message"
    message_id: int
    content: str
    terminated: bool


class TurnCancelled(_ChatEventBase):
    """The current turn was cancelled (user or takeover)."""

    kind: Literal["turn_cancelled"] = "turn_cancelled"
    reason: str


class TurnError(_ChatEventBase):
    """The current turn failed before completion."""

    kind: Literal["error"] = "error"
    message: str


class TurnDone(_ChatEventBase):
    """Turn completed successfully. Carries the final assembled response."""

    kind: Literal["done"] = "done"
    full_response: str


ChatEvent = Annotated[
    Union[  # noqa: UP007 — pydantic discriminator requires typing.Union
        AssistantChunk,
        ToolCallStart,
        ToolCallProgress,
        PermissionRequest,
        PermissionResolved,
        UsageUpdate,
        TurnStarted,
        UserMessagePersisted,
        AssistantMessagePersisted,
        TurnCancelled,
        TurnError,
        TurnDone,
    ],
    Field(discriminator="kind"),
]


__all__ = [
    # Chat-specific variants
    "AssistantChunk",
    "AssistantMessagePersisted",
    "ChatEvent",
    # Shared base variants re-exported from kagan.core.events_common
    "MessageEnd",
    "MessageStart",
    "MessageUpdate",
    "PermissionRequest",
    "PermissionResolved",
    "ToolCallProgress",
    "ToolCallStart",
    "ToolExecutionEnd",
    "ToolExecutionStart",
    "ToolExecutionUpdate",
    "TurnCancelled",
    "TurnDone",
    "TurnError",
    "TurnStarted",
    "UsageUpdate",
    "UserMessagePersisted",
]
