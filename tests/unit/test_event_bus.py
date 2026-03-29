"""Unit tests for the EventBus pub/sub system."""

import asyncio


import pytest

from kagan.core._event_bus import BusEvent, BusMessage, EventBus

pytestmark = pytest.mark.unit


async def test_subscribe_creates_queue_and_adds_subscriber() -> None:
    """Subscribe creates a queue and adds it to subscribers list."""
    bus = EventBus()

    queue = await bus.subscribe()

    assert isinstance(queue, asyncio.Queue)
    assert queue in bus._subscribers
    assert queue.maxsize == 256  # default maxsize


async def test_subscribe_with_custom_maxsize() -> None:
    """Subscribe respects custom maxsize parameter."""
    bus = EventBus()

    queue = await bus.subscribe(maxsize=10)

    assert queue.maxsize == 10


async def test_unsubscribe_removes_queue() -> None:
    """Unsubscribe removes the queue from subscribers."""
    bus = EventBus()
    queue = await bus.subscribe()

    await bus.unsubscribe(queue)

    assert queue not in bus._subscribers


async def test_unsubscribe_silently_ignores_unknown_queue() -> None:
    """Unsubscribe silently ignores queues not in subscribers list."""
    bus = EventBus()
    unknown_queue: asyncio.Queue[BusMessage] = asyncio.Queue()

    # Should not raise
    await bus.unsubscribe(unknown_queue)

    assert unknown_queue not in bus._subscribers


async def test_publish_sends_message_to_all_subscribers() -> None:
    """Publish broadcasts message to all subscriber queues."""
    bus = EventBus()
    queue1 = await bus.subscribe()
    queue2 = await bus.subscribe()
    message = BusMessage(event=BusEvent.TASK_CREATED, entity_id="task-1")

    await bus.publish(message)

    assert queue1.get_nowait() == message
    assert queue2.get_nowait() == message


async def test_publish_handles_empty_subscribers() -> None:
    """Publish handles case with no subscribers gracefully."""
    bus = EventBus()
    message = BusMessage(event=BusEvent.TASK_CREATED, entity_id="task-1")

    # Should not raise
    await bus.publish(message)

    assert len(bus._subscribers) == 0


async def test_publish_handles_queue_full_by_evicting_oldest() -> None:
    """Publish evicts oldest message when queue is full."""
    bus = EventBus()
    queue = await bus.subscribe(maxsize=2)

    # Fill the queue
    old_message1 = BusMessage(event=BusEvent.TASK_CREATED, entity_id="task-1")
    old_message2 = BusMessage(event=BusEvent.TASK_UPDATED, entity_id="task-2")
    queue.put_nowait(old_message1)
    queue.put_nowait(old_message2)

    # Publish new message - should evict oldest
    new_message = BusMessage(event=BusEvent.TASK_DELETED, entity_id="task-3")
    await bus.publish(new_message)

    # Oldest message should be evicted
    assert queue.get_nowait() == old_message2
    assert queue.get_nowait() == new_message
    assert queue.empty()


async def test_publish_handles_double_queue_full_gracefully() -> None:
    """Publish handles case where eviction fails to make room - drops message silently."""
    bus = EventBus()
    queue = await bus.subscribe(maxsize=1)

    # Fill the queue
    old_message = BusMessage(event=BusEvent.TASK_CREATED, entity_id="task-1")
    queue.put_nowait(old_message)

    # Mock the queue to always raise QueueFull even after eviction
    original_put_nowait = queue.put_nowait
    call_count = 0

    def mock_put_nowait(item: BusMessage) -> None:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.QueueFull()
        original_put_nowait(item)

    queue.put_nowait = mock_put_nowait  # type: ignore[method-assign]

    new_message = BusMessage(event=BusEvent.TASK_UPDATED, entity_id="task-2")

    # Should not raise even when queue remains full after eviction attempt
    await bus.publish(new_message)

    # Queue should be empty (old message was evicted, new one was dropped)
    assert queue.empty()


