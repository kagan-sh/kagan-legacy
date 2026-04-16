"""Kagan client package.

Provides LocalClient for interacting with an embedded Kagan server
over a Unix socket.

Example:
    from kagan.server.client import LocalClient

    async with LocalClient() as client:
        task = await client.create_task("Fix the bug")
        await client.run_task(task.id)

        async for event in client.subscribe_events():
            print(f"Event: {event.type} - {event}")
"""

from kagan.server.client._local_client import EmbeddedServer, LocalClient
from kagan.server.client.events import (
    AnyEvent,
    Event,
    SessionEndedEvent,
    SessionEvent,
    SessionOutputEvent,
    SessionStartedEvent,
    SettingsChangedEvent,
    TaskCreatedEvent,
    TaskDeletedEvent,
    TaskEvent,
    TaskStatusChangedEvent,
    TaskUpdatedEvent,
)

__all__ = [
    "AnyEvent",
    "EmbeddedServer",
    "Event",
    "LocalClient",
    "SessionEndedEvent",
    "SessionEvent",
    "SessionOutputEvent",
    "SessionStartedEvent",
    "SettingsChangedEvent",
    "TaskCreatedEvent",
    "TaskDeletedEvent",
    "TaskEvent",
    "TaskStatusChangedEvent",
    "TaskUpdatedEvent",
]
