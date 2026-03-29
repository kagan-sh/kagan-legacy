"""Lightweight in-process pub/sub event bus for cross-client notifications."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from loguru import logger


class BusEvent(StrEnum):
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    SESSION_EVENT = "session_event"
    SETTINGS_CHANGED = "settings_changed"
    CHAT_SESSION_UPDATED = "chat_session_updated"


@dataclass(frozen=True, slots=True)
class BusMessage:
    event: BusEvent
    entity_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[BusMessage]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self, maxsize: int = 256) -> asyncio.Queue[BusMessage]:
        queue: asyncio.Queue[BusMessage] = asyncio.Queue(maxsize=maxsize)
        async with self._lock:
            self._subscribers.append(queue)
        logger.debug("EventBus: new subscriber (total={})", len(self._subscribers))
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[BusMessage]) -> None:
        async with self._lock:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(queue)
        logger.debug("EventBus: removed subscriber (total={})", len(self._subscribers))

    async def publish(self, message: BusMessage) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Evict oldest message to make room
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    logger.warning("EventBus: dropping message after eviction attempt")

    def publish_sync(self, message: BusMessage) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("EventBus: no running loop for publish_sync, skipping")
            return
        loop.call_soon_threadsafe(loop.create_task, self.publish(message))


__all__ = ["BusEvent", "BusMessage", "EventBus"]
