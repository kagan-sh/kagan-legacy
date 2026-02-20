"""Wire event transport for decoupling core from renderers."""

from __future__ import annotations

from kagan.core.wire.events import (
    WireEvent,
    WireEventEnvelope,
    WireEventType,
    is_wire_event,
)
from kagan.core.wire.transport import (
    BroadcastQueue,
    Wire,
    WireEventQueue,
    WireSoulSide,
    WireUISide,
)

__all__ = [
    "BroadcastQueue",
    "Wire",
    "WireEvent",
    "WireEventEnvelope",
    "WireEventQueue",
    "WireEventType",
    "WireSoulSide",
    "WireUISide",
    "is_wire_event",
]

# Re-export events for consumers that need them
from kagan.core.wire import events as _events  # noqa: F401
