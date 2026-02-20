"""Wire event transport: BroadcastQueue and Wire for decoupling core from renderers."""

from __future__ import annotations

import asyncio
import copy

from kagan.core.wire.events import StreamChunk, WireEvent, is_wire_event


class BroadcastQueue[T]:
    """
    Async fan-out queue: one publish delivers to all subscribers.
    Uses asyncio.Queue per subscriber for zero-copy delivery.
    """

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[T]] = set()

    def subscribe(self) -> asyncio.Queue[T]:
        """Create a new subscription queue."""
        queue: asyncio.Queue[T] = asyncio.Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[T]) -> None:
        """Remove a subscription queue."""
        self._queues.discard(queue)

    async def publish(self, item: T) -> None:
        """Publish an item to all subscription queues."""
        await asyncio.gather(*(q.put(item) for q in self._queues))

    def publish_nowait(self, item: T) -> None:
        """Publish an item to all subscription queues without waiting."""
        for queue in self._queues:
            queue.put_nowait(item)

    def shutdown(self) -> None:
        """Signal shutdown by clearing subscribers. Queues are left for drain."""
        self._queues.clear()


WireEventQueue = BroadcastQueue[WireEvent]


class WireSoulSide:
    """
    Producer side of the Wire. Core domain logic emits events here.
    Supports raw (every event) and merged (consecutive StreamChunks coalesced) modes.
    """

    def __init__(self, raw_queue: WireEventQueue, merged_queue: WireEventQueue) -> None:
        self._raw_queue = raw_queue
        self._merged_queue = merged_queue
        self._merge_buffer: StreamChunk | None = None

    def emit(self, event: WireEvent) -> None:
        """Emit an event to all subscribers."""
        # Always send raw
        self._raw_queue.publish_nowait(event)

        # Merge and send merged
        if isinstance(event, StreamChunk):
            if self._merge_buffer is None:
                self._merge_buffer = copy.deepcopy(event)
            elif self._merge_buffer.merge_in_place(event):
                pass
            else:
                self._flush()
                self._merge_buffer = copy.deepcopy(event)
        else:
            self._flush()
            self._merged_queue.publish_nowait(event)

    def flush(self) -> None:
        """Flush any buffered StreamChunk to merged queue."""
        self._flush()

    def _flush(self) -> None:
        buffer = self._merge_buffer
        if buffer is None:
            return
        assert is_wire_event(buffer)
        self._merged_queue.publish_nowait(buffer)
        self._merge_buffer = None


class WireUISide:
    """
    Consumer side of the Wire. Clients receive events here.
    """

    def __init__(self, queue: asyncio.Queue[WireEvent]) -> None:
        self._queue = queue

    async def receive(self) -> WireEvent:
        """Receive the next event. Blocks until one is available."""
        return await self._queue.get()

    def receive_nowait(self) -> WireEvent | None:
        """Receive an event if available, else None."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


class Wire:
    """
    Single-producer, multi-consumer event channel.
    Decouples core domain logic from all client renderers.
    """

    def __init__(self) -> None:
        self._raw_queue: WireEventQueue = BroadcastQueue()
        self._merged_queue: WireEventQueue = BroadcastQueue()
        self._soul_side = WireSoulSide(self._raw_queue, self._merged_queue)

    @property
    def soul_side(self) -> WireSoulSide:
        """Producer side. Core domain emits events via soul_side.emit()."""
        return self._soul_side

    def subscribe(self, *, merge: bool = False) -> WireUISide:
        """
        Create a consumer subscription.

        Args:
            merge: If True, consecutive StreamChunks are coalesced (TUI block appends).
                   If False, every event is delivered individually (CLI character streaming).
        """
        queue = self._merged_queue.subscribe() if merge else self._raw_queue.subscribe()
        return WireUISide(queue)

    def emit(self, event: WireEvent) -> None:
        """Convenience: emit via soul_side."""
        self.soul_side.emit(event)

    def shutdown(self) -> None:
        """Shutdown the Wire. Flush soul side and clear queues."""
        self.soul_side.flush()
        self._raw_queue.shutdown()
        self._merged_queue.shutdown()


__all__ = [
    "BroadcastQueue",
    "Wire",
    "WireEventQueue",
    "WireSoulSide",
    "WireUISide",
]
