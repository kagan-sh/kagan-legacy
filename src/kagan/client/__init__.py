"""Unified KaganClient package with adapter pattern.

This package provides a unified interface for interacting with Kagan,
supporting both local (in-process) and remote (HTTP) implementations.

Example:
    from kagan.client import LocalClient

    async with LocalClient() as client:
        task = await client.create_task("Fix the bug")
        await client.run_task(task.id)

        async for event in client.subscribe_events():
            print(f"Event: {event.type} - {event}")

Architecture:
    - KaganClient: Abstract base class defining the interface
    - LocalClient: Wraps KaganCore for in-process use
    - RemoteClient: HTTP/WebSocket client (TODO - Week 2)
    - Event types: Typed Pydantic models for all events
"""

from kagan.client._local_client import EmbeddedServer, LocalClient, UnixSocketClient
from kagan.client.base import KaganClient
from kagan.client.events import (
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
    "KaganClient",
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
    "UnixSocketClient",
]
