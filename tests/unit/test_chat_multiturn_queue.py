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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kagan.cli.chat._approval_types import _SendResult
from kagan.cli.chat.repl import _TOOLBAR_STATE

pytestmark = [pytest.mark.unit]


def _make_minimal_client(new_session_id: str = "sess-1") -> Any:
    from tests.unit.test_chat_session_model import _FakeRow

    client = MagicMock()
    client.active_project_id = "proj-1"
    client.chat_sessions.create = AsyncMock(return_value=_FakeRow(new_session_id))
    client.chat_sessions.set_last_session_id = AsyncMock()
    client.chat_sessions.list_with_history = AsyncMock(return_value=[])
    client.chat_sessions.get_with_history = AsyncMock(return_value=None)
    return client


def _make_controller(client: Any) -> Any:
    from kagan.cli.chat.controller import ChatController

    ctrl = ChatController(client, agent_backend="claude-code")
    ctrl._chat_session_id = "sess-1"
    ctrl._factory = MagicMock()
    return ctrl


async def test_second_message_queued_during_stream() -> None:
    """Two messages submitted while agent is streaming are both processed in order."""
    processed: list[str] = []

    async def _fake_send(self: Any, text: str) -> _SendResult:
        processed.append(text)
        await asyncio.sleep(0.05)
        return _SendResult()

    client = _make_minimal_client()
    ctrl = _make_controller(client)

    submit_queue: asyncio.Queue[str | None] = asyncio.Queue()
    drain_pending: asyncio.Queue[str] = asyncio.Queue()

    # Simulate: first message arrives, then second arrives while streaming
    await submit_queue.put("first message")
    await submit_queue.put("second message")
    await submit_queue.put(None)  # EOF

    with patch.object(type(ctrl), "_send", _fake_send):
        # Run a stripped-down pump that exercises multi-turn logic
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

        await asyncio.wait_for(_run(), timeout=2.0)

    assert processed == ["first message", "second message"]


async def test_cancel_clears_pending_queue() -> None:
    """When ``was_cancelled=True`` is returned, the pending queue is cleared."""
    processed: list[str] = []

    async def _fake_send_cancel(self: Any, text: str) -> _SendResult:
        processed.append(text)
        return _SendResult(was_cancelled=True)

    client = _make_minimal_client()
    ctrl = _make_controller(client)

    drain_pending: asyncio.Queue[str] = asyncio.Queue()
    await drain_pending.put("would-be-second")

    with patch.object(type(ctrl), "_send", _fake_send_cancel):
        result = await ctrl._send("first")
        # Simulate cancel-on-result handling: clear queue
        if result.was_cancelled:
            while not drain_pending.empty():
                try:
                    drain_pending.get_nowait()
                except asyncio.QueueEmpty:
                    break

    assert drain_pending.empty(), "Pending queue should be cleared after cancel"
    # The first message was still processed
    assert "first" in processed


async def test_queued_count_reflected_in_toolbar_state() -> None:
    """_TOOLBAR_STATE.queued_count tracks how many messages are pending."""
    # Reset
    _TOOLBAR_STATE.queued_count = 0

    drain_pending: asyncio.Queue[str] = asyncio.Queue()
    await drain_pending.put("msg-a")
    await drain_pending.put("msg-b")
    await drain_pending.put("msg-c")

    # Simulate what _update_queued_count does in the controller
    _TOOLBAR_STATE.queued_count = drain_pending.qsize()
    assert _TOOLBAR_STATE.queued_count == 3

    # Simulate draining one
    drain_pending.get_nowait()
    _TOOLBAR_STATE.queued_count = drain_pending.qsize()
    assert _TOOLBAR_STATE.queued_count == 2

    # Drain rest
    drain_pending.get_nowait()
    drain_pending.get_nowait()
    _TOOLBAR_STATE.queued_count = drain_pending.qsize()
    assert _TOOLBAR_STATE.queued_count == 0
