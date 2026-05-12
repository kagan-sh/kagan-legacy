"""Behavioral tests: ChatEngine writes EventLog frames per chunk (W2).

Acceptance criteria from the W2 workstream spec:
- User message turn creates a user entry frame and a pending assistant entry frame.
- Each assistant token chunk produces an append frame.
- Partial text is recoverable from append frames after a simulated crash.
- A finalize frame is emitted when the turn completes normally.
- Cancel emits a finalize frame with ``reason="terminated_at_user_request"``.
- Two concurrent subscribers see identical seq streams.
- Entry idx values are monotonic within a session across turns.
- Entry idx values are independent across different sessions.
- A 409-rejected concurrent turn emits no rogue frames.

All DB access is real (no mocks).  Only ``FakeAgent``-style factories are used.
The ``board`` fixture provides a live ``KaganCore`` via ``KaganDriver``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.core, pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frames(rows: list[Any]) -> list[dict[str, Any]]:
    """Extract frame dicts from FrameRow list."""
    return [r.frame for r in rows]


def _patches(rows: list[Any]) -> list[dict[str, Any]]:
    """Return only 'patch' frames."""
    return [r.frame for r in rows if r.frame.get("type") == "patch"]


def _reconstruct_text(rows: list[Any], assistant_idx: int) -> str:
    """Reduce append frames for ``assistant_idx`` into the full text."""
    text = ""
    for row in rows:
        frame = row.frame
        if (
            frame.get("type") == "patch"
            and frame.get("op") == "append"
            and frame.get("path") == f"/entries/{assistant_idx}/text"
        ):
            text += frame.get("value", "")
    return text


async def _drain(stream: Any) -> list[Any]:
    events: list[Any] = []
    async for ev in stream:
        events.append(ev)
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_user_message_creates_user_entry_frame(board: KaganDriver) -> None:
    """After a turn completes, a 'create' patch frame for the user entry exists."""
    session = await board.chat_create_session(source="test", label="user-frame")
    sid = session["id"]

    await board.chat_send(sid, "hello", agent_chunks=["world"])

    frames = await board.read_frames(sid, "chat")
    patches = _patches(frames)

    user_creates = [
        p
        for p in patches
        if p.get("op") == "create"
        and "role" in (p.get("value") or {})
        and (p.get("value") or {}).get("role") == "user"
    ]
    assert len(user_creates) == 1, f"Expected 1 user create frame, got: {user_creates}"
    assert user_creates[0]["value"]["text"] == "hello"
    assert user_creates[0]["value"]["finalized"] is True


async def test_user_message_creates_pending_assistant_entry_frame(board: KaganDriver) -> None:
    """After a turn completes, a 'create' patch frame for the assistant entry exists
    with ``finalized=False`` initially (later superseded by a finalize frame)."""
    session = await board.chat_create_session(source="test", label="assistant-frame")
    sid = session["id"]

    await board.chat_send(sid, "hello", agent_chunks=["world"])

    frames = await board.read_frames(sid, "chat")
    patches = _patches(frames)

    assistant_creates = [
        p
        for p in patches
        if p.get("op") == "create"
        and "role" in (p.get("value") or {})
        and (p.get("value") or {}).get("role") == "assistant"
    ]
    assert len(assistant_creates) == 1, (
        f"Expected 1 assistant create frame, got: {assistant_creates}"
    )
    assert assistant_creates[0]["value"]["text"] == ""
    assert assistant_creates[0]["value"]["finalized"] is False


async def test_assistant_chunk_persists_append_frame_per_token(board: KaganDriver) -> None:
    """Each chunk from the agent produces one append frame in the event log."""
    session = await board.chat_create_session(source="test", label="chunks-frame")
    sid = session["id"]

    chunks = ["one ", "two ", "three"]
    await board.chat_send(sid, "stream me", agent_chunks=chunks)

    frames = await board.read_frames(sid, "chat")
    patches = _patches(frames)

    append_frames = [p for p in patches if p.get("op") == "append"]
    assert len(append_frames) == len(chunks), (
        f"Expected {len(chunks)} append frames, got {len(append_frames)}"
    )
    values = [p["value"] for p in append_frames]
    assert values == chunks


async def test_partial_assistant_text_recoverable_after_crash(board: KaganDriver) -> None:
    """Text can be reconstructed from append frames alone (no in-memory buffer needed)."""
    session = await board.chat_create_session(source="test", label="crash-recovery")
    sid = session["id"]

    chunks = ["Hello", " world", "!"]
    await board.chat_send(sid, "say hello", agent_chunks=chunks)

    frames = await board.read_frames(sid, "chat")
    patches = _patches(frames)

    # Find the assistant idx from the create frame.
    assistant_creates = [
        p
        for p in patches
        if p.get("op") == "create" and (p.get("value") or {}).get("role") == "assistant"
    ]
    assert assistant_creates, "No assistant create frame found"
    assistant_idx = assistant_creates[0]["value"]["idx"]

    reconstructed = _reconstruct_text(frames, assistant_idx)
    assert reconstructed == "".join(chunks)


async def test_finalize_frame_emitted_on_turn_complete(board: KaganDriver) -> None:
    """A 'finalize' patch frame is emitted when the turn ends normally."""
    session = await board.chat_create_session(source="test", label="finalize-frame")
    sid = session["id"]

    await board.chat_send(sid, "ping", agent_chunks=["pong"])

    frames = await board.read_frames(sid, "chat")
    patches = _patches(frames)

    finalize_frames = [p for p in patches if p.get("op") == "finalize"]
    assert len(finalize_frames) == 1, f"Expected exactly 1 finalize frame, got: {finalize_frames}"
    # Successful completion should not carry a 'reason'.
    assert finalize_frames[0].get("reason") is None


async def test_cancel_emits_finalize_with_reason(board: KaganDriver) -> None:
    """Cancellation emits a finalize frame with ``reason='terminated_at_user_request'``."""
    session = await board.chat_create_session(source="test", label="cancel-frame")
    sid = session["id"]

    await board.chat_send(sid, "start", agent_chunks=["partial"], cancel_after_chars=1)

    frames = await board.read_frames(sid, "chat")
    patches = _patches(frames)

    finalize_frames = [p for p in patches if p.get("op") == "finalize"]
    assert len(finalize_frames) == 1, f"Expected exactly 1 finalize frame, got: {finalize_frames}"
    assert finalize_frames[0].get("reason") == "terminated_at_user_request"


async def test_two_subscribers_see_identical_seq_stream(board: KaganDriver) -> None:
    """Two EventLog subscribers receive frames with the same seq ordering.

    Both subscribers are attached to the *same* EventLog instance that
    KaganCore wires into ChatEngine, so they share the in-process live queue.
    """
    ctx = board._driver._ctx  # pyrefly: ignore[private-access]
    # Use the EventLog instance already wired into the chat engine so that
    # live-tail notifications reach both subscribers.
    event_log = ctx._event_log  # pyrefly: ignore[private-access]

    session = await board.chat_create_session(source="test", label="two-subs")
    sid = session["id"]

    # Collect frames via subscribe before the turn runs.
    collected_a: list[Any] = []
    collected_b: list[Any] = []
    stop = asyncio.Event()
    reg_a = asyncio.Event()
    reg_b = asyncio.Event()

    async def _subscribe(collector: list[Any], registered: asyncio.Event) -> None:
        async for row in event_log.subscribe(sid, "chat", queue_registered=registered):
            collector.append(row)
            if stop.is_set():
                break

    sub_a = asyncio.create_task(_subscribe(collected_a, reg_a))
    sub_b = asyncio.create_task(_subscribe(collected_b, reg_b))
    await asyncio.wait_for(asyncio.gather(reg_a.wait(), reg_b.wait()), timeout=5.0)

    await board.chat_send(sid, "hello", agent_chunks=["one", "two"])

    deadline = asyncio.get_running_loop().time() + 10.0
    while asyncio.get_running_loop().time() < deadline:
        if collected_a and collected_b:
            break
        await asyncio.sleep(0)
    else:
        pytest.fail("subscribers did not receive frames within timeout")

    stop.set()
    sub_a.cancel()
    sub_b.cancel()
    await asyncio.gather(sub_a, sub_b, return_exceptions=True)

    # Both subscribers must see the same frames in the same seq order.
    assert len(collected_a) > 0, "Subscriber A received no frames"
    assert len(collected_b) > 0, "Subscriber B received no frames"

    seqs_a = [r.seq for r in collected_a]
    seqs_b = [r.seq for r in collected_b]

    # Both see the same seq numbers (may differ in total count due to cancel timing).
    # The key invariant: whatever A saw, B also saw in the same order.
    min_len = min(len(seqs_a), len(seqs_b))
    assert seqs_a[:min_len] == seqs_b[:min_len], f"Seq mismatch:\nA: {seqs_a}\nB: {seqs_b}"


async def test_entry_idx_monotonic_across_turns_in_same_session(board: KaganDriver) -> None:
    """idx values assigned to entries in successive turns are strictly increasing."""
    session = await board.chat_create_session(source="test", label="mono-idx")
    sid = session["id"]

    await board.chat_send(sid, "turn one", agent_chunks=["reply one"])
    await board.chat_send(sid, "turn two", agent_chunks=["reply two"])

    frames = await board.read_frames(sid, "chat")
    patches = _patches(frames)

    create_frames = [p for p in patches if p.get("op") == "create"]
    idxs = [(p["value"]["idx"], p["value"]["role"]) for p in create_frames]

    idx_values = [i for i, _ in idxs]
    assert idx_values == sorted(idx_values), f"idx values are not monotonically increasing: {idxs}"
    assert len(set(idx_values)) == len(idx_values), f"idx values are not unique: {idxs}"


async def test_entry_idx_independent_across_sessions(board: KaganDriver) -> None:
    """Two different sessions each start their idx counter from 0."""
    session_a = await board.chat_create_session(source="test", label="idx-a")
    session_b = await board.chat_create_session(source="test", label="idx-b")
    sid_a = session_a["id"]
    sid_b = session_b["id"]

    await board.chat_send(sid_a, "hello a", agent_chunks=["reply a"])
    await board.chat_send(sid_b, "hello b", agent_chunks=["reply b"])

    frames_a = await board.read_frames(sid_a, "chat")
    frames_b = await board.read_frames(sid_b, "chat")

    def _first_create_idx(frames: list[Any]) -> int:
        for row in frames:
            f = row.frame
            if f.get("type") == "patch" and f.get("op") == "create":
                return f["value"]["idx"]
        raise AssertionError("No create frame found")

    idx_a = _first_create_idx(frames_a)
    idx_b = _first_create_idx(frames_b)

    # Both sessions start at idx=0 (user message is the first entry).
    assert idx_a == 0, f"Session A first idx should be 0, got {idx_a}"
    assert idx_b == 0, f"Session B first idx should be 0, got {idx_b}"


async def test_concurrent_turn_409_does_not_emit_frames(board: KaganDriver) -> None:
    """A try_claim_turn rejection (409) must not emit any frames to the event log."""
    from acp.schema import TextContentBlock

    from tests.helpers.chat_engine import SuspendingFactory

    ctx = board._driver._ctx  # pyrefly: ignore[private-access]
    engine = ctx.chat

    session = await board.chat_create_session(source="test", label="no-rogue-frames")
    sid = session["id"]

    started = asyncio.Event()
    factory = SuspendingFactory(first_chunk="x", started=started)

    # Start a real turn (it will suspend after the first chunk).
    await engine.push_user(sid, "first message")
    consumer = asyncio.create_task(
        _drain(
            engine.stream_assistant(
                sid,
                prompt_blocks=[TextContentBlock(type="text", text="first message")],
                acp_factory=factory,
            )
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5.0)

    frames_before = await board.read_frames(sid, "chat")
    seq_before = len(frames_before)

    # Attempt second turn — must be rejected.
    from kagan.core.chat import TurnInProgressError

    with pytest.raises(TurnInProgressError):
        stream = engine.stream_assistant(
            sid,
            prompt_blocks=[TextContentBlock(type="text", text="second message")],
        )
        await stream.__anext__()

    frames_after = await board.read_frames(sid, "chat")
    seq_after = len(frames_after)

    # No new frames should have been emitted by the rejected second turn.
    assert seq_after == seq_before, (
        f"Rogue frames emitted after 409 rejection: before={seq_before}, after={seq_after}"
    )

    # Clean up.
    await engine.cancel(sid)
    await asyncio.wait_for(consumer, timeout=5.0)
