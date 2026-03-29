"""Abstract base class for KaganClient using the adapter pattern.

This module defines the unified interface that both local (KaganCore)
and remote (HTTP/WebSocket) clients implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from kagan.client.events import AnyEvent, TaskCreatedEvent


class KaganClient(ABC):
    """Abstract base class for Kagan clients.

    Implementations:
        - LocalClient: Wraps KaganCore for in-process use
        - RemoteClient: HTTP/WebSocket client for remote servers (TODO)

    Usage:
        async with LocalClient() as client:
            task = await client.create_task("Fix bug")
            await client.run_task(task.id)
            async for event in client.subscribe_events():
                print(event)
    """

    @abstractmethod
    async def create_task(
        self,
        title: str,
        *,
        description: str = "",
        status: str = "BACKLOG",
        priority: str = "MEDIUM",
        acceptance_criteria: list[str] | None = None,
    ) -> TaskCreatedEvent:
        """Create a new task in the active project.

        Args:
            title: Task title (required)
            description: Task description
            status: Initial status (BACKLOG, IN_PROGRESS, REVIEW, DONE)
            priority: Task priority (LOW, MEDIUM, HIGH, CRITICAL)
            acceptance_criteria: List of acceptance criteria strings

        Returns:
            TaskCreatedEvent with task details

        Raises:
            SessionError: If no active project is set
        """
        ...

    @abstractmethod
    async def run_task(
        self,
        task_id: str,
        *,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> None:
        """Start an agent session on a task.

        Args:
            task_id: ID of the task to run
            agent_backend: Agent backend to use (defaults to system default)
            launcher: Launcher configuration

        Raises:
            NotFoundError: If task doesn't exist
            SessionError: If task is already running
        """
        ...

    @abstractmethod
    def subscribe_events(self) -> AsyncIterator[AnyEvent]:
        """Subscribe to all real-time events.

        Yields typed events with sequence numbers for gap detection.
        Consumers should track seq numbers and resync if gaps are detected.

        Yields:
            AnyEvent: Task, session, or settings events
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the client and cleanup resources."""
        ...

    async def __aenter__(self) -> KaganClient:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit - ensures cleanup."""
        await self.close()


__all__ = ["KaganClient"]
