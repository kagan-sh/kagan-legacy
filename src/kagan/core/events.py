"""kagan.core.events — single union of all streamed chat events.

Twelve tagged dataclasses cover the full chat surface. The ``type`` field is the
discriminator used both at the Python layer (``match event.type:``) and on the
wire (JSON key ``"type"``).

Serialization: ``dataclasses.asdict(event)`` produces a dict that already
contains the ``type`` literal. Deserialization: switch on ``type`` and call the
matching constructor.

Design constraints (alpha — breaking changes allowed):
- Frozen, slotted dataclasses — no inheritance hierarchy.
- No Pydantic: ``dataclasses.asdict`` + ``json.dumps`` is the wire serializer.
- ``PermissionRequest`` is a *sidechannel* — see ``kagan.core.permission``.
- ``TaskStatusChanged`` stays on its own channel in ``_transitions.py``.

Two additional persistence variants (``AssistantMessagePersisted``,
``UserMessagePersisted``) carry message-row metadata that TUI/CLI surfaces
display. They appear in the union so consumers handle them in a single
``match`` block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Turn lifecycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TurnStart:
    """A new assistant turn has begun."""

    turn_id: str
    session_id: str
    agent_id: str
    type: Literal["turn_start"] = "turn_start"


@dataclass(frozen=True, slots=True)
class TurnEnd:
    """The current turn has completed.

    ``reason`` values:
    - ``"done"`` — normal completion.
    - ``"cancelled"`` — user or system-initiated cancel.
    - ``"error"`` — unrecoverable error; check ``Error`` event for details.
    - ``"max_turns"`` — backend hit its turn limit.
    - ``"refusal"`` — model refused to continue.
    - ``"permission_denied"`` — permission was denied at an unresolvable gate.
    """

    turn_id: str
    reason: Literal["done", "cancelled", "error", "max_turns", "refusal", "permission_denied"]
    type: Literal["turn_end"] = "turn_end"


# ---------------------------------------------------------------------------
# Streamed content
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssistantChunk:
    """A streamed text chunk from the assistant's reply."""

    turn_id: str
    session_id: str
    message_id: str
    delta: str
    type: Literal["assistant_chunk"] = "assistant_chunk"


@dataclass(frozen=True, slots=True)
class ThinkingChunk:
    """A reasoning / thinking token from the assistant (rendered dimmed)."""

    turn_id: str
    session_id: str
    message_id: str
    delta: str
    type: Literal["thinking_chunk"] = "thinking_chunk"


# ---------------------------------------------------------------------------
# Tool calls
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool call dispatched by the agent.

    ``tool_call_id`` is stable across update and result events.
    ``kind`` carries an optional backend-level hint (e.g. ``"read"``,
    ``"write"``, ``"bash"``).
    """

    turn_id: str
    session_id: str
    tool_call_id: str
    name: str
    args: str | None
    title: str
    kind: str | None
    type: Literal["tool_call"] = "tool_call"


@dataclass(frozen=True, slots=True)
class ToolCallUpdate:
    """Partial result / progress from a long-running tool call."""

    tool_call_id: str
    content: str | None
    progress: str | None
    type: Literal["tool_call_update"] = "tool_call_update"


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """A tool call has completed.

    ``is_error`` is ``True`` when the call returned an error result rather
    than a success payload.
    """

    tool_call_id: str
    output: str | None
    is_error: bool
    type: Literal["tool_call_result"] = "tool_call_result"


# ---------------------------------------------------------------------------
# Usage / cost
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsageUpdate:
    """Token-usage / cost snapshot, mirrored from ACP's UsageUpdate.

    All numeric fields are ``None`` when the backend does not expose them.
    """

    turn_id: str
    input: int | None
    output: int | None
    cached: int | None
    cost: float | None
    type: Literal["usage_update"] = "usage_update"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Error:
    """A recoverable or fatal error during the turn.

    When ``fatal`` is ``True`` the engine will also emit ``TurnEnd(reason="error")``.
    """

    turn_id: str | None
    code: str
    message: str
    fatal: bool
    type: Literal["error"] = "error"


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentLifecycle:
    """Session-level lifecycle event.

    ``kind`` values:
    - ``"started"`` — session ready, first turn can begin.
    - ``"finished"`` — normal exit after completion.
    - ``"stopped"`` — user / system cancel.
    - ``"failed"`` — unrecoverable session failure.
    """

    session_id: str
    task_id: str | None
    kind: Literal["started", "finished", "stopped", "failed"]
    detail: str | None
    type: Literal["agent_lifecycle"] = "agent_lifecycle"


# ---------------------------------------------------------------------------
# Persistence acknowledgements (transport-layer side effects)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssistantMessagePersisted:
    """The assistant message row was just written to the DB.

    ``terminated`` indicates a partial save after a user-initiated cancel.
    Consumers use ``message_id`` and ``content`` for display / catchup.
    """

    message_id: int
    content: str
    terminated: bool
    type: Literal["assistant_message"] = "assistant_message"


@dataclass(frozen=True, slots=True)
class UserMessagePersisted:
    """The user message row was just written to the DB.

    Emitted by the SSE transport (``_sse_stream.py``) right after
    ``engine.push_user`` persists the row. Not emitted by the engine itself.
    """

    message_id: int
    content: str
    type: Literal["user_message"] = "user_message"


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

Event = (
    TurnStart
    | TurnEnd
    | AssistantChunk
    | ThinkingChunk
    | ToolCall
    | ToolCallUpdate
    | ToolCallResult
    | UsageUpdate
    | Error
    | AgentLifecycle
    | AssistantMessagePersisted
    | UserMessagePersisted
)

# ---------------------------------------------------------------------------
# Wire helpers
# ---------------------------------------------------------------------------


def event_to_dict(event: Event) -> dict[str, Any]:
    """Serialize an event to a plain dict suitable for ``json.dumps``.

    Uses ``dataclasses.asdict`` which includes the ``type`` literal field.
    """
    import dataclasses

    return dataclasses.asdict(event)


def event_from_dict(data: dict[str, Any]) -> Event:
    """Deserialize a dict (parsed from JSON) into the matching event dataclass.

    Raises ``ValueError`` for unknown ``type`` values.
    """
    kind = data.get("type")
    _drop = {"type"}
    fields = {k: v for k, v in data.items() if k not in _drop}
    match kind:
        case "turn_start":
            return TurnStart(**fields)
        case "turn_end":
            return TurnEnd(**fields)
        case "assistant_chunk":
            return AssistantChunk(**fields)
        case "thinking_chunk":
            return ThinkingChunk(**fields)
        case "tool_call":
            return ToolCall(**fields)
        case "tool_call_update":
            return ToolCallUpdate(**fields)
        case "tool_call_result":
            return ToolCallResult(**fields)
        case "usage_update":
            return UsageUpdate(**fields)
        case "error":
            return Error(**fields)
        case "agent_lifecycle":
            return AgentLifecycle(**fields)
        case "assistant_message":
            return AssistantMessagePersisted(**fields)
        case "user_message":
            return UserMessagePersisted(**fields)
        case _:
            raise ValueError(f"Unknown event type: {kind!r}")


__all__ = [
    "AgentLifecycle",
    "AssistantChunk",
    "AssistantMessagePersisted",
    "Error",
    "Event",
    "ThinkingChunk",
    "ToolCall",
    "ToolCallResult",
    "ToolCallUpdate",
    "TurnEnd",
    "TurnStart",
    "UsageUpdate",
    "UserMessagePersisted",
    "event_from_dict",
    "event_to_dict",
]
