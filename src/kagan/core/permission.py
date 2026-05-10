"""kagan.core.permission — the permission request/response sidechannel.

``PermissionRequest`` is intentionally NOT part of the ``Event`` union
(``kagan.core.events``). Permission exchange is a request/response handshake
driven by ``asyncio.Future``; yielding it from the event stream would create
ordering and cancellation hazards.

The engine's ``resolve_permission(session_id, future_id, outcome, feedback)``
API is the sole route for resolving a pending request. Surfaces that need to
present a UI for the user should:

1. Register a handler that receives ``PermissionRequest`` instances via whatever
   out-of-band channel the surface supports (callback, queue, etc.).
2. Call ``engine.resolve_permission(...)`` with the user's decision.

See ``kagan.core.chat.engine.ChatEngine._resolve_via_queue`` for the
engine-side wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    """An agent is asking the user to allow or deny a tool call.

    This dataclass is emitted via a *sidechannel* (the engine's internal
    permission queue), never via the main ``Event`` stream.

    Fields
    ------
    future_id : str
        Opaque identifier that must be passed back to
        ``ChatEngine.resolve_permission`` to resolve the gate.
    tool_call : dict
        Raw ACP tool-call descriptor (name, args, etc.).
    options : list[dict]
        ACP-provided response options (allow_once, allow_always, deny, …).
    """

    future_id: str
    tool_call: dict[str, Any]
    options: list[dict[str, Any]]
    kind: Literal["permission_request"] = "permission_request"


@dataclass(frozen=True, slots=True)
class PermissionResolved:
    """Resolution of a previously emitted ``PermissionRequest``.

    Emitted by the engine after ``resolve_permission`` is called, for surfaces
    that want to close any pending UI (e.g. the CLI approval panel).
    """

    future_id: str
    outcome: Literal["allow_once", "allow_always", "deny", "deny_feedback"]
    feedback: str | None
    kind: Literal["permission_resolved"] = "permission_resolved"


__all__ = [
    "PermissionRequest",
    "PermissionResolved",
]
