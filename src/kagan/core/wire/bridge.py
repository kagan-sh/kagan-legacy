"""EventBusWireBridge: translates domain events to WireEvents.

Subscribes to EventBus and emits corresponding WireEvents when a Wire is
configured. Wire is optional — if no Wire is set, existing behavior is unchanged.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from kagan.core.events import (
    AutomationAgentAttached,
    AutomationReviewAgentAttached,
    AutomationTaskEnded,
    AutomationTaskStarted,
    DomainEvent,
    EventBus,
    MergeCompleted,
    MergeFailed,
    PRCreated,
    ProjectCreated,
    ProjectOpened,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from kagan.core.wire.events import (
    AgentCompleted,
    AgentFailed,
    AgentStatus,
    TaskMerged,
    TaskTransitioned,
)
from kagan.core.wire.events import (
    PRCreated as WirePRCreated,
)
from kagan.core.wire.events import (
    ProjectOpened as WireProjectOpened,
)
from kagan.core.wire.events import (
    TaskCreated as WireTaskCreated,
)
from kagan.core.wire.events import (
    TaskDeleted as WireTaskDeleted,
)

if TYPE_CHECKING:
    from kagan.core.wire.transport import Wire


def _status_str(value: object) -> str:
    """Convert TaskStatus enum or similar to string."""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _pr_number_from_url(url: str) -> int | str:
    """Extract PR number from GitHub-style URL, or return 0."""
    match = re.search(r"/pull/(\d+)(?:/|$|\?)", url)
    if match:
        return int(match.group(1))
    return 0


def _domain_to_wire(event: DomainEvent):
    """Map a domain event to a WireEvent. Returns None if no mapping exists."""
    if isinstance(event, TaskCreated):
        return WireTaskCreated(
            task_id=event.task_id,
            status=_status_str(event.status),
            title=event.title,
        )
    if isinstance(event, TaskStatusChanged):
        return TaskTransitioned(
            task_id=event.task_id,
            from_status=_status_str(event.from_status),
            to_status=_status_str(event.to_status),
            reason=event.reason,
        )
    if isinstance(event, TaskDeleted):
        return WireTaskDeleted(task_id=event.task_id)
    if isinstance(event, TaskUpdated):
        # TaskUpdated has no direct Wire equivalent; status changes emit TaskStatusChanged.
        return None
    if isinstance(event, AutomationTaskStarted):
        return AgentStatus(
            task_id=event.task_id,
            status="initializing",
            message="Agent is starting…",
        )
    if isinstance(event, AutomationAgentAttached):
        return AgentStatus(
            task_id=event.task_id,
            status="ready",
            message="Agent ready",
        )
    if isinstance(event, AutomationReviewAgentAttached):
        return AgentStatus(
            task_id=event.task_id,
            status="ready",
            message="Review agent ready",
        )
    if isinstance(event, AutomationTaskEnded):
        return AgentCompleted(task_id=event.task_id, outcome="ended")
    if isinstance(event, MergeCompleted):
        return TaskMerged(
            task_id=None,
            merge_strategy=event.target_branch,
        )
    if isinstance(event, MergeFailed):
        return AgentFailed(
            task_id=None,
            error=event.error,
        )
    if isinstance(event, ProjectOpened):
        return WireProjectOpened(
            task_id=None,
            project_id=event.project_id,
        )
    if isinstance(event, ProjectCreated):
        return WireProjectOpened(
            task_id=None,
            project_id=event.project_id,
        )
    if isinstance(event, PRCreated):
        return WirePRCreated(
            task_id=None,
            pr_number=_pr_number_from_url(event.pr_url),
            url=event.pr_url,
        )
    return None


class EventBusWireBridge:
    """Subscribes to EventBus and translates domain events to WireEvents.

    When Wire is configured, domain events are mapped and emitted to Wire
    subscribers. If Wire is None, the bridge does nothing (zero risk to
    existing tests).
    """

    def __init__(self, event_bus: EventBus, wire: Wire | None = None) -> None:
        self._event_bus = event_bus
        self._wire = wire
        self._handler_registered = False

    def set_wire(self, wire: Wire | None) -> None:
        """Set or clear the Wire. Safe to call at runtime."""
        self._wire = wire

    def start(self) -> None:
        """Register with EventBus. Call once at daemon startup."""
        if self._handler_registered:
            return
        self._event_bus.add_handler(self._on_event)
        self._handler_registered = True

    def stop(self) -> None:
        """Unregister from EventBus. Call on shutdown."""
        if not self._handler_registered:
            return
        self._event_bus.remove_handler(self._on_event)
        self._handler_registered = False

    def _on_event(self, event: DomainEvent) -> None:
        """Handle domain event: map and emit to Wire if configured."""
        if self._wire is None:
            return
        wire_event = _domain_to_wire(event)
        if wire_event is not None:
            self._wire.emit(wire_event)


__all__ = ["EventBusWireBridge"]
