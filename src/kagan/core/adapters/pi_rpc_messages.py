"""Pi RPC protocol boundary models.

Pydantic models that sit at the JSON-in / Python-out boundary for pi's
JSONL-framed RPC stdout stream. Every frame that arrives on the wire is
validated once here; downstream code reads typed attributes instead of
doing ``msg.get(X) + isinstance(X, T)`` per field.

Sources of truth:
  references/pi-mono/packages/agent/src/types.ts (AgentEvent)
  references/pi-mono/packages/coding-agent/src/core/agent-session.ts (AgentSessionEvent)
  references/pi-mono/packages/coding-agent/src/modes/rpc/rpc-types.ts (RpcResponse)

Design:
  - ``extra="allow"`` on all models — pi may add fields we do not yet care about.
  - ``frozen=True`` — immutable after parsing.
  - ``parse_pi_rpc_message`` does type-tag lookup then per-model validation so
    unknown frames return ``None`` without a full union traversal.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PiAgentEnd",
    "PiAgentStart",
    "PiAssistantMessageEvent",
    "PiAutoRetryEnd",
    "PiAutoRetryStart",
    "PiCompactionEnd",
    "PiCompactionStart",
    "PiExtensionUiRequest",
    "PiMessage",
    "PiMessageEnd",
    "PiMessageStart",
    "PiMessageUpdate",
    "PiQueueUpdate",
    "PiResponseAck",
    "PiSessionInfoChanged",
    "PiThinkingLevelChanged",
    "PiToolCallEnd",
    "PiToolCallStart",
    "PiToolCallUpdate",
    "PiTurnEnd",
    "PiTurnStart",
    "parse_pi_rpc_message",
]

# Registry populated at the bottom of the module, after all classes are defined.
_PI_RPC_REGISTRY: dict[str, type[_PiBase]] = {}


class _PiBase(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------


class PiAgentStart(_PiBase):
    type: Literal["agent_start"]


class PiAgentEnd(_PiBase):
    type: Literal["agent_end"]
    messages: list[Any] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Turn lifecycle
# ---------------------------------------------------------------------------
# Real pi protocol: turn_start / turn_end have NO turn_index field.
# references/pi-mono/packages/agent/src/types.ts:
#   { type: "turn_start" }
#   { type: "turn_end"; message: AgentMessage; toolResults: ToolResultMessage[] }


class PiTurnStart(_PiBase):
    type: Literal["turn_start"]


class PiTurnEnd(_PiBase):
    type: Literal["turn_end"]


# ---------------------------------------------------------------------------
# Message lifecycle
# ---------------------------------------------------------------------------


class PiMessage(_PiBase):
    """Embedded message object in message_start / message_update / message_end frames."""

    id: str | None = None
    role: str  # "user" | "assistant" | "tool" | "system" — tolerate unknowns
    content: list[Any] = Field(default_factory=list)


class PiAssistantMessageEvent(_PiBase):
    """Streaming delta event nested inside message_update frames.

    Only ``text_delta`` and ``thinking_delta`` carry a non-empty ``delta``
    field (per the AssistantMessageEvent union in pi-ai). Other subtypes
    (e.g. ``stop_reason``) have no delta and must be ignored.
    """

    type: str  # "text_delta" | "thinking_delta" | "stop_reason" | ...
    delta: str = ""


class PiMessageStart(_PiBase):
    type: Literal["message_start"]
    message: PiMessage


class PiMessageUpdate(_PiBase):
    type: Literal["message_update"]
    message: PiMessage
    assistantMessageEvent: PiAssistantMessageEvent | None = None


class PiMessageEnd(_PiBase):
    type: Literal["message_end"]
    message: PiMessage


# ---------------------------------------------------------------------------
# Tool execution lifecycle
# ---------------------------------------------------------------------------
# Real field names per types.ts:
#   tool_execution_start:  toolCallId, toolName, args
#   tool_execution_update: toolCallId, toolName, args, partialResult
#   tool_execution_end:    toolCallId, toolName, result, isError: boolean


class PiToolCallStart(_PiBase):
    type: Literal["tool_execution_start"]
    toolCallId: str | None = None
    toolName: str | None = None
    args: Any = None


class PiToolCallUpdate(_PiBase):
    type: Literal["tool_execution_update"]
    toolCallId: str | None = None
    partialResult: Any = None


class PiToolCallEnd(_PiBase):
    type: Literal["tool_execution_end"]
    toolCallId: str | None = None
    result: Any = None
    isError: bool = False


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------
# compaction_start: { type: "compaction_start"; reason: "manual" | "threshold" | "overflow" }


class PiCompactionStart(_PiBase):
    type: Literal["compaction_start"]
    reason: str = ""


class PiCompactionEnd(_PiBase):
    type: Literal["compaction_end"]


# ---------------------------------------------------------------------------
# Non-event / noise frames we recognise but do not translate
# ---------------------------------------------------------------------------


class PiResponseAck(_PiBase):
    type: Literal["response"]


class PiExtensionUiRequest(_PiBase):
    type: Literal["extension_ui_request"]


class PiQueueUpdate(_PiBase):
    type: Literal["queue_update"]


class PiSessionInfoChanged(_PiBase):
    type: Literal["session_info_changed"]


class PiThinkingLevelChanged(_PiBase):
    type: Literal["thinking_level_changed"]


class PiAutoRetryStart(_PiBase):
    type: Literal["auto_retry_start"]


class PiAutoRetryEnd(_PiBase):
    type: Literal["auto_retry_end"]


# ---------------------------------------------------------------------------
# Registry: type-tag → model class (in the order they appear above)
# ---------------------------------------------------------------------------

_PI_RPC_REGISTRY.update(
    {
        "agent_start": PiAgentStart,
        "agent_end": PiAgentEnd,
        "turn_start": PiTurnStart,
        "turn_end": PiTurnEnd,
        "message_start": PiMessageStart,
        "message_update": PiMessageUpdate,
        "message_end": PiMessageEnd,
        "tool_execution_start": PiToolCallStart,
        "tool_execution_update": PiToolCallUpdate,
        "tool_execution_end": PiToolCallEnd,
        "compaction_start": PiCompactionStart,
        "compaction_end": PiCompactionEnd,
        "response": PiResponseAck,
        "extension_ui_request": PiExtensionUiRequest,
        "queue_update": PiQueueUpdate,
        "session_info_changed": PiSessionInfoChanged,
        "thinking_level_changed": PiThinkingLevelChanged,
        "auto_retry_start": PiAutoRetryStart,
        "auto_retry_end": PiAutoRetryEnd,
    }
)


def parse_pi_rpc_message(raw: dict[str, Any]) -> _PiBase | None:
    """Validate *raw* against the pi RPC boundary model for its ``type`` tag.

    Returns the typed model instance or ``None`` when:
    - ``raw["type"]`` is missing or not a str
    - ``raw["type"]`` is not a recognised frame type
    - Pydantic validation fails (malformed frame)

    This is a one-shot lookup + validate: no union traversal, O(1) dispatch.
    """
    event_type = raw.get("type")
    if not isinstance(event_type, str):
        return None
    model_cls = _PI_RPC_REGISTRY.get(event_type)
    if model_cls is None:
        return None
    try:
        return model_cls.model_validate(raw)
    except Exception:  # pydantic.ValidationError or unexpected
        return None
