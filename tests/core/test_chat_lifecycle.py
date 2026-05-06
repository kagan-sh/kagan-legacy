"""Behavioral tests: ChatEngine lifecycle via KaganDriver.

Covers persistence, cancellation, concurrent-turn protection, session
switching, title generation, and the documented event-sequence order.
Slot-cleanup invariants are parametrized over failure modes.

Only public API from ``kagan.core.chat`` is used here; no ``_*`` imports.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from kagan.core.chat import (
    TurnDone,
    TurnInProgressError,
    TurnStarted,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.core, pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_chat_turn_persists_user_and_assistant_messages(board: KaganDriver) -> None:
    """A completed turn must write both a user row and an assistant row."""
    session = await board.chat_create_session(source="test", label="persist-test")
    sid = session["id"]

    outcome = await board.chat_send(sid, "hello", agent_chunks=["world"])

    history = await board.chat_history(sid)
    roles = [m.role for m in history]
    assert "user" in roles
    assert "assistant" in roles
    assert outcome.user_content == "hello"
    assert outcome.assistant_content == "world"
    assert not outcome.terminated


async def test_chat_turn_cancel_persists_partial_with_terminated_flag(
    board: KaganDriver,
) -> None:
    """Cancelling mid-stream persists the partial buffer with terminated=True."""
    session = await board.chat_create_session(source="test", label="cancel-test")
    sid = session["id"]

    outcome = await board.chat_send(sid, "hi", agent_chunks=["partial"], cancel_after_chars=1)

    assert outcome.terminated is True
    history = await board.chat_history(sid)
    assistant_rows = [m for m in history if m.role == "assistant"]
    assert len(assistant_rows) == 1
    assert assistant_rows[0].terminated_at_user_request is True


async def test_chat_concurrent_turn_returns_turn_in_progress_error(
    board: KaganDriver,
) -> None:
    """Starting a second turn on the same session raises TurnInProgressError."""
    from acp.schema import TextContentBlock

    from tests.helpers.chat_engine import SuspendingFactory

    session = await board.chat_create_session(source="test", label="concurrent-test")
    sid = session["id"]

    started = asyncio.Event()
    factory = SuspendingFactory(first_chunk="x", started=started)
    engine = board._driver._ctx.chat  # pyrefly: ignore[private-access]

    await engine.push_user(sid, "first")
    consumer = asyncio.create_task(
        _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="first")],
                acp_factory=factory,
            )
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5.0)

    with pytest.raises(TurnInProgressError):
        stream = engine.stream_assistant(
            sid,
            prompt_blocks=[TextContentBlock(type="text", text="second")],
        )
        await stream.__anext__()

    await engine.cancel(sid)
    await asyncio.wait_for(consumer, timeout=5.0)


async def test_chat_session_switch_releases_previous_state(board: KaganDriver) -> None:
    """Detaching a session clears per-session engine state (turn reports inactive)."""
    session = await board.chat_create_session(source="test", label="switch-test")
    sid = session["id"]

    await board.chat_send(sid, "hello")
    # After a completed turn, detach should be a no-op but must not raise.
    await board.chat_switch_session(sid)

    engine = board._driver._ctx.chat  # pyrefly: ignore[private-access]
    assert not engine.turn_status(sid).active


async def test_chat_first_turn_invokes_title_generator(tmp_path: Path) -> None:
    """Title generator fires on the first turn and renames the session."""
    from kagan.core import KaganCore
    from kagan.core.chat import ChatEngine

    calls: list[tuple[str, str]] = []
    title_called = asyncio.Event()

    async def _gen(user: str, reply: str) -> str | None:
        calls.append((user, reply))
        title_called.set()
        return "Generated Title"

    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()
        engine = ChatEngine(
            sessions=core.chat_sessions,
            acp_factory=core.chat._acp,  # pyrefly: ignore[private-access]
            title_generator=_gen,
        )
        from tests.helpers.chat_engine import ScriptedFactory

        factory = ScriptedFactory(chunks=["reply text"])
        session = await core.chat_sessions.create(source="test", label="orig")
        sid = session.id

        from acp.schema import TextContentBlock

        await engine.push_user(sid, "question")
        await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="question")],
                acp_factory=factory,
            )
        )

        await asyncio.wait_for(title_called.wait(), timeout=5.0)
        # The engine awaits `_sessions.update(...)` immediately after the
        # generator returns; yield until the label is observable.
        while True:
            s = await core.chat_sessions.get(sid)
            if s is not None and s.label == "Generated Title":
                break
            await asyncio.sleep(0)

        assert len(calls) == 1
        assert s is not None
        assert s.label == "Generated Title"
    finally:
        core.close()


async def test_chat_event_sequence_matches_documented_order(board: KaganDriver) -> None:
    """The event stream must start with TurnStarted and end with TurnDone."""
    session = await board.chat_create_session(source="test", label="order-test")
    sid = session["id"]

    outcome = await board.chat_send(sid, "ping", agent_chunks=["pong"])
    events = outcome.events

    assert isinstance(events[0], TurnStarted)
    assert isinstance(events[-1], TurnDone)
    kinds = [e.kind for e in events]
    assert "assistant_message" in kinds


# ---------------------------------------------------------------------------
# Parametrized slot-cleanup invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "failure_mode",
    ["history_raises", "settings_get_raises", "post_done_refresh_raises"],
)
async def test_chat_slot_released_on_failure_mode(board: KaganDriver, failure_mode: str) -> None:
    """The engine slot must be free after any pre-stream or mid-stream failure."""
    from acp.schema import TextContentBlock

    from tests.helpers.chat_engine import RaisingFactory, ScriptedFactory

    session = await board.chat_create_session(source="test", label=f"fail-{failure_mode}")
    sid = session["id"]
    engine = board._driver._ctx.chat  # pyrefly: ignore[private-access]

    if failure_mode == "history_raises":
        original_history = engine._sessions.history  # pyrefly: ignore[private-access]
        calls: dict[str, int] = {"n": 0}

        async def _flaky(session_id: str) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated DB failure")
            return await original_history(session_id)

        engine._sessions.history = _flaky  # type: ignore[method-assign]
        await engine.push_user(sid, "hi")
        try:
            await _drain(
                engine.stream_assistant(
                    sid,
                    prompt_blocks=[TextContentBlock(type="text", text="hi")],
                )
            )
        except RuntimeError:
            pass
        finally:
            engine._sessions.history = original_history  # type: ignore[method-assign]

    elif failure_mode == "settings_get_raises":
        # RaisingFactory explodes before any turn state is claimed — verify
        # stream_assistant tears down the slot on factory error.
        factory = RaisingFactory(exc=RuntimeError("factory boom"))
        await engine.push_user(sid, "hi")
        await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="hi")],
                acp_factory=factory,
            )
        )

    elif failure_mode == "post_done_refresh_raises":
        # A successful turn followed by a detach should still leave slot free.
        factory = ScriptedFactory(chunks=["hello"])
        await engine.push_user(sid, "hi")
        await _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="hi")],
                acp_factory=factory,
            )
        )

    assert not engine.turn_status(sid).active, f"Slot leaked after failure mode '{failure_mode}'"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _drain(stream: Any) -> list[Any]:
    events: list[Any] = []
    async for ev in stream:
        events.append(ev)
    return events