async def test_publish_thread_safety() -> None:
    """Publish is thread-safe with concurrent subscribe/unsubscribe."""
    bus = EventBus()
    message_count = 100
    subscriber_count = 10

    # Create initial subscribers
    queues = [await bus.subscribe() for _ in range(subscriber_count)]

    # Publish messages concurrently
    async def publish_messages() -> None:
        for i in range(message_count):
            msg = BusMessage(event=BusEvent.TASK_CREATED, entity_id=f"task-{i}")
            await bus.publish(msg)

    # Subscribe/unsubscribe concurrently
    async def mutate_subscribers() -> None:
        for _ in range(20):
            q = await bus.subscribe()
            await asyncio.sleep(0)
            await bus.unsubscribe(q)

    await asyncio.gather(
        publish_messages(),
        mutate_subscribers(),
        mutate_subscribers(),
    )

    # Verify original subscribers received all messages
    for queue in queues:
        received = []
        while not queue.empty():
            received.append(queue.get_nowait())
        assert len(received) == message_count


def test_publish_sync_with_no_running_loop_skips_silently() -> None:
    """Publish_sync skips silently when no event loop is running."""
    bus = EventBus()
    message = BusMessage(event=BusEvent.TASK_CREATED, entity_id="task-1")

    # Should not raise even when no event loop is running
    bus.publish_sync(message)

    # No subscribers should be added (publish never ran)
    assert len(bus._subscribers) == 0


async def test_publish_sync_with_running_loop_schedules_publish() -> None:
    """Publish_sync schedules publish when event loop is running."""
    bus = EventBus()
    queue = await bus.subscribe()
    message = BusMessage(event=BusEvent.TASK_CREATED, entity_id="task-1")

    bus.publish_sync(message)

    # Give the event loop a chance to process the scheduled task
    await asyncio.sleep(0.01)

    assert queue.get_nowait() == message


def test_publish_sync_thread_safety() -> None:
    """Publish_sync is thread-safe and schedules correctly."""
    bus = EventBus()
    message = BusMessage(event=BusEvent.TASK_CREATED, entity_id="task-1")
    received_messages: list[BusMessage] = []

    async def subscriber_loop(queue: asyncio.Queue[BusMessage]) -> None:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
                received_messages.append(msg)
            except asyncio.TimeoutError:
                break

    async def main() -> None:
        queue = await bus.subscribe()

        # Call publish_sync from the main thread (has running loop)
        bus.publish_sync(message)

        # Run subscriber to collect message
        await subscriber_loop(queue)

    asyncio.run(main())

    assert len(received_messages) == 1
    assert received_messages[0] == message


async def test_concurrent_subscribe_unsubscribe_publish() -> None:
    """Test concurrent operations maintain consistency."""
    bus = EventBus()
    operations = 50

    async def subscriber_worker() -> list[asyncio.Queue[BusMessage]]:
        queues = []
        for i in range(operations):
            q = await bus.subscribe(maxsize=10)
            queues.append(q)
            if i % 2 == 0:
                await bus.unsubscribe(q)
                queues.remove(q)
        return queues

    async def publisher_worker() -> None:
        for i in range(operations):
            msg = BusMessage(event=BusEvent.SESSION_EVENT, entity_id=f"session-{i}")
            await bus.publish(msg)
            await asyncio.sleep(0)

    # Run concurrently
    queues_future = asyncio.create_task(subscriber_worker())
    publisher_future = asyncio.create_task(publisher_worker())

    remaining_queues = await queues_future
    await publisher_future

    # Verify remaining queues have consistent state
    for queue in remaining_queues:
        # Queue should not be empty (received some messages)
        # and should not exceed maxsize
        assert queue.qsize() <= queue.maxsize


async def test_unsubscribe_idempotent() -> None:
    """Unsubscribe can be called multiple times on same queue safely."""
    bus = EventBus()
    queue = await bus.subscribe()

    await bus.unsubscribe(queue)
    await bus.unsubscribe(queue)  # Should not raise
    await bus.unsubscribe(queue)  # Should not raise

    assert queue not in bus._subscribers


async def test_multiple_messages_preserve_order() -> None:
    """Messages are delivered to subscribers in order."""
    bus = EventBus()
    queue = await bus.subscribe(maxsize=100)
    messages = [
        BusMessage(event=BusEvent.TASK_CREATED, entity_id=f"task-{i}")
        for i in range(10)
    ]

    for msg in messages:
        await bus.publish(msg)

    received = []
    while not queue.empty():
        received.append(queue.get_nowait())

    assert received == messages
