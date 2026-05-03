"""Unit tests for ``kagan.core.chat.engine.ChatEngine``.

Uses fake ``ACPSessionFactory`` implementations from ``tests.helpers.chat_engine``
to drive synthetic ACP updates, so the tests exercise the engine's lifecycle
independently of any real orchestrator process.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from kagan.core.chat.engine import ChatEngine, TurnInProgressError
from kagan.core.chat.events import (
    AssistantChunk,
    AssistantMessagePersisted,
    ChatEvent,
    TurnCancelled,
    TurnDone,
    TurnError,
    TurnStarted,
)
from tests.helpers.chat_engine import (
    RaisingFactory,
    ScriptedFactory,
    SuspendingFactory,
    boot_engine,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.core]


async def _drain(stream: Any) -> list[ChatEvent]:
    events: list[ChatEvent] = []
    async for ev in stream:
        events.append(ev)
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_push_user_persists_message(tmp_path: Path) -> None:
    factory = ScriptedFactory(chunks=[])
    core, engine, sid = await boot_engine(tmp_path, factory)
    try:
        msg = await engine.push_user(sid, "Hello world")
        assert msg.role == "user"
        assert msg.content == "Hello world"

        history = await engine.history(sid)
        assert [m.content for m in history] == ["Hello world"]
    finally:
        core.close()


async def test_stream_assistant_emits_events_in_order(tmp_path: Path) -> None:
    factory = ScriptedFactory(chunks=["Hello, ", "world!"])
    core, engine, sid = await boot_engine(tmp_path, factory)
    try:
        await engine.push_user(sid, "Hi")
        from acp.schema import TextContentBlock

        events = await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="Hi")],
            )
        )

        kinds = [e.kind for e in events]
        assert kinds[0] == "turn_started"
        assert kinds[-1] == "done"
        assert "assistant_chunk" in kinds
        assert "assistant_message" in kinds

        chunk_events = [e for e in events if isinstance(e, AssistantChunk)]
        assert [c.text for c in chunk_events] == ["Hello, ", "world!"]

        persisted = next(e for e in events if isinstance(e, AssistantMessagePersisted))
        assert persisted.content == "Hello, world!"
        assert persisted.terminated is False

        done = events[-1]
        assert isinstance(done, TurnDone)
        assert done.full_response == "Hello, world!"

        assert isinstance(events[0], TurnStarted)

        history = await engine.history(sid)
        assert history[-1].role == "assistant"
        assert history[-1].content == "Hello, world!"
        assert history[-1].terminated_at_user_request is False
    finally:
        core.close()


async def test_stream_assistant_persists_partial_on_cancel(tmp_path: Path) -> None:
    started = asyncio.Event()
    factory = SuspendingFactory(first_chunk="partial-text", started=started)
    core, engine, sid = await boot_engine(tmp_path, factory)
    try:
        await engine.push_user(sid, "Hi")
        from acp.schema import TextContentBlock

        async def _consume() -> list[ChatEvent]:
            return await _drain(
                engine.stream_assistant(
                    sid,
                    prompt_blocks=[TextContentBlock(type="text", text="Hi")],
                )
            )

        consumer = asyncio.create_task(_consume())
        await asyncio.wait_for(started.wait(), timeout=5.0)
        # Wait until the chunk has been streamed out (drain task has yielded it).
        await asyncio.sleep(0.05)
        result = await engine.cancel(sid)
        assert result.was_running is True
        assert result.partial_chars == len("partial-text")

        events = await asyncio.wait_for(consumer, timeout=5.0)
        kinds = [e.kind for e in events]
        assert kinds[-1] == "turn_cancelled"
        persisted = [e for e in events if isinstance(e, AssistantMessagePersisted)]
        assert len(persisted) == 1
        assert persisted[0].content == "partial-text"
        assert persisted[0].terminated is True
        assert any(isinstance(e, TurnCancelled) for e in events)

        history = await engine.history(sid)
        assistant_rows = [m for m in history if m.role == "assistant"]
        assert len(assistant_rows) == 1
        assert assistant_rows[0].content == "partial-text"
        assert assistant_rows[0].terminated_at_user_request is True
    finally:
        core.close()


async def test_concurrent_turn_raises_turn_in_progress(tmp_path: Path) -> None:
    started = asyncio.Event()
    factory = SuspendingFactory(first_chunk="x", started=started)
    core, engine, sid = await boot_engine(tmp_path, factory)
    try:
        await engine.push_user(sid, "Hi")
        from acp.schema import TextContentBlock

        async def _consume_first() -> list[ChatEvent]:
            return await _drain(
                engine.stream_assistant(
                    sid,
                    prompt_blocks=[TextContentBlock(type="text", text="Hi")],
                )
            )

        first = asyncio.create_task(_consume_first())
        await asyncio.wait_for(started.wait(), timeout=5.0)

        with pytest.raises(TurnInProgressError):
            stream = engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="Again")],
            )
            # Need to await the iterator setup — the claim happens before any yield.
            await stream.__anext__()

        await engine.cancel(sid)
        await asyncio.wait_for(first, timeout=5.0)
    finally:
        core.close()


async def test_detach_clears_state(tmp_path: Path) -> None:
    factory = ScriptedFactory(chunks=["ok"])
    core, engine, sid = await boot_engine(tmp_path, factory)
    try:
        await engine.push_user(sid, "Hi")
        from acp.schema import TextContentBlock

        await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="Hi")],
            )
        )
        # After a clean turn the engine tears down state itself.
        assert engine.turn_status(sid).active is False
        await engine.detach(sid)
        # Detach is idempotent and clears any residual entry.
        assert engine.turn_status(sid).active is False
    finally:
        core.close()


async def test_title_generator_fires_only_on_first_turn(tmp_path: Path) -> None:
    """Issue 1: ``is_first_turn`` must count prior assistant rows, not total
    history rows. The documented caller flow persists the user row before
    ``stream_assistant`` runs, so a naive ``len(history) == 0`` check would
    never fire title generation.
    """
    calls: list[tuple[str, str]] = []

    async def fake_title(user_text: str, reply: str) -> str | None:
        calls.append((user_text, reply))
        return f"Title: {user_text[:10]}"

    factory = ScriptedFactory(chunks=["First reply"])
    core, engine, sid = await boot_engine(tmp_path, factory, title_generator=fake_title)
    try:
        from acp.schema import TextContentBlock

        # Turn 1: title generator should fire exactly once.
        await engine.push_user(sid, "What's up?")
        await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="What's up?")],
            )
        )

        # Title generation is fire-and-forget — wait briefly for the
        # background task to settle.
        for _ in range(50):
            if calls:
                break
            await asyncio.sleep(0.01)

        assert len(calls) == 1, f"Expected exactly one title call, got {calls}"
        assert calls[0][0] == "What's up?"
        assert calls[0][1] == "First reply"

        # Wait for the rename to be persisted.
        for _ in range(50):
            session = await core.chat_sessions.get(sid)
            if session is not None and session.label == "Title: What's up?":
                break
            await asyncio.sleep(0.01)
        session = await core.chat_sessions.get(sid)
        assert session is not None
        assert session.label == "Title: What's up?"

        # Turn 2: assistant row already exists, so generator must NOT fire.
        await engine.push_user(sid, "Follow-up")
        await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="Follow-up")],
            )
        )
        # Give any spurious background task a chance to run.
        await asyncio.sleep(0.05)
        assert len(calls) == 1, f"Title generator fired again on turn 2: {calls}"
    finally:
        core.close()


async def test_generator_exit_tears_down_state(tmp_path: Path) -> None:
    """Breaking out of ``stream_assistant`` early (GeneratorExit) MUST clear
    the engine's per-session ``_TurnState`` — otherwise the slot leaks and the
    next ``stream_assistant`` call would 409.
    """
    started = asyncio.Event()
    factory = SuspendingFactory(first_chunk="x", started=started)
    core, engine, sid = await boot_engine(tmp_path, factory)
    try:
        await engine.push_user(sid, "Hi")
        from acp.schema import TextContentBlock

        stream = engine.stream_assistant(
            sid, prompt_blocks=[TextContentBlock(type="text", text="Hi")]
        )
        # Pump until the first chunk arrives, then break out early.
        async for ev in stream:
            if ev.kind == "assistant_chunk":
                break
        # Closing the async generator triggers GeneratorExit inside the engine.
        await stream.aclose()

        # State should be torn down; turn_status reports inactive.
        status = engine.turn_status(sid)
        assert status.active is False, "GeneratorExit must clear _TurnState"

        # And we must be able to start a new turn without 409.
        factory2 = ScriptedFactory(chunks=["ok"])
        engine_with_factory = engine
        await _drain(
            engine_with_factory.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="Again")],
                acp_factory=factory2,
            )
        )
    finally:
        core.close()


async def test_factory_failure_emits_single_turn_error(tmp_path: Path) -> None:
    """Issue 2: a raising ``ACPSessionFactory.prompt`` must produce exactly
    one ``TurnError`` event — not two from the drain + outer except both
    reporting the same exception.
    """
    factory = RaisingFactory(exc=RuntimeError("boom"))
    core, engine, sid = await boot_engine(tmp_path, factory)
    try:
        from acp.schema import TextContentBlock

        await engine.push_user(sid, "Hi")
        events = await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="Hi")],
            )
        )
        errors = [e for e in events if isinstance(e, TurnError)]
        assert len(errors) == 1, f"Expected exactly one TurnError, got {errors}"
        assert errors[0].message == "boom"
        # Engine should clean up state after a failed turn.
        assert engine.turn_status(sid).active is False
    finally:
        core.close()
