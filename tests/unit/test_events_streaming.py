import asyncio
from typing import Any, cast

import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical

from kagan.core._events import Events, _BoundedEventQueue
from kagan.core.models import SessionEvent
from kagan.tui.widgets.streaming import OutputChunk, StreamingOutput, _sanitize_stream_text

pytestmark = [pytest.mark.unit]


class _StreamingHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield StreamingOutput(id="stream")


def test_enqueue_output_chunk_replaces_old_non_critical_event_when_queue_is_full() -> None:
    events = Events.__new__(Events)
    queue: _BoundedEventQueue[SessionEvent] = _BoundedEventQueue(maxsize=1)
    queue.put_nowait(
        SessionEvent(
            task_id="task-1",
            session_id="session-1",
            event_type="agent_status",
            payload={"status": "running"},
        )
    )

    incoming = SessionEvent(
        task_id="task-1",
        session_id="session-1",
        event_type="output_chunk",
        payload={"text": "hello"},
    )
    events._enqueue_session_event(queue, incoming)

    stored = queue.get_nowait()
    assert stored.event_type == "output_chunk"
    assert stored.payload == {"text": "hello"}


def test_sanitize_stream_text_normalizes_control_sequences() -> None:
    raw = "A\rB\x1b[31m red\x1b[0m\x07\tC\r\nD\x00"

    assert _sanitize_stream_text(raw) == "A\nB red\tC\nD"


async def test_streaming_output_append_chunk_sanitizes_before_merge() -> None:
    app = _StreamingHarness()

    async with app.run_test() as pilot:
        await pilot.pause()
        stream = app.query_one(StreamingOutput)
        stream.append_chunk("hel\x1b[31mlo\r", kind="assistant", merge=True)
        stream.append_chunk("wor\x07ld", kind="assistant", merge=True)
        await pilot.pause()

        content = stream.query_one("#streaming-body-content", Vertical)
        chunks = [child for child in content.children if isinstance(child, OutputChunk)]

        assert len(chunks) == 1
        assert chunks[0]._accumulated_text == "hello\nworld"


async def test_output_chunk_queues_fragment_before_mount() -> None:
    chunk = OutputChunk("", kind="assistant")

    chunk.stream_fragment("opening words")

    assert chunk._accumulated_text == "opening words"
    assert chunk._pending_fragments.qsize() == 1


async def test_output_chunk_drain_suppresses_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk = OutputChunk("", kind="assistant")
    chunk.stream_fragment("opening words")

    async def _raise(_fragment: str) -> None:
        raise RuntimeError("unmounted")

    monkeypatch.setattr(chunk, "_write_animated", _raise)

    await chunk._drain_fragments()


@pytest.mark.asyncio
async def test_emit_non_persistent_event_streams_without_db_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_db_async(*_args, **_kwargs):
        raise AssertionError("_db_async should not be called for non-persistent emit")

    monkeypatch.setattr("kagan.core._events._db_async", _unexpected_db_async)

    events = cast("Any", Events.__new__(Events))
    events._engine = cast("Any", object())
    events._signals = {}
    queue: asyncio.Queue[SessionEvent] = asyncio.Queue(maxsize=1)
    events._live_queues = {"task-1": [queue]}
    events._global_live_queues = []
    events._board_live_queues = []

    emitted = await events.emit(
        "task-1",
        "output_chunk",
        {"text": "live"},
        session_id="session-1",
        persist=False,
    )

    queued = queue.get_nowait()
    assert emitted.event_type == "output_chunk"
    assert queued.payload == {"text": "live"}


@pytest.mark.asyncio
async def test_stream_stops_after_terminal_event_without_db_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_db_async(*_args, **_kwargs):
        raise AssertionError("_db_async should not be polled in live stream loop")

    monkeypatch.setattr("kagan.core._events._db_async", _unexpected_db_async)

    events = cast("Any", Events.__new__(Events))
    events._engine = cast("Any", object())
    events._signals = {}
    events._live_queues = {}
    events._global_live_queues = []
    events._board_live_queues = []

    stream = events.stream("task-1", replay=False)

    async def _next_event() -> SessionEvent:
        return await anext(stream)

    next_event_task = asyncio.create_task(_next_event())
    await asyncio.sleep(0)

    queue = events._live_queues["task-1"][0]
    queue.put_nowait(
        SessionEvent(
            task_id="task-1",
            session_id="session-1",
            event_type="agent_completed",
            payload={},
        )
    )

    event = await next_event_task
    assert event.event_type == "agent_completed"

    with pytest.raises(StopAsyncIteration):
        await anext(stream)
