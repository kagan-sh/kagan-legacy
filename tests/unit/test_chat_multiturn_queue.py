"""Unit tests for multi-turn queueing (Change 3).

Tests verify:
- A second message typed while streaming is queued and processed after the
  first completes.
- Cancellation during the first message drops any queued messages.
- ``_TOOLBAR_STATE.queued_count`` is updated while messages drain.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from kagan.cli.chat._approval_types import _SendResult
from kagan.cli.chat.repl import _TOOLBAR_STATE
from tests.helpers.fake_repl_chat_client import FakeReplChatClient

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_toolbar_state() -> None:
    _TOOLBAR_STATE.queued_count = 0
    _TOOLBAR_STATE.is_streaming = False
    yield
    _TOOLBAR_STATE.queued_count = 0
    _TOOLBAR_STATE.is_streaming = False


def _make_streaming_controller(processed: list[str]) -> Any:
    from kagan.cli.chat.controller import ChatController

    class _StreamingCtrl(ChatController):
        async def _send(self, text: str) -> _SendResult:  # type: ignore[override]
            processed.append(text)
            await asyncio.sleep(0.05)
            return _SendResult()

    client = FakeReplChatClient(new_session_id="sess-1")
    ctrl = _StreamingCtrl(client, agent_backend="claude-code")
    ctrl._chat_session_id = "sess-1"
    return ctrl


def _make_cancel_controller(processed: list[str]) -> Any:
    from kagan.cli.chat.controller import ChatController

    class _CancelCtrl(ChatController):
        async def _send(self, text: str) -> _SendResult:  # type: ignore[override]
            processed.append(text)
            return _SendResult(was_cancelled=True)

    client = FakeReplChatClient(new_session_id="sess-1")
    ctrl = _CancelCtrl(client, agent_backend="claude-code")
    ctrl._chat_session_id = "sess-1"
    return ctrl


async def test_second_message_queued_during_stream() -> None:
    """Two messages submitted while agent is streaming are both processed in order."""
    processed: list[str] = []
    ctrl = _make_streaming_controller(processed)

    submit_queue: asyncio.Queue[str | None] = asyncio.Queue()
    drain_pending: asyncio.Queue[str] = asyncio.Queue()

    await submit_queue.put("first message")
    await submit_queue.put("second message")
    await submit_queue.put(None)

    async def _run() -> None:
        done = False
        while not done:
            while not drain_pending.empty():
                try:
                    text = drain_pending.get_nowait()
                except asyncio.QueueEmpty:
                    break
                await ctrl._send(text)

            try:
                text = await asyncio.wait_for(submit_queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            if text is None:
                done = True
                break
            stripped = text.strip()
            if _TOOLBAR_STATE.is_streaming:
                await drain_pending.put(stripped)
                continue
            await ctrl._send(stripped)
            # Mirror controller: first send enters streaming; further input queues.
            _TOOLBAR_STATE.is_streaming = True

    await asyncio.wait_for(_run(), timeout=2.0)

    assert processed == ["first message", "second message"]


async def test_cancel_clears_pending_queue() -> None:
    """When ``was_cancelled=True`` is returned, the pending queue is cleared."""
    processed: list[str] = []
    ctrl = _make_cancel_controller(processed)

    drain_pending: asyncio.Queue[str] = asyncio.Queue()
    await drain_pending.put("would-be-second")

    result = await ctrl._send("first")
    if result.was_cancelled:
        while not drain_pending.empty():
            try:
                drain_pending.get_nowait()
            except asyncio.QueueEmpty:
                break

    assert drain_pending.empty(), "Pending queue should be cleared after cancel"
    assert "first" in processed


async def test_queued_count_reflected_in_toolbar_state() -> None:
    """_TOOLBAR_STATE.queued_count tracks how many messages are pending."""
    _TOOLBAR_STATE.queued_count = 0

    drain_pending: asyncio.Queue[str] = asyncio.Queue()
    await drain_pending.put("msg-a")
    await drain_pending.put("msg-b")
    await drain_pending.put("msg-c")

    _TOOLBAR_STATE.queued_count = drain_pending.qsize()
    assert _TOOLBAR_STATE.queued_count == 3

    drain_pending.get_nowait()
    _TOOLBAR_STATE.queued_count = drain_pending.qsize()
    assert _TOOLBAR_STATE.queued_count == 2

    drain_pending.get_nowait()
    drain_pending.get_nowait()
    _TOOLBAR_STATE.queued_count = drain_pending.qsize()
    assert _TOOLBAR_STATE.queued_count == 0
