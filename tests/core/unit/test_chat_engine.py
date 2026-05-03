"""Unit tests for ``kagan.core.chat.engine.ChatEngine``.

Uses a fake ACPSessionFactory that drives synthetic ACP updates, so the tests
exercise the engine's lifecycle independently of any real orchestrator
process.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from kagan.core import KaganCore
from kagan.core.chat.acp import ACPSessionFactory, ACPTurnResult
from kagan.core.chat.engine import ChatEngine, TurnInProgressError
from kagan.core.chat.events import (
    AssistantChunk,
    AssistantMessagePersisted,
    ChatEvent,
    TurnCancelled,
    TurnDone,
    TurnStarted,
)

pytestmark = [pytest.mark.core]


# ---------------------------------------------------------------------------
# Synthetic ACP payloads — match the duck-typed shapes used by the real
# ``acp.schema`` classes that ``acp_update_to_chat_event`` checks against.
# Using real classes from acp.schema keeps the mapping side honest.
# ---------------------------------------------------------------------------


def _text_chunk(text: str) -> Any:
    from acp.schema import AgentMessageChunk, TextContentBlock

    return AgentMessageChunk(
        content=TextContentBlock(type="text", text=text),
        session_update="agent_message_chunk",
    )


# ---------------------------------------------------------------------------
# Fake factories
# ---------------------------------------------------------------------------


@dataclass
class _ScriptedFactory:
    """ACPSessionFactory that emits a scripted list of ACP updates."""

    chunks: list[str]

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
    ) -> ACPTurnResult:
        del session_id, prompt_blocks, agent_backend
        for chunk in self.chunks:
            if cancel_event.is_set():
                return ACPTurnResult(full_response="", cancelled=True)
            await on_update(_text_chunk(chunk))
            await asyncio.sleep(0)
        return ACPTurnResult(full_response="".join(self.chunks), cancelled=False)


@dataclass
class _SuspendingFactory:
    """ACPSessionFactory that emits one chunk then suspends until cancelled."""

    first_chunk: str
    started: asyncio.Event

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
    ) -> ACPTurnResult:
        del session_id, prompt_blocks, agent_backend
        await on_update(_text_chunk(self.first_chunk))
        self.started.set()
        await cancel_event.wait()
        return ACPTurnResult(full_response="", cancelled=True)


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------


async def _boot_engine(
    tmp_path: Path,
    factory: ACPSessionFactory,
) -> tuple[KaganCore, ChatEngine, str]:
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    # Initialize schema
    await core.reset()
    engine = ChatEngine(sessions=core.chat_sessions, acp_factory=factory)
    session = await core.chat_sessions.create(source="test", label="Engine test")
    return core, engine, session.id


async def _drain(stream: Any) -> list[ChatEvent]:
    events: list[ChatEvent] = []
    async for ev in stream:
        events.append(ev)
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_push_user_persists_message(tmp_path: Path) -> None:
    factory = _ScriptedFactory(chunks=[])
    core, engine, sid = await _boot_engine(tmp_path, factory)
    try:
        msg = await engine.push_user(sid, "Hello world")
        assert msg.role == "user"
        assert msg.content == "Hello world"

        history = await engine.history(sid)
        assert [m.content for m in history] == ["Hello world"]
    finally:
        core.close()


async def test_stream_assistant_emits_events_in_order(tmp_path: Path) -> None:
    factory = _ScriptedFactory(chunks=["Hello, ", "world!"])
    core, engine, sid = await _boot_engine(tmp_path, factory)
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
    factory = _SuspendingFactory(first_chunk="partial-text", started=started)
    core, engine, sid = await _boot_engine(tmp_path, factory)
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
    factory = _SuspendingFactory(first_chunk="x", started=started)
    core, engine, sid = await _boot_engine(tmp_path, factory)
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
    factory = _ScriptedFactory(chunks=["ok"])
    core, engine, sid = await _boot_engine(tmp_path, factory)
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
